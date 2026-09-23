"""Shared helpers for the listen spike tests (VM-2274): a synthetic source,
a fake STT and a sink that records when (in audio frames) each line landed.

No real audio device and no real STT server is touched.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from voice_mode.listen import FRAME_S, SAMPLE_RATE, ArraySource, EnergyClassifier, JsonlSink, SilenceTurnDetector


def synth(segments: list[tuple[str, float]]) -> np.ndarray:
    """``[("speech", 1.0), ("silence", 3.0), ...]`` -> 16 kHz int16.

    Speech is a loud 220 Hz tone; silence is digital zero. The tests pair
    it with :class:`EnergyClassifier`, so what counts as speech is exact.
    """
    parts = []
    for kind, seconds in segments:
        n = int(round(seconds * SAMPLE_RATE))
        if kind == "speech":
            t = np.arange(n) / SAMPLE_RATE
            parts.append((4000 * np.sin(2 * np.pi * 220 * t)).astype(np.int16))
        elif kind == "silence":
            parts.append(np.zeros(n, dtype=np.int16))
        else:
            raise ValueError(kind)
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.int16)


class CountingSource(ArraySource):
    """An unpaced ArraySource that counts the frames it has yielded."""

    def __init__(self, samples, *, tail_silence_s=None, realtime=False, device="synthetic"):
        super().__init__(samples, name="file", device=device, realtime=realtime, tail_silence_s=tail_silence_s)
        self.yielded = 0

    def frames(self):
        for frame in super().frames():
            self.yielded += 1
            yield frame


class FakeSTT:
    """Returns ``w1``, ``w2``, ... per chunk (or scripted texts), instantly."""

    name = "fake"

    def __init__(self, texts=None, fail_always=False):
        self.calls = 0
        self.texts = list(texts) if texts else None
        self.fail_always = fail_always

    def transcribe(self, audio):
        self.calls += 1
        if self.fail_always:
            raise RuntimeError("fake STT is down")
        if self.texts is not None:
            return self.texts.pop(0) if self.texts else ""
        return f"w{self.calls}"


class RecordingSink(JsonlSink):
    """A JsonlSink that also notes, per line, the source's frame count and the wall clock."""

    def __init__(self, path, source: CountingSource | None = None):
        super().__init__(path)
        self.source = source
        self.at_frames: dict[int, int] = {}
        self.at_wall: dict[int, float] = {}

    def write(self, line):
        seq = super().write(line)
        self.at_wall[seq] = time.monotonic()
        if self.source is not None:
            self.at_frames[seq] = self.source.yielded
        return seq


def stream_s_at(sink: RecordingSink, seq: int) -> float:
    """Stream seconds consumed when line ``seq`` was written."""
    return sink.at_frames[seq] * FRAME_S


def read_lines(path: Path) -> list[dict]:
    return [json.loads(raw) for raw in Path(path).read_text().splitlines() if raw.strip()]


def energy_detector(silence_s: float = 2.0) -> SilenceTurnDetector:
    return SilenceTurnDetector(silence_s, classifier=EnergyClassifier(500.0))


def parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)
