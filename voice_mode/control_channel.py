"""In-process control-channel state and command schema for VoiceMode (VM-1676).

The control channel is a side channel that lets an external trigger -- a Stream
Deck press, a media key, a spoken keyword, or any local process -- pause /
resume / stop an in-flight TTS utterance *without* going through the MCP
protocol stream and *without* pressing ESC.

This module is the foundation: **pure logic, no sockets and no audio.** Two
pieces, kept transport-agnostic so a socket listener (or an HTTP one later) can
sit on top without playback ever caring:

* ``ControlState`` -- a thread-safe object. One side (a listener thread) calls
  ``request_pause`` / ``request_resume`` / ``request_stop``; the other side (the
  TTS playback coroutine) polls ``snapshot`` each chunk and uses
  ``wait_while_paused`` to hold without busy-spinning. ``reset`` clears it back
  to *running* between utterances.

* The newline-delimited JSON command schema -- ``parse_command`` turns one line
  of ``{"command": "pause"|"resume"|"stop", "message"?, "hint"?}`` into a
  validated ``ControlCommand``, raising ``ControlCommandError`` on anything
  malformed or unknown so a bad line can be logged and ignored rather than
  crashing the server.

A process-wide ``get_control_state()`` singleton gives the listener and the
playback loops a shared instance to talk through without threading a reference
down every call signature.
"""

import json
import logging
import threading
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("voicemode.control_channel")


# --- Control states -------------------------------------------------------

# The three states a ControlState can be in. Plain strings (not an Enum) to
# match the rest of the codebase, and so a snapshot is trivially loggable.
STATE_RUNNING = "running"   # nothing requested -- normal playback
STATE_PAUSED = "paused"     # hold playback until resume or stop
STATE_STOPPED = "stopped"   # break playback; terminal until reset()

VALID_STATES = (STATE_RUNNING, STATE_PAUSED, STATE_STOPPED)


# --- Command schema -------------------------------------------------------

COMMAND_PAUSE = "pause"
COMMAND_RESUME = "resume"
COMMAND_STOP = "stop"

# The commands a control client may send over the channel. ``volume`` is a
# documented stretch goal (VM-1676) -- intentionally NOT accepted in v1 so an
# unimplemented command fails validation loudly rather than being silently
# dropped on the floor.
VALID_COMMANDS = (COMMAND_PAUSE, COMMAND_RESUME, COMMAND_STOP)


class ControlCommandError(ValueError):
    """Raised when a control-channel line is malformed or carries an unknown command.

    Subclasses ``ValueError`` so existing ``except ValueError`` handlers catch
    it too. The socket listener catches this, logs it, and keeps serving -- a
    bad line must never crash the server.
    """


@dataclass(frozen=True)
class ControlCommand:
    """One parsed, validated control-channel command.

    ``message`` and ``hint`` are only meaningful for ``stop`` today (they feed
    the normal ``converse`` return string -- e.g. hint ``switch-to-text``), but
    the schema accepts them on any command for forward compatibility.
    """

    command: str
    message: Optional[str] = None
    hint: Optional[str] = None

    def apply_to(self, state: "ControlState") -> None:
        """Drive ``state`` according to this command.

        A thin dispatcher so a listener can do
        ``parse_command(line).apply_to(state)`` instead of re-implementing the
        command -> method mapping.
        """
        if self.command == COMMAND_PAUSE:
            state.request_pause()
        elif self.command == COMMAND_RESUME:
            state.request_resume()
        elif self.command == COMMAND_STOP:
            state.request_stop(message=self.message, hint=self.hint)
        else:  # pragma: no cover -- parse_command guarantees a valid command
            raise ControlCommandError(f"unhandled command: {self.command!r}")


def parse_command(line: str) -> ControlCommand:
    """Parse one newline-delimited JSON control line into a ``ControlCommand``.

    Schema: ``{"command": "pause"|"resume"|"stop", "message"?: str, "hint"?: str}``.
    Surrounding whitespace (including the trailing newline) is tolerated.

    Raises ``ControlCommandError`` on anything that isn't a JSON object with a
    known ``command`` and (optionally) string ``message`` / ``hint`` fields.
    """
    if line is None:
        raise ControlCommandError("empty control line")
    text = line.strip()
    if not text:
        raise ControlCommandError("empty control line")

    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ControlCommandError(f"invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ControlCommandError(
            f"command must be a JSON object, got {type(payload).__name__}"
        )

    command = payload.get("command")
    if not isinstance(command, str):
        raise ControlCommandError("missing or non-string 'command' field")
    if command not in VALID_COMMANDS:
        raise ControlCommandError(
            f"unknown command: {command!r} "
            f"(expected one of {', '.join(VALID_COMMANDS)})"
        )

    message = payload.get("message")
    if message is not None and not isinstance(message, str):
        raise ControlCommandError("'message' must be a string if present")

    hint = payload.get("hint")
    if hint is not None and not isinstance(hint, str):
        raise ControlCommandError("'hint' must be a string if present")

    return ControlCommand(command=command, message=message, hint=hint)


