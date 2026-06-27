"""Tests for converse's advance-to-record on a control-channel skip_forward (VM-1739).

skip_forward is the deterministic transport barge-in: when an external trigger
(Stream Deck, media key, spoken keyword, any local process) fires ``skip_forward``
over the control channel mid-TTS, ``converse`` must end the current utterance
(same instant-cut as ``stop``) and then **advance straight to the record/listen
turn** -- returning the NORMAL user response, NOT a ``[control: stop]`` marker.

This is the *one* place skip_forward diverges from stop:
* ``stop``  -> end the turn, return ``[control: stop] ...`` (see test_converse_control_return.py)
* ``skip_forward`` -> consume the edge, listen, return ``Voice response: ...``

In speak-only mode (``wait_for_response=False``) there is no record turn to
advance to, so skip_forward just ends the utterance and returns the ordinary
speak-only success string.

These mock the TTS / record / STT path (as test_converse_control_return.py does --
no real audio) and drive the process-wide control state directly, exactly as the
socket-listener thread does at runtime.
"""

from unittest.mock import patch

import numpy as np
import pytest

from voice_mode.control_channel import STATE_RUNNING, get_control_state


def _converse_fn():
    """The underlying coroutine behind the converse MCP tool."""
    from voice_mode.tools.converse import converse
    return getattr(converse, "fn", converse)


@pytest.fixture(autouse=True)
def reset_control_state():
    """Keep the process-wide control singleton clean around every test.

    It is a module-level singleton, so a stray skip_forward could otherwise leak
    into an unrelated test (or the broader suite). Reset before and after.
    """
    get_control_state().reset()
    yield
    get_control_state().reset()


def _fake_tts_that_skips_forward():
    """A text_to_speech_with_failover stand-in that fires a skip_forward.

    Models the runtime: the listener thread set the control state to
    ``skip_forward`` and the streaming loop aborted playback (surfacing
    ``control_stopped`` in the metrics) before returning success.
    """
    async def _fake(*_args, **_kwargs):
        get_control_state().request_skip_forward()
        metrics = {"ttfa": 0.1, "generation": 0.2, "playback": 0.3, "control_stopped": True}
        config = {"provider": "kokoro", "voice": "af_sky"}
        return True, metrics, config

    return _fake


class TestConverseSkipForwardAdvancesToRecord:
    """skip_forward mid-TTS with wait_for_response -> listen + normal response."""

    @pytest.mark.asyncio
    async def test_skip_forward_advances_to_record_and_returns_response(self):
        """The cut utterance gives way to the record turn; STT result is returned."""
        recorded = {"called": False}

        async def _noop_feedback(*_args, **_kwargs):
            return None

        def _record(*_args, **_kwargs):
            # Proof we advanced into the record/listen turn (not a control-stop return).
            recorded["called"] = True
            return (np.zeros(2400, dtype=np.int16), True)

        async def _fake_stt(*_args, **_kwargs):
            return {"text": "I have a question about the design", "provider": "whisper"}

        with patch("voice_mode.tools.converse.text_to_speech_with_failover",
                   new=_fake_tts_that_skips_forward()):
            with patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback):
                with patch("voice_mode.tools.converse.record_audio_with_silence_detection",
                           new=_record):
                    with patch("voice_mode.tools.converse.speech_to_text", new=_fake_stt):
                        with patch("voice_mode.config.TTS_BASE_URLS",
                                   ["https://api.openai.com/v1"]):
                            with patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                                result = await _converse_fn()(
                                    message="Let me explain at length...",
                                    wait_for_response=True,
                                )

        assert isinstance(result, str)
        # Advanced to record: we got the user's transcribed words back...
        assert recorded["called"], "skip_forward did not advance to the record turn"
        assert "I have a question about the design" in result
        # ...and NOT the stop control marker (this is the load-bearing divergence).
        assert "[control: stop]" not in result
        assert "skip_forward" not in result.lower()
        # The transport edge was consumed: state is back to running after the turn.
        assert get_control_state().snapshot().state == STATE_RUNNING

    @pytest.mark.asyncio
    async def test_skip_forward_consumes_edge_before_recording(self):
        """By the time the record loop runs, the skip_forward edge is cleared.

        The record loop only honours ``stop``; a lingering skip_forward must not
        be mistaken for one. converse reset()s the state before listening, so the
        loop sees ``running``.
        """
        seen_state = {}

        async def _noop_feedback(*_args, **_kwargs):
            return None

        def _record(*_args, **_kwargs):
            seen_state["at_record"] = get_control_state().snapshot().state
            return (np.zeros(2400, dtype=np.int16), True)

        async def _fake_stt(*_args, **_kwargs):
            return {"text": "carry on then", "provider": "whisper"}

        with patch("voice_mode.tools.converse.text_to_speech_with_failover",
                   new=_fake_tts_that_skips_forward()):
            with patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback):
                with patch("voice_mode.tools.converse.record_audio_with_silence_detection",
                           new=_record):
                    with patch("voice_mode.tools.converse.speech_to_text", new=_fake_stt):
                        with patch("voice_mode.config.TTS_BASE_URLS",
                                   ["https://api.openai.com/v1"]):
                            with patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                                await _converse_fn()(
                                    message="Talking too long...",
                                    wait_for_response=True,
                                )

        assert seen_state.get("at_record") == STATE_RUNNING, (
            "skip_forward edge not consumed before the record turn: "
            f"{seen_state.get('at_record')!r}"
        )


class TestConverseSkipForwardSpeakOnly:
    """skip_forward in speak-only mode just ends the utterance (no record turn)."""

    @pytest.mark.asyncio
    async def test_speak_only_returns_speak_only_string(self):
        with patch("voice_mode.tools.converse.text_to_speech_with_failover",
                   new=_fake_tts_that_skips_forward()):
            with patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]):
                with patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                    result = await _converse_fn()(
                        message="Quick note.",
                        wait_for_response=False,
                    )

        assert isinstance(result, str)
        # No control marker, no fabricated record turn -- the ordinary speak-only line.
        assert "[control: stop]" not in result
        assert "spoken successfully" in result.lower()
        # State reset per-utterance, so it's running again.
        assert get_control_state().snapshot().state == STATE_RUNNING
