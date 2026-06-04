"""Tests for the audio-reactive DSP (FR-EFF-05) — pure, no sound hardware."""

import numpy as np

from ambilight.audio_input import AudioAnalyzer


SR = 48_000


def _sine(freq: float, n: int, amp: float = 0.8) -> np.ndarray:
    t = np.arange(n) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_silence_is_quiet():
    a = AudioAnalyzer(samplerate=SR)
    for _ in range(10):
        a.push(np.zeros(2048, dtype=np.float32))
    assert a.level < 0.05
    assert a.beat is False
    assert a.pulse < 0.05


def test_loud_signal_raises_level():
    a = AudioAnalyzer(samplerate=SR)
    for _ in range(8):
        a.push(_sine(440, 2048, amp=0.8))
    assert a.level > 0.5


def test_level_decays_after_signal_stops():
    a = AudioAnalyzer(samplerate=SR)
    for _ in range(8):
        a.push(_sine(440, 2048, amp=0.8))
    peak = a.level
    for _ in range(20):
        a.push(np.zeros(2048, dtype=np.float32))
    assert a.level < peak * 0.5


def test_beat_detection_on_energy_onset():
    a = AudioAnalyzer(samplerate=SR)
    # Fill history with quiet so the rolling mean is low.
    for _ in range(12):
        a.push(_sine(440, 2048, amp=0.02))
    a.push(_sine(440, 2048, amp=0.9))   # sudden onset
    assert a.beat is True
    assert a.pulse == 1.0


def test_frequency_bands_separate_bass_from_treble():
    a = AudioAnalyzer(samplerate=SR)
    a.push(_sine(100, 4096, amp=0.8))     # bass tone
    assert a.bass > a.treble

    b = AudioAnalyzer(samplerate=SR)
    b.push(_sine(9000, 4096, amp=0.8))    # treble tone
    assert b.treble > b.bass


def test_stereo_input_is_reduced_to_mono():
    a = AudioAnalyzer(samplerate=SR)
    block = np.stack([_sine(440, 2048, 0.8), _sine(440, 2048, 0.8)], axis=1)  # (n, 2)
    a.push(block)
    assert a.level > 0.0
