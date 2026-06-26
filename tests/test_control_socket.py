"""Integration tests for voice_mode.control_socket (VM-1676, socket-listener feature).

These exercise the real Unix-domain-socket listener with a real client socket --
no audio, no MCP. Coverage:

* bind/teardown lifecycle: start binds the socket, stop closes + unlinks it
* command dispatch: pause / resume / stop (+ message / hint) over the wire land
  in ControlState; multiple newline-delimited commands in one connection
* robustness: malformed JSON / unknown commands / non-UTF-8 are ignored without
  killing the listener (a subsequent good command still lands)
* stale-socket recovery: a leftover socket file is unlink-then-bind'd over
* the config-gated module seam: start_control_listener honours
  VOICEMODE_CONTROL_CHANNEL_ENABLED

Socket paths are kept SHORT on purpose: AF_UNIX paths have a ~104-char limit on
macOS, and pytest's tmp_path is often too long, so we mint our own short tempdir.
"""

import json
import socket
import tempfile
import time
from pathlib import Path

import pytest

from voice_mode import control_socket
from voice_mode.control_channel import (
    STATE_PAUSED,
    STATE_RUNNING,
    STATE_STOPPED,
    ControlState,
)
from voice_mode.control_socket import ControlSocketListener


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------


@pytest.fixture
def socket_path(tmp_path_factory):
    """A short-enough Unix socket path (avoids the AF_UNIX path-length limit).

    Uses a fresh system tempdir with a tiny filename rather than pytest's long
    tmp_path. The dir is cleaned up afterwards.
    """
    import shutil

    d = tempfile.mkdtemp(prefix="vmctl")
    path = Path(d) / "c.sock"
    # Guard: if the platform tempdir is pathologically long, fail loudly rather
    # than producing a confusing "AF_UNIX path too long".
    assert len(str(path)) < 100, f"socket path too long for AF_UNIX: {path}"
    yield path
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def listener(socket_path):
    """A started listener with its own ControlState, torn down after the test."""
    state = ControlState()
    lis = ControlSocketListener(socket_path=socket_path, control_state=state)
    lis.start()
    # Expose the state on the listener object for convenience in tests.
    lis.test_state = state  # type: ignore[attr-defined]
    yield lis
    lis.stop()


def send_lines(path, *payloads, raw=None):
    """Connect, send each payload as a JSON line, then close the connection.

    ``payloads`` are dicts serialised to JSON + newline. ``raw`` (bytes) is sent
    verbatim instead, for malformed-input tests.
    """
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
        c.settimeout(2.0)
        c.connect(str(path))
        if raw is not None:
            c.sendall(raw)
        for payload in payloads:
            c.sendall((json.dumps(payload) + "\n").encode())


