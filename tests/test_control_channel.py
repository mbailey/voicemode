"""Unit tests for voice_mode.control_channel (VM-1676, foundation feature).

Pure logic -- no sockets, no audio. Covers:

* every ControlState transition (idle -> pause -> resume -> stop, reset)
* message / hint propagation and stickiness
* thread-safe wait_while_paused (no busy-spin) under real threads
* the newline-JSON command schema: parse/validate of good and malformed input
* ControlCommand dispatch (apply_to) and the process-wide singleton
"""

import json
import threading

import pytest

from voice_mode.control_channel import (
    COMMAND_PAUSE,
    COMMAND_RESUME,
    COMMAND_SKIP_BACK,
    COMMAND_SKIP_FORWARD,
    COMMAND_STOP,
    STATE_PAUSED,
    STATE_RUNNING,
    STATE_SKIP_FORWARD,
    STATE_STOPPED,
    VALID_COMMANDS,
    ControlCommand,
    ControlCommandError,
    ControlSnapshot,
    ControlState,
    get_control_state,
    parse_command,
)


# --------------------------------------------------------------------------
# ControlState transitions
# --------------------------------------------------------------------------


class TestControlStateTransitions:
    """idle -> pause -> resume -> stop, plus reset."""

    def test_initial_state_is_running(self):
        state = ControlState()
        snap = state.snapshot()
        assert snap.state == STATE_RUNNING
        assert snap.is_running and not snap.is_paused and not snap.is_stopped
        assert snap.message is None and snap.hint is None
        assert state.state == STATE_RUNNING

    def test_pause_then_resume(self):
        state = ControlState()

        assert state.request_pause() is True
        assert state.snapshot().state == STATE_PAUSED
        assert state.snapshot().is_paused

        assert state.request_resume() is True
        assert state.snapshot().state == STATE_RUNNING
        assert state.snapshot().is_running

    def test_full_idle_pause_resume_stop_cycle(self):
        state = ControlState()
        assert state.snapshot().state == STATE_RUNNING
        state.request_pause()
        assert state.snapshot().state == STATE_PAUSED
        state.request_resume()
        assert state.snapshot().state == STATE_RUNNING
        state.request_stop()
        assert state.snapshot().state == STATE_STOPPED

    def test_stop_from_running(self):
        state = ControlState()
        assert state.request_stop() is True
        assert state.snapshot().is_stopped

    def test_stop_from_paused(self):
        state = ControlState()
        state.request_pause()
        state.request_stop()
        assert state.snapshot().state == STATE_STOPPED

    def test_reset_clears_back_to_running(self):
        state = ControlState()
        state.request_stop(message="bye", hint="switch-to-text")
        assert state.snapshot().is_stopped

        state.reset()
        snap = state.snapshot()
        assert snap.state == STATE_RUNNING
        assert snap.message is None
        assert snap.hint is None

    def test_reset_from_paused(self):
        state = ControlState()
        state.request_pause()
        state.reset()
        assert state.snapshot().state == STATE_RUNNING


class TestStopStickiness:
    """stop is terminal until reset; first stop's message/hint wins."""

    def test_pause_ignored_after_stop(self):
        state = ControlState()
        state.request_stop()
        assert state.request_pause() is False
        assert state.snapshot().state == STATE_STOPPED

    def test_resume_ignored_after_stop(self):
        state = ControlState()
        state.request_stop()
        assert state.request_resume() is False
        assert state.snapshot().state == STATE_STOPPED

    def test_message_and_hint_propagate_on_stop(self):
        state = ControlState()
        state.request_stop(message="user can't talk right now", hint="switch-to-text")
        snap = state.snapshot()
        assert snap.message == "user can't talk right now"
        assert snap.hint == "switch-to-text"

    def test_second_stop_does_not_overwrite_message_hint(self):
        state = ControlState()
        state.request_stop(message="first", hint="switch-to-text")
        state.request_stop(message="second", hint="something-else")
        snap = state.snapshot()
        assert snap.message == "first"
        assert snap.hint == "switch-to-text"

    def test_stop_without_message_leaves_none(self):
        state = ControlState()
        state.request_stop()
        snap = state.snapshot()
        assert snap.message is None and snap.hint is None

    def test_reset_allows_running_again_after_stop(self):
        state = ControlState()
        state.request_stop()
        state.reset()
        # pause now works again because reset cleared the terminal state
        assert state.request_pause() is True
        assert state.snapshot().state == STATE_PAUSED


