"""Process-wide utterance history buffer for VoiceMode (VM-1685).

The control channel (VM-1676) can pause / resume / stop the *in-flight* TTS
utterance. VM-1685 adds CD-style transport on top: **skip back** to re-hear a
previous utterance. That needs the server to remember the audio it has already
spoken, so this module is the memory layer underneath it -- a small, bounded,
process-wide ring buffer of recently rendered utterances.

It is **pure storage, no sockets and no audio**. The playback loop in
``streaming.py`` captures each rendered utterance here; a later feature
(``impl-replay``) reads it back out to drive skip-back. Kept deliberately
independent of the control state so either side can evolve on its own.

* ``UtteranceRecord`` -- one immutable rendered utterance: the decoded
  ``pcm_bytes`` (16-bit signed little-endian, the format ``sounddevice``
  replays directly) plus ``sample_rate`` / ``channels`` to play it back, the
  ``text`` that produced it, a capture ``timestamp``, and the cheap-to-grab
  ``voice`` / ``conversation_id`` context.

* ``HistoryBuffer`` -- a thread-safe ``deque(maxlen=N)``. One side (the playback
  coroutine) calls ``append``; another (a future skip-back driver, or a status
  query) calls ``snapshot`` / ``latest`` / ``get`` to read it back. ``clear``
  empties it.

Memory note (load-bearing -- raw PCM is large): at the 24 kHz mono 16-bit TTS
default, audio costs ~48 KB per second, so a ~10 s utterance is ~470 KB. The
buffer is bounded by ``maxlen`` (default ``DEFAULT_HISTORY_SIZE``,
env-configurable via ``VOICEMODE_HISTORY_BUFFER_SIZE``) precisely so this can't
grow without bound -- keep N small.

A process-wide ``get_history_buffer()`` singleton (mirroring
``get_control_state()``) gives the playback loop and any reader a shared
instance without threading a reference through every call signature.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("voicemode.history_buffer")


# How many rendered utterances to keep when no explicit size is configured.
# Small on purpose: raw PCM is large (see the module memory note), so the
# default trades a shallow history for a bounded footprint. Override with
# VOICEMODE_HISTORY_BUFFER_SIZE.
DEFAULT_HISTORY_SIZE = 8


@dataclass(frozen=True)
class UtteranceRecord:
    """One rendered TTS utterance, captured for later replay.

    ``pcm_bytes`` is raw 16-bit signed little-endian PCM at ``sample_rate`` /
    ``channels`` -- i.e. exactly what ``sounddevice`` writes back out, so a
    replay can feed it straight to an output stream with no decode step.

    Frozen so a record handed to a reader can't be mutated underneath the
    buffer. ``text`` is the spoken text; ``voice`` / ``conversation_id`` are
    optional context grabbed cheaply at capture time.
    """

    text: str
    pcm_bytes: bytes
    sample_rate: int
    channels: int
    timestamp: float
    voice: Optional[str] = None
    conversation_id: Optional[str] = None

    @property
    def nbytes(self) -> int:
        """Size of the captured audio in bytes -- handy for memory accounting."""
        return len(self.pcm_bytes)

    @property
    def duration(self) -> float:
        """Approximate playback duration in seconds (0 if metadata is unusable).

        Derived from the PCM length: 2 bytes per sample (16-bit) times channels
        times sample_rate. A read-side ("now playing") convenience.
        """
        frame_bytes = 2 * max(self.channels, 1)
        rate = self.sample_rate or 0
        if rate <= 0 or frame_bytes <= 0:
            return 0.0
        return len(self.pcm_bytes) / (frame_bytes * rate)


class HistoryBuffer:
    """Thread-safe, bounded ring buffer of recently rendered utterances.

    Backed by ``deque(maxlen=N)``: appending past ``maxlen`` evicts the oldest
    record automatically, so memory stays bounded without any explicit pruning.
    Ordering is oldest-first; ``latest()`` and negative ``get`` indices reach the
    newest end, which is what a skip-back cursor walks backwards from.

    Every public method takes the lock so a reader always sees a consistent
    view even while the playback loop is appending from another thread.
    """

    def __init__(self, maxlen: int = DEFAULT_HISTORY_SIZE) -> None:
        if maxlen < 1:
            raise ValueError(f"history buffer maxlen must be >= 1, got {maxlen}")
        self._lock = threading.Lock()
        self._records: "deque[UtteranceRecord]" = deque(maxlen=maxlen)

    # --- mutations (playback side) ---------------------------------------

    def append(
        self,
        *,
        text: str,
        pcm_bytes: bytes,
        sample_rate: int,
        channels: int = 1,
        voice: Optional[str] = None,
        conversation_id: Optional[str] = None,
        timestamp: Optional[float] = None,
    ) -> UtteranceRecord:
        """Capture one rendered utterance, returning the stored record.

        ``timestamp`` defaults to ``time.time()`` at capture. Appending past
        ``maxlen`` silently evicts the oldest record (deque semantics).
        """
        record = UtteranceRecord(
            text=text,
            pcm_bytes=pcm_bytes,
            sample_rate=sample_rate,
            channels=channels,
            timestamp=time.time() if timestamp is None else timestamp,
            voice=voice,
            conversation_id=conversation_id,
        )
        return self.append_record(record)

    def append_record(self, record: UtteranceRecord) -> UtteranceRecord:
        """Append a pre-built record. Returns the record for convenience."""
        with self._lock:
            self._records.append(record)
            logger.debug(
                "history buffer append: %d bytes, depth %d/%d",
                record.nbytes, len(self._records), self._records.maxlen,
            )
        return record

    def clear(self) -> None:
        """Drop all captured utterances (e.g. between conversations / in tests)."""
        with self._lock:
            self._records.clear()

    # --- reads (replay / status side) ------------------------------------

    @property
    def maxlen(self) -> int:
        """The buffer's bound -- the most records it will ever hold."""
        return self._records.maxlen

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def snapshot(self) -> List[UtteranceRecord]:
        """Return a list copy of the records, oldest first.

        A snapshot so a reader can iterate / index without holding the lock and
        without seeing a concurrent append shift the contents underneath it.
        """
        with self._lock:
            return list(self._records)

    def latest(self) -> Optional[UtteranceRecord]:
        """The most recently captured utterance, or ``None`` if empty."""
        with self._lock:
            return self._records[-1] if self._records else None

    def get(self, index: int) -> Optional[UtteranceRecord]:
        """Return the record at ``index`` (negative indexes from the newest end).

        ``get(-1)`` is the latest, ``get(-2)`` the one before -- the access
        pattern a skip-back cursor uses. Out-of-range returns ``None`` rather
        than raising, so a cursor can walk off the end harmlessly.
        """
        with self._lock:
            try:
                return self._records[index]
            except IndexError:
                return None


