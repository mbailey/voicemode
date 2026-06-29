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

import threading
from unittest.mock import MagicMock, patch

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


# --------------------------------------------------------------------------
# VM-1754: skip_forward ALSO ends the RECORD/listen turn -- the manual
# "I'm done, go now" end-of-turn and the VAD fallback when silence detection
# isn't firing. During recording it ends capture now, transcribes whatever
# was captured, and returns it as the user's response -- NOT a [control: stop]
# marker (that is stop), and NOT a replay (that is skip_back).
# --------------------------------------------------------------------------


def _fake_tts_ok():
    """A plain TTS stand-in that completes normally with no control event.

    Unlike ``_fake_tts_that_skips_forward`` above (which barges during PLAYBACK),
    these record-phase tests need TTS to finish cleanly so the skip_forward fires
    later -- while we are LISTENING.
    """
    async def _fake(*_args, **_kwargs):
        metrics = {"ttfa": 0.1, "generation": 0.2, "playback": 0.3}
        config = {"provider": "kokoro", "voice": "af_sky"}
        return True, metrics, config

    return _fake


async def _noop_feedback(*_args, **_kwargs):
    return None


def _record_then_skip_forward(audio):
    """A record stand-in that fires skip_forward mid-capture, then returns ``audio``.

    Models the runtime: the user presses skip-forward while VoiceMode is
    listening, so the listener thread latches STATE_SKIP_FORWARD and the record
    loop breaks early -- handing back whatever was captured so far.
    """
    def _record(*_args, **_kwargs):
        get_control_state().request_skip_forward()
        return audio

    return _record


class TestConverseSkipForwardEndsRecord:
    """skip_forward during the record turn -> transcribe-what-we-have + return."""

    @pytest.mark.asyncio
    async def test_skip_forward_mid_record_transcribes_and_returns(self):
        """Main case: speech was captured, skip_forward ends the turn, STT runs,
        and the transcript is returned normally -- no stop marker, no replay."""
        captured = np.zeros(2400, dtype=np.int16)

        async def _fake_stt(*_args, **_kwargs):
            return {"text": "that's all I wanted to say", "provider": "whisper"}

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection",
                   new=_record_then_skip_forward((captured, True))), \
             patch("voice_mode.tools.converse.speech_to_text", new=_fake_stt), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Tell me when you're done.",
                wait_for_response=True,
            )

        assert isinstance(result, str)
        # The captured buffer was transcribed and returned as the user response...
        assert "that's all I wanted to say" in result
        # ...and the load-bearing divergence holds: NOT a stop marker, NOT an error.
        assert "[control: stop]" not in result
        assert "Error: Could not record audio" not in result
        # Sticky skip_forward edge consumed -> back to running for the next turn.
        assert get_control_state().snapshot().state == STATE_RUNNING

    @pytest.mark.asyncio
    async def test_skip_forward_before_any_audio_advances_gracefully(self):
        """VAD-fallback edge: skip_forward fired before a single chunk was captured
        (empty buffer). That empty buffer is intentional ("go now"), so the turn
        advances gracefully -- NOT the 'Could not record audio' error, NOT a stop
        marker -- and STT is skipped (nothing to transcribe)."""
        empty = np.array([], dtype=np.int16)
        stt_spy = MagicMock(
            side_effect=AssertionError("STT must be skipped when nothing was captured")
        )

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection",
                   new=_record_then_skip_forward((empty, False))), \
             patch("voice_mode.tools.converse.speech_to_text", new=stt_spy), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Anything to add?",
                wait_for_response=True,
            )

        assert isinstance(result, str)
        # The empty buffer must NOT surface as a recording error or a stop marker.
        assert "Error: Could not record audio" not in result
        assert "[control: stop]" not in result
        # It is a graceful no-speech advance (success, not an error).
        assert "No speech detected" in result
        stt_spy.assert_not_called()
        assert get_control_state().snapshot().state == STATE_RUNNING

    @pytest.mark.asyncio
    async def test_skip_forward_before_speech_with_partial_audio_advances(self):
        """skip_forward fired after some audio but before VAD flagged speech:
        speech_detected is False, so we advance with no speech (no STT), not an
        error -- the buffer is non-empty but there is nothing to transcribe."""
        partial = np.zeros(480, dtype=np.int16)
        stt_spy = MagicMock(
            side_effect=AssertionError("STT must be skipped when no speech was detected")
        )

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection",
                   new=_record_then_skip_forward((partial, False))), \
             patch("voice_mode.tools.converse.speech_to_text", new=stt_spy), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Go on...",
                wait_for_response=True,
            )

        assert isinstance(result, str)
        assert "No speech detected" in result
        assert "Error: Could not record audio" not in result
        assert "[control: stop]" not in result
        stt_spy.assert_not_called()
        assert get_control_state().snapshot().state == STATE_RUNNING


