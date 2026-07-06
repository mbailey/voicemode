"""Tests for the listen_and_transcribe() seam (VM-1775 impl-000, VM-1832's named
extraction goal).

Slice 0 is a pure refactor: extract the chime->record_audio_with_silence_detection
(control-aware)->chime->STT->classified ``ListenResult`` sequence out of the three
inline copies that used to live in ``converse()`` (the single-message listen
path, plus the `should_repeat` and `should_wait` re-listens), and re-point all
three call sites onto it. No behaviour change for the main listen path (golden
byte-equivalence below); the repeat/wait re-listens *gain* control-channel
awareness they previously lacked entirely (documented explicitly, per the
feature's steps).

Coverage:
  * ``listen_and_transcribe()`` unit tests -- every classified outcome.
  * Golden byte-equivalence of the single-message listen path's return string.
  * Repeat/wait re-listens now honour a control-channel stop (the noted gain).
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from voice_mode.control_channel import get_control_state, COMMAND_SKIP_BACK
from voice_mode.tools.converse import ListenResult, listen_and_transcribe


def _converse_fn():
    from voice_mode.tools.converse import converse
    return getattr(converse, "fn", converse)


@pytest.fixture(autouse=True)
def reset_control_state():
    """Keep the process-wide control singleton clean around every test."""
    get_control_state().reset()
    yield
    get_control_state().reset()


async def _noop_feedback(*_a, **_k):
    return None


def _listen_kwargs(**overrides):
    kwargs = dict(
        control_state=get_control_state(),
        listen_duration_max=10.0,
        listen_duration_min=0.5,
        disable_silence_detection=False,
        vad_aggressiveness=None,
        chime_enabled=False,
        chime_leading_silence=None,
        chime_trailing_silence=None,
        transport="local",
        event_logger=None,
    )
    kwargs.update(overrides)
    return kwargs


# ---------------------------------------------------------------------------
# listen_and_transcribe() -- classified outcomes
# ---------------------------------------------------------------------------

class TestListenAndTranscribe:
    async def test_answered(self):
        def _record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def _stt(*_a, **_k):
            return {"text": "hello there", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=_stt):
            result = await listen_and_transcribe(**_listen_kwargs())

        assert isinstance(result, ListenResult)
        assert result.outcome == "answered"
        assert result.text == "hello there"
        assert result.stt_provider == "whisper-local"
        assert result.stt_classified is True
        assert "record" in result.timings and "stt" in result.timings

    async def test_no_speech_vad_level_skips_stt(self):
        """VAD never detected speech -- STT must not even be called."""
        def _record(*_a, **_k):
            return (np.zeros(10, dtype=np.int16), False)

        stt_spy = MagicMock(side_effect=AssertionError("STT must be skipped"))

        with patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=stt_spy):
            result = await listen_and_transcribe(**_listen_kwargs())

        assert result.outcome == "no_speech"
        assert result.text is None
        assert result.stt_classified is False
        stt_spy.assert_not_called()

    async def test_no_speech_stt_level(self):
        """VAD detected speech but STT classifies it as no_speech."""
        def _record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def _stt(*_a, **_k):
            return {"error_type": "no_speech", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=_stt):
            result = await listen_and_transcribe(**_listen_kwargs())

        assert result.outcome == "no_speech"
        assert result.text is None
        assert result.stt_classified is True

    async def test_stt_connection_failure(self):
        def _record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def _stt(*_a, **_k):
            return {
                "error_type": "connection_failed",
                "attempted_endpoints": [{"endpoint": "http://x", "error": "refused"}],
            }

        with patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=_stt):
            result = await listen_and_transcribe(**_listen_kwargs())

        assert result.outcome == "stt_error"
        assert "connection failed" in result.error_message.lower()
        assert "refused" in result.error_message
        # S2 (fable progress review): a stable machine-readable classifier,
        # not string-sniffed from the human-readable message.
        assert result.error_kind == "stt_connection_failed"
        # S3: STT genuinely ran here, but stt_classified is False because it
        # never produced a classification (connection failure, not a
        # text-or-no-speech verdict) -- the rename documents this precisely.
        assert result.stt_classified is False

    async def test_empty_buffer_without_skip_forward_is_stt_error(self):
        def _record(*_a, **_k):
            return (np.array([], dtype=np.int16), False)

        with patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record):
            result = await listen_and_transcribe(**_listen_kwargs())

        assert result.outcome == "stt_error"
        assert result.error_message == "Error: Could not record audio"
        # S2: distinct error_kind from the STT-connection-failure case above --
        # this is a record-side failure, STT was never even reached.
        assert result.error_kind == "record_failed"

    async def test_control_stop_after_recording(self):
        def _record(*_a, **_k):
            get_control_state().request_stop(hint="switch-to-text")
            return (np.zeros(2400, dtype=np.int16), True)

        stt_spy = MagicMock(side_effect=AssertionError("STT must be skipped on stop"))

        with patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=stt_spy):
            result = await listen_and_transcribe(**_listen_kwargs())

        assert result.outcome == "stopped"
        assert result.control is not None and result.control.is_stopped
        stt_spy.assert_not_called()

    async def test_skip_forward_ends_recording_early_but_still_transcribes(self):
        def _record(*_a, **_k):
            get_control_state().request_skip_forward()
            return (np.zeros(1200, dtype=np.int16), True)

        async def _stt(*_a, **_k):
            return {"text": "go now", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=_stt):
            result = await listen_and_transcribe(**_listen_kwargs())

        assert result.outcome == "answered"
        assert result.text == "go now"
        assert result.skip_forward_ended is True
        # The sticky skip_forward edge was consumed (VM-1754).
        assert not get_control_state().snapshot().is_skip_forward

    async def test_skip_forward_with_empty_capture_is_no_speech_not_error(self):
        def _record(*_a, **_k):
            get_control_state().request_skip_forward()
            return (np.array([], dtype=np.int16), True)

        stt_spy = MagicMock(side_effect=AssertionError("STT must be skipped"))

        with patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=stt_spy):
            result = await listen_and_transcribe(**_listen_kwargs())

        assert result.outcome == "no_speech"
        assert result.skip_forward_ended is True
        stt_spy.assert_not_called()

    async def test_pending_skip_back_signals_caller_without_consuming(self):
        get_control_state()  # ensure singleton exists

        def _record(*_a, **_k):
            get_control_state().request_skip_back()
            return (np.zeros(10, dtype=np.int16), False)

        stt_spy = MagicMock(side_effect=AssertionError("STT must be skipped"))

        with patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=stt_spy):
            result = await listen_and_transcribe(**_listen_kwargs())

        assert result.outcome == "skip_back"
        # Peeked only -- the caller (e.g. _drain_skip_back) still needs to
        # consume it.
        assert get_control_state().pending_transport == COMMAND_SKIP_BACK
        stt_spy.assert_not_called()

    async def test_pre_listen_pause_applied_when_given(self):
        with patch("voice_mode.tools.converse.asyncio.sleep", new=AsyncMock()) as mock_sleep, \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection",
                   return_value=(np.zeros(10, dtype=np.int16), False)):
            await listen_and_transcribe(**_listen_kwargs(pre_listen_pause=0.5))

        mock_sleep.assert_awaited_once_with(0.5)

    async def test_no_pre_listen_pause_by_default(self):
        with patch("voice_mode.tools.converse.asyncio.sleep", new=AsyncMock()) as mock_sleep, \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection",
                   return_value=(np.zeros(10, dtype=np.int16), False)):
            await listen_and_transcribe(**_listen_kwargs())

        mock_sleep.assert_not_awaited()


# ---------------------------------------------------------------------------
# Golden byte-equivalence: the single-message listen path's return string
# ---------------------------------------------------------------------------

async def _fake_tts_ok(*_a, **_k):
    return True, {"ttfa": 0.0, "generation": 0.0, "playback": 0.0}, {
        "provider": "kokoro", "voice": "af_sky",
    }


class TestGoldenSingleMessageListenPath:
    """The single-message listen path's return string, byte-for-byte, minimal
    metrics level (no timing floats to fuzz an exact-string comparison)."""

    async def test_answered_minimal(self):
        def _record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def _stt(*_a, **_k):
            return {"text": "forty two", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=_stt), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="What is the answer?",
                wait_for_response=True,
                metrics_level="minimal",
                skip_conch=True,
            )

        assert result == "Voice response: forty two"

    async def test_no_speech_minimal(self):
        def _record(*_a, **_k):
            return (np.zeros(10, dtype=np.int16), False)

        stt_spy = MagicMock(side_effect=AssertionError("STT must be skipped"))

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=stt_spy), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Anyone there?",
                wait_for_response=True,
                metrics_level="minimal",
                skip_conch=True,
            )

        assert result == "No speech detected"
        stt_spy.assert_not_called()

    async def test_answered_summary_shape(self):
        """summary (default) includes the response, STT provider, and a timing
        breakdown -- structure asserted, not exact floats (real perf_counter
        deltas make float-for-float comparison flaky)."""
        def _record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def _stt(*_a, **_k):
            return {"text": "forty two", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=_stt), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="What is the answer?",
                wait_for_response=True,
                skip_conch=True,
            )

        assert result.startswith("Voice response: forty two (STT: whisper-local) | Timing:")
        assert "record" in result and "stt" in result and "total" in result

    async def test_empty_recording_buffer_returns_bare_error(self):
        """Pre-extraction, an empty buffer (not a skip_forward) is a bare early
        return with no stats tracking -- preserved exactly."""
        def _record(*_a, **_k):
            return (np.array([], dtype=np.int16), False)

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Hello?",
                wait_for_response=True,
                skip_conch=True,
            )

        assert result == "Error: Could not record audio"

    async def test_stt_connection_failure_returns_bare_error(self):
        def _record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def _stt(*_a, **_k):
            return {
                "error_type": "connection_failed",
                "attempted_endpoints": [{"endpoint": "http://x", "error": "refused"}],
            }

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=_stt), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Hello?",
                wait_for_response=True,
                skip_conch=True,
            )

        assert result.startswith("STT service connection failed:")
        assert "refused" in result


# ---------------------------------------------------------------------------
# Repeat / wait re-listens: gained control-channel awareness (follow-up commit)
# ---------------------------------------------------------------------------

class TestRepeatWaitGainControlAwareness:
    async def test_stop_during_repeat_relisten_returns_control_marker(self):
        """Pre-extraction this re-listen had NO control checks at all -- a stop
        during it silently fell through. Now it ends the turn cleanly."""
        record_calls = {"n": 0}

        def _record(*_a, **_k):
            record_calls["n"] += 1
            if record_calls["n"] == 1:
                return (np.zeros(2400, dtype=np.int16), True)
            # Second listen (after "repeat") -- a stop arrives.
            get_control_state().request_stop(hint="switch-to-text")
            return (np.zeros(2400, dtype=np.int16), True)

        async def _stt(*_a, **_k):
            return {"text": "repeat", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.play_system_audio", new=AsyncMock()), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=_stt), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Long explanation...",
                wait_for_response=True,
                skip_conch=True,
            )

        assert result.startswith("[control: stop] ")
        assert record_calls["n"] == 2

    async def test_repeat_relisten_overwrites_response_only_when_stt_ran(self):
        """Matches the pre-extraction guard (len(audio) > 0 and speech_detected):
        a VAD-level no-speech re-listen leaves the prior response untouched."""
        record_calls = {"n": 0}

        def _record(*_a, **_k):
            record_calls["n"] += 1
            if record_calls["n"] == 1:
                return (np.zeros(2400, dtype=np.int16), True)
            return (np.zeros(10, dtype=np.int16), False)  # no speech on re-listen

        stt_calls = {"n": 0}

        async def _stt(*_a, **_k):
            stt_calls["n"] += 1
            return {"text": "repeat", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.play_system_audio", new=AsyncMock()), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=_stt), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Long explanation...",
                wait_for_response=True,
                metrics_level="minimal",
                skip_conch=True,
            )

        # STT ran once for the initial "repeat" capture only, never for the
        # re-listen (VAD reported no speech).
        assert stt_calls["n"] == 1
        assert result == "Voice response: repeat"

    # -----------------------------------------------------------------------
    # S4/S5/S6 (fable progress review, impl-003b): skip_back is no longer
    # silently swallowed on a repeat/wait re-listen; the re-listen no longer
    # emits its own event-log entries; an STT failure on a re-listen is
    # surfaced instead of hidden behind the prior "repeat"/"wait" utterance.
    # -----------------------------------------------------------------------

    async def test_repeat_relisten_skip_back_replays_then_relistens(self):
        """S4: a skip_back arriving during the repeat re-listen used to be
        silently swallowed (no replay, capture discarded, pending latched,
        "repeat" returned as the answer). Now it replays via the same
        shared history-buffer helper the main loop uses, then re-listens."""
        calls = {"n": 0}

        async def _fake_listen(*_a, **_k):
            calls["n"] += 1
            if calls["n"] == 1:
                # Initial listen -- captures "repeat".
                return ListenResult(outcome="answered", text="repeat",
                                     stt_provider="whisper-local", stt_classified=True)
            if calls["n"] == 2:
                # First repeat re-listen -- a skip_back arrives.
                return ListenResult(outcome="skip_back")
            # Second repeat re-listen (post skip_back replay) -- real answer.
            return ListenResult(outcome="answered", text="forty two",
                                 stt_provider="whisper-local", stt_classified=True)

        drain_spy = AsyncMock(side_effect=lambda cs, cursor: cursor)

        with patch("voice_mode.tools.converse.listen_and_transcribe", new=_fake_listen), \
             patch("voice_mode.tools.converse._drain_skip_back", new=drain_spy), \
             patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.play_system_audio", new=AsyncMock()), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Long explanation...",
                wait_for_response=True,
                metrics_level="minimal",
                skip_conch=True,
            )

        # 1 main listen + 2 repeat re-listens (skip_back, then the real answer).
        assert calls["n"] == 3
        # _drain_skip_back is consulted once per loop iteration (main loop's
        # own iteration, then each repeat re-listen iteration) -- mirroring
        # the main loop's replay-then-relisten shape.
        assert drain_spy.await_count == 3
        assert result == "Voice response: forty two"

    async def test_repeat_relisten_does_not_emit_its_own_events(self):
        """S5: the repeat re-listen must NOT emit its own
        RECORDING_START/RECORDING_END/STT_START -- restoring master's
        event-log cardinality (previously: 2 STT_START for 1 STT_COMPLETE)."""

        class _FakeEventLogger:
            RECORDING_START = "RECORDING_START"
            RECORDING_END = "RECORDING_END"
            STT_START = "STT_START"
            STT_COMPLETE = "STT_COMPLETE"
            STT_NO_SPEECH = "STT_NO_SPEECH"

            def __init__(self):
                self.events = []

            def log_event(self, event_type, data=None):
                self.events.append(event_type)

            def start_session(self, session_id=None):
                return session_id or "fake-session"

            def end_session(self):
                return None

        fake_event_logger = _FakeEventLogger()
        record_calls = {"n": 0}

        def _record(*_a, **_k):
            record_calls["n"] += 1
            return (np.zeros(2400, dtype=np.int16), True)

        async def _stt(*_a, **_k):
            if record_calls["n"] == 1:
                return {"text": "repeat", "provider": "whisper-local"}
            return {"text": "forty two", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.get_event_logger", return_value=fake_event_logger), \
             patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.play_system_audio", new=AsyncMock()), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=_stt), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Long explanation...",
                wait_for_response=True,
                metrics_level="minimal",
                skip_conch=True,
            )

        assert record_calls["n"] == 2
        assert result == "Voice response: forty two"
        # Only ONE RECORDING_START/END/STT_START -- from the initial listen;
        # the repeat re-listen contributes none of its own.
        assert fake_event_logger.events.count("RECORDING_START") == 1
        assert fake_event_logger.events.count("RECORDING_END") == 1
        assert fake_event_logger.events.count("STT_START") == 1

    async def test_repeat_relisten_stt_error_is_surfaced_not_hidden(self):
        """S6: an STT failure during the repeat re-listen must surface the
        STT error (matching the main listen path's behaviour), not silently
        present the "repeat" utterance itself as the user's answer."""
        calls = {"n": 0}

        async def _fake_listen(*_a, **_k):
            calls["n"] += 1
            if calls["n"] == 1:
                return ListenResult(outcome="answered", text="repeat",
                                     stt_provider="whisper-local", stt_classified=True)
            return ListenResult(
                outcome="stt_error",
                error_message="STT service connection failed:\n  - http://x: refused",
                error_kind="stt_connection_failed",
            )

        with patch("voice_mode.tools.converse.listen_and_transcribe", new=_fake_listen), \
             patch("voice_mode.tools.converse._drain_skip_back",
                   new=AsyncMock(side_effect=lambda cs, cursor: cursor)), \
             patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.play_system_audio", new=AsyncMock()), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Long explanation...",
                wait_for_response=True,
                metrics_level="minimal",
                skip_conch=True,
            )

        assert result.startswith("STT service connection failed:")
        assert "repeat" not in result

    # -----------------------------------------------------------------------
    # F1 (fable pre-merge audit): the repeat/wait re-listen loops were
    # missing the main listen path's VM-1763 consume -- a skip_forward
    # pressed during/around the _drain_skip_back replay left the sticky
    # STATE_SKIP_FORWARD latch armed into the IMMEDIATE re-listen, whose
    # record loop then exits on its very first poll with an (near-)empty
    # capture (stt_classified stays False), silently returning the stale
    # "repeat"/"wait" utterance as the final answer instead of listening for
    # real -- the precise misleading return S4/S6 were built to kill.
    # -----------------------------------------------------------------------

    async def test_repeat_relisten_skip_forward_during_skip_back_replay_is_consumed(self):
        record_calls = {"n": 0}

        def _record(*_a, **_k):
            record_calls["n"] += 1
            if record_calls["n"] == 1:
                return (np.zeros(2400, dtype=np.int16), True)  # initial "repeat" capture
            # Second listen (post skip_back replay): faithfully reproduce the
            # real record loop -- an already-armed sticky skip_forward ends
            # recording on its very first poll.
            if get_control_state().snapshot().is_skip_forward:
                return (np.zeros(0, dtype=np.int16), False)
            return (np.zeros(2400, dtype=np.int16), True)

        stt_texts = ["repeat", "forty two"]

        async def _stt(*_a, **_k):
            return {"text": stt_texts.pop(0), "provider": "whisper-local"}

        drain_calls = {"n": 0}

        async def _drain_that_arms_skip_forward(control_state, cursor):
            drain_calls["n"] += 1
            if drain_calls["n"] == 2:
                # The repeat re-listen's OWN drain call -- simulate a
                # skip_forward pressed DURING the replay it manages.
                # play_cached_utterance stops playback but (like
                # _play_samples_controllable) does not reset the sticky
                # latch itself.
                get_control_state().request_skip_forward()
            return cursor

        with patch("voice_mode.tools.converse._drain_skip_back", new=_drain_that_arms_skip_forward), \
             patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.play_system_audio", new=AsyncMock()), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=_stt), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Long explanation...",
                wait_for_response=True,
                metrics_level="minimal",
                skip_conch=True,
            )

        assert record_calls["n"] == 2
        assert result == "Voice response: forty two"
        assert get_control_state().snapshot().is_skip_forward is False

    async def test_wait_relisten_skip_forward_during_skip_back_replay_is_consumed(self):
        record_calls = {"n": 0}

        def _record(*_a, **_k):
            record_calls["n"] += 1
            if record_calls["n"] == 1:
                return (np.zeros(2400, dtype=np.int16), True)  # initial "wait" capture
            if get_control_state().snapshot().is_skip_forward:
                return (np.zeros(0, dtype=np.int16), False)
            return (np.zeros(2400, dtype=np.int16), True)

        stt_texts = ["wait", "ready now"]

        async def _stt(*_a, **_k):
            return {"text": stt_texts.pop(0), "provider": "whisper-local"}

        drain_calls = {"n": 0}

        async def _drain_that_arms_skip_forward(control_state, cursor):
            drain_calls["n"] += 1
            if drain_calls["n"] == 2:
                get_control_state().request_skip_forward()
            return cursor

        with patch("voice_mode.tools.converse._drain_skip_back", new=_drain_that_arms_skip_forward), \
             patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.play_system_audio", new=AsyncMock()), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=_stt), \
             patch("voice_mode.tools.converse.asyncio.sleep", new=AsyncMock()), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Long explanation...",
                wait_for_response=True,
                metrics_level="minimal",
                skip_conch=True,
            )

        assert record_calls["n"] == 2
        assert result == "Voice response: ready now"
        assert get_control_state().snapshot().is_skip_forward is False

    async def test_repeat_relisten_stop_during_skip_back_replay_ends_turn(self):
        """A stop pressed during the repeat re-listen's own skip_back replay
        must end the turn immediately -- not fall through to another
        (spurious) listen."""
        record_calls = {"n": 0}

        def _record(*_a, **_k):
            record_calls["n"] += 1
            return (np.zeros(2400, dtype=np.int16), True)

        async def _stt(*_a, **_k):
            return {"text": "repeat", "provider": "whisper-local"}

        drain_calls = {"n": 0}

        async def _drain_that_stops(control_state, cursor):
            drain_calls["n"] += 1
            if drain_calls["n"] == 2:
                get_control_state().request_stop(hint="switch-to-text")
            return cursor

        with patch("voice_mode.tools.converse._drain_skip_back", new=_drain_that_stops), \
             patch("voice_mode.tools.converse.text_to_speech_with_failover", new=_fake_tts_ok), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.play_system_audio", new=AsyncMock()), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=_stt), \
             patch("voice_mode.config.TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.config.OPENAI_API_KEY", "test-api-key"):
            result = await _converse_fn()(
                message="Long explanation...",
                wait_for_response=True,
                skip_conch=True,
            )

        assert result.startswith("[control: stop] ")
        # Only ONE real record call (the initial "repeat" capture) -- the
        # stop during the re-listen's own replay ends the turn before a
        # second listen ever starts.
        assert record_calls["n"] == 1
