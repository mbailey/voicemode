"""The ``listen`` loop: capture, detect, chunk, transcribe, write; return late.

``listen`` does NOT return at the end of a turn. It writes a ``partial``
line per chunk as it is recognised and a ``turn`` line at each end of turn,
and returns only when:

- ``turn``: the newest turn is older than ``age`` and no speech is going on
- ``ceiling``: the call has run for ``ceiling`` seconds
- ``stop``: the caller asked it to stop
- ``error``: the source failed, or STT failed ``max_stt_failures`` times in a row
- ``eof``: a finite source ran out (test/measurement sources only; the mic
  and ``file:`` sources never end on their own)

Every exit writes a ``listen stopped`` event with the reason. The return is
``{reason, text, cursor}``: ``text`` is every turn this call wrote, one per
line, and ``cursor`` is the ``seq`` of the last line written.

Time is STREAM time -- seconds of audio consumed -- so silence, age,
heartbeat and ceiling are measured on the audio. For the mic, and for a
``file:`` source paced at real time, stream time is wall time.

It never takes the conch and never makes a sound: nothing here imports
``voice_mode.conch`` or opens an output stream.
"""

from __future__ import annotations

import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Optional, Union

from .chunker import Chunk, Chunker
from .detector import SilenceTurnDetector, TurnDetector
from .sink import Sink
from .sources import FRAME_S, Source
from .stt import STT

DEFAULT_AGE_S = 8.0
DEFAULT_CEILING_S = 25 * 60.0
DEFAULT_HEARTBEAT_S = 60.0

StopRequest = Union[Callable[[], bool], "object", None]


@dataclass
class ListenResult:
    reason: str
    text: str
    cursor: int
    error: Optional[str] = None

    def to_dict(self) -> dict:
        out = {"reason": self.reason, "text": self.text, "cursor": self.cursor}
        if self.error:
            out["error"] = self.error
        return out


def _stop_checker(stop: StopRequest) -> Callable[[], bool]:
    if stop is None:
        return lambda: False
    if hasattr(stop, "is_set"):  # threading.Event
        return stop.is_set  # type: ignore[union-attr]
    if callable(stop):
        return stop  # type: ignore[return-value]
    raise TypeError("stop must be a threading.Event, a callable returning bool, or None")


def _r(x: float) -> float:
    return round(x, 3)


