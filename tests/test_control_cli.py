"""Tests for the control-channel client + `voicemode control` CLI (VM-1676).

These cover the *client* end of the control channel -- the "second local
process" that drives an in-flight utterance (success criterion 2):

* :func:`voice_mode.control_socket.send_control_command` -- builds + validates a
  JSON command line and writes it to the socket; bad commands fail fast.
* the `voicemode control {pause|resume|stop}` Click CLI -- invoked against a real
  temp socket + listener, the command lands in ``ControlState``; with no listener
  it exits non-zero with a friendly message rather than hanging.

A real ``ControlSocketListener`` (from the socket-listener feature) is bound to a
short temp socket; we assert the listener's ``ControlState`` reflects each
command. No audio, no MCP.

Socket paths are kept SHORT on purpose (AF_UNIX ~104-char limit; pytest's
tmp_path is often too long), matching tests/test_control_socket.py.
"""

import shutil
import socket
import tempfile
import time
from pathlib import Path

import pytest
from click.testing import CliRunner

from voice_mode.cli import voice_mode_main_cli
from voice_mode.control_channel import (
    STATE_PAUSED,
    STATE_RUNNING,
    STATE_SKIP_FORWARD,
    STATE_STOPPED,
    ControlCommandError,
    ControlState,
)
from voice_mode.control_socket import ControlSocketListener, send_control_command


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------


@pytest.fixture
def socket_path():
    """A short-enough Unix socket path (avoids the AF_UNIX path-length limit)."""
    d = tempfile.mkdtemp(prefix="vmctl")
    path = Path(d) / "c.sock"
    assert len(str(path)) < 100, f"socket path too long for AF_UNIX: {path}"
    yield path
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def listener(socket_path):
    """A started listener with its own ControlState, torn down after the test."""
    state = ControlState()
    lis = ControlSocketListener(socket_path=socket_path, control_state=state)
    lis.start()
    lis.test_state = state  # type: ignore[attr-defined]
    yield lis
    lis.stop()


def wait_for(predicate, timeout=2.0, interval=0.01):
    """Poll ``predicate`` until true or timeout. Returns its final truthiness."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def run_control(*args):
    """Invoke `voicemode control ...` in-process via Click's CliRunner."""
    runner = CliRunner()
    return runner.invoke(voice_mode_main_cli, ["control", *args])


# --------------------------------------------------------------------------
# send_control_command (the reusable client)
# --------------------------------------------------------------------------


class TestSendControlCommand:
    def test_pause(self, listener):
        send_control_command("pause", socket_path=listener.socket_path)
        assert wait_for(lambda: listener.test_state.snapshot().state == STATE_PAUSED)

    def test_resume(self, listener):
        listener.test_state.request_pause()
        send_control_command("resume", socket_path=listener.socket_path)
        assert wait_for(lambda: listener.test_state.snapshot().state == STATE_RUNNING)

    def test_stop(self, listener):
        send_control_command("stop", socket_path=listener.socket_path)
        assert wait_for(lambda: listener.test_state.snapshot().is_stopped)

    def test_skip_forward(self, listener):
        # VM-1739: skip_forward latches the transport-barge-in state on the listener.
        send_control_command("skip_forward", socket_path=listener.socket_path)
        assert wait_for(lambda: listener.test_state.snapshot().is_skip_forward)
        assert listener.test_state.snapshot().state == STATE_SKIP_FORWARD

    def test_stop_with_message_and_hint(self, listener):
        send_control_command(
            "stop",
            message="user can't talk right now",
            hint="switch-to-text",
            socket_path=listener.socket_path,
        )
        assert wait_for(lambda: listener.test_state.snapshot().is_stopped)
        snap = listener.test_state.snapshot()
        assert snap.message == "user can't talk right now"
        assert snap.hint == "switch-to-text"

    def test_unknown_command_fails_fast_before_connecting(self, socket_path):
        # volume is a documented stretch goal -- rejected in v1. The client
        # validates against the listener's own schema BEFORE opening a socket,
        # so this raises even though nothing is listening at socket_path.
        assert not socket_path.exists()
        with pytest.raises(ControlCommandError):
            send_control_command("volume", socket_path=socket_path)

    def test_no_listener_raises_filenotfound(self, socket_path):
        # A valid command with nothing listening surfaces the socket error.
        assert not socket_path.exists()
        with pytest.raises(FileNotFoundError):
            send_control_command("stop", socket_path=socket_path)


# --------------------------------------------------------------------------
# `voicemode control` CLI
# --------------------------------------------------------------------------


class TestControlCLI:
    def test_pause(self, listener):
        result = run_control("pause", "--socket", str(listener.socket_path))
        assert result.exit_code == 0, result.output
        assert "Sent 'pause'" in result.output
        assert wait_for(lambda: listener.test_state.snapshot().state == STATE_PAUSED)

    def test_resume(self, listener):
        listener.test_state.request_pause()
        result = run_control("resume", "--socket", str(listener.socket_path))
        assert result.exit_code == 0, result.output
        assert wait_for(lambda: listener.test_state.snapshot().state == STATE_RUNNING)

    def test_stop(self, listener):
        result = run_control("stop", "--socket", str(listener.socket_path))
        assert result.exit_code == 0, result.output
        assert wait_for(lambda: listener.test_state.snapshot().is_stopped)

    def test_skip_forward(self, listener):
        # The hyphenated subcommand maps to the underscored wire command.
        result = run_control("skip-forward", "--socket", str(listener.socket_path))
        assert result.exit_code == 0, result.output
        assert "Sent 'skip_forward'" in result.output
        assert wait_for(lambda: listener.test_state.snapshot().is_skip_forward)

    def test_stop_with_message_and_hint(self, listener):
        result = run_control(
            "stop",
            "--hint", "switch-to-text",
            "-m", "user can't talk right now",
            "--socket", str(listener.socket_path),
        )
        assert result.exit_code == 0, result.output
        assert wait_for(lambda: listener.test_state.snapshot().is_stopped)
        snap = listener.test_state.snapshot()
        assert snap.message == "user can't talk right now"
        assert snap.hint == "switch-to-text"

    def test_invalid_command_is_usage_error(self, listener):
        # Click constrains the subcommand set: an unknown verb is a usage error
        # (exit 2), and never touches the socket.
        result = run_control("volume", "--socket", str(listener.socket_path))
        assert result.exit_code == 2
        assert listener.test_state.snapshot().state == STATE_RUNNING

    def test_no_listener_exits_nonzero_with_message(self, socket_path):
        # Nothing bound at socket_path -> the CLI reports it cleanly instead of
        # hanging or dumping a traceback.
        assert not socket_path.exists()
        result = run_control("stop", "--socket", str(socket_path))
        assert result.exit_code == 1
        assert "No control socket" in result.output

    def test_stale_socket_exits_nonzero_with_message(self, socket_path):
        # Simulate a crashed server: a socket file exists but no one is
        # accepting -> connect() raises ConnectionRefusedError, which the CLI
        # turns into a clean non-zero exit rather than a traceback.
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(socket_path))
        stale.close()  # leave the file behind, nothing listening
        assert socket_path.exists()
        result = run_control("stop", "--socket", str(socket_path))
        assert result.exit_code == 1
        assert "no server is accepting" in result.output

    def test_help_lists_subcommands(self):
        result = run_control("--help")
        assert result.exit_code == 0
        for verb in ("pause", "resume", "stop", "skip-forward"):
            assert verb in result.output
