"""
Audio Input Module (FR-EFF-05)
==============================
System-audio analysis for the audio-reactive effect.

Two pieces, deliberately separated so the DSP is unit-testable without any
sound hardware:

* :class:`AudioAnalyzer` — pure NumPy DSP. Feed it blocks of samples via
  :meth:`push`; read ``level`` (0..1, fast-attack / slow-decay loudness),
  ``pulse`` (0..1, decaying beat flash) and ``bass``/``mid``/``treble``
  (0..1 band energies). No I/O, fully deterministic, covered by tests.

* :class:`AudioCapture` — optional loopback capture running on a daemon thread,
  pushing speaker output into an analyzer. Degrades gracefully: if no backend
  (``soundcard``) or device is available, ``available`` stays ``False`` and the
  caller falls back. Mirrors the GPU/capture "try then fall back" pattern.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


class AudioAnalyzer:
    """Turns raw audio blocks into smooth, normalised reactive signals."""

    def __init__(
        self,
        samplerate: int = 48_000,
        sensitivity: float = 1.0,
        attack: float = 0.9,
        decay: float = 0.15,
        beat_sensitivity: float = 1.4,
        history: int = 43,          # ~1 s of ~1024-sample blocks at 48 kHz
    ) -> None:
        self.samplerate = samplerate
        self.sensitivity = max(0.05, sensitivity)
        self.attack = attack
        self.decay = decay
        self.beat_sensitivity = beat_sensitivity

        self.level: float = 0.0     # smoothed loudness 0..1
        self.pulse: float = 0.0     # decaying beat flash 0..1
        self.beat: bool = False     # beat detected on the most recent push
        self.bass: float = 0.0
        self.mid: float = 0.0
        self.treble: float = 0.0

        self._energy_hist: "deque[float]" = deque(maxlen=history)

    @staticmethod
    def _to_mono(samples: np.ndarray) -> np.ndarray:
        a = np.asarray(samples, dtype=np.float32)
        if a.ndim == 2:                      # (frames, channels) -> mono
            a = a.mean(axis=1)
        return a.reshape(-1)

    def push(self, samples: np.ndarray) -> None:
        """Analyse one block of float samples (range roughly -1..1)."""
        mono = self._to_mono(samples)
        if mono.size == 0:
            self.pulse *= 0.85
            return

        # --- Loudness (RMS → 0..1 with fast attack, slow decay) ---
        rms = float(np.sqrt(np.mean(mono * mono)))
        target = min(1.0, rms * 4.0 * self.sensitivity)
        if target > self.level:
            self.level += (target - self.level) * self.attack
        else:
            self.level += (target - self.level) * self.decay

        # --- Beat detection (energy onset vs. rolling mean) ---
        energy = rms * rms
        if len(self._energy_hist) >= 8:
            avg = sum(self._energy_hist) / len(self._energy_hist)
            self.beat = energy > avg * self.beat_sensitivity and energy > 1e-5
        else:
            self.beat = False
        self._energy_hist.append(energy)
        self.pulse = 1.0 if self.beat else self.pulse * 0.85

        # --- Frequency bands (bass / mid / treble), normalised 0..1 ---
        self._analyse_bands(mono)

    def _analyse_bands(self, mono: np.ndarray) -> None:
        n = mono.size
        if n < 16:
            return
        windowed = mono * np.hanning(n)
        spectrum = np.abs(np.fft.rfft(windowed))
        freqs = np.fft.rfftfreq(n, d=1.0 / self.samplerate)

        def band(lo: float, hi: float) -> float:
            m = (freqs >= lo) & (freqs < hi)
            return float(spectrum[m].sum())

        bass = band(20, 250)
        mid = band(250, 4_000)
        treble = band(4_000, 16_000)
        total = bass + mid + treble
        if total <= 1e-9:
            self.bass = self.mid = self.treble = 0.0
            return
        self.bass = bass / total
        self.mid = mid / total
        self.treble = treble / total


class AudioCapture:
    """Optional loopback capture feeding an :class:`AudioAnalyzer`.

    Uses the ``soundcard`` library's loopback microphone (WASAPI on Windows,
    PulseAudio monitor on Linux). If it is not installed or no device is
    available, :attr:`available` is ``False`` and nothing is captured.
    """

    def __init__(self, analyzer: AudioAnalyzer, blocksize: int = 1024) -> None:
        self.analyzer = analyzer
        self.blocksize = blocksize
        self.available = False
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> bool:
        """Begin capture on a daemon thread. Returns whether it started."""
        try:
            import soundcard  # noqa: F401  (optional dependency)
        except Exception as exc:  # pragma: no cover - depends on environment
            logger.warning("[Audio] 'soundcard' unavailable (%s); audio-reactive disabled.", exc)
            return False

        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="AmbilightAudioCapture", daemon=True)
        self._thread.start()
        return True

    def _run(self) -> None:  # pragma: no cover - requires audio hardware
        import soundcard
        try:
            speaker = soundcard.default_speaker()
            mic = soundcard.get_microphone(id=str(speaker.name), include_loopback=True)
            with mic.recorder(samplerate=self.analyzer.samplerate, blocksize=self.blocksize) as rec:
                self.available = True
                logger.info("[Audio] Loopback capture started on '%s'.", speaker.name)
                while not self._stop.is_set():
                    data = rec.record(numframes=self.blocksize)
                    self.analyzer.push(data)
        except Exception as exc:
            logger.warning("[Audio] Loopback capture failed (%s); audio-reactive disabled.", exc)
            self.available = False

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=1.0)
        self._thread = None
        self.available = False
