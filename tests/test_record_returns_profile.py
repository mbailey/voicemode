import inspect

import numpy as np
import voice_mode.tools.converse as c
from voice_mode.tools.silence_profile import SilenceProfile


def test_signature_has_silence_release_sec_no_disable_bool():
    sig = inspect.signature(c.record_audio_with_silence_detection)
    params = list(sig.parameters)
    assert "silence_release_sec" in params
    assert "disable_silence_detection" not in params


def test_returns_three_tuple_with_profile(monkeypatch):
    # Force the no-VAD fallback so the test needs no microphone.
    monkeypatch.setattr(c, "VAD_AVAILABLE", False)
    monkeypatch.setattr(c, "record_audio", lambda d: np.array([0.0], dtype=np.float32))
    result = c.record_audio_with_silence_detection(1.0)
    assert isinstance(result, tuple) and len(result) == 3
    audio, speech, profile = result
    assert isinstance(profile, SilenceProfile)


def test_release_threshold_mapping():
    from voice_mode.tools.converse import _release_threshold_ms, SILENCE_THRESHOLD_MS
    assert _release_threshold_ms(0) == float(SILENCE_THRESHOLD_MS)
    assert _release_threshold_ms(60) == 60000
    assert _release_threshold_ms(-1) == float("inf")
