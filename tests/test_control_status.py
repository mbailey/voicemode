"""Tests for the control-socket now-playing read-side (VM-1685, impl-nowplaying).

The control socket is fire-and-forget for pause / resume / stop / skip_back; this
feature adds ONE request/response query on top -- ``{"command":"status"}`` returns
a single JSON line describing the current control state + the history-buffer
"now playing" position. Coverage:

* ``build_status_payload`` (pure, no socket): empty + populated buffer, the
  newest entry is surfaced, state / pending_transport reflected, request_id echoed
* over the real socket: a status query returns the expected JSON during
  "playback" (buffer populated) and when idle; reflects pause + a pending
  skip_back; echoes request_id; is repeatable on one connection
* the fire-and-forget command path is UNTOUCHED: pause/resume/stop/skip_back still
  apply and write **nothing** back; a status query never mutates state
* the ``query_status`` client round-trips and errors cleanly when nothing listens

Socket paths are kept SHORT on purpose (AF_UNIX ~104-char limit on macOS).
"""

import json
import shutil
import socket
import tempfile
import time
from pathlib import Path

import pytest

from voice_mode.control_channel import (
    STATE_PAUSED,
    STATE_RUNNING,
    STATE_STOPPED,
    ControlState,
)
from voice_mode.control_socket import (
    ControlSocketListener,
    build_status_payload,
    query_status,
)
from voice_mode.history_buffer import HistoryBuffer


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
def status_listener(socket_path):
    """A started listener with its own ControlState + HistoryBuffer.

    Both are injected (not the process-wide singletons) so a test drives a known
    buffer/state. Exposed on the listener as ``test_state`` / ``test_history``.
    """
    state = ControlState()
    history = HistoryBuffer(maxlen=4)
    lis = ControlSocketListener(
        socket_path=socket_path, control_state=state, history_buffer=history
    )
    lis.start()
    lis.test_state = state  # type: ignore[attr-defined]
    lis.test_history = history  # type: ignore[attr-defined]
    yield lis
    lis.stop()


def add_utterance(history, text, *, seconds=1.0, sample_rate=24000, channels=1,
                  voice=None, timestamp=None):
    """Append a synthetic completed utterance of a known duration to ``history``."""
    nframes = int(seconds * sample_rate)
    pcm = b"\x00\x00" * nframes * channels  # 16-bit samples, all silence
    return history.append(
        text=text,
        pcm_bytes=pcm,
        sample_rate=sample_rate,
        channels=channels,
        voice=voice,
        timestamp=timestamp,
    )


