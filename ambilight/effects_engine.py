import time
import math
import random
import logging
import datetime
import importlib.util
import inspect
import colorsys
from pathlib import Path
from typing import Tuple, Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class BaseEffect:
    """Base class for all LED effects.

    Plugin effects subclass this, expose a class attribute ``name``, and accept
    keyword params in ``__init__``. Drop a ``*.py`` file exporting such a class
    into ``~/.ambilight/plugins/`` to register it.
    """
    name: str = "base"

    def update(self) -> Optional[Tuple[int, int, int]]:
        """
        Calculate the next color.
        Returns (R, G, B) or None if no update is needed.
        """
        raise NotImplementedError

class StaticColorEffect(BaseEffect):
    def __init__(self, r: int, g: int, b: int):
        self.color = (r, g, b)
        
    def update(self) -> Tuple[int, int, int]:
        return self.color

class BreathingEffect(BaseEffect):
    def __init__(self, r: int, g: int, b: int, speed: float = 1.0):
        self.base_color = (r, g, b)
        self.speed = speed
        self.start_time = time.monotonic()
        
    def update(self) -> Tuple[int, int, int]:
        elapsed = time.monotonic() - self.start_time
        # Breathing math: sin wave mapped from 0.1 to 1.0 intensity
        intensity = 0.1 + 0.9 * ((math.sin(elapsed * self.speed * 2) + 1) / 2)
        r, g, b = self.base_color
        return (int(r * intensity), int(g * intensity), int(b * intensity))

class RainbowCycleEffect(BaseEffect):
    name = "rainbow"

    def __init__(self, speed: float = 1.0):
        self.speed = speed
        self.start_time = time.monotonic()

    def update(self) -> Tuple[int, int, int]:
        elapsed = time.monotonic() - self.start_time
        hue = (elapsed * 0.2 * self.speed) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        return (int(r * 255), int(g * 255), int(b * 255))


class CandleEffect(BaseEffect):
    """Warm candle flicker — a bounded random walk on brightness (FR-EFF-06)."""
    name = "candle"

    def __init__(self, r: int = 255, g: int = 140, b: int = 40, speed: float = 1.0):
        self.base = (r, g, b)
        self.speed = max(0.1, speed)
        self.level = 1.0

    def update(self) -> Tuple[int, int, int]:
        self.level += random.uniform(-0.15, 0.15) * self.speed
        self.level = max(0.45, min(1.0, self.level))
        r, g, b = self.base
        return (int(r * self.level), int(g * self.level), int(b * self.level))


# Built-in effect classes keyed by their `name`.
BUILTIN_EFFECTS = {
    "static": StaticColorEffect,
    "breathing": BreathingEffect,
    "rainbow": RainbowCycleEffect,
    "candle": CandleEffect,
}


def _parse_window(window: str):
    """Parse 'HH:MM-HH:MM' → (start_minutes, end_minutes). Supports overnight wrap."""
    start_s, end_s = window.split("-")
    def mins(s: str) -> int:
        h, m = s.strip().split(":")
        return int(h) * 60 + int(m)
    return mins(start_s), mins(end_s)


def _in_window(now_minutes: int, start: int, end: int) -> bool:
    if start == end:
        return False
    if start < end:
        return start <= now_minutes < end
    # Overnight window (e.g. 22:00-07:00)
    return now_minutes >= start or now_minutes < end


class EffectScheduler:
    """Activates effects within time-of-day windows (FR-EFF-08).

    Schedule entries: ``[{"effect": "candle", "params": {...}, "window": "22:00-07:00"}]``.
    :meth:`current` returns the entry that should be active now, or ``None``.
    """

    def __init__(self, schedule: Optional[List[Dict[str, Any]]] = None) -> None:
        self.schedule = schedule or []

    def current(self, now: Optional[datetime.datetime] = None) -> Optional[Dict[str, Any]]:
        now = now or datetime.datetime.now()
        now_min = now.hour * 60 + now.minute
        for entry in self.schedule:
            try:
                start, end = _parse_window(entry["window"])
            except Exception:
                continue
            if _in_window(now_min, start, end):
                return entry
        return None

class EffectsManager:
    """
    Manages the active effect.
    Mode 'screen_sync' means the pipeline runs its normal capture logic.
    Other modes use the generated effects.
    """
    def __init__(self):
        self.current_mode = "screen_sync"
        self.active_effect: Optional[BaseEffect] = None
        self.fps_target = 30
        # name -> effect class (built-ins + discovered plugins)
        self._registry: Dict[str, type] = dict(BUILTIN_EFFECTS)

    def load_plugins(self, plugins_dir: str) -> List[str]:
        """Import every ``*.py`` in *plugins_dir* and register BaseEffect subclasses."""
        loaded: List[str] = []
        d = Path(plugins_dir)
        if not d.is_dir():
            return loaded
        for path in d.glob("*.py"):
            try:
                spec = importlib.util.spec_from_file_location(f"ambilight_plugin_{path.stem}", path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)  # type: ignore[union-attr]
                for _, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, BaseEffect) and obj is not BaseEffect:
                        name = getattr(obj, "name", obj.__name__).lower()
                        self._registry[name] = obj
                        loaded.append(name)
            except Exception as exc:
                logger.warning("[Effects] Failed to load plugin %s: %s", path.name, exc)
        if loaded:
            logger.info("[Effects] Loaded plugin effects: %s", ", ".join(loaded))
        return loaded

    def list_effects(self) -> List[str]:
        """All selectable modes (screen_sync + built-ins + plugins)."""
        return ["screen_sync", *sorted(self._registry.keys())]

    def set_mode(self, mode: str, params: Dict[str, Any] = None) -> bool:
        """Set the active effect mode (built-in or plugin)."""
        params = params or {}

        if mode == "screen_sync":
            self.current_mode = "screen_sync"
            self.active_effect = None
            return True

        cls = self._registry.get(mode)
        if cls is None:
            return False
        try:
            effect = cls(**params)
        except TypeError:
            # Plugin/effect that doesn't accept these kwargs — fall back to defaults.
            effect = cls()
        self.current_mode = mode
        self.active_effect = effect
        return True

    def update(self) -> Optional[Tuple[int, int, int]]:
        """Get the next color for the active effect, if any."""
        if self.active_effect:
            return self.active_effect.update()
        return None