# --------------------------------------------------------------------------
# wait_while_paused -- no busy-spin, wakes on resume/stop
# --------------------------------------------------------------------------


class TestWaitWhilePaused:
    def test_returns_immediately_when_running(self):
        state = ControlState()
        snap = state.wait_while_paused(timeout=5.0)
        assert snap.state == STATE_RUNNING

    def test_returns_immediately_when_stopped(self):
        state = ControlState()
        state.request_stop()
        snap = state.wait_while_paused(timeout=5.0)
        assert snap.state == STATE_STOPPED

    def test_timeout_returns_paused_snapshot_when_still_paused(self):
        state = ControlState()
        state.request_pause()
        snap = state.wait_while_paused(timeout=0.05)
        assert snap.state == STATE_PAUSED

    def test_wakes_on_resume(self):
        state = ControlState()
        state.request_pause()
        result = {}

        def waiter():
            result["snap"] = state.wait_while_paused(timeout=5.0)

        t = threading.Thread(target=waiter)
        t.start()
        # Resume from this thread; the waiter must wake and return running.
        state.request_resume()
        t.join(timeout=5.0)
        assert not t.is_alive(), "waiter did not wake on resume"
        assert result["snap"].state == STATE_RUNNING

    def test_wakes_on_stop(self):
        state = ControlState()
        state.request_pause()
        result = {}

        def waiter():
            result["snap"] = state.wait_while_paused(timeout=5.0)

        t = threading.Thread(target=waiter)
        t.start()
        state.request_stop(message="cut", hint="switch-to-text")
        t.join(timeout=5.0)
        assert not t.is_alive(), "waiter did not wake on stop"
        snap = result["snap"]
        assert snap.state == STATE_STOPPED
        assert snap.message == "cut"
        assert snap.hint == "switch-to-text"


class TestThreadSafety:
    """Listener thread mutating while a poller reads must never corrupt state."""

    def test_concurrent_mutation_and_polling_is_consistent(self):
        state = ControlState()
        seen_states = []
        stop_flag = threading.Event()

        def poller():
            while not stop_flag.is_set():
                snap = state.snapshot()
                seen_states.append(snap.state)

        def mutator():
            for _ in range(500):
                state.request_pause()
                state.request_resume()
            state.request_stop(message="done")

        p = threading.Thread(target=poller)
        m = threading.Thread(target=mutator)
        p.start()
        m.start()
        m.join(timeout=10.0)
        stop_flag.set()
        p.join(timeout=10.0)

        # Every observed state must be a valid one -- no torn reads.
        assert set(seen_states) <= {STATE_RUNNING, STATE_PAUSED, STATE_STOPPED}
        # The mutator's final stop must stick.
        assert state.snapshot().state == STATE_STOPPED
        assert state.snapshot().message == "done"


# --------------------------------------------------------------------------
# Command schema -- parse / validate
# --------------------------------------------------------------------------


class TestParseCommandGood:
    @pytest.mark.parametrize(
        "command", [COMMAND_PAUSE, COMMAND_RESUME, COMMAND_STOP, COMMAND_SKIP_BACK]
    )
    def test_each_valid_command(self, command):
        cmd = parse_command(json.dumps({"command": command}))
        assert cmd.command == command
        assert cmd.message is None
        assert cmd.hint is None

    def test_stop_with_message_and_hint(self):
        line = json.dumps(
            {"command": "stop", "message": "text mode please", "hint": "switch-to-text"}
        )
        cmd = parse_command(line)
        assert cmd.command == COMMAND_STOP
        assert cmd.message == "text mode please"
        assert cmd.hint == "switch-to-text"

    def test_trailing_newline_and_whitespace_tolerated(self):
        cmd = parse_command('  {"command": "pause"}  \n')
        assert cmd.command == COMMAND_PAUSE

    def test_returns_frozen_dataclass(self):
        cmd = parse_command('{"command": "pause"}')
        assert isinstance(cmd, ControlCommand)
        with pytest.raises((AttributeError, Exception)):
            cmd.command = "stop"  # frozen


