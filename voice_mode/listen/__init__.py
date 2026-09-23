"""``listen``: a fresh, long-lived listener that writes what it hears (VM-2274).

Spec: ``openspec/changes/ambient-listen/`` (task 3.0, the spike). Its own
capture, VAD and chunking -- not ``converse``'s capture path. It writes a
``partial`` line per recognised chunk and a ``turn`` line per end of turn,
and returns only on an aged turn, the ceiling, a stop request or an error.
It never takes the conch and never makes a sound.

Arm it from a shell::

    python -m voice_mode.listen --source file:X.wav --age 8 --log PATH
"""

from .chunker import Chunk, Chunker
from .detector import EnergyClassifier, SilenceTurnDetector, WebRtcClassifier, make_detector
from .loop import DEFAULT_AGE_S, DEFAULT_CEILING_S, DEFAULT_HEARTBEAT_S, ListenResult, listen
from .sink import JsonlSink, MemorySink, Sink
from .sources import (
    FRAME_S,
    FRAME_SAMPLES,
    SAMPLE_RATE,
    ArraySource,
    FileSource,
    MicSource,
    Source,
    SourceError,
    open_source,
)
from .stt import STT, WhisperSTT

__all__ = [
    "ArraySource",
    "Chunk",
    "Chunker",
    "DEFAULT_AGE_S",
    "DEFAULT_CEILING_S",
    "DEFAULT_HEARTBEAT_S",
    "EnergyClassifier",
    "FRAME_S",
    "FRAME_SAMPLES",
    "FileSource",
    "JsonlSink",
    "ListenResult",
    "MemorySink",
    "MicSource",
    "SAMPLE_RATE",
    "STT",
    "SilenceTurnDetector",
    "Sink",
    "Source",
    "SourceError",
    "WebRtcClassifier",
    "WhisperSTT",
    "listen",
    "make_detector",
    "open_source",
]
