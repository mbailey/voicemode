"""Speech in progress must not be truncated at listen_duration_max.

`max_duration` is chosen by the calling agent before it knows how long the human
will speak. It exists to stop an *idle* microphone running forever. Applying it
to speech that is actively in progress clips the user mid-word, so once speech
has been detected the window extends and the normal silence exit ends the
recording — bounded by `LISTEN_OVERRUN` so a microphone that never goes quiet
still terminates.

These tests drive the real `record_audio_with_silence_detection` loop with a
fake `sd.InputStream` (a producer thread feeding 30ms chunks to the callback)
and a scripted VAD. That runs about 30x faster than real time and needs no
microphone, so unlike a `sd.rec()` mock it does not hang.
"""
import threading
import time
import types

import numpy as np
import pytest

from voice_mode.tools import converse

CHUNK_MS = 30  # converse.VAD_CHUNK_DURATION_MS


class FakeVad:
    """Scripted VAD: reports speech for the first `speech_until_s` seconds."""

    def __init__(self, aggressiveness):
        self.calls = 0
        self.speech_until_s = 0.0

    def is_speech(self, chunk_bytes, sample_rate):
        t = self.calls * CHUNK_MS / 1000.0
        self.calls += 1
        return t < self.speech_until_s


class FakeInputStream:
    """Feeds 30ms int16 chunks to the callback from a producer thread."""

    def __init__(self, samplerate, channels, dtype, callback, blocksize):
        self.callback = callback
        self.blocksize = blocksize
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._produce, daemon=True)

    def _produce(self):
        chunk = np.zeros((self.blocksize, 1), dtype=np.int16)
        while not self._stop.is_set():
            self.callback(chunk, self.blocksize, None, None)
            time.sleep(0.001)  # ~30x real time; keeps the queue bounded

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=2)
        return False


@pytest.fixture
def vad_env(monkeypatch):
    """Patch converse's audio/VAD environment.

    Yields a config dict; set ``cfg["speech_until_s"]`` before recording to
    script how long the fake user speaks.
    """
    cfg = {"speech_until_s": 0.0}

    def vad_factory(aggressiveness):
        v = FakeVad(aggressiveness)
        v.speech_until_s = cfg["speech_until_s"]
        return v

    fake_sd = types.SimpleNamespace(
        InputStream=FakeInputStream,
        PortAudioError=RuntimeError,
    )
    monkeypatch.setattr(converse, "sd", fake_sd)
    monkeypatch.setattr(converse, "webrtcvad", types.SimpleNamespace(Vad=vad_factory))
    monkeypatch.setattr(converse, "VAD_AVAILABLE", True)
    monkeypatch.setattr(converse, "DISABLE_SILENCE_DETECTION", False)
    monkeypatch.setattr(converse, "VAD_DEBUG", False)
    monkeypatch.setattr(converse, "DEBUG", False)
    monkeypatch.setattr(converse, "SILENCE_THRESHOLD_MS", 1000)
    monkeypatch.setattr(converse, "MIN_RECORDING_DURATION", 0.0)
    return cfg


def _record(max_duration):
    audio, speech_detected = converse.record_audio_with_silence_detection(
        max_duration=max_duration,
        disable_silence_detection=False,
        min_duration=0.0,
        vad_aggressiveness=3,
    )
    return len(audio) / converse.SAMPLE_RATE, speech_detected


def test_active_speech_is_not_truncated_at_max_duration(vad_env):
    """Speech runs 0-2.0s with max_duration 1.0s.

    The recording must continue through the speech and end via the normal
    1s-silence exit (~3.0s), not at the 1.0s cap.
    """
    vad_env["speech_until_s"] = 2.0
    duration, speech_detected = _record(max_duration=1.0)
    assert speech_detected is True
    assert duration > 2.0, f"truncated at {duration:.2f}s - cap hit during speech"
    assert duration < 4.5, f"ran too long ({duration:.2f}s)"


def test_silent_window_still_stops_at_max_duration(vad_env):
    """No speech at all: the idle window is unchanged and still ends at the cap."""
    duration, speech_detected = _record(max_duration=1.0)
    assert speech_detected is False
    assert duration < 1.5, f"idle window should end at max_duration, got {duration:.2f}s"


def test_overrun_bounds_a_vad_stuck_on_speech(vad_env, monkeypatch):
    """A VAD that never reports silence (constant background noise) must still
    terminate, at max_duration + LISTEN_OVERRUN."""
    monkeypatch.setattr(converse, "LISTEN_OVERRUN", 0.5)
    vad_env["speech_until_s"] = 100.0
    duration, speech_detected = _record(max_duration=1.0)
    assert speech_detected is True
    assert 1.3 < duration < 2.2, f"expected ~1.5s ceiling, got {duration:.2f}s"


def test_overrun_zero_restores_the_hard_cap(vad_env, monkeypatch):
    """Opt-out: LISTEN_OVERRUN=0 reproduces the previous behaviour exactly."""
    monkeypatch.setattr(converse, "LISTEN_OVERRUN", 0.0)
    vad_env["speech_until_s"] = 100.0
    duration, speech_detected = _record(max_duration=1.0)
    assert speech_detected is True
    assert duration < 1.4, f"overrun=0 should cap at 1.0s, got {duration:.2f}s"


def test_stall_backstop_is_unaffected(vad_env, monkeypatch):
    """The 8.11 dead-stream backstop is orthogonal and must still fire.

    A stream that stops delivering chunks ends within AUDIO_STALL_TIMEOUT even
    though speech was detected and the overrun window is wide open.
    """
    class DeadAfterFirstChunk(FakeInputStream):
        def _produce(self):
            chunk = np.zeros((self.blocksize, 1), dtype=np.int16)
            self.callback(chunk, self.blocksize, None, None)
            # then nothing ever again - the device is gone

    monkeypatch.setattr(
        converse, "sd",
        types.SimpleNamespace(InputStream=DeadAfterFirstChunk, PortAudioError=RuntimeError),
    )
    vad_env["speech_until_s"] = 100.0
    start = time.monotonic()
    _record(max_duration=60.0)
    elapsed = time.monotonic() - start
    assert elapsed < 15.0, f"dead stream should end via the stall backstop, took {elapsed:.1f}s"