def wait_for(predicate, timeout=2.0, interval=0.01):
    """Poll ``predicate`` until true or timeout. Returns its final truthiness."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# --------------------------------------------------------------------------
# Lifecycle: bind / teardown
# --------------------------------------------------------------------------


class TestLifecycle:
    def test_start_binds_socket_and_is_running(self, socket_path):
        lis = ControlSocketListener(socket_path=socket_path, control_state=ControlState())
        assert not lis.is_running
        assert not socket_path.exists()
        try:
            lis.start()
            assert lis.is_running
            assert socket_path.exists()
            # A client can connect immediately after start() returns.
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
                c.settimeout(2.0)
                c.connect(str(socket_path))
        finally:
            lis.stop()

    def test_stop_closes_and_unlinks(self, socket_path):
        lis = ControlSocketListener(socket_path=socket_path, control_state=ControlState())
        lis.start()
        assert socket_path.exists()
        lis.stop()
        assert not lis.is_running
        assert not socket_path.exists()
        # Connecting after teardown fails -- nothing is listening.
        with pytest.raises(OSError):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
                c.settimeout(1.0)
                c.connect(str(socket_path))

    def test_start_is_idempotent(self, socket_path):
        lis = ControlSocketListener(socket_path=socket_path, control_state=ControlState())
        try:
            lis.start()
            thread = lis._accept_thread
            lis.start()  # second start is a no-op, same thread
            assert lis._accept_thread is thread
            assert lis.is_running
        finally:
            lis.stop()

    def test_stop_without_start_is_safe(self, socket_path):
        lis = ControlSocketListener(socket_path=socket_path, control_state=ControlState())
        lis.stop()  # must not raise
        assert not lis.is_running

    def test_double_stop_is_safe(self, socket_path):
        lis = ControlSocketListener(socket_path=socket_path, control_state=ControlState())
        lis.start()
        lis.stop()
        lis.stop()  # must not raise
        assert not lis.is_running

    def test_can_restart_after_stop(self, socket_path):
        lis = ControlSocketListener(socket_path=socket_path, control_state=ControlState())
        lis.start()
        lis.stop()
        lis.start()  # rebind the same well-known path
        try:
            assert lis.is_running
            assert socket_path.exists()
        finally:
            lis.stop()


# --------------------------------------------------------------------------
# Command dispatch over the wire
# --------------------------------------------------------------------------


class TestCommandDispatch:
    def test_pause(self, listener):
        send_lines(listener.socket_path, {"command": "pause"})
        assert wait_for(lambda: listener.test_state.snapshot().state == STATE_PAUSED)

    def test_resume(self, listener):
        listener.test_state.request_pause()
        send_lines(listener.socket_path, {"command": "resume"})
        assert wait_for(lambda: listener.test_state.snapshot().state == STATE_RUNNING)

    def test_stop(self, listener):
        send_lines(listener.socket_path, {"command": "stop"})
        assert wait_for(lambda: listener.test_state.snapshot().state == STATE_STOPPED)

    def test_stop_with_message_and_hint(self, listener):
        send_lines(
            listener.socket_path,
            {"command": "stop", "message": "text mode please", "hint": "switch-to-text"},
        )
        assert wait_for(lambda: listener.test_state.snapshot().is_stopped)
        snap = listener.test_state.snapshot()
        assert snap.message == "text mode please"
        assert snap.hint == "switch-to-text"

    def test_pause_then_resume_then_stop_sequence(self, listener):
        send_lines(listener.socket_path, {"command": "pause"})
        assert wait_for(lambda: listener.test_state.snapshot().is_paused)
        send_lines(listener.socket_path, {"command": "resume"})
        assert wait_for(lambda: listener.test_state.snapshot().is_running)
        send_lines(listener.socket_path, {"command": "stop"})
        assert wait_for(lambda: listener.test_state.snapshot().is_stopped)

    def test_multiple_commands_one_connection(self, listener):
        # Two newline-delimited commands sent down a single connection: last wins.
        send_lines(
            listener.socket_path,
            {"command": "pause"},
            {"command": "stop", "hint": "switch-to-text"},
        )
        assert wait_for(lambda: listener.test_state.snapshot().is_stopped)
        assert listener.test_state.snapshot().hint == "switch-to-text"

    def test_line_without_trailing_newline(self, listener):
        # A client that forgets the trailing newline still gets its line applied
        # at EOF (close).
        send_lines(listener.socket_path, raw=b'{"command": "stop"}')
        assert wait_for(lambda: listener.test_state.snapshot().is_stopped)


# --------------------------------------------------------------------------
# Robustness: bad input must not kill the listener
# --------------------------------------------------------------------------


class TestMalformedInput:
    def test_malformed_json_is_ignored(self, listener):
        send_lines(listener.socket_path, raw=b"not json at all\n")
        # State unchanged...
        time.sleep(0.1)
        assert listener.test_state.snapshot().state == STATE_RUNNING
        # ...and the listener is still alive: a good command still lands.
        send_lines(listener.socket_path, {"command": "stop"})
        assert wait_for(lambda: listener.test_state.snapshot().is_stopped)

    def test_unknown_command_is_ignored(self, listener):
        send_lines(listener.socket_path, {"command": "self-destruct"})
        time.sleep(0.1)
        assert listener.test_state.snapshot().state == STATE_RUNNING
        # volume is a documented stretch goal -- explicitly NOT accepted in v1.
        send_lines(listener.socket_path, {"command": "volume", "level": 50})
        time.sleep(0.1)
        assert listener.test_state.snapshot().state == STATE_RUNNING
        assert listener.is_running

    def test_non_utf8_line_is_ignored(self, listener):
        send_lines(listener.socket_path, raw=b"\xff\xfe\x00bad\n")
        time.sleep(0.1)
        assert listener.test_state.snapshot().state == STATE_RUNNING
        send_lines(listener.socket_path, {"command": "pause"})
        assert wait_for(lambda: listener.test_state.snapshot().is_paused)

    def test_empty_lines_are_ignored(self, listener):
        send_lines(listener.socket_path, raw=b"\n\n  \n")
        time.sleep(0.1)
        assert listener.test_state.snapshot().state == STATE_RUNNING
        assert listener.is_running

    def test_bad_line_then_good_line_same_connection(self, listener):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
            c.settimeout(2.0)
            c.connect(str(listener.socket_path))
            c.sendall(b"garbage\n")
            c.sendall(b'{"command": "stop"}\n')
        assert wait_for(lambda: listener.test_state.snapshot().is_stopped)


# --------------------------------------------------------------------------
# Stale-socket recovery
# --------------------------------------------------------------------------


class TestStaleSocketRecovery:
    def test_start_over_stale_socket_file(self, socket_path):
        # Simulate a crashed server: bind a socket to the path and leak it
        # (close without unlinking) so the file remains on disk.
        stale = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        stale.bind(str(socket_path))
        stale.close()
        assert socket_path.exists()

        state = ControlState()
        lis = ControlSocketListener(socket_path=socket_path, control_state=state)
        try:
            lis.start()  # must unlink-then-bind, not raise EADDRINUSE
            assert lis.is_running
            send_lines(socket_path, {"command": "stop"})
            assert wait_for(lambda: state.snapshot().is_stopped)
        finally:
            lis.stop()

    def test_refuses_to_clobber_a_regular_file(self, socket_path):
        # F6 (VM-1697): a non-socket squatting at the path must NOT be unlinked --
        # only a socket we own is stale-recoverable. Bind fails; the file survives.
        socket_path.write_bytes(b"leftover")
        assert socket_path.exists()

        state = ControlState()
        lis = ControlSocketListener(socket_path=socket_path, control_state=state)
        with pytest.raises(OSError):
            lis.start()
        assert not lis.is_running
        # The regular file was left untouched, not silently deleted.
        assert socket_path.read_bytes() == b"leftover"
        lis.stop()  # safe no-op cleanup


# --------------------------------------------------------------------------
# Socket file permissions (local-only side channel)
# --------------------------------------------------------------------------


class TestSocketPermissions:
    def test_socket_is_user_only(self, listener):
        import stat

        mode = stat.S_IMODE(listener.socket_path.stat().st_mode)
        # No group/other bits -- only the owning user may touch the socket file.
        assert mode & 0o077 == 0


# --------------------------------------------------------------------------
# Config-gated module seam (start_control_listener / stop_control_listener)
# --------------------------------------------------------------------------


@pytest.fixture
def reset_module_listener():
    """Reset the process-wide listener singleton around a test."""
    control_socket._listener = None
    yield
    if control_socket._listener is not None:
        control_socket._listener.stop()
    control_socket._listener = None


class TestModuleSeam:
    def test_start_is_noop_when_disabled(self, monkeypatch, reset_module_listener):
        monkeypatch.setattr(control_socket.config, "CONTROL_CHANNEL_ENABLED", False)
        assert control_socket.start_control_listener() is None
        # Nothing was created.
        assert control_socket._listener is None
        # stop is still safe to call.
        control_socket.stop_control_listener()

    def test_start_when_enabled_returns_running_listener(
        self, monkeypatch, reset_module_listener, socket_path
    ):
        monkeypatch.setattr(control_socket.config, "CONTROL_CHANNEL_ENABLED", True)
        monkeypatch.setattr(control_socket.config, "CONTROL_SOCKET_PATH", socket_path)

        lis = control_socket.start_control_listener()
        assert lis is not None
        assert lis.is_running
        assert lis.socket_path == socket_path
        assert socket_path.exists()

        # Idempotent: a second start returns the same singleton.
        assert control_socket.start_control_listener() is lis

        control_socket.stop_control_listener()
        assert not lis.is_running
        assert not socket_path.exists()

    def test_get_control_listener_is_singleton(self, reset_module_listener):
        a = control_socket.get_control_listener()
        b = control_socket.get_control_listener()
        assert a is b
        assert isinstance(a, ControlSocketListener)

    def test_stop_when_never_started_is_safe(self, reset_module_listener):
        # No listener has been created yet.
        assert control_socket._listener is None
        control_socket.stop_control_listener()  # must not raise

    def test_bind_failure_is_non_fatal(self, monkeypatch, reset_module_listener):
        # A control channel that can't bind must NOT break voice: the helper
        # logs and returns None rather than propagating the OSError.
        monkeypatch.setattr(control_socket.config, "CONTROL_CHANNEL_ENABLED", True)

        def boom(self):
            raise OSError("cannot bind")

        monkeypatch.setattr(ControlSocketListener, "start", boom, raising=True)
        assert control_socket.start_control_listener() is None
