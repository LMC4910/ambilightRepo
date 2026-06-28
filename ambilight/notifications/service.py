"""
Notification Flash service
==========================
Owns the notification listener, the per-app icon-colour cache, rule matching,
de-duplication, burst throttling, and dispatch to the pipeline. Lives in the API
process and mirrors :class:`AutoProfileSwitcher`'s lifecycle (created at startup,
refreshed on ``CONFIG_UPDATE``).

The listener thread only ever produces :class:`NotificationEvent`s; everything
here runs on the asyncio loop thread (events are marshalled there by the base
listener), so the dedup/throttle state needs no locking. Only the final RGB +
blink pattern is handed to ``PipelineController.flash`` — the pipeline owns the
device and runs the actual blink overlay.
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections import OrderedDict
from typing import Callable, Optional, Tuple

from ..config import AppConfig
from .base import NotificationEvent, get_notification_listener
from .brand_colors import brand_color, brand_color_from_text, is_forwarder
from .icon_color import icon_dominant_color

logger = logging.getLogger(__name__)

_CACHE_PATH = os.path.join(os.path.expanduser("~"), ".ambilight", "notification_colors.json")
# Sentinel cached for apps whose icon yields no usable colour, so we don't retry
# extraction on every notification from them.
_NO_ICON = "none"

RGB = Tuple[int, int, int]


class NotificationFlashService:
    def __init__(
        self,
        cfg: AppConfig,
        controller,
        loop=None,
        listener_factory: Optional[Callable] = None,
        clock: Callable[[], float] = time.monotonic,
        dnd_probe: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._controller = controller
        self._loop = loop
        self._clock = clock
        self._listener_factory = listener_factory or get_notification_listener
        self._dnd_probe = dnd_probe
        self._listener = None
        # app_id → [r,g,b] or _NO_ICON sentinel
        self._color_cache: dict = {}
        self._recent: "OrderedDict[str, float]" = OrderedDict()  # dedup hash → ts
        self._load_cache()
        self.update_config(cfg)

    # --- config -----------------------------------------------------------
    def update_config(self, cfg: AppConfig) -> None:
        n = cfg.notifications
        self.enabled = bool(n.enabled)
        self.default_color = list(n.default_color or [255, 255, 255])
        self.brightness = float(n.brightness)
        self.blink_count = int(n.blink_count)
        self.on_ms = int(n.on_ms)
        self.off_ms = int(n.off_ms)
        self.color_mode = str(n.color_mode or "icon")
        self.suppress_during_dnd = bool(n.suppress_during_dnd)
        self.dedup_window_s = float(n.dedup_window_s)
        self.min_flash_interval_s = float(n.min_flash_interval_s)
        self.app_overrides = dict(n.app_overrides or {})
        # Case-insensitive view so an override keyed "discord" still matches an app
        # whose display name / id is "Discord" (and vice-versa).
        self._app_overrides_ci = {str(k).lower(): v for k, v in self.app_overrides.items()}
        self.keyword_rules = list(n.keyword_rules or [])

    # --- lifecycle --------------------------------------------------------
    def start(self) -> None:
        try:
            self._listener = self._listener_factory(self._on_notification, self._loop)
        except Exception as exc:
            logger.info("[Notify] listener unavailable: %s", exc)
            self._listener = None
        if self._listener is not None:
            self._listener.start()
        else:
            logger.info("[Notify] No notification listener on this platform/config.")

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
        self._save_cache()

    def permission_status(self) -> dict:
        if self._listener is None:
            return {"status": "unavailable", "available": False}
        try:
            return {"status": self._listener.permission_status(), "available": True}
        except Exception:
            return {"status": "unknown", "available": True}

    # --- event handling (runs on the loop thread) -------------------------
    def _on_notification(self, ev: NotificationEvent) -> None:
        label = ev.app_name or ev.app_id or "notification"
        try:
            if not self.enabled:
                return
            if self.suppress_during_dnd and self._dnd_active():
                logger.info("[Notify] Suppressed (Do Not Disturb): %s", label)
                return
            now = self._clock()
            key = f"{ev.app_id}|{ev.title}|{ev.body}"
            self._purge_recent(now)
            if key in self._recent:
                # An identical (app, title, body) within the de-dup window: a genuine
                # repeat (e.g. the OS re-delivering the same toast), not a new alert.
                logger.info(
                    "[Notify] Duplicate within %.0fs; not queued: %s",
                    self.dedup_window_s, label,
                )
                return
            self._recent[key] = now
            # Every distinct notification is dispatched — the pipeline owns an
            # ordered queue that flashes them one after another (with a short gap
            # so same-colour alerts stay distinct) and retries failures. No
            # burst-dropping here, so stacked alerts never silently disappear.
            color = self.resolve_color(ev)
            self._controller.flash(color, self._pattern(), label=label)
            logger.info(
                "[Notify] Queued flash for %s (%s) -> %s",
                label, ev.source, color,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("[Notify] handling failed for %s: %s", label, exc)

    def test_flash(self, color: Optional[list] = None) -> None:
        """Dispatch a flash immediately, bypassing dedup/DND (UI preview)."""
        rgb = color or self.default_color
        try:
            self._controller.flash(rgb, self._pattern(), label="Test flash")
        except Exception as exc:
            logger.debug("[Notify] test flash failed: %s", exc)

    # --- colour resolution ------------------------------------------------
    def resolve_color(self, ev: NotificationEvent) -> RGB:
        """Resolve a flash colour for *ev*.

        Priority: override → keyword → forwarded source → brand → live icon →
        default. The forwarded-source, brand and icon steps are all "logo colour"
        sources and are skipped in ``fixed`` mode.
        """
        # 1. Per-app override (by stable id or display name, case-insensitive).
        ov = self._override_for(ev)
        if ov:
            return _as_rgb(ov, self.default_color)

        # 2. Keyword rules (Phone Link / forwarded): substring over name+title+body.
        haystack = f"{ev.app_name} {ev.title} {ev.body}".lower()
        for rule in self.keyword_rules:
            kw = str(rule.get("keyword", "")).strip().lower()
            if kw and kw in haystack:
                return _as_rgb(rule.get("color"), self.default_color)

        if self.color_mode != "fixed":
            # 3. Forwarded / mirrored notifications. A bridge such as Phone Link /
            #    Link to Windows attributes the alert to *itself*, so resolve the REAL
            #    source app and NEVER the bridge: try the source named in the text,
            #    then the source app-name (some bridges report it directly), then the
            #    forwarded toast's own icon — which is the source app's logo. The
            #    bridge's app_id is the same for every forwarded app, so it must not
            #    drive the brand lookup nor key the shared icon cache.
            if is_forwarder(ev.app_name, ev.app_id):
                return self._resolve_forwarded(ev, haystack)

            # 4. Curated brand/logo colour. Preferred over live icon extraction: it
            #    is the official brand colour and works even when the notification
            #    carries no icon bytes. Only used when the user has set no override
            #    for this app (guaranteed by the order above).
            brand = brand_color(ev.app_name, ev.app_id)
            if brand is not None:
                return _as_rgb(brand, self.default_color)

            # 5. Live icon dominant colour (cached) for apps not in the brand table.
            cached = self._color_cache.get(ev.app_id)
            if cached is None:
                extracted = icon_dominant_color(ev.icon_bytes) if ev.icon_bytes else None
                if extracted:
                    cached = list(extracted)
                    self._color_cache[ev.app_id] = cached
                    self._save_cache()
                elif ev.icon_bytes:
                    # Icon was present but unusable → cache the sentinel so we
                    # don't re-extract every time. When there were no icon bytes
                    # at all, skip caching so a later notification that *does*
                    # carry an icon can still populate the colour.
                    cached = _NO_ICON
                    self._color_cache[ev.app_id] = cached
                    self._save_cache()
                else:
                    cached = _NO_ICON
            if cached != _NO_ICON:
                return _as_rgb(cached, self.default_color)

        # 6. Fallback.
        return _as_rgb(self.default_color, [255, 255, 255])

    def _override_for(self, ev: NotificationEvent) -> Optional[list]:
        """Per-app override for *ev*, matched on app id or display name, exactly
        first then case-insensitively."""
        ov = self.app_overrides.get(ev.app_id) or self.app_overrides.get(ev.app_name)
        if ov:
            return ov
        for key in (ev.app_id, ev.app_name):
            if key:
                ov = self._app_overrides_ci.get(str(key).lower())
                if ov:
                    return ov
        return None

    def _resolve_forwarded(self, ev: NotificationEvent, haystack: str) -> RGB:
        """Resolve a forwarded/mirrored notification to its *source* app's colour.

        Order: source named in the text → source app-name (never the bridge's
        app_id) → the forwarded toast's own icon (the source app's logo, extracted
        uncached because the bridge app_id is shared across every source) → default.
        The bridge's own colour is deliberately never used.
        """
        src = brand_color_from_text(haystack) or brand_color(ev.app_name)
        if src is not None:
            return _as_rgb(src, self.default_color)
        if ev.icon_bytes:
            rgb = icon_dominant_color(ev.icon_bytes)
            if rgb is not None:
                return _as_rgb(rgb, self.default_color)
        return _as_rgb(self.default_color, [255, 255, 255])

    def _pattern(self) -> dict:
        return {
            "blink_count": self.blink_count,
            "on_ms": self.on_ms,
            "off_ms": self.off_ms,
            "brightness": self.brightness,
        }

    # --- helpers ----------------------------------------------------------
    def _purge_recent(self, now: float) -> None:
        stale = [k for k, ts in self._recent.items() if now - ts > self.dedup_window_s]
        for k in stale:
            self._recent.pop(k, None)

    def _dnd_active(self) -> bool:
        if self._dnd_probe is not None:
            try:
                return bool(self._dnd_probe())
            except Exception:
                return False
        # Best-effort only; reliable cross-version DND detection isn't available,
        # so default to "not in DND" (flashes still fire — the intended default).
        return False

    def _load_cache(self) -> None:
        try:
            if os.path.exists(_CACHE_PATH):
                with open(_CACHE_PATH, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                # A corrupt/non-dict file (e.g. a JSON list) would later break
                # self._color_cache.get(...) and silently drop flashes; reset it.
                if isinstance(data, dict):
                    self._color_cache = data
                else:
                    logger.warning("[Notify] colour cache is not a mapping; ignoring.")
                    self._color_cache = {}
        except Exception as exc:
            logger.debug("[Notify] colour cache load failed: %s", exc)
            self._color_cache = {}

    def _save_cache(self) -> None:
        try:
            os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
            tmp = _CACHE_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._color_cache, fh)
            os.replace(tmp, _CACHE_PATH)
        except Exception as exc:
            logger.debug("[Notify] colour cache save failed: %s", exc)


def _as_rgb(value, default) -> RGB:
    try:
        rgb = [max(0, min(255, int(c))) for c in value][:3]
        if len(rgb) == 3:
            return (rgb[0], rgb[1], rgb[2])
    except (TypeError, ValueError):
        pass
    d = list(default)
    return (int(d[0]), int(d[1]), int(d[2]))
