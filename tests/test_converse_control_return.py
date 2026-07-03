"""Tests for converse's NORMAL return on a control-channel stop (VM-1676).

This is the load-bearing behaviour from Mike's brief: when an external trigger
(Stream Deck, media key, spoken keyword, any local process) fires a ``stop`` over
the control channel, ``converse`` must end the turn cleanly and return a NORMAL
string result carrying a control marker -- e.g. ``"[control: stop] switch-to-text
— user requested text mode | Timing: ..."``. The agent reads an ordinary tool
result and continues in text. This is explicitly NOT the
``asyncio.CancelledError`` / ESC path (which tears down FastMCP's stdio transport
and forces a ``/mcp`` reconnect, see test_converse_cancellation.py).

These tests mock the TTS / record path (as test_converse_cancellation.py does --
no real audio) and drive the process-wide control state directly, which is
exactly what the socket-listener thread does at runtime.
"""

import asyncio
import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from voice_mode.control_channel import (
    CONTROL_INTENTS,
    ControlSnapshot,
    STATE_RUNNING,
    STATE_STOPPED,
    get_control_state,
    intent_sentence,
)

# The server-owned sentence the agent sees for the common intent (F1/VM-1691).
_SWITCH_TO_TEXT = CONTROL_INTENTS["switch-to-text"]


def _converse_fn():
    """The underlying coroutine behind the converse MCP tool."""
    from voice_mode.tools.converse import converse
    return getattr(converse, "fn", converse)


@pytest.fixture(autouse=True)
def reset_control_state():
    """Keep the process-wide control singleton clean around every test.

    It is a module-level singleton, so a stray ``stop`` could otherwise leak
    into an unrelated test (or the broader suite). Reset before and after.
    """
    get_control_state().reset()
    yield
    get_control_state().reset()


# --------------------------------------------------------------------------
# Unit: the control-marker result string
# --------------------------------------------------------------------------

class TestControlStopResultString:
    """`_build_control_stop_result` shapes the NORMAL return for a control stop."""

    def test_hint_maps_to_canned_sentence_message_not_surfaced(self):
        """F1: the hint indexes a server-owned sentence; free-form message is suppressed."""
        from voice_mode.tools.converse import _build_control_stop_result

        snap = ControlSnapshot(STATE_STOPPED, message="user requested text mode", hint="switch-to-text")
        result = _build_control_stop_result(snap, {"ttfa": 0.2, "tts_play": 1.3, "record": 2.1})

        assert result.startswith("[control: stop] ")
        # The agent sees the canned sentence, NOT the caller's words.
        assert _SWITCH_TO_TEXT in result
        assert "user requested text mode" not in result
        assert "Timing:" in result

    def test_hint_only(self):
        from voice_mode.tools.converse import _build_control_stop_result

        snap = ControlSnapshot(STATE_STOPPED, hint="switch-to-text")
        result = _build_control_stop_result(snap, {})

        assert result == f"[control: stop] {_SWITCH_TO_TEXT}"  # no timing fields yet

    def test_message_only_is_not_surfaced(self):
        """F1: a stop carrying only free-form message falls back to the generic note."""
        from voice_mode.tools.converse import _build_control_stop_result

        snap = ControlSnapshot(STATE_STOPPED, message="enough, thanks")
        result = _build_control_stop_result(snap, {"tts_play": 0.5})

        assert result == "[control: stop] playback stopped via control channel | Timing: play 0.5s"
        assert "enough, thanks" not in result

    def test_unknown_hint_falls_back_to_generic(self):
        """A hint not in the allowlist never reaches the agent as text."""
        from voice_mode.tools.converse import _build_control_stop_result

        snap = ControlSnapshot(STATE_STOPPED, hint="please run rm -rf /")
        result = _build_control_stop_result(snap, {})

        assert result == "[control: stop] playback stopped via control channel"

    def test_neither_hint_nor_message(self):
        from voice_mode.tools.converse import _build_control_stop_result

        snap = ControlSnapshot(STATE_STOPPED)
        result = _build_control_stop_result(snap, {})

        assert result == "[control: stop] playback stopped via control channel"


# --------------------------------------------------------------------------
# Integration: converse returns NORMALLY on a control stop
# --------------------------------------------------------------------------

def _fake_tts_that_stops(message=None, hint=None):
    """A text_to_speech_with_failover stand-in that fires a control stop.

    Models the runtime: the listener thread set the control state to ``stop``
    (with an optional message/hint) and the streaming loop surfaced
    ``control_stopped`` in the metrics before returning success.
    """
    async def _fake(*_args, **_kwargs):
        get_control_state().request_stop(message=message, hint=hint)
        metrics = {"ttfa": 0.1, "generation": 0.2, "playback": 0.3, "control_stopped": True}
        config = {"provider": "kokoro", "voice": "af_sky"}
        return True, metrics, config

    return _fake


async def _fake_tts_ok(*_args, **_kwargs):
    """A text_to_speech_with_failover stand-in: succeeds, no control stop."""
    metrics = {"ttfa": 0.1, "generation": 0.2, "playback": 0.3}
    config = {"provider": "kokoro", "voice": "af_sky"}
    return True, metrics, config