@dataclass(frozen=True)
class ControlSnapshot:
    """An immutable point-in-time view of a ``ControlState``.

    Returned by ``ControlState.snapshot()`` so the polling coroutine reads a
    consistent ``(state, message, hint)`` triple without holding the lock.
    """

    state: str
    message: Optional[str] = None
    hint: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self.state == STATE_RUNNING

    @property
    def is_paused(self) -> bool:
        return self.state == STATE_PAUSED

    @property
    def is_stopped(self) -> bool:
        return self.state == STATE_STOPPED


class ControlState:
    """Thread-safe pause / resume / stop state for a single TTS utterance.

    One side (a listener thread) calls ``request_pause`` / ``request_resume`` /
    ``request_stop``; the other side (the playback coroutine) calls ``snapshot``
    each chunk and ``wait_while_paused`` to hold without busy-spinning.
    ``reset`` clears everything back to *running* between utterances.

    State machine::

        running  --pause-->  paused  --resume-->  running
        running/paused  --stop-->  stopped   (terminal until reset)
        any  --reset-->  running

    ``stop`` is sticky: once stopped, ``pause`` / ``resume`` are ignored so a
    late command can't revive a cancelled utterance, and a second ``stop`` won't
    overwrite the latched ``message`` / ``hint`` (first stop wins). ``reset`` is
    the only way back to *running*.
    """

    def __init__(self) -> None:
        # A Condition wraps a Lock and lets the playback side block until a
        # state change instead of polling in a tight loop.
        self._cond = threading.Condition()
        self._state = STATE_RUNNING
        self._message: Optional[str] = None
        self._hint: Optional[str] = None

    # --- mutations (listener side) ---------------------------------------

    def request_pause(self) -> bool:
        """Request a pause. Returns False (no-op) if already stopped."""
        with self._cond:
            if self._state == STATE_STOPPED:
                logger.debug("pause ignored -- already stopped")
                return False
            self._state = STATE_PAUSED
            self._cond.notify_all()
            return True

    def request_resume(self) -> bool:
        """Resume from a pause. Returns False (no-op) if already stopped."""
        with self._cond:
            if self._state == STATE_STOPPED:
                logger.debug("resume ignored -- already stopped")
                return False
            self._state = STATE_RUNNING
            self._cond.notify_all()
            return True

    def request_stop(
        self, message: Optional[str] = None, hint: Optional[str] = None
    ) -> bool:
        """Request a stop, latching an optional ``message`` and ``hint``.

        Sticky: the first stop wins -- a later stop won't overwrite the latched
        ``message`` / ``hint``. Always wakes any paused waiter. Returns True.
        """
        with self._cond:
            if self._state != STATE_STOPPED:
                self._state = STATE_STOPPED
                self._message = message
                self._hint = hint
            else:
                logger.debug("stop ignored -- already stopped (keeping first message/hint)")
            self._cond.notify_all()
            return True

    def reset(self) -> None:
        """Clear back to *running* and drop any latched message / hint.

        Called at the start of each utterance so stale state from a previous
        utterance never leaks in.
        """
        with self._cond:
            self._state = STATE_RUNNING
            self._message = None
            self._hint = None
            self._cond.notify_all()

    # --- reads (playback side) -------------------------------------------

    @property
    def state(self) -> str:
        """The current state string. Prefer ``snapshot()`` when you also need message/hint."""
        with self._cond:
            return self._state

    def snapshot(self) -> ControlSnapshot:
        """Return a consistent ``(state, message, hint)`` view. Cheap; poll per chunk."""
        with self._cond:
            return ControlSnapshot(self._state, self._message, self._hint)

    def wait_while_paused(self, timeout: Optional[float] = None) -> ControlSnapshot:
        """Block while paused, returning as soon as resumed or stopped.

        Never busy-spins: it blocks on the Condition until a state change wakes
        it. With ``timeout`` set, returns after at most ``timeout`` seconds even
        if still paused, so the caller can keep a heartbeat and re-check. If not
        currently paused, returns immediately. Returns a snapshot taken after
        waking.
        """
        with self._cond:
            if self._state == STATE_PAUSED:
                self._cond.wait_for(
                    lambda: self._state != STATE_PAUSED, timeout=timeout
                )
            return ControlSnapshot(self._state, self._message, self._hint)


# --- Process-wide singleton ----------------------------------------------

_default_state: Optional[ControlState] = None
_default_lock = threading.Lock()


def get_control_state() -> ControlState:
    """Return the process-wide ``ControlState`` shared by the listener and playback.

    The socket listener and the streaming playback loops live in different
    parts of the codebase and don't share an object reference, so they reach the
    same state through this singleton. Created lazily and thread-safely.
    """
    global _default_state
    if _default_state is None:
        with _default_lock:
            if _default_state is None:
                _default_state = ControlState()
    return _default_state
