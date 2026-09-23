"""Capture, "the ears": a long-lived loop that writes what it hears (M1).

Capture outlives the call (the design split, Cora ROADMAP 04:07). It writes
through ``heard``: a ``listen-started`` event before the first frame, a
``partial`` per chunk as it is recognised, a ``turn`` at each end of turn,
a ``heartbeat`` on a period (with the input level over that period, so a
dead-zero mic is visible), and a ``listen-stopped`` event with the reason
on every exit.

It does NOT return on a turn. It stops only on:

- ``stop``: the caller asked (a ``threading.Event``/callable, SIGINT/SIGTERM
  in the CLI, or a stop file)
- ``error``: the source failed, or STT failed ``max_stt_failures`` times in a row
- ``eof``: a file source ran out (the mic never does)
- ``ceiling``: only if one was given

Waking an agent on an aged turn is a separate waiter's job (do-003); its
rule is :func:`voice_mode.listen.aged.aged_turn`.

Time is STREAM time -- seconds of audio consumed -- so silence, heartbeat
and ceiling are measured on the audio. For the mic, and for a ``file:``
source paced at real time, stream time is wall time.

It never takes the conch and never makes a sound: nothing here imports
``voice_mode.conch`` or opens an output stream.
"""

from __future__ import annotations

import math
import os
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .. import heard
from .chunker import Chunk, Chunker
from .detector import SilenceTurnDetector, TurnDetector
from .sink import HeardSink, Sink
from .sources import FRAME_S, Source
from .stt import STT

DEFAULT_HEARTBEAT_S = 60.0
STOP_FILE_CHECK_S = 0.3


@dataclass
class CaptureResult:
    reason: str
    text: str  # every turn this capture wrote, one per line
    cursor: int  # seq of the last line written (the listen-stopped event)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        out = {"reason": self.reason, "text": self.text, "cursor": self.cursor}
        if self.error:
            out["error"] = self.error
        return out


def _stop_checker(stop, stop_file: Optional[Path]) -> Callable[[], bool]:
    if stop is None:
        requested: Callable[[], bool] = lambda: False
    elif hasattr(stop, "is_set"):  # threading.Event
        requested = stop.is_set
    elif callable(stop):
        requested = stop
    else:
        raise TypeError("stop must be a threading.Event, a callable returning bool, or None")
    if stop_file is None:
        return requested
    path = Path(stop_file).expanduser()
    return lambda: requested() or path.exists()


def _r(x: float) -> float:
    return round(x, 3)