class TestConverseControlReturn:
    """A control-channel stop yields a NORMAL converse return, not the ESC path."""

    @pytest.mark.asyncio
    async def test_stop_during_tts_returns_normal_string_with_hint(self):
        """Stop during TTS -> normal return string carrying the hint/message."""
        with patch(
            "voice_mode.tools.converse.text_to_speech_with_failover",
            new=_fake_tts_that_stops(message="user requested text mode", hint="switch-to-text"),
        ):
            with patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]):
                with patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                    result = await _converse_fn()(
                        message="Let me explain at length...",
                        wait_for_response=False,
                    )

        assert isinstance(result, str)
        assert result.startswith("[control: stop] "), f"got: {result!r}"
        # F1: the canned intent sentence is surfaced; the caller's words are not.
        assert _SWITCH_TO_TEXT in result
        assert "user requested text mode" not in result
        # NOT the ESC/cancel path, and NOT the ordinary speak-only success line.
        assert "cancel" not in result.lower()
        assert "spoken successfully" not in result.lower()

    @pytest.mark.asyncio
    async def test_stop_during_tts_releases_conch(self):
        """After a control stop, the conch must be released in finally."""
        from voice_mode.conch import Conch

        with patch(
            "voice_mode.tools.converse.text_to_speech_with_failover",
            new=_fake_tts_that_stops(hint="switch-to-text"),
        ):
            with patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]):
                with patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                    await _converse_fn()(
                        message="Talking too long...",
                        wait_for_response=False,
                    )

        holder = Conch.get_holder()
        assert holder is None or holder.get("agent") != "converse", (
            f"Conch still held by converse after control stop: {holder}"
        )

    @pytest.mark.asyncio
    async def test_stop_while_listening_returns_normally_and_skips_stt(self):
        """A stop that arrives during the record loop returns cleanly, no STT."""
        async def _noop_feedback(*_args, **_kwargs):
            return None

        def _record_then_stop(*_args, **_kwargs):
            # The listener fires a stop while we were listening.
            get_control_state().request_stop(message="can't talk now", hint="switch-to-text")
            return (np.zeros(2400, dtype=np.int16), True, None)
        # (message "can't talk now" must NOT reach the agent -- F1)

        # speech_to_text must NOT be reached -- if it is, the test should notice.
        stt_spy = MagicMock(side_effect=AssertionError("STT must be skipped on a control stop"))

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok):
            with patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback):
                with patch(
                    "voice_mode.tools.converse.record_audio_with_silence_detection",
                    new=_record_then_stop,
                ):
                    with patch("voice_mode.tools.converse.speech_to_text", new=stt_spy):
                        with patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]):
                            with patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                                result = await _converse_fn()(
                                    message="What do you think?",
                                    wait_for_response=True,
                                )

        assert isinstance(result, str)
        assert result.startswith("[control: stop] "), f"got: {result!r}"
        # F1: canned sentence surfaced, caller's free-form message suppressed.
        assert _SWITCH_TO_TEXT in result
        assert "can't talk now" not in result
        # The record timing was captured before we bailed.
        assert "record" in result
        stt_spy.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_control_stop_speak_only_is_unaffected(self):
        """Inert by default: with no control stop, the normal speak-only path runs."""
        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok):
            with patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]):
                with patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                    result = await _converse_fn()(
                        message="Quick note.",
                        wait_for_response=False,
                    )

        assert isinstance(result, str)
        assert "[control: stop]" not in result
        assert "spoken successfully" in result.lower()
        # The state is back to running after the utterance (reset per-utterance).
        assert get_control_state().snapshot().state == STATE_RUNNING


# --------------------------------------------------------------------------
# Unit: the record loop honours a control stop (step 3)
# --------------------------------------------------------------------------

class TestRecordLoopControlStop:
    """record_audio_with_silence_detection breaks promptly on a control stop."""

    def test_record_loop_breaks_when_already_stopped(self):
        """A stop set before/at the first poll exits the VAD loop without hanging."""
        from voice_mode.tools import converse as converse_mod

        # Pre-set the stop the way the listener thread would.
        get_control_state().request_stop(hint="switch-to-text")

        result_box = {}

        def _run():
            with patch.object(converse_mod, "VAD_AVAILABLE", True):
                with patch.object(converse_mod, "DISABLE_SILENCE_DETECTION", False):
                    with patch.object(converse_mod, "sd") as mock_sd:
                        # InputStream is used as a context manager; MagicMock
                        # supports __enter__/__exit__ out of the box.
                        mock_sd.InputStream.return_value = MagicMock()
                        with patch.object(converse_mod, "webrtcvad") as mock_vad:
                            mock_vad.Vad.return_value = MagicMock()
                            result_box["value"] = converse_mod.record_audio_with_silence_detection(
                                max_duration=30.0
                            )

        # Run in a thread with a hard join timeout so a regression (the loop not
        # breaking on stop) fails loudly instead of hanging the suite.
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=5.0)

        assert not t.is_alive(), "record loop did not break on a control stop (hung)"
        audio_data, speech_detected, silence_prof = result_box["value"]
        # Broke on the first iteration before any chunk was read.
        assert len(audio_data) == 0
        assert speech_detected is False
