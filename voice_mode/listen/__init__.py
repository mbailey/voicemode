"""``listen``, the spike (VM-2274): capture that writes what it hears.

Spec: ``openspec/changes/ambient-listen/`` (task 3.0). Split by Cora's
ROADMAP (04:07): capture outlives the call.

- **capture** ("the ears", M1): one long-lived process with its own capture,
  VAD and chunking (not ``converse``'s capture path). It writes a
  ``partial`` per recognised chunk and a ``turn`` per end of turn through
  Pip's ``heard`` writer, and does not return on a turn.
- **aged_turn**: the waiter's rule (do-003) as a pure function over
  ``heard`` lines.

It never takes the conch and never makes a sound.

    python -m voice_mode.listen capture --source mic --device C930e
"""

from .aged import aged_turn
from .chunker import Chunk, Chunker
from .detector import EnergyClassifier, SilenceTurnDetector, WebRtcClassifier, make_detector
from .loop import DEFAULT_HEARTBEAT_S, CaptureResult, capture
from .sink import HeardSink, MemorySink, Sink
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
    resolve_input_device,
)
from .stt import STT, WhisperSTT

__all__ = [
    "ArraySource",
    "CaptureResult",
    "Chunk",
    "Chunker",
    "DEFAULT_HEARTBEAT_S",
    "EnergyClassifier",
    "FRAME_S",
    "FRAME_SAMPLES",
    "FileSource",
    "HeardSink",
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
    "aged_turn",
    "capture",
    "make_detector",
    "open_source",
    "resolve_input_device",
]
