"""No ``socket.AF_UNIX`` (native Windows) must not fail converse (VM-2544, #588).

VM-1676 promised a non-fatal control-channel bind, but a platform without Unix
domain sockets raised ``AttributeError`` out of ``start_control_listener`` and
every converse call failed before it spoke. These tests simulate that platform on
macOS/Linux the way VM-2536's ``evidence/588/no_af_unix_probe.py`` does: the
module under test is handed a ``socket`` module with ``AF_UNIX`` removed, and
nothing else changes. No Windows machine, no audio device, no network.
"""

import asyncio
import logging
import socket as real_socket
import types
from unittest.mock import patch

import pytest
from click.testing import CliRunner

import voice_mode.control_socket as cs
from voice_mode.cli import voice_mode_main_cli

MESSAGE = "control channel needs Unix domain sockets, not available on this platform"


def _socket_without_af_unix() -> types.ModuleType:
    """A stand-in ``socket`` module: everything the real one has, minus AF_UNIX."""
    fake = types.ModuleType("socket")
    fake.__dict__.update({k: v for k, v in vars(real_socket).items() if k != "AF_UNIX"})
    assert not hasattr(fake, "AF_UNIX")
    return fake


@pytest.fixture
def no_af_unix(monkeypatch, tmp_path):
    """control_socket sees no AF_UNIX; the channel flag is ON; state is fresh."""
    monkeypatch.setattr(cs, "socket", _socket_without_af_unix())
    monkeypatch.setattr(cs.config, "CONTROL_CHANNEL_ENABLED", True)
    monkeypatch.setattr(cs.config, "CONTROL_SOCKET_PATH", str(tmp_path / "c.sock"))
    # The once-per-process latch and the shared listener are module state.
    monkeypatch.setattr(cs, "_unix_unavailable_logged", False, raising=False)
    monkeypatch.setattr(cs, "_listener", None)
    yield
    cs._listener = None


def _messages(caplog):
    return [r for r in caplog.records if MESSAGE in r.getMessage()]


# --------------------------------------------------------------------------
# Listener: logged once, returns None
# --------------------------------------------------------------------------


class TestListenerWithoutAfUnix:
    def test_start_returns_none_and_logs_once_across_calls(self, no_af_unix, caplog):
        caplog.set_level(logging.DEBUG, logger="voicemode.control_socket")
        assert cs.start_control_listener() is None
        assert cs.start_control_listener() is None
        hits = _messages(caplog)
        assert len(hits) == 1, [r.getMessage() for r in caplog.records]
        assert hits[0].levelno == logging.WARNING
        # The warning is a plain sentence, not a traceback.
        assert hits[0].exc_info is None

    def test_stop_after_unavailable_start_is_safe(self, no_af_unix):
        assert cs.start_control_listener() is None
        cs.stop_control_listener()  # must not raise

    def test_flag_off_says_nothing(self, no_af_unix, monkeypatch, caplog):
        monkeypatch.setattr(cs.config, "CONTROL_CHANNEL_ENABLED", False)
        caplog.set_level(logging.DEBUG, logger="voicemode.control_socket")
        assert cs.start_control_listener() is None
        assert _messages(caplog) == []

    def test_direct_listener_start_raises_oserror_not_attributeerror(self, no_af_unix, tmp_path):
        # A caller driving ControlSocketListener directly gets an OSError, which
        # every existing non-fatal path already catches.
        sock_dir = tmp_path / "never-made"
        lis = cs.ControlSocketListener(socket_path=sock_dir / "c.sock")
        with pytest.raises(OSError, match="Unix domain sockets"):
            lis.start()
        assert not sock_dir.exists(), "nothing is touched on disk before the check"

    def test_unix_sockets_available_reflects_the_module(self, no_af_unix, monkeypatch):
        assert cs.unix_sockets_available() is False
        monkeypatch.setattr(cs, "socket", real_socket)
        assert cs.unix_sockets_available() is hasattr(real_socket, "AF_UNIX")


# --------------------------------------------------------------------------
# Converse: the scope does not raise; a whole converse call speaks normally
# --------------------------------------------------------------------------


class TestConverseWithoutAfUnix:
    def test_control_listener_scope_does_not_raise(self, no_af_unix):
        from voice_mode.tools.converse import _control_listener_scope

        async def run():
            async with _control_listener_scope() as state:
                return state

        assert asyncio.run(run()) is not None

    @pytest.mark.asyncio
    async def test_converse_speaks_with_flag_on(self, no_af_unix, caplog):
        from voice_mode.tools.converse import converse

        async def fake_tts(*_a, **_k):
            return True, {"ttfa": 0.1, "generation": 0.2, "playback": 0.3}, {
                "provider": "kokoro",
                "voice": "af_sky",
            }

        caplog.set_level(logging.DEBUG, logger="voicemode.control_socket")
        fn = getattr(converse, "fn", converse)
        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=fake_tts):
            with patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]):
                with patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                    result = await fn(message="hello", wait_for_response=False)

        assert isinstance(result, str)
        assert "AF_UNIX" not in result, result
        assert not result.lower().startswith("error"), result
        assert len(_messages(caplog)) == 1


# --------------------------------------------------------------------------
# Client verbs + `voicemode control`: plain message, non-zero, no traceback
# --------------------------------------------------------------------------


class TestClientWithoutAfUnix:
    def test_send_control_command_raises_plain_oserror(self, no_af_unix):
        with pytest.raises(OSError) as exc:
            cs.send_control_command("stop")
        assert str(exc.value) == MESSAGE

    def test_query_status_raises_plain_oserror(self, no_af_unix):
        with pytest.raises(OSError) as exc:
            cs.query_status()
        assert str(exc.value) == MESSAGE

    def test_bad_command_still_fails_validation_first(self, no_af_unix):
        from voice_mode.control_channel import ControlCommandError

        with pytest.raises(ControlCommandError):
            cs.send_control_command("volume")

    @pytest.mark.parametrize("verb", ["stop", "pause", "resume", "skip-back", "skip-forward"])
    def test_cli_prints_message_and_exits_nonzero(self, no_af_unix, verb):
        result = CliRunner().invoke(voice_mode_main_cli, ["control", verb])
        assert isinstance(result.exception, SystemExit), repr(result.exception)
        assert result.exit_code == 1
        assert MESSAGE in result.output
        assert "Traceback" not in result.output


# --------------------------------------------------------------------------
# The other AF_UNIX sites: dj (mpv IPC) and the mouth's call leg
# --------------------------------------------------------------------------


class TestOtherSitesWithoutAfUnix:
    def test_dj_socket_backend_returns_failed_result(self, monkeypatch):
        from voice_mode.dj import player

        monkeypatch.setattr(player, "socket", _socket_without_af_unix())
        result = player.SocketBackend("/nonexistent/mpv.sock").send_command(["get_property", "pid"])
        assert result.success is False
        assert "Unix domain sockets" in result.error

    def test_mouth_live_calls_is_empty_not_a_crash(self, monkeypatch):
        from voice_mode.mouth import output

        monkeypatch.setattr(output, "socket", _socket_without_af_unix())
        monkeypatch.setenv("VOICEMODE_MOUTH_CALL_SOCKS", "/nonexistent/call-mouth.sock")
        with pytest.raises(OSError, match="Unix domain sockets"):
            output._ask("/nonexistent/call-mouth.sock", {"probe": True})
        assert output.live_calls() == []