class TestParseCommandMalformed:
    @pytest.mark.parametrize("bad", ["", "   ", "\n", "\t  \n"])
    def test_empty_or_blank_line(self, bad):
        with pytest.raises(ControlCommandError):
            parse_command(bad)

    def test_none_line(self):
        with pytest.raises(ControlCommandError):
            parse_command(None)

    @pytest.mark.parametrize("bad", ["{not json", "{'command': 'pause'}", "pause", "{"])
    def test_invalid_json(self, bad):
        with pytest.raises(ControlCommandError):
            parse_command(bad)

    @pytest.mark.parametrize("bad", ["[]", "42", '"pause"', "true", "null"])
    def test_non_object_json(self, bad):
        with pytest.raises(ControlCommandError):
            parse_command(bad)

    def test_missing_command_field(self):
        with pytest.raises(ControlCommandError):
            parse_command(json.dumps({"message": "hi"}))

    def test_non_string_command(self):
        with pytest.raises(ControlCommandError):
            parse_command(json.dumps({"command": 5}))

    def test_unknown_command(self):
        with pytest.raises(ControlCommandError) as exc:
            parse_command(json.dumps({"command": "explode"}))
        assert "unknown command" in str(exc.value)

    def test_volume_rejected_in_v1(self):
        # volume is a documented stretch goal -- must NOT validate yet.
        assert "volume" not in VALID_COMMANDS
        with pytest.raises(ControlCommandError):
            parse_command(json.dumps({"command": "volume", "level": 50}))

    def test_non_string_message(self):
        with pytest.raises(ControlCommandError):
            parse_command(json.dumps({"command": "stop", "message": 123}))

    def test_non_string_hint(self):
        with pytest.raises(ControlCommandError):
            parse_command(json.dumps({"command": "stop", "hint": ["x"]}))

    def test_error_is_a_valueerror(self):
        # Subclassing ValueError lets `except ValueError` handlers catch it.
        assert issubclass(ControlCommandError, ValueError)


# --------------------------------------------------------------------------
# ControlCommand.apply_to -- dispatch to ControlState
# --------------------------------------------------------------------------


class TestApplyTo:
    def test_pause_command_pauses(self):
        state = ControlState()
        parse_command('{"command": "pause"}').apply_to(state)
        assert state.snapshot().state == STATE_PAUSED

    def test_resume_command_resumes(self):
        state = ControlState()
        state.request_pause()
        parse_command('{"command": "resume"}').apply_to(state)
        assert state.snapshot().state == STATE_RUNNING

    def test_stop_command_stops_with_message_and_hint(self):
        state = ControlState()
        line = json.dumps(
            {"command": "stop", "message": "bye", "hint": "switch-to-text"}
        )
        parse_command(line).apply_to(state)
        snap = state.snapshot()
        assert snap.state == STATE_STOPPED
        assert snap.message == "bye"
        assert snap.hint == "switch-to-text"

    def test_parse_then_apply_round_trip_for_all_commands(self):
        for command in VALID_COMMANDS:
            state = ControlState()
            parse_command(json.dumps({"command": command})).apply_to(state)
            expected = {
                COMMAND_PAUSE: STATE_PAUSED,
                COMMAND_RESUME: STATE_RUNNING,  # resume from running is a no-op -> running
                COMMAND_STOP: STATE_STOPPED,
                # skip_back is a transport request -- it sets the pending slot,
                # not the play/hold/cut state, so the state stays running.
                COMMAND_SKIP_BACK: STATE_RUNNING,
                COMMAND_SKIP_FORWARD: STATE_SKIP_FORWARD,
            }[command]
            assert state.snapshot().state == expected

    def test_skip_back_command_sets_transport_request(self):
        state = ControlState()
        parse_command('{"command": "skip_back"}').apply_to(state)
        # The play/hold/cut state is untouched; the transport slot carries it.
        assert state.snapshot().state == STATE_RUNNING
        assert state.snapshot().pending_transport == COMMAND_SKIP_BACK


# --------------------------------------------------------------------------
# Transport requests -- skip_back (VM-1685)
# --------------------------------------------------------------------------