class _Level:
    """Peak and RMS of the input over one heartbeat period (int16 full scale)."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._peak = 0
        self._sumsq = 0.0
        self._n = 0

    def add(self, frame: np.ndarray) -> None:
        x = frame.astype(np.int64)
        self._peak = max(self._peak, int(np.abs(x).max(initial=0)))
        self._sumsq += float(np.dot(x, x))
        self._n += len(x)

    def fields(self) -> dict:
        rms = math.sqrt(self._sumsq / self._n) if self._n else 0.0
        dbfs = round(20 * math.log10(rms / 32768.0), 1) if rms > 0 else None
        return {"peak": self._peak, "rms": round(rms, 1), "rms_dbfs": dbfs}


class _Capture:
    def __init__(
        self,
        source: Source,
        sink: Sink,
        stt: STT,
        *,
        heartbeat: float,
        ceiling: Optional[float],
        detector: TurnDetector,
        chunker: Chunker,
        stop: Callable[[], bool],
        session: Optional[str],
        agent: Optional[str],
        stt_workers: int,
        max_stt_failures: int,
    ) -> None:
        self.source = source
        self.sink = sink
        self.stt = stt
        self.heartbeat = heartbeat
        self.ceiling = ceiling
        self.detector = detector
        self.chunker = chunker
        self.stop_requested = stop
        self.session = session
        self.agent = agent
        self.max_stt_failures = max_stt_failures
        self._executor = ThreadPoolExecutor(max_workers=stt_workers, thread_name_prefix="listen-stt") if stt_workers > 0 else None
        self._pending: deque = deque()  # (Future | text | Exception, Chunk), in cut order
        self._partials: list[str] = []  # texts of partials not yet in a turn
        self._turns: list[str] = []  # texts of turns this capture wrote
        self._turn_t0: Optional[float] = None
        self._stt_failures = 0
        self._level = _Level()
        self.cursor = 0
        self.t = 0.0

    # -- writing -----------------------------------------------------------

    def _write(self, line: dict) -> int:
        line = {**line, "source": self.source.name, "device": self.source.device, "session": self.session, "agent": self.agent}
        self.cursor = self.sink.write(line)
        return self.cursor

    def event(self, name: str, **extra) -> int:
        return self._write({"kind": "event", "event": name, **extra})

    def _partial(self, text: str, chunk: Chunk) -> None:
        self._write({"kind": "partial", "text": text, "final": False, "t0": _r(chunk.t0), "t1": _r(chunk.t1)})
        self._partials.append(text)

    def _turn(self, t_end_speech: float) -> None:
        text = " ".join(p for p in self._partials if p)
        self._partials = []
        t0 = self._turn_t0 if self._turn_t0 is not None else t_end_speech
        self._turn_t0 = None
        if not text:
            # whisper heard nothing in it: a noise burst must not become a turn
            self.event("turn-discarded", why="no text recognised", t0=_r(t0), t1=_r(t_end_speech))
            return
        self._write(
            {
                "kind": "turn",
                "text": text,
                "final": True,
                "detector": self.detector.name,
                "t0": _r(t0),
                "t1": _r(t_end_speech),
            }
        )
        self._turns.append(text)

    # -- transcription -----------------------------------------------------

    def _submit(self, chunk: Optional[Chunk]) -> None:
        if chunk is None:
            return
        if self._executor is None:
            try:
                self._pending.append((self.stt.transcribe(chunk.audio), chunk))
            except Exception as exc:
                self._pending.append((exc, chunk))
        else:
            self._pending.append((self._executor.submit(self.stt.transcribe, chunk.audio), chunk))

    def _collect(self, wait: bool) -> None:
        """Write partials for finished chunks, in cut order; ``wait`` drains all."""
        while self._pending:
            result, chunk = self._pending[0]
            if isinstance(result, Future):
                if not wait and not result.done():
                    return
                try:
                    result = result.result()
                except Exception as exc:
                    result = exc
            self._pending.popleft()
            if isinstance(result, Exception):
                self._stt_failures += 1
                self.event("stt-error", detail=str(result), t0=_r(chunk.t0), t1=_r(chunk.t1))
                if self._stt_failures >= self.max_stt_failures:
                    raise RuntimeError(f"STT failed {self._stt_failures} times in a row: {result}")
                continue
            self._stt_failures = 0
            text = str(result).strip()
            if text:
                self._partial(text, chunk)

    # -- the loop ----------------------------------------------------------

    def run(self) -> CaptureResult:
        wall0 = time.monotonic()
        reason, error = "error", None
        next_hb = self.heartbeat  # on a fixed grid, so beats do not drift by a frame each
        stop_every = max(1, int(round(STOP_FILE_CHECK_S / FRAME_S)))
        try:
            self.event(
                heard.EV_LISTEN_STARTED,
                detector=self.detector.name,
                stt=getattr(self.stt, "name", type(self.stt).__name__),
                heartbeat=self.heartbeat,
                ceiling=self.ceiling,
                pid=os.getpid(),
            )
            reason = "eof"
            for n, frame in enumerate(self.source.frames()):
                t_frame = n * FRAME_S
                self.t = (n + 1) * FRAME_S
                self._level.add(frame)
                verdict = self.detector.feed(frame)
                if verdict.turn_started:
                    self._turn_t0 = t_frame
                self._submit(self.chunker.feed(frame, verdict.speech, t_frame))
                if verdict.turn_started and self.chunker.start_t is not None:
                    # the turn began where its first chunk did (pre-roll included)
                    self._turn_t0 = min(self._turn_t0, self.chunker.start_t)
                if verdict.end_of_turn:
                    self._submit(self.chunker.flush(self.t))
                    self._collect(wait=True)
                    self._turn(self.t - getattr(self.detector, "silence_s", 0.0))
                else:
                    self._collect(wait=False)
                    if not verdict.in_turn and not self.chunker.open and not self._pending:
                        # Partials with no turn around them (a blip): they stay in
                        # the log, but are not glued onto the next turn's text.
                        self._partials = []

                if n % stop_every == 0 and self.stop_requested():
                    reason = "stop"
                    break
                if self.ceiling is not None and self.t >= self.ceiling:
                    reason = "ceiling"
                    break
                if self.heartbeat > 0 and self.t >= next_hb - 1e-9:
                    next_hb += self.heartbeat
                    self.event(heard.EV_HEARTBEAT, stream_s=_r(self.t), **self._level.fields())
                    self._level.reset()
            # Nothing already heard is lost: finish the open chunk's partial,
            # and close a turn the source ended in the middle of.
            self._submit(self.chunker.flush(self.t))
            self._collect(wait=True)
            if self.detector.in_turn or self._partials:
                self._turn(self.t)
        except Exception as exc:  # the source died, STT kept failing, or the log cannot be written
            reason, error = "error", f"{type(exc).__name__}: {exc}"
        finally:
            try:
                self.source.close()
            finally:
                if self._executor is not None:
                    self._executor.shutdown(wait=False, cancel_futures=True)
        extra = {"reason": reason, "stream_s": _r(self.t), "wall_s": _r(time.monotonic() - wall0), "turns": len(self._turns)}
        if error:
            extra["error"] = error
        try:
            self.event(heard.EV_LISTEN_STOPPED, **extra)
        except Exception as exc:  # the log itself is gone: say so in the return
            error = f"{error + '; ' if error else ''}listen-stopped not written: {exc}"
            reason = "error"
        return CaptureResult(reason=reason, text="\n".join(self._turns), cursor=self.cursor, error=error)


def capture(
    source: Source,
    stt: STT,
    sink: Optional[Sink] = None,
    *,
    heartbeat: float = DEFAULT_HEARTBEAT_S,
    ceiling: Optional[float] = None,
    detector: Optional[TurnDetector] = None,
    chunker: Optional[Chunker] = None,
    stop=None,
    stop_file: Optional[str | Path] = None,
    session: Optional[str] = None,
    agent: Optional[str] = None,
    stt_workers: int = 1,
    max_stt_failures: int = 3,
) -> CaptureResult:
    """Capture from ``source`` until stopped, an error, the end of a file, or ``ceiling``.

    Blocking; run it in its own process (the CLI) or off the event loop.
    ``sink`` defaults to :class:`HeardSink` (Pip's ``heard`` writer).
    ``stt_workers=0`` transcribes inline (deterministic, for tests).
    """
    return _Capture(
        source,
        sink if sink is not None else HeardSink(),
        stt,
        heartbeat=heartbeat,
        ceiling=ceiling,
        detector=detector or SilenceTurnDetector(),
        chunker=chunker or Chunker(),
        stop=_stop_checker(stop, Path(stop_file) if stop_file else None),
        session=session,
        agent=agent,
        stt_workers=stt_workers,
        max_stt_failures=max_stt_failures,
    ).run()
