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
from .brand_colors import brand_color
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
        # -inf so the first notification is never throttled by the startup gap.
        self._last_dispatch: float = float("-inf")
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
        try:
            if not self.enabled:
                return
            if self.suppress_during_dnd and self._dnd_active():
                return
            now = self._clock()
            key = f"{ev.app_id}|{ev.title}|{ev.body}"
            self._purge_recent(now)
            if key in self._recent:
                return
            self._recent[key] = now
            # Throttle bursts: the pipeline deque also coalesces, but dropping
            # here avoids flooding the command queue.
            if now - self._last_dispatch < self.min_flash_interval_s:
                return
            self._last_dispatch = now
            color = self.resolve_color(ev)
            self._controller.flash(color, self._pattern())
            logger.info(
                "[Notify] Flash for %s (%s) → %s",
                ev.app_name or ev.app_id, ev.source, color,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("[Notify] handling failed: %s", exc)

    def test_flash(self, color: Optional[list] = None) -> None:
        """Dispatch a flash immediately, bypassing dedup/DND (UI preview)."""
        rgb = color or self.default_color
        try:
            self._controller.flash(rgb, self._pattern())
        except Exception as exc:
            logger.debug("[Notify] test flash failed: %s", exc)

    # --- colour resolution ------------------------------------------------
    def resolve_color(self, ev: NotificationEvent) -> RGB:
        """Resolve a flash colour for *ev*.

        Priority: override → keyword → brand colour → live icon → default. Brand
        and icon are both "logo colour" sources and are skipped in ``fixed`` mode.
        """
        # 1. Per-app override (by stable id or display name).
        ov = self.app_overrides.get(ev.app_id) or self.app_overrides.get(ev.app_name)
        if ov:
            return _as_rgb(ov, self.default_color)

        # 2. Keyword rules (Phone Link / forwarded): substring over name+title+body.
        haystack = f"{ev.app_name} {ev.title} {ev.body}".lower()
        for rule in self.keyword_rules:
            kw = str(rule.get("keyword", "")).strip().lower()
            if kw and kw in haystack:
                return _as_rgb(rule.get("color"), self.default_color)

        if self.color_mode != "fixed":
            # 3. Curated brand/logo colour. Preferred over live icon extraction: it
            #    is the official brand colour and works even when the notification
            #    carries no icon bytes (e.g. Phone Link forwards). Only used when the
            #    user has set no override for this app (guaranteed by the order above).
            brand = brand_color(ev.app_name, ev.app_id)
            if brand is not None:
                return _as_rgb(brand, self.default_color)

            # 4. Live icon dominant colour (cached) for apps not in the brand table.
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

        # 5. Fallback.
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
