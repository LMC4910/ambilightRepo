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

    def stop(self) -> None:
        """Release any resources (audio streams, threads). Default: no-op.

        Called by :meth:`EffectsManager.set_mode` when this effect is replaced,
        so stateful effects (e.g. audio-reactive) can shut down cleanly.
        """
        return None

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


def _lerp_color(c1: Tuple[int, int, int], c2: Tuple[int, int, int], t: float) -> Tuple[int, int, int]:
    return tuple(int(round(c1[i] + (c2[i] - c1[i]) * t)) for i in range(3))  # type: ignore[return-value]


def _gradient_at(keys, t: float) -> Tuple[int, int, int]:
    """Sample a keyframe gradient ``[(pos0,(r,g,b)), ...]`` (pos in 0..1) at *t*."""
    t = max(0.0, min(1.0, t))
    for i in range(len(keys) - 1):
        p0, c0 = keys[i]
        p1, c1 = keys[i + 1]
        if t <= p1:
            seg = (t - p0) / (p1 - p0) if p1 > p0 else 0.0
            return _lerp_color(c0, c1, seg)
    return keys[-1][1]


class _TimedScene(BaseEffect):
    """Base for one-shot scenes that progress over *duration* then hold the end."""
    KEYS: list = []

    def __init__(self, duration: float = 300.0):
        self.duration = max(1.0, float(duration))
        self.start_time = time.monotonic()

    def update(self) -> Tuple[int, int, int]:
        t = (time.monotonic() - self.start_time) / self.duration
        return _gradient_at(self.KEYS, t)


class SunriseEffect(_TimedScene):
    """Night → dawn → warm daylight over ``duration`` seconds (FR-EFF-06)."""
    name = "sunrise"
    KEYS = [
        (0.0, (8, 2, 12)), (0.25, (60, 15, 20)), (0.5, (200, 70, 20)),
        (0.75, (255, 150, 60)), (1.0, (255, 214, 150)),
    ]


class SunsetEffect(_TimedScene):
    """Warm daylight → dusk → night over ``duration`` seconds (FR-EFF-06)."""
    name = "sunset"
    KEYS = [
        (0.0, (255, 214, 150)), (0.25, (255, 140, 50)), (0.5, (200, 60, 20)),
        (0.75, (80, 20, 30)), (1.0, (10, 3, 15)),
    ]


class OceanEffect(BaseEffect):
    """Slow blue/teal swell — gentle hue and brightness waves (FR-EFF-06)."""
    name = "ocean"

    def __init__(self, speed: float = 1.0):
        self.speed = max(0.05, speed)
        self.start_time = time.monotonic()

    def update(self) -> Tuple[int, int, int]:
        e = (time.monotonic() - self.start_time) * 0.1 * self.speed
        hue = 0.52 + 0.06 * math.sin(e)                 # cyan ↔ blue
        val = 0.6 + 0.4 * (0.5 + 0.5 * math.sin(e * 0.7))
        r, g, b = colorsys.hsv_to_rgb(hue, 0.85, val)
        return (int(r * 255), int(g * 255), int(b * 255))


class AmbientEffect(BaseEffect):
    """Very slow, low-saturation full-hue drift — calm pastel wash (FR-EFF-06)."""
    name = "ambient"

    def __init__(self, speed: float = 1.0):
        self.speed = max(0.05, speed)
        self.start_time = time.monotonic()

    def update(self) -> Tuple[int, int, int]:
        e = time.monotonic() - self.start_time
        hue = (e * 0.01 * self.speed) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 0.45, 0.9)
        return (int(r * 255), int(g * 255), int(b * 255))


class AudioReactiveEffect(BaseEffect):
    """Drive brightness/colour from system audio (FR-EFF-05).

    ``mode="level"`` pulses *base* colour with loudness + beat flashes;
    ``mode="spectrum"`` maps bass→R, mid→G, treble→B. Degrades to a dim *base*
    colour when no loopback audio backend is available.
    """
    name = "audio"

    def __init__(self, r: int = 0, g: int = 120, b: int = 255, mode: str = "level", sensitivity: float = 1.0):
        self.base = (int(r), int(g), int(b))
        self.mode = mode
        # Imported lazily so the module loads without the optional audio backend.
        from .audio_input import AudioAnalyzer, AudioCapture
        self.analyzer = AudioAnalyzer(sensitivity=sensitivity)
        self.capture = AudioCapture(self.analyzer)
        self.capture.start()

    def update(self) -> Tuple[int, int, int]:
        if not self.capture.available:
            r, g, b = self.base                 # dim base = "on, but no audio yet"
            return (r // 6, g // 6, b // 6)
        a = self.analyzer
        if self.mode == "spectrum":
            scale = 0.3 + 0.7 * a.level
            return (int(255 * a.bass * scale), int(255 * a.mid * scale), int(255 * a.treble * scale))
        bright = min(1.0, a.level + 0.35 * a.pulse)
        r, g, b = self.base
        return (int(r * bright), int(g * bright), int(b * bright))

    def stop(self) -> None:
        self.capture.stop()


class CustomSequenceEffect(BaseEffect):
    """Cycle through a user-defined ordered colour list with smooth interpolation
    at a configurable speed (FR-EFF-07: "what colours in what order")."""
    name = "custom"

    def __init__(self, colors=None, speed: float = 1.0):
        seq = colors or [[255, 0, 0], [0, 255, 0], [0, 0, 255]]
        self.colors = [tuple(int(x) for x in c[:3]) for c in seq] or [(0, 0, 0)]
        self.speed = max(0.05, float(speed))
        self.start_time = time.monotonic()

    def update(self) -> Tuple[int, int, int]:
        n = len(self.colors)
        if n == 1:
            return self.colors[0]
        pos = ((time.monotonic() - self.start_time) * 0.2 * self.speed) % n
        i = int(pos)
        frac = pos - i
        c0, c1 = self.colors[i % n], self.colors[(i + 1) % n]
        return tuple(int(round(c0[k] + (c1[k] - c0[k]) * frac)) for k in range(3))  # type: ignore[return-value]


# Built-in effect classes keyed by their `name`.
BUILTIN_EFFECTS = {
    "static": StaticColorEffect,
    "breathing": BreathingEffect,
    "rainbow": RainbowCycleEffect,
    "candle": CandleEffect,
    "sunrise": SunriseEffect,
    "sunset": SunsetEffect,
    "ocean": OceanEffect,
    "ambient": AmbientEffect,
    "audio": AudioReactiveEffect,
    "custom": CustomSequenceEffect,
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

    def _stop_active(self) -> None:
        """Release the current effect's resources (e.g. audio stream) if any."""
        if self.active_effect is not None:
            try:
                self.active_effect.stop()
            except Exception as exc:  # pragma: no cover - defensive
                logger.debug("[Effects] stop() on %s failed: %s", self.current_mode, exc)

    def set_mode(self, mode: str, params: Dict[str, Any] = None) -> bool:
        """Set the active effect mode (built-in or plugin)."""
        params = params or {}

        if mode == "screen_sync":
            self._stop_active()
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
        self._stop_active()
        self.current_mode = mode
        self.active_effect = effect
        return True

    def update(self) -> Optional[Tuple[int, int, int]]:
        """Get the next color for the active effect, if any."""
        if self.active_effect:
            return self.active_effect.update()
        return None