# --- Process-wide singleton ----------------------------------------------

_default_buffer: Optional[HistoryBuffer] = None
_default_lock = threading.Lock()


def _configured_size() -> int:
    """Resolve the buffer size from config, falling back to the default.

    Imported lazily (config pulls in a lot) and guarded so a missing/invalid
    setting can never stop the buffer from being created.
    """
    try:
        from . import config
        size = int(getattr(config, "HISTORY_BUFFER_SIZE", DEFAULT_HISTORY_SIZE))
        return size if size >= 1 else DEFAULT_HISTORY_SIZE
    except Exception:  # pragma: no cover -- defensive; config import shouldn't fail
        return DEFAULT_HISTORY_SIZE


def get_history_buffer() -> HistoryBuffer:
    """Return the process-wide ``HistoryBuffer`` shared by playback and readers.

    The playback loop (capture side) and any skip-back / status reader live in
    different parts of the codebase and don't share an object reference, so they
    reach the same buffer through this singleton. Created lazily and
    thread-safely, sized from ``VOICEMODE_HISTORY_BUFFER_SIZE``.
    """
    global _default_buffer
    if _default_buffer is None:
        with _default_lock:
            if _default_buffer is None:
                _default_buffer = HistoryBuffer(maxlen=_configured_size())
    return _default_buffer