class TestTransportRequest:
    """The non-sticky transport-request slot: set / peek / read-and-clear,
    and its independence from the sticky stop latch."""

    def test_initial_pending_transport_is_none(self):
        state = ControlState()
        assert state.pending_transport is None
        assert state.snapshot().pending_transport is None
        assert state.take_transport_request() is None

    def test_request_skip_back_records_and_returns_true(self):
        state = ControlState()
        assert state.request_skip_back() is True
        assert state.pending_transport == COMMAND_SKIP_BACK
        assert state.snapshot().pending_transport == COMMAND_SKIP_BACK

    def test_take_transport_request_reads_and_clears(self):
        state = ControlState()
        state.request_skip_back()
        # First take returns the request...
        assert state.take_transport_request() == COMMAND_SKIP_BACK
        # ...and clears it, so a single press is acted on exactly once.
        assert state.pending_transport is None
        assert state.take_transport_request() is None

    def test_snapshot_peek_is_non_destructive(self):
        state = ControlState()
        state.request_skip_back()
        # snapshot() peeks without consuming -- repeatable.
        assert state.snapshot().pending_transport == COMMAND_SKIP_BACK
        assert state.snapshot().pending_transport == COMMAND_SKIP_BACK
        # take_transport_request is the one that consumes it.
        assert state.take_transport_request() == COMMAND_SKIP_BACK
        assert state.snapshot().pending_transport is None

    def test_repeated_presses_coalesce(self):
        state = ControlState()
        state.request_skip_back()
        state.request_skip_back()
        assert state.take_transport_request() == COMMAND_SKIP_BACK
        # Only one pending request survived; the next take is empty.
        assert state.take_transport_request() is None

    def test_transport_request_does_not_change_play_state(self):
        state = ControlState()
        state.request_skip_back()
        assert state.snapshot().state == STATE_RUNNING
        assert state.snapshot().is_running

    def test_skip_back_composes_with_pause(self):
        # pause then skip_back: the request is recorded and the paused state is
        # left intact (the replay layer re-plays without un-pausing).
        state = ControlState()
        state.request_pause()
        state.request_skip_back()
        snap = state.snapshot()
        assert snap.state == STATE_PAUSED
        assert snap.pending_transport == COMMAND_SKIP_BACK

    def test_independent_from_stop_stickiness(self):
        # Unlike pause/resume (swallowed once stopped), a transport request is on
        # a separate slot: it still records after a stop, and it neither revives
        # nor clears the sticky stop latch.
        state = ControlState()
        state.request_stop(message="cut", hint="switch-to-text")
        assert state.request_skip_back() is True
        snap = state.snapshot()
        assert snap.state == STATE_STOPPED  # stop latch untouched
        assert snap.message == "cut" and snap.hint == "switch-to-text"
        assert snap.pending_transport == COMMAND_SKIP_BACK
        # And pause/resume remain ignored after stop (bit-for-bit unchanged).
        assert state.request_pause() is False
        assert state.request_resume() is False
        assert state.snapshot().state == STATE_STOPPED

    def test_stop_does_not_clear_pending_transport(self):
        state = ControlState()
        state.request_skip_back()
        state.request_stop()
        assert state.snapshot().pending_transport == COMMAND_SKIP_BACK

    def test_reset_clears_pending_transport(self):
        state = ControlState()
        state.request_skip_back()
        state.reset()
        snap = state.snapshot()
        assert snap.state == STATE_RUNNING
        assert snap.pending_transport is None
        assert state.take_transport_request() is None


# --------------------------------------------------------------------------
# Snapshot helpers and the process-wide singleton
# --------------------------------------------------------------------------


class TestSnapshotAndSingleton:
    def test_snapshot_is_immutable(self):
        snap = ControlSnapshot(STATE_PAUSED, "m", "h")
        with pytest.raises((AttributeError, Exception)):
            snap.state = STATE_RUNNING

    def test_snapshot_properties(self):
        assert ControlSnapshot(STATE_RUNNING).is_running
        assert ControlSnapshot(STATE_PAUSED).is_paused
        assert ControlSnapshot(STATE_STOPPED).is_stopped

    def test_snapshot_pending_transport_defaults_none(self):
        # Backward compatible: existing 1-3 arg constructions still work and the
        # new field defaults to None.
        assert ControlSnapshot(STATE_RUNNING).pending_transport is None
        assert ControlSnapshot(STATE_PAUSED, "m", "h").pending_transport is None
        assert (
            ControlSnapshot(STATE_RUNNING, None, None, "skip_back").pending_transport
            == "skip_back"
        )

    def test_get_control_state_returns_singleton(self):
        a = get_control_state()
        b = get_control_state()
        assert a is b
        assert isinstance(a, ControlState)


