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

Turn text (``turn_text``, VM-2274 do-008). ``joined`` -- the DEFAULT, and
what spec conversation-log:12-13 says -- writes the turn as the join of its
partials. ``redecode`` re-decodes the turn's WHOLE audio and writes that
instead, because joined chunks split and duplicate words cut by the 2 s soft
max ("build status? status", 17 of 32 turns in M4). The re-decode is launched
speculatively once ``quiet_s`` of quiet follows speech inside the turn, so it
runs inside the ``silence_s`` wait and costs no turn latency; speech resuming
drops it. Partials are unchanged in both modes. A turn is still discarded when
its partials heard nothing, so the mode changes turn TEXT, never turn COUNT.
It is an option, not a spec change (cora 05:02, RULES 160): the default flips
only if Mike rules Q24.

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
TURN_TEXT_MODES = ("joined", "redecode")
DEFAULT_REDECODE_MAX_S = 60.0  # longer turns fall back to joined: bounded memory and whisper work
_HISTORY_S = 4.0  # audio kept before a turn opens; covers pre-roll and a chunk opened up to max_s early
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
        turn_text: str = "joined",
        redecode_max_s: float = DEFAULT_REDECODE_MAX_S,
    ) -> None:
        if turn_text not in TURN_TEXT_MODES:
            raise ValueError(f"turn_text must be one of {TURN_TEXT_MODES}, not {turn_text!r}")
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
        # The waiter's contract (do-003, FOREMAN 04:17): `period` on
        # listen-started and every heartbeat; it calls capture down after 2x
        # period with no line. No heartbeat, no period (heard drops None).
        self._period = heartbeat if heartbeat > 0 else None
        # turn text re-decode (do-008); all unused when turn_text == "joined"
        self.turn_text = turn_text
        self._redecode = turn_text == "redecode"
        self._redecode_max_frames = max(1, int(round(redecode_max_s / FRAME_S)))
        self._history: deque = deque(maxlen=int(round(_HISTORY_S / FRAME_S)))
        self._turn_audio: Optional[list] = None  # frames of the open turn (None: no turn open)
        self._turn_too_long = False
        self._quiet_run = 0  # non-speech frames since the turn's last speech frame
        self._quiet_frames = max(1, int(round(getattr(chunker, "quiet_s", 0.35) / FRAME_S)))
        self._spec: Optional[Future] = None  # the speculative whole-turn decode
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
        extra: dict = {}
        if self._redecode:
            # a turn whose partials heard nothing is discarded as before: the
            # re-decode changes a turn's text, never whether it is one
            text, extra = self._redecoded_text(text) if text else (text, {})
            self._turn_audio, self._spec, self._turn_too_long, self._quiet_run = None, None, False, 0
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
                **extra,
            }
        )
        self._turns.append(text)

    # -- turn re-decode (do-008) -------------------------------------------

    def _launch(self, audio: np.ndarray) -> Future:
        if self._executor is not None:
            return self._executor.submit(self.stt.transcribe, audio)
        fut: Future = Future()  # inline STT (tests): the same shape, already done
        try:
            fut.set_result(self.stt.transcribe(audio))
        except Exception as exc:
            fut.set_exception(exc)
        return fut

    def _drop_spec(self) -> None:
        if self._spec is not None:
            self._spec.cancel()  # a no-op if whisper already has it; its result is ignored
            self._spec = None

    def _track_turn_audio(self, frame: np.ndarray, verdict) -> None:
        """Keep the open turn's audio, and launch/drop the speculative re-decode."""
        self._history.append(frame)
        if verdict.turn_started:
            # the turn began at _turn_t0 (the first chunk's pre-roll included)
            back = int(round((self.t - self._turn_t0) / FRAME_S))
            hist = list(self._history)
            self._turn_audio = hist[-back:] if 0 < back < len(hist) else hist
            self._turn_too_long = False
            self._quiet_run = 0
            self._drop_spec()
            return
        if self._turn_audio is None:
            return
        if not self._turn_too_long:
            self._turn_audio.append(frame)
            if len(self._turn_audio) > self._redecode_max_frames:
                self._turn_too_long = True
                self._turn_audio = []  # free it; this turn's text will be joined
                self._drop_spec()
        if verdict.speech:
            self._quiet_run = 0
            self._drop_spec()  # speech resumed: what was launched is now short
        else:
            self._quiet_run += 1
            if self._quiet_run == self._quiet_frames and not self._turn_too_long:
                self._spec = self._launch(np.concatenate(self._turn_audio))

    def _redecoded_text(self, joined: str) -> tuple[str, dict]:
        """The turn's text from its whole audio; the joined partials on any failure."""
        audio, spec, too_long = self._turn_audio, self._spec, self._turn_too_long
        if too_long or not audio:
            return joined, {"text_from": "joined", "redecode": "too-long" if too_long else "no-audio"}
        waited = time.monotonic()
        fut = spec if spec is not None else self._launch(np.concatenate(audio))
        try:
            text = str(fut.result()).strip()
        except Exception as exc:  # whisper hiccup: the turn still lands, with the joined text
            return joined, {"text_from": "joined", "redecode": f"error: {exc}"}
        info = {"redecode_wait_s": _r(time.monotonic() - waited), "speculative": spec is not None}
        if not text:
            return joined, {"text_from": "joined", "redecode": "empty", **info}
        return text, {"text_from": "redecode", "joined": joined, **info}

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
                period=self._period,
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
                if self._redecode:
                    self._track_turn_audio(frame, verdict)
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
                    self.event(heard.EV_HEARTBEAT, period=self._period, stream_s=_r(self.t), **self._level.fields())
                    self._level.reset()
            # Nothing already heard is lost: finish the open chunk's partial,
            # and close a turn the source ended in the middle of.
            self._submit(self.chunker.flush(self.t))
            self._collect(wait=True)
            if self.detector.in_turn or self._partials:
                self._turn(self.t)
        except KeyboardInterrupt:  # Ctrl-C outside the CLI's signal handler: a stop, and still logged
            reason = "stop"
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
    turn_text: str = "joined",
    redecode_max_s: float = DEFAULT_REDECODE_MAX_S,
) -> CaptureResult:
    """Capture from ``source`` until stopped, an error, the end of a file, or ``ceiling``.

    Blocking; run it in its own process (the CLI) or off the event loop.
    ``sink`` defaults to :class:`HeardSink` (Pip's ``heard`` writer).
    ``stt_workers=0`` transcribes inline (deterministic, for tests).
    ``turn_text`` is ``joined`` (the default, per the spec) or ``redecode``.
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
        turn_text=turn_text,
        redecode_max_s=redecode_max_s,
    ).run()
