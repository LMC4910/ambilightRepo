"""
Auto Profile Switcher (FR-PROF-07)
==================================
Polls the foreground application and applies a mapped profile when it changes
(e.g. a game → "gaming", a media player → "movie"), reverting to a default
otherwise. The matching logic (:func:`match_profile`) and a single :meth:`tick`
are pure/synchronous so they unit-test without an event loop or sound/display.

Lifecycle: created in the API process at startup, refreshed on ``CONFIG_UPDATE``,
and runs a poll loop on the asyncio loop. It applies profiles via
``ProfileManager.apply_profile`` (which excludes the ``auto_profile`` section, so
switching profiles never clobbers these rules).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Optional

from .config import AppConfig
from .foreground import get_foreground_app

logger = logging.getLogger(__name__)


def match_profile(app: Optional[str], rules: list, default: str = "") -> Optional[str]:
    """Return the profile for *app* (first matching rule wins), else *default*/None.

    Matching is a case-insensitive substring test, so a rule ``"notepad"`` or
    ``"notepad.exe"`` both match a foreground exe of ``"notepad.exe"``.
    """
    name = (app or "").lower()
    if name:
        for rule in rules or []:
            m = str(rule.get("match", "")).strip().lower()
            p = str(rule.get("profile", "")).strip()
            if m and p and m in name:
                return p
    return default or None


class AutoProfileSwitcher:
    def __init__(
        self,
        cfg: AppConfig,
        get_app: Optional[Callable[[], Optional[str]]] = None,
        apply_profile: Optional[Callable[[str], bool]] = None,
    ) -> None:
        self._get_app = get_app or get_foreground_app
        if apply_profile is not None:
            self._apply = apply_profile
        else:
            from .profile_manager import profile_manager
            self._apply = profile_manager.apply_profile
        self._last_applied: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self.update_config(cfg)

    def update_config(self, cfg: AppConfig) -> None:
        ap = cfg.auto_profile
        self.enabled = bool(ap.enabled)
        self.interval = max(0.5, float(ap.poll_interval))
        self.default_profile = ap.default_profile or ""
        self.rules = list(ap.rules or [])

    def tick(self) -> Optional[str]:
        """One synchronous evaluation. Applies + returns a profile only when the
        matched target changes (so it never re-applies on every poll)."""
        if not self.enabled:
            return None
        target = match_profile(self._get_app(), self.rules, self.default_profile)
        if target and target != self._last_applied:
            ok = self._apply(target)
            if ok is not False:
                self._last_applied = target
                logger.info("[AutoProfile] Foreground change → applied profile '%s'.", target)
                return target
        return None

    async def run(self) -> None:
        while True:
            try:
                await asyncio.sleep(self.interval)
                if self.enabled:
                    # Foreground query + profile write are blocking; keep them off the loop.
                    await asyncio.get_running_loop().run_in_executor(None, self.tick)
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("[AutoProfile] tick error: %s", exc)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run())

    def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