# --------------------------------------------------------------------------
# skip_forward -- the VM-1739 transport barge-in (4th state, sticky like stop)
# --------------------------------------------------------------------------


class TestSkipForwardState:
    """request_skip_forward latches STATE_SKIP_FORWARD; snapshot surfaces it."""

    def test_skip_forward_from_running(self):
        state = ControlState()
        assert state.request_skip_forward() is True
        snap = state.snapshot()
        assert snap.state == STATE_SKIP_FORWARD
        assert snap.is_skip_forward
        assert not snap.is_stopped and not snap.is_paused and not snap.is_running

    def test_skip_forward_from_paused(self):
        state = ControlState()
        state.request_pause()
        assert state.request_skip_forward() is True
        assert state.snapshot().is_skip_forward

    def test_reset_clears_skip_forward(self):
        state = ControlState()
        state.request_skip_forward()
        state.reset()
        snap = state.snapshot()
        assert snap.state == STATE_RUNNING
        assert not snap.is_skip_forward

    def test_snapshot_property_independent_of_other_states(self):
        assert ControlSnapshot(STATE_SKIP_FORWARD).is_skip_forward
        assert not ControlSnapshot(STATE_STOPPED).is_skip_forward
        assert not ControlSnapshot(STATE_RUNNING).is_skip_forward


class TestSkipForwardStickiness:
    """skip_forward is sticky; pause/resume are no-ops; a racing stop dominates."""

    def test_pause_ignored_after_skip_forward(self):
        state = ControlState()
        state.request_skip_forward()
        assert state.request_pause() is False
        assert state.snapshot().is_skip_forward

    def test_resume_ignored_after_skip_forward(self):
        state = ControlState()
        state.request_skip_forward()
        assert state.request_resume() is False
        assert state.snapshot().is_skip_forward

    def test_stop_overrides_skip_forward(self):
        # stop is the harder terminal -- a racing stop after skip_forward wins.
        state = ControlState()
        state.request_skip_forward()
        assert state.request_stop(hint="switch-to-text") is True
        snap = state.snapshot()
        assert snap.state == STATE_STOPPED
        assert snap.hint == "switch-to-text"

    def test_skip_forward_ignored_after_stop(self):
        # The reverse: once stopped, a later skip_forward is a no-op (stop wins).
        state = ControlState()
        state.request_stop()
        assert state.request_skip_forward() is False
        assert state.snapshot().is_stopped

    def test_skip_forward_is_idempotent(self):
        state = ControlState()
        assert state.request_skip_forward() is True
        assert state.request_skip_forward() is True
        assert state.snapshot().is_skip_forward

    def test_reset_allows_running_again_after_skip_forward(self):
        state = ControlState()
        state.request_skip_forward()
        state.reset()
        # pause works again because reset cleared the transport terminal.
        assert state.request_pause() is True
        assert state.snapshot().state == STATE_PAUSED


class TestSkipForwardSchema:
    """parse_command accepts skip_forward; apply_to dispatches to request_skip_forward."""

    def test_skip_forward_in_valid_commands(self):
        assert COMMAND_SKIP_FORWARD == "skip_forward"
        assert COMMAND_SKIP_FORWARD in VALID_COMMANDS

    def test_parse_skip_forward(self):
        cmd = parse_command(json.dumps({"command": "skip_forward"}))
        assert cmd.command == COMMAND_SKIP_FORWARD
        assert cmd.message is None and cmd.hint is None

    def test_apply_skip_forward_latches_state(self):
        state = ControlState()
        parse_command('{"command": "skip_forward"}').apply_to(state)
        assert state.snapshot().is_skip_forward

    def test_wait_while_paused_wakes_on_skip_forward(self):
        # A paused playback waiter must wake (and abort) when skip_forward fires.
        state = ControlState()
        state.request_pause()
        result = {}

        def waiter():
            result["snap"] = state.wait_while_paused(timeout=5.0)

        t = threading.Thread(target=waiter)
        t.start()
        state.request_skip_forward()
        t.join(timeout=5.0)
        assert not t.is_alive(), "waiter did not wake on skip_forward"
        assert result["snap"].is_skip_forward