class _Listener:
    def __init__(
        self,
        source: Source,
        sink: Sink,
        stt: STT,
        *,
        age: float,
        ceiling: float,
        heartbeat: float,
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
        self.age = age
        self.ceiling = ceiling
        self.heartbeat = heartbeat
        self.detector = detector
        self.chunker = chunker
        self.stop_requested = stop
        self.session = session
        self.agent = agent
        self.max_stt_failures = max_stt_failures
        self._executor = ThreadPoolExecutor(max_workers=stt_workers, thread_name_prefix="listen-stt") if stt_workers > 0 else None
        self._pending: deque = deque()  # (Future | text, Chunk), in cut order
        self._partials: list[str] = []  # texts of partials not yet in a turn
        self._turns: list[str] = []  # texts of turns this call wrote
        self._turn_t0: Optional[float] = None
        self._last_turn_t: Optional[float] = None
        self._stt_failures = 0
        self.cursor = 0
        self.t = 0.0

    # -- writing -----------------------------------------------------------

    def _common(self) -> dict:
        return {
            "source": self.source.name,
            "device": self.source.device,
            "session": self.session,
            "agent": self.agent,
        }

    def event(self, name: str, **extra) -> int:
        self.cursor = self.sink.write({"kind": "event", "event": name, **self._common(), **extra})
        return self.cursor

    def _partial(self, text: str, chunk: Chunk) -> None:
        self.cursor = self.sink.write(
            {"kind": "partial", "text": text, **self._common(), "final": False, "t0": _r(chunk.t0), "t1": _r(chunk.t1)}
        )
        self._partials.append(text)

    def _turn(self, t_end_speech: float) -> None:
        text = " ".join(p for p in self._partials if p)
        self._partials = []
        t0 = self._turn_t0 if self._turn_t0 is not None else t_end_speech
        self._turn_t0 = None
        if not text:
            self.event("turn-discarded", why="no text recognised", t0=_r(t0), t1=_r(t_end_speech))
            return
        self.cursor = self.sink.write(
            {
                "kind": "turn",
                "text": text,
                **self._common(),
                "final": True,
                "detector": self.detector.name,
                "t0": _r(t0),
                "t1": _r(t_end_speech),
            }
        )
        self._turns.append(text)
        self._last_turn_t = self.t

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

    def run(self) -> ListenResult:
        wall0 = time.monotonic()
        reason, error = "error", None
        self.event(
            "listen started",
            detector=self.detector.name,
            stt=getattr(self.stt, "name", type(self.stt).__name__),
            age=self.age,
            ceiling=self.ceiling,
            heartbeat=self.heartbeat,
        )
        next_hb = self.heartbeat  # on a fixed grid, so beats do not drift by a frame each
        try:
            reason = "eof"
            for n, frame in enumerate(self.source.frames()):
                t_frame = n * FRAME_S
                self.t = (n + 1) * FRAME_S
                verdict = self.detector.feed(frame)
                if verdict.turn_started:
                    # The turn began at the chunk's start if one is open (pre-roll
                    # and the speech frames that opened it), else at this frame.
                    self._turn_t0 = t_frame
                self._submit(self.chunker.feed(frame, verdict.speech, t_frame))
                if verdict.turn_started and self.chunker.start_t is not None:
                    self._turn_t0 = min(self._turn_t0, self.chunker.start_t)
                if verdict.end_of_turn:
                    self._submit(self.chunker.flush(self.t))
                    self._collect(wait=True)
                    silence_s = getattr(self.detector, "silence_s", 0.0)
                    self._turn(self.t - silence_s)
                else:
                    self._collect(wait=False)
                    if not verdict.in_turn and not self.chunker.open and not self._pending:
                        # Partials with no turn around them (a blip): they stay in
                        # the log, but are not glued onto the next turn's text.
                        self._partials = []

                if self.stop_requested():
                    reason = "stop"
                    break
                if (
                    self._last_turn_t is not None
                    and not self.detector.in_turn
                    and not self.chunker.open
                    and self.t - self._last_turn_t >= self.age
                ):
                    reason = "turn"
                    break
                if self.t >= self.ceiling:
                    reason = "ceiling"
                    break
                if self.heartbeat > 0 and self.t >= next_hb - 1e-9:
                    next_hb += self.heartbeat
                    self.event("heartbeat", stream_s=_r(self.t))
            if reason in ("ceiling", "stop", "eof"):
                # Nothing already heard is lost: finish the open chunk's partial.
                self._submit(self.chunker.flush(self.t))
                self._collect(wait=True)
                if reason == "eof" and self.detector.in_turn:
                    self._turn(self.t)
        except Exception as exc:  # the source died, or STT kept failing
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
        self.event("listen stopped", **extra)
        return ListenResult(reason=reason, text="\n".join(self._turns), cursor=self.cursor, error=error)


def listen(
    source: Source,
    sink: Sink,
    stt: STT,
    *,
    age: float = DEFAULT_AGE_S,
    ceiling: float = DEFAULT_CEILING_S,
    heartbeat: float = DEFAULT_HEARTBEAT_S,
    detector: Optional[TurnDetector] = None,
    chunker: Optional[Chunker] = None,
    stop: StopRequest = None,
    session: Optional[str] = None,
    agent: Optional[str] = None,
    stt_workers: int = 1,
    max_stt_failures: int = 3,
) -> ListenResult:
    """Listen on ``source`` until an aged turn, the ceiling, a stop or an error.

    Blocking; run it off the event loop (a thread) from async code.
    ``stt_workers=0`` transcribes inline (deterministic, for tests).
    """
    return _Listener(
        source,
        sink,
        stt,
        age=age,
        ceiling=ceiling,
        heartbeat=heartbeat,
        detector=detector or SilenceTurnDetector(),
        chunker=chunker or Chunker(),
        stop=_stop_checker(stop),
        session=session,
        agent=agent,
        stt_workers=stt_workers,
        max_stt_failures=max_stt_failures,
    ).run()