def raw_query(path, payload, timeout=2.0):
    """Send one JSON line to the socket and return the parsed response line."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
        c.settimeout(timeout)
        c.connect(str(path))
        c.sendall((json.dumps(payload) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            chunk = c.recv(4096)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf.split(b"\n", 1)[0].decode())


def wait_for(predicate, timeout=2.0, interval=0.01):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


# --------------------------------------------------------------------------
# build_status_payload -- pure, no socket
# --------------------------------------------------------------------------


class TestBuildStatusPayload:
    def test_empty_buffer_idle(self):
        state = ControlState()
        history = HistoryBuffer(maxlen=4)
        payload = build_status_payload(state, history)
        assert payload["ok"] is True
        assert payload["action"] == "status"
        assert payload["state"] == STATE_RUNNING
        assert payload["pending_transport"] is None
        assert payload["buffer"] == {"depth": 0, "capacity": 4}
        assert payload["now_playing"] is None
        assert payload["request_id"] is None

    def test_single_utterance_fields(self):
        state = ControlState()
        history = HistoryBuffer(maxlen=4)
        # 1.0s of 24kHz mono 16-bit = 48000 bytes -> duration 1.0
        add_utterance(history, "hello there", seconds=1.0, voice="af_sky",
                      timestamp=123.5)
        payload = build_status_payload(state, history)
        assert payload["buffer"] == {"depth": 1, "capacity": 4}
        now = payload["now_playing"]
        assert now["index"] == 0
        assert now["text"] == "hello there"
        assert now["duration"] == 1.0
        assert now["sample_rate"] == 24000
        assert now["channels"] == 1
        assert now["timestamp"] == 123.5
        assert now["voice"] == "af_sky"

    def test_now_playing_is_newest_entry(self):
        state = ControlState()
        history = HistoryBuffer(maxlen=4)
        add_utterance(history, "first")
        add_utterance(history, "second")
        add_utterance(history, "third")
        payload = build_status_payload(state, history)
        assert payload["buffer"]["depth"] == 3
        # newest entry, at index depth-1
        assert payload["now_playing"]["index"] == 2
        assert payload["now_playing"]["text"] == "third"

    def test_eviction_keeps_depth_at_capacity(self):
        state = ControlState()
        history = HistoryBuffer(maxlen=2)
        add_utterance(history, "a")
        add_utterance(history, "b")
        add_utterance(history, "c")  # evicts "a"
        payload = build_status_payload(state, history)
        assert payload["buffer"] == {"depth": 2, "capacity": 2}
        assert payload["now_playing"]["index"] == 1
        assert payload["now_playing"]["text"] == "c"

    def test_paused_state_reflected(self):
        state = ControlState()
        state.request_pause()
        payload = build_status_payload(state, HistoryBuffer(maxlen=4))
        assert payload["state"] == STATE_PAUSED

    def test_stopped_state_reflected(self):
        state = ControlState()
        state.request_stop()
        payload = build_status_payload(state, HistoryBuffer(maxlen=4))
        assert payload["state"] == STATE_STOPPED

    def test_pending_transport_reflected_and_not_consumed(self):
        state = ControlState()
        state.request_skip_back()
        payload = build_status_payload(state, HistoryBuffer(maxlen=4))
        assert payload["pending_transport"] == "skip_back"
        # read-side only: the peek must NOT consume the pending request, so the
        # playback loop's take_transport_request still sees it.
        assert state.take_transport_request() == "skip_back"

    def test_request_id_echoed(self):
        payload = build_status_payload(
            ControlState(), HistoryBuffer(maxlen=4), request_id=42
        )
        assert payload["request_id"] == 42

    def test_payload_is_json_serialisable(self):
        history = HistoryBuffer(maxlen=4)
        add_utterance(history, "round trip", voice="af_sky")
        payload = build_status_payload(ControlState(), history)
        # one line, no surprises -- it goes on the wire verbatim
        assert json.loads(json.dumps(payload)) == payload


# --------------------------------------------------------------------------
# Status query over the real socket (request/response)
# --------------------------------------------------------------------------


class TestStatusQueryOverSocket:
    def test_status_when_idle(self, status_listener):
        resp = raw_query(status_listener.socket_path, {"command": "status"})
        assert resp["ok"] is True
        assert resp["action"] == "status"
        assert resp["state"] == STATE_RUNNING
        assert resp["buffer"] == {"depth": 0, "capacity": 4}
        assert resp["now_playing"] is None

    def test_status_during_playback(self, status_listener):
        add_utterance(status_listener.test_history, "the bit from just before",
                      seconds=2.0, voice="af_sky")
        resp = raw_query(status_listener.socket_path, {"command": "status"})
        assert resp["buffer"] == {"depth": 1, "capacity": 4}
        assert resp["now_playing"]["text"] == "the bit from just before"
        assert resp["now_playing"]["duration"] == 2.0
        assert resp["now_playing"]["index"] == 0
        assert resp["now_playing"]["voice"] == "af_sky"

    def test_status_reflects_pause(self, status_listener):
        status_listener.test_state.request_pause()
        resp = raw_query(status_listener.socket_path, {"command": "status"})
        assert resp["state"] == STATE_PAUSED

    def test_status_reflects_pending_skip_back(self, status_listener):
        status_listener.test_state.request_skip_back()
        resp = raw_query(status_listener.socket_path, {"command": "status"})
        assert resp["pending_transport"] == "skip_back"
        # the query peeked -- a real playback consumer still gets the request
        assert status_listener.test_state.take_transport_request() == "skip_back"

    def test_status_echoes_request_id(self, status_listener):
        resp = raw_query(
            status_listener.socket_path, {"command": "status", "request_id": "abc-1"}
        )
        assert resp["request_id"] == "abc-1"

    def test_status_does_not_mutate_state(self, status_listener):
        raw_query(status_listener.socket_path, {"command": "status"})
        # a query is read-only: state stays running, buffer untouched
        assert status_listener.test_state.snapshot().state == STATE_RUNNING
        assert len(status_listener.test_history) == 0

    def test_multiple_queries_one_connection(self, status_listener):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
            c.settimeout(2.0)
            c.connect(str(status_listener.socket_path))

            def read_line():
                buf = b""
                while b"\n" not in buf:
                    chunk = c.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                return json.loads(buf.split(b"\n", 1)[0].decode())

            c.sendall(b'{"command": "status", "request_id": 1}\n')
            first = read_line()
            assert first["request_id"] == 1
            assert first["now_playing"] is None

            add_utterance(status_listener.test_history, "now something plays")
            c.sendall(b'{"command": "status", "request_id": 2}\n')
            second = read_line()
            assert second["request_id"] == 2
            assert second["now_playing"]["text"] == "now something plays"

    def test_status_without_trailing_newline_at_eof(self, status_listener):
        # A client that sends the query then half-closes (no newline) still gets a
        # response at EOF (mirrors the command path's newline-less tolerance).
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
            c.settimeout(2.0)
            c.connect(str(status_listener.socket_path))
            c.sendall(b'{"command": "status"}')  # no newline
            c.shutdown(socket.SHUT_WR)
            buf = b""
            while b"\n" not in buf:
                chunk = c.recv(4096)
                if not chunk:
                    break
                buf += chunk
        resp = json.loads(buf.split(b"\n", 1)[0].decode())
        assert resp["action"] == "status"


# --------------------------------------------------------------------------
# Fire-and-forget command path stays untouched
# --------------------------------------------------------------------------


class TestCommandPathUntouched:
    def test_pause_still_dispatches_and_writes_nothing(self, status_listener):
        # The command path is fire-and-forget: the state flips and NOTHING is
        # written back (proven by the recv timing out with no bytes).
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
            c.settimeout(0.5)
            c.connect(str(status_listener.socket_path))
            c.sendall(b'{"command": "pause"}\n')
            with pytest.raises(socket.timeout):
                c.recv(4096)  # no response to a fire-and-forget command
        assert wait_for(
            lambda: status_listener.test_state.snapshot().state == STATE_PAUSED
        )

    def test_skip_back_still_dispatches_and_writes_nothing(self, status_listener):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
            c.settimeout(0.5)
            c.connect(str(status_listener.socket_path))
            c.sendall(b'{"command": "skip_back"}\n')
            with pytest.raises(socket.timeout):
                c.recv(4096)
        assert wait_for(
            lambda: status_listener.test_state.pending_transport == "skip_back"
        )

    def test_status_then_command_same_connection(self, status_listener):
        # A status query (response) followed by a fire-and-forget command (no
        # response) on one connection: the query answers, the command applies.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
            c.settimeout(2.0)
            c.connect(str(status_listener.socket_path))
            c.sendall(b'{"command": "status"}\n')
            buf = b""
            while b"\n" not in buf:
                chunk = c.recv(4096)
                if not chunk:
                    break
                buf += chunk
            assert json.loads(buf.split(b"\n", 1)[0].decode())["action"] == "status"
            c.sendall(b'{"command": "stop"}\n')
        assert wait_for(lambda: status_listener.test_state.snapshot().is_stopped)

    def test_unknown_command_still_ignored_no_response(self, status_listener):
        # Not a status query and not a valid command -> ignored, no response, no
        # crash (a subsequent good query still works).
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as c:
            c.settimeout(0.5)
            c.connect(str(status_listener.socket_path))
            c.sendall(b'{"command": "self-destruct"}\n')
            with pytest.raises(socket.timeout):
                c.recv(4096)
        assert status_listener.is_running
        resp = raw_query(status_listener.socket_path, {"command": "status"})
        assert resp["action"] == "status"


# --------------------------------------------------------------------------
# query_status client
# --------------------------------------------------------------------------


class TestQueryStatusClient:
    def test_round_trips_payload(self, status_listener):
        add_utterance(status_listener.test_history, "client round trip", voice="af_sky")
        resp = query_status(socket_path=status_listener.socket_path)
        assert resp["ok"] is True
        assert resp["now_playing"]["text"] == "client round trip"
        # matches what the pure builder would produce for the same inputs
        expected = build_status_payload(
            status_listener.test_state, status_listener.test_history
        )
        assert resp["now_playing"] == expected["now_playing"]
        assert resp["buffer"] == expected["buffer"]

    def test_echoes_request_id(self, status_listener):
        resp = query_status(socket_path=status_listener.socket_path, request_id=7)
        assert resp["request_id"] == 7

    def test_raises_when_nothing_listening(self, socket_path):
        # No listener bound at this path.
        with pytest.raises(FileNotFoundError):
            query_status(socket_path=socket_path)
