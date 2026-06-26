"""
Ownership coordinator
=====================
Decides which devices *this* instance may drive and keeps that decision in sync
with every other Ambilight instance on the network.

Model
-----
* Each instance has a stable ``instance_id`` (config) and announces, every
  heartbeat, the device keys it wants plus a ``priority`` and a sticky
  ``claimed_at`` per key.
* For any device key, the single owner is the live claim that wins the
  deterministic order **higher priority → earliest claimed_at → lowest
  instance_id**. "Live" means the peer was heard from within ``ttl`` (tracked by
  local receive time, so cross-machine clock skew can't expire a live owner).
* When the set of keys *we* own changes, we publish ``OWNERSHIP_UPDATE`` on the
  event bus; the pipeline controller relays it to the capture process.

Lifecycle mirrors :class:`~ambilight.integrations.mqtt_bridge.MqttBridge`:
``start()`` / ``stop()`` / ``update_config(cfg)``. The heartbeat runs on a daemon
thread; transports run their own threads and call back into :meth:`_on_remote`.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class OwnershipCoordinator:
    """Cooperative cross-instance device ownership (see module docstring)."""

    def __init__(self, cfg, *, event_bus=None, get_password=None) -> None:
        if event_bus is None:
            from ..events import bus
            event_bus = bus
        self._bus = event_bus
        self._get_password = get_password

        self._lock = threading.RLock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Transport state.
        self._transport = None
        self._transport_kind: Optional[str] = None  # "mqtt" | "lan" | None

        # Heartbeat thread.
        self._hb_thread: Optional[threading.Thread] = None
        self._hb_stop = threading.Event()

        # Peer announcements: instance_id -> {"label", "claims": {key: claim}, "seen": monotonic}
        self._peers: dict[str, dict] = {}
        # Our sticky per-key claim start (wall clock) and force-takeover overrides.
        self._claimed_at: dict[str, float] = {}
        self._overrides: dict[str, int] = {}
        # Keys the user explicitly released (suppressed from our announcement).
        self._released: set[str] = set()
        # Last owned set we published (so we only emit on change).
        self._owned: frozenset[str] = frozenset()

        self._cfg = None
        self._id = ""
        self._label = ""
        self._priority = 0
        self._hb = 10.0
        self._ttl = 30.0
        self._desired: set[str] = set()

        self.update_config(cfg)

    # ------------------------------------------------------------------ config
    def _refresh_identity(self) -> None:
        o = self._cfg.ownership
        self._id = o.instance_id
        self._label = o.instance_label or (o.instance_id[:8] if o.instance_id else "instance")
        self._priority = int(o.priority)
        self._hb = max(1.0, float(o.heartbeat_interval))
        self._ttl = max(float(o.ttl), 2.0 * self._hb)

    def _compute_desired(self) -> set:
        from ..pipeline import _device_specs, device_key
        try:
            return {device_key(s) for s in _device_specs(self._cfg)}
        except Exception as exc:  # pragma: no cover - config edge cases
            logger.debug("[Ownership] desired-set compute failed: %s", exc)
            return set()

    def _wanted_transport(self) -> str:
        m = getattr(self._cfg, "mqtt", None)
        if m is not None and getattr(m, "enabled", False) and str(getattr(m, "broker", "") or "").strip():
            return "mqtt"
        return "lan"

    def update_config(self, cfg) -> None:
        """Adopt the latest config; re-pick transport and re-announce if running."""
        with self._lock:
            self._cfg = cfg
            self._refresh_identity()
            self._desired = self._compute_desired()
        # Before start() there's no loop yet — just store config + identity.
        if self._loop is None:
            return
        self._ensure_running()
        if bool(self._cfg.ownership.enabled):
            self._select_transport(self._wanted_transport())
            self._announce_and_recompute()

    # --------------------------------------------------------------- lifecycle
    def start(self) -> None:
        """Capture the running loop and start coordinating (if enabled)."""
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
        self._ensure_running()
        if bool(self._cfg.ownership.enabled):
            logger.info(
                "[Ownership] Started as '%s' (%s); coordinating %d device(s) over %s.",
                self._label, self._id[:8], len(self._desired), self._transport_kind,
            )
        else:
            logger.info("[Ownership] Disabled; every configured device is driven locally.")

    def stop(self) -> None:
        self._hb_stop.set()
        # Best-effort "leaving" announcement so peers can take over immediately
        # rather than waiting out the TTL (MQTT also clears its retained topic in
        # transport.stop(); this covers the LAN broadcast path).
        try:
            if self._transport is not None and bool(self._cfg.ownership.enabled):
                self._transport.publish({"instance_id": self._id, "_offline": True})
        except Exception as exc:  # pragma: no cover - teardown
            logger.debug("[Ownership] offline announce failed: %s", exc)
        self._select_transport(None)
        self._hb_thread = None

    def _ensure_running(self) -> None:
        """Start/stop the heartbeat + transport to match ``ownership.enabled``."""
        enabled = bool(self._cfg.ownership.enabled)
        running = self._hb_thread is not None and self._hb_thread.is_alive()
        if enabled and not running:
            self._select_transport(self._wanted_transport())
            self._hb_stop.clear()
            self._hb_thread = threading.Thread(
                target=self._heartbeat_loop, name="ownership-hb", daemon=True
            )
            self._hb_thread.start()
        elif not enabled and running:
            self._hb_stop.set()
            self._select_transport(None)
            self._hb_thread = None
            # Disabled now → drive everything again.
            self._publish_owned(frozenset(self._desired))

    # ---------------------------------------------------------------- transport
    def _select_transport(self, kind: Optional[str]) -> None:
        if kind == self._transport_kind and (kind is None or self._transport is not None):
            return
        if self._transport is not None:
            try:
                self._transport.stop()
            except Exception as exc:  # pragma: no cover - teardown
                logger.debug("[Ownership] transport stop error: %s", exc)
            self._transport = None
        self._transport_kind = kind
        if kind == "mqtt":
            from .mqtt_transport import MqttTransport
            t = MqttTransport(self._cfg.mqtt, self._id, self._on_remote, get_password=self._get_password)
            if t.start():
                self._transport = t
                return
            logger.info("[Ownership] MQTT unavailable; falling back to LAN announce.")
            kind = "lan"
            self._transport_kind = "lan"
        if kind == "lan":
            from .lan_transport import LanTransport
            t = LanTransport(self._cfg.ownership.lan_port, self._on_remote)
            t.start()
            self._transport = t

    # ------------------------------------------------------------------ claims
    def _active_keys(self) -> set:
        """Device keys we currently claim: desired ∪ forced, minus released."""
        return (set(self._desired) | set(self._overrides)) - self._released

    def _self_announcement(self) -> dict:
        now = time.time()
        claims = []
        for k in self._active_keys():
            claimed_at = self._claimed_at.setdefault(k, now)
            priority = self._overrides.get(k, self._priority)
            claims.append({
                "device_key": k,
                "priority": int(priority),
                "claimed_at": float(claimed_at),
            })
        return {
            "instance_id": self._id,
            "instance_label": self._label,
            "ts": now,
            "claims": claims,
        }

    def _on_remote(self, msg: dict) -> None:
        """Merge a peer announcement (called on a transport thread)."""
        instance_id = str(msg.get("instance_id") or "")
        if not instance_id or instance_id == self._id:
            return
        with self._lock:
            if msg.get("_offline"):
                self._peers.pop(instance_id, None)
            else:
                claims = {}
                for c in (msg.get("claims") or []):
                    key = str(c.get("device_key") or "")
                    if not key:
                        continue
                    claims[key] = {
                        "instance_id": instance_id,
                        "priority": int(c.get("priority", 0)),
                        "claimed_at": float(c.get("claimed_at", 0.0)),
                    }
                self._peers[instance_id] = {
                    "label": str(msg.get("instance_label") or instance_id[:8]),
                    "claims": claims,
                    "seen": time.monotonic(),
                }
        self._recompute_and_publish()

    def _prune(self) -> None:
        """Drop peers not heard from within the TTL (caller holds the lock)."""
        now = time.monotonic()
        stale = [i for i, p in self._peers.items() if now - p["seen"] > self._ttl]
        for i in stale:
            self._peers.pop(i, None)

    def _claimants(self, key: str) -> list:
        """Live claimants for *key* as (priority, claimed_at, id, label, is_self).

        Peers not heard from within the TTL are excluded so a crashed owner never
        wins (liveness uses local receive time, immune to cross-machine skew).
        """
        out = []
        if key in self._active_keys():
            claimed_at = self._claimed_at.get(key, time.time())
            out.append((self._overrides.get(key, self._priority), claimed_at, self._id, self._label, True))
        now = time.monotonic()
        for instance_id, peer in self._peers.items():
            if now - peer["seen"] > self._ttl:
                continue
            claim = peer["claims"].get(key)
            if claim:
                out.append((claim["priority"], claim["claimed_at"], instance_id, peer["label"], False))
        return out

    def _winner(self, key: str):
        cands = self._claimants(key)
        if not cands:
            return None
        # higher priority first, then earliest claim, then lowest instance id.
        cands.sort(key=lambda t: (-t[0], t[1], t[2]))
        return cands[0]

    def _owned_keys(self) -> frozenset:
        owned = set()
        for key in self._active_keys():
            winner = self._winner(key)
            if winner is not None and winner[4]:  # is_self
                owned.add(key)
        return frozenset(owned)

    # ------------------------------------------------------------- recompute/io
    def _recompute_and_publish(self, force: bool = False) -> None:
        with self._lock:
            if not bool(self._cfg.ownership.enabled):
                return
            self._prune()
            owned = self._owned_keys()
            changed = owned != self._owned
            self._owned = owned
        # ``force`` re-emits the current set even when unchanged so a pipeline
        # worker that just (re)spawned — and started in standby — catches up
        # within one heartbeat instead of staying dark until ownership changes.
        if changed or force:
            self._publish_owned(owned)

    def _publish_owned(self, owned: frozenset) -> None:
        payload = sorted(owned)
        logger.info("[Ownership] Driving %d/%d device(s): %s", len(payload), len(self._desired), payload)
        if self._loop is None:
            return
        try:
            asyncio.run_coroutine_threadsafe(
                self._bus.publish("OWNERSHIP_UPDATE", payload), self._loop
            )
        except RuntimeError:  # pragma: no cover - loop gone during shutdown
            pass

    def _announce_and_recompute(self, force: bool = False) -> None:
        announcement = None
        with self._lock:
            if bool(self._cfg.ownership.enabled):
                announcement = self._self_announcement()
        if announcement is not None and self._transport is not None:
            self._transport.publish(announcement)
        self._recompute_and_publish(force=force)

    def _heartbeat_loop(self) -> None:
        # Listen briefly before asserting ownership so a freshly-started instance
        # learns existing owners first (avoids a needless takeover/flap on boot).
        self._hb_stop.wait(min(2.0, self._hb))
        while not self._hb_stop.is_set():
            try:
                # force=True: re-broadcast the owned set each beat so a respawned
                # pipeline worker re-syncs even when nothing changed.
                self._announce_and_recompute(force=True)
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("[Ownership] heartbeat error: %s", exc)
            self._hb_stop.wait(self._hb)

    # ----------------------------------------------------------------- public API
    @property
    def instance_id(self) -> str:
        return self._id

    @property
    def instance_label(self) -> str:
        return self._label

    @property
    def transport_kind(self) -> Optional[str]:
        return self._transport_kind

    def owns(self, key: str) -> bool:
        """Whether this instance is the current owner of *key*."""
        with self._lock:
            if not bool(self._cfg.ownership.enabled):
                return True
            winner = self._winner(key)
            return bool(winner and winner[4])

    def owner_of(self, key: str) -> Optional[dict]:
        """The current owner of *key* as ``{instance_id, label, is_self}`` or None."""
        with self._lock:
            if not bool(self._cfg.ownership.enabled):
                return {"instance_id": self._id, "label": self._label, "is_self": True}
            winner = self._winner(key)
            if winner is None:
                return None
            return {"instance_id": winner[2], "label": winner[3], "is_self": winner[4]}

    def snapshot(self) -> list:
        """All known device keys with their owner + claimants (for the API/UI)."""
        with self._lock:
            self._prune()
            enabled = bool(self._cfg.ownership.enabled)
            keys = set(self._active_keys())
            for peer in self._peers.values():
                keys.update(peer["claims"].keys())
            out = []
            for key in sorted(keys):
                if not enabled:
                    owner = {"instance_id": self._id, "label": self._label, "is_self": True}
                else:
                    winner = self._winner(key)
                    owner = None if winner is None else {
                        "instance_id": winner[2], "label": winner[3], "is_self": winner[4],
                    }
                out.append({
                    "device_key": key,
                    "owner": owner,
                    "claimants": [
                        {"instance_id": c[2], "label": c[3], "priority": c[0], "is_self": c[4]}
                        for c in self._claimants(key)
                    ],
                })
            return out

    def claim(self, key: str, *, force: bool = False) -> bool:
        """Claim *key* for this instance. ``force`` wins a contested device by
        out-prioritising every current claimant (manual "take control")."""
        with self._lock:
            self._released.discard(key)
            if force:
                others = [
                    p["claims"][key]["priority"]
                    for p in self._peers.values() if key in p["claims"]
                ]
                base = (max(others) + 1) if others else (self._priority + 1)
                self._overrides[key] = max(self._priority, base)
                # Reset stickiness so we also win any earliest-claim tie-break.
                self._claimed_at[key] = 0.0
            else:
                self._claimed_at.setdefault(key, time.time())
        self._announce_and_recompute()
        return self.owns(key)

    def release(self, key: str) -> bool:
        """Stop claiming *key* so another instance may take it."""
        with self._lock:
            self._released.add(key)
            self._overrides.pop(key, None)
            self._claimed_at.pop(key, None)
        self._announce_and_recompute()
        return True