class TestRecordLoopSkipForward:
    """record_audio_with_silence_detection breaks promptly on a skip_forward.

    The record-loop counterpart of TestRecordLoopControlStop (the stop path) in
    test_converse_control_return.py -- exercises the real VAD loop with a mocked
    InputStream, proving the new poll branch ends capture without hanging.
    """

    def test_record_loop_breaks_when_skip_forward(self):
        """A skip_forward set before/at the first poll exits the VAD loop without
        hanging, returning the (empty) capture for converse to handle."""
        from voice_mode.tools import converse as converse_mod

        # Pre-set skip_forward the way the listener thread would.
        get_control_state().request_skip_forward()

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
        # breaking on skip_forward) fails loudly instead of hanging the suite.
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join(timeout=5.0)

        assert not t.is_alive(), "record loop did not break on skip_forward (hung)"
        audio_data, speech_detected = result_box["value"]
        # Broke on the first iteration before any chunk was read.
        assert len(audio_data) == 0
        assert speech_detected is False


class TestRecordPhaseRegressions:
    """The new skip_forward branch must not disturb stop / skip_back during record."""

    @pytest.mark.asyncio
    async def test_stop_during_record_still_returns_control_marker(self):
        """Regression: a stop while listening still ends the turn with a
        [control: stop] marker -- skip_forward must not hijack the stop path."""
        def _record(*_args, **_kwargs):
            get_control_state().request_stop(hint="switch-to-text")
            return (np.zeros(2400, dtype=np.int16), True)

        stt_spy = MagicMock(
            side_effect=AssertionError("STT must be skipped on a control stop")
        )

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=stt_spy), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="What next?",
                wait_for_response=True,
            )

        assert result.startswith("[control: stop] "), f"got: {result!r}"
        stt_spy.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_back_during_record_still_replays_then_relistens(self):
        """Regression: a skip_back while listening still replays cached audio and
        re-listens -- no skip_forward interference, and no STT for the replay."""
        from voice_mode.history_buffer import get_history_buffer
        from voice_mode.streaming import REPLAY_COMPLETED

        buf = get_history_buffer()
        buf.clear()
        buf.append(text="latest", pcm_bytes=b"\x01\x00", sample_rate=24000, channels=1)

        replayed = []

        async def fake_replay(record, control_state=None):
            replayed.append(record.text)
            return REPLAY_COMPLETED

        record_calls = {"n": 0}

        def _record(*_args, **_kwargs):
            record_calls["n"] += 1
            if record_calls["n"] == 1:
                # First listen: user presses skip_back instead of speaking.
                get_control_state().request_skip_back()
                return (np.zeros(10, dtype=np.int16), False)
            # Second listen (after the replay): still no speech -> end the turn.
            return (np.zeros(10, dtype=np.int16), False)

        stt_spy = MagicMock(
            side_effect=AssertionError("STT must not run for a replay")
        )

        try:
            with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok()), \
                 patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
                 patch("voice_mode.streaming.play_cached_utterance", new=fake_replay), \
                 patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
                 patch("voice_mode.tools.converse.speech_to_text", new=stt_spy), \
                 patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
                 patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
                result = await _converse_fn()(
                    message="Anything else?",
                    wait_for_response=True,
                )
        finally:
            buf.clear()

        assert replayed == ["latest"]          # the press during listening replayed
        assert record_calls["n"] == 2          # ...and we listened again afterwards
        assert isinstance(result, str)
