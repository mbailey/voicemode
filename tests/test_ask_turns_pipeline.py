"""Tests for the survey loop `_ask_turns_pipeline` (VM-1775 impl-002).

Slice 2 builds the module-level sibling of `_speak_turns_pipeline` that also
collects a reply after each `ask` turn: producer/consumer pipelining, the
control matrix (stop/skip_forward/skip_back per phase), should_repeat/
should_wait rescoped per ask turn, standalone break phrases, and the
per-turn failure policy. This slice does NOT wire the pipeline into
converse()'s dispatch or the JSON return contract -- see impl-003.

Coverage:
  * `_is_survey_break` -- standalone-only matcher (no false positives).
  * `_play_samples_controllable` -- polls the control channel, aborts on
    stop/skip_forward.
  * `_ask_turns_pipeline` -- ordering/pipelining, per-turn failure policy,
    the control matrix, keyword rescoping, and the alignment invariant
    (results always length N) across every abort path.
"""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from voice_mode.control_channel import get_control_state
from voice_mode.tools.converse import (
    _ask_turns_pipeline,
    _is_survey_break,
    _normalize_turns,
    _play_samples_controllable,
)


def _samples():
    return np.zeros(16, dtype=np.float32)


def _norm(items, default_pause=0, default_voice="default"):
    return _normalize_turns(
        items, default_voice=default_voice, default_pause_after_ms=default_pause,
        default_tts_instructions=None, default_speed=None,
    )


async def _noop_feedback(*_a, **_k):
    return None


@pytest.fixture(autouse=True)
def reset_control_state():
    """Keep the process-wide control singleton clean around every test."""
    get_control_state().reset()
    yield
    get_control_state().reset()


def _pipeline_kwargs(**overrides):
    kwargs = dict(
        tts_model=None,
        tts_provider=None,
        audio_format=None,
        resolved_ref_text=None,
        should_skip_tts=False,
        control_state=get_control_state(),
        disable_silence_detection=False,
        chime_enabled=False,
        chime_leading_silence=None,
        chime_trailing_silence=None,
        transport="local",
        event_logger=None,
    )
    kwargs.update(overrides)
    return kwargs


def _ok_synth(*, message, voice, **_kw):
    return (True, _samples(), 24000, {"generation": 0.0}, {})


def _make_play_fn(outcomes_by_call=None, default="played"):
    """A fake `_play_samples_controllable` that returns scripted outcomes.

    ``outcomes_by_call`` is a list consumed in call order; when exhausted,
    ``default`` is returned.
    """
    calls = []
    queue = list(outcomes_by_call or [])

    async def fake_play(samples, sample_rate, control_state):
        calls.append((samples, sample_rate))
        if queue:
            return queue.pop(0)
        return default

    fake_play.calls = calls
    return fake_play


# ---------------------------------------------------------------------------
# _is_survey_break
# ---------------------------------------------------------------------------

class TestIsSurveyBreak:
    @pytest.mark.parametrize("text", [
        "break", "Break!", "  break  ", "stop the survey", "END SURVEY",
        "cancel the survey",
    ])
    def test_standalone_break_phrases_match(self, text):
        assert _is_survey_break(text) is True

    @pytest.mark.parametrize("text", [
        "I don't want to break up the work",
        "let's take a break later",
        "no",
        "",
        None,
        "stop",  # bare "stop" deliberately excluded -- too common in answers
    ])
    def test_non_standalone_or_unrelated_text_is_not_a_break(self, text):
        assert _is_survey_break(text) is False


# ---------------------------------------------------------------------------
# _play_samples_controllable
# ---------------------------------------------------------------------------

class _FakePlayer:
    """Stand-in for NonBlockingAudioPlayer that never actually touches audio
    hardware. ``playback_complete`` starts unset so the poll loop keeps
    running until the test (via control_state) tells it to stop."""

    def __init__(self, already_complete=False):
        self.playback_complete = threading.Event()
        if already_complete:
            self.playback_complete.set()
        self.stream = "fake-stream"
        self.stopped = False
        self.waited = False

    def play(self, samples, sample_rate, blocking=False):
        pass

    def stop(self):
        self.stopped = True
        self.playback_complete.set()

    def wait(self, timeout=None):
        self.waited = True
        # Mirror NonBlockingAudioPlayer.wait(): clears the stream once
        # playback finishes, so our own instant-abort ``finally`` guard
        # doesn't call stop() a second time after a clean completion.
        self.stream = None


class TestPlaySamplesControllable:
    async def test_plays_to_completion_when_never_interrupted(self):
        player = _FakePlayer(already_complete=True)
        with patch("voice_mode.tools.converse.NonBlockingAudioPlayer", return_value=player):
            outcome = await _play_samples_controllable(_samples(), 24000, get_control_state())
        assert outcome == "played"
        assert player.waited is True
        assert player.stopped is False

    async def test_stop_aborts_playback_instantly(self):
        player = _FakePlayer(already_complete=False)
        control_state = get_control_state()
        control_state.request_stop()
        with patch("voice_mode.tools.converse.NonBlockingAudioPlayer", return_value=player):
            outcome = await _play_samples_controllable(
                _samples(), 24000, control_state, poll_interval=0.001,
            )
        assert outcome == "stopped"
        assert player.stopped is True

    async def test_skip_forward_aborts_playback_instantly(self):
        player = _FakePlayer(already_complete=False)
        control_state = get_control_state()
        control_state.request_skip_forward()
        with patch("voice_mode.tools.converse.NonBlockingAudioPlayer", return_value=player):
            outcome = await _play_samples_controllable(
                _samples(), 24000, control_state, poll_interval=0.001,
            )
        assert outcome == "skip_forward"
        assert player.stopped is True


# ---------------------------------------------------------------------------
# _ask_turns_pipeline -- ordering, pipelining, alignment
# ---------------------------------------------------------------------------

class TestPipelineBasic:
    async def test_full_completion_mixed_say_ask(self):
        turns = _norm([
            {"say": "Welcome."},
            {"ask": "What color?"},
            {"say": "Thanks."},
            {"ask": "Favorite animal?"},
        ])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        stt_calls = {"n": 0}

        async def fake_stt(*_a, **_k):
            stt_calls["n"] += 1
            texts = ["blue", "a swallow"]
            return {"text": texts[stt_calls["n"] - 1], "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert len(results) == 4
        assert [r["index"] for r in results] == [0, 1, 2, 3]
        assert results[0]["verb"] == "say" and results[0]["status"] == "spoken"
        assert "reply" not in results[0]
        assert results[1]["verb"] == "ask" and results[1]["status"] == "answered"
        assert results[1]["reply"] == "blue"
        assert results[2]["status"] == "spoken"
        assert results[3]["status"] == "answered" and results[3]["reply"] == "a swallow"

    async def test_producer_synthesizes_ahead_while_listening(self):
        """Pipelining preserved: the producer synthesizes the NEXT turn while
        the current ask turn is still listening (no synth barrier at ask
        turns)."""
        turns = _norm([{"ask": "Q1"}, {"say": "Q2 followup"}])
        synth_calls = []
        next_turn_synthesized = threading.Event()

        async def tracking_synth(*, message, voice, **_kw):
            synth_calls.append(message)
            if message == "Q2 followup":
                next_turn_synthesized.set()
            return (True, _samples(), 24000, {"generation": 0.0}, {})

        def fake_record(*_a, **_k):
            # By the time we're recording turn 0's answer, the producer
            # should already be (or about to be) synthesizing turn 1.
            got = next_turn_synthesized.wait(timeout=2.0)
            assert got, "producer did not synthesize the next turn during the listen"
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "an answer", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=tracking_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert synth_calls == ["Q1", "Q2 followup"]
        assert results[0]["status"] == "answered"
        assert results[1]["status"] == "spoken"

    async def test_alignment_invariant_holds_on_full_completion(self):
        turns = _norm([{"say": "a"}, {"ask": "b"}, {"say": "c"}])

        def fake_record(*_a, **_k):
            return (np.zeros(10, dtype=np.int16), False)  # no speech

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert len(results) == 3
        assert results[1]["status"] == "no_speech" and results[1]["reply"] is None


# ---------------------------------------------------------------------------
# _ask_turns_pipeline -- per-turn failure policy
# ---------------------------------------------------------------------------

class TestPipelineFailurePolicy:
    async def test_tts_failure_on_say_turn_skips_playback_and_continues(self):
        turns = _norm([{"say": "one"}, {"say": "two"}])

        async def failing_synth(*, message, **_kw):
            if message == "one":
                return (False, None, None, {}, {"error_type": "all_providers_failed"})
            return _ok_synth(message=message, voice=None)

        play_fn = _make_play_fn()
        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=failing_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=play_fn):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert results[0]["status"] == "tts_failed"
        assert results[1]["status"] == "spoken"
        # Only the second turn's audio ever played.
        assert len(play_fn.calls) == 1

    async def test_tts_failure_on_ask_turn_skips_listen_entirely(self):
        turns = _norm([{"ask": "unheard question"}, {"say": "continues"}])

        async def failing_synth(*, message, **_kw):
            if message == "unheard question":
                return (False, None, None, {}, {"error_type": "all_providers_failed"})
            return _ok_synth(message=message, voice=None)

        listen_spy = AsyncMock(side_effect=AssertionError("must not listen after tts_failed"))
        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=failing_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.listen_and_transcribe", new=listen_spy):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert results[0]["status"] == "tts_failed"
        assert results[0]["reply"] is None
        assert results[1]["status"] == "spoken"
        listen_spy.assert_not_awaited()

    async def test_stt_connection_failure_aborts_with_partials(self):
        turns = _norm([{"ask": "q1"}, {"ask": "q2"}, {"ask": "q3"}])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {
                "error_type": "connection_failed",
                "attempted_endpoints": [{"endpoint": "http://x", "error": "refused"}],
            }

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at == {"turn": 0, "phase": "listening", "reason": "stt_connection_failed"}
        assert len(results) == 3
        assert results[0]["status"] == "stt_failed"
        assert results[1]["status"] == "not_reached"
        assert results[2]["status"] == "not_reached"

    async def test_audio_device_exception_mid_record_aborts_with_partials(self):
        turns = _norm([{"ask": "q1"}, {"ask": "q2"}])

        def raising_record(*_a, **_k):
            raise OSError("device unavailable")

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=raising_record):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at == {"turn": 0, "phase": "listening", "reason": "audio_device_error"}
        assert results[0]["status"] == "stt_failed"
        assert results[1]["status"] == "not_reached"

    async def test_empty_recording_buffer_aborts_as_audio_device_error(self):
        """listen_and_transcribe's non-connection stt_error (an empty buffer,
        not a skip_forward) maps to audio_device_error, not stt_connection_failed."""
        turns = _norm([{"ask": "q1"}, {"ask": "q2"}])

        def empty_record(*_a, **_k):
            return (np.array([], dtype=np.int16), False)

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=empty_record):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at == {"turn": 0, "phase": "listening", "reason": "audio_device_error"}
        assert results[0]["status"] == "stt_failed"
        assert results[1]["status"] == "not_reached"

    async def test_generic_exception_mid_pipeline_aborts_with_partials_reason_error(self):
        """N-e (fable pre-merge audit): the generic-exception branch (reason
        "error") previously had no test of its own -- only its
        CancelledError twin was covered (impl-003)."""
        turns = _norm([{"say": "a"}, {"ask": "b"}])

        async def boom(*_a, **_k):
            raise RuntimeError("synthetic unexpected failure")

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=boom):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at == {"turn": 0, "phase": "speaking", "reason": "error"}
        assert results[0]["status"] == "not_reached"
        assert results[1]["status"] == "not_reached"


# ---------------------------------------------------------------------------
# _ask_turns_pipeline -- control matrix
# ---------------------------------------------------------------------------

class TestPipelineControlMatrix:
    async def test_stop_during_speaking_ends_survey_with_partials(self):
        turns = _norm([{"say": "a"}, {"ask": "b"}, {"say": "c"}])
        play_fn = _make_play_fn(outcomes_by_call=["stopped"])
        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=play_fn):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at == {"turn": 0, "phase": "speaking", "reason": "stop"}
        assert len(results) == 3
        assert results[0]["status"] == "spoken"     # cut mid-play, most-truthful status
        assert results[1]["status"] == "not_reached"
        assert results[2]["status"] == "not_reached"

    async def test_stop_during_listening_ends_survey_with_partials(self):
        turns = _norm([{"ask": "q1"}, {"ask": "q2"}])

        def fake_record(*_a, **_k):
            get_control_state().request_stop()
            return (np.zeros(2400, dtype=np.int16), True)

        stt_spy = AsyncMock(side_effect=AssertionError("STT must be skipped on stop"))
        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=stt_spy):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at == {"turn": 0, "phase": "listening", "reason": "stop"}
        assert results[0]["status"] == "no_speech" and results[0]["reply"] is None
        assert results[1]["status"] == "not_reached"
        stt_spy.assert_not_awaited()

    async def test_skip_forward_during_say_playback_advances(self):
        turns = _norm([{"say": "a"}, {"say": "b"}])
        play_fn = _make_play_fn(outcomes_by_call=["skip_forward"])
        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=play_fn):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert results[0]["status"] == "spoken"
        assert results[1]["status"] == "spoken"
        # skip_forward never breaks -- both turns are reached.
        assert len(play_fn.calls) == 2

    async def test_skip_forward_during_ask_playback_is_answer_early(self):
        """skip_forward while an ask turn's question is still playing jumps
        straight into LISTEN (the documented "answer early" barge-in)."""
        turns = _norm([{"ask": "long question"}])
        play_fn = _make_play_fn(outcomes_by_call=["skip_forward"])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "early answer", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=play_fn), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert results[0]["status"] == "answered"
        assert results[0]["reply"] == "early answer"

    async def test_skip_forward_during_listening_ends_capture_and_advances(self):
        """listen_and_transcribe's own skip_forward_ended handling: whatever
        was captured is transcribed and the turn advances (VM-1754)."""
        turns = _norm([{"ask": "q1"}])

        def fake_record(*_a, **_k):
            get_control_state().request_skip_forward()
            return (np.zeros(1200, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "go now", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert results[0]["status"] == "answered" and results[0]["reply"] == "go now"

    async def test_skip_back_during_listening_replays_and_relistens(self):
        turns = _norm([{"ask": "q1"}])
        record_calls = {"n": 0}

        def fake_record(*_a, **_k):
            record_calls["n"] += 1
            if record_calls["n"] == 1:
                get_control_state().request_skip_back()
                return (np.zeros(10, dtype=np.int16), False)
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "final answer", "provider": "whisper-local"}

        play_fn = _make_play_fn()
        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=play_fn), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert record_calls["n"] == 2
        # Initial play + one skip_back replay.
        assert len(play_fn.calls) == 2
        assert results[0]["status"] == "answered" and results[0]["reply"] == "final answer"

    # -------------------------------------------------------------------
    # F1 (fable pre-merge audit): skip_forward during a replayed question
    # used to discard _play_samples_controllable's outcome, leaving the
    # sticky STATE_SKIP_FORWARD latch armed into the immediate re-listen and
    # silently destroying the answer window (turn resolved no_speech). A
    # stop during the replay itself used to fall through to another
    # (spurious) listen/chime instead of ending the survey there.
    # -------------------------------------------------------------------

    async def test_skip_forward_during_skip_back_replay_does_not_forfeit_answer(self):
        turns = _norm([{"ask": "q1"}])
        record_calls = {"n": 0}

        def fake_record(*_a, **_k):
            record_calls["n"] += 1
            if record_calls["n"] == 1:
                # First listen: user presses skip_back mid-recording.
                get_control_state().request_skip_back()
                return (np.zeros(10, dtype=np.int16), False)
            # Second listen (post skip_back replay): faithfully reproduce
            # the real record loop's behaviour -- if the sticky skip_forward
            # latch from the replay survived, it exits on its very first
            # poll with an (near-)empty, unclassified capture.
            if get_control_state().snapshot().is_skip_forward:
                return (np.zeros(0, dtype=np.int16), False)
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "final answer", "provider": "whisper-local"}

        play_calls = {"n": 0}

        async def fake_play(samples, sample_rate, control_state):
            play_calls["n"] += 1
            if play_calls["n"] == 1:
                return "played"  # initial question playback
            # The skip_back replay -- barge in with skip_forward ("cut the
            # replay, let me answer"). The real _play_samples_controllable
            # never resets the sticky latch itself (only stops playback) --
            # mirror that here.
            get_control_state().request_skip_forward()
            return "skip_forward"

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=fake_play), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert record_calls["n"] == 2
        assert results[0]["status"] == "answered" and results[0]["reply"] == "final answer"

    async def test_stop_during_skip_back_replay_ends_survey_immediately(self):
        turns = _norm([{"ask": "q1"}, {"ask": "q2"}])
        record_calls = {"n": 0}

        def fake_record(*_a, **_k):
            record_calls["n"] += 1
            get_control_state().request_skip_back()
            return (np.zeros(10, dtype=np.int16), False)

        play_calls = {"n": 0}

        async def fake_play(samples, sample_rate, control_state):
            play_calls["n"] += 1
            if play_calls["n"] == 1:
                return "played"
            get_control_state().request_stop()
            return "stopped"

        stt_spy = AsyncMock(side_effect=AssertionError("STT must not run after a stop-during-replay"))

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=fake_play), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=stt_spy):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at == {"turn": 0, "phase": "listening", "reason": "stop"}
        assert results[0]["status"] == "no_speech" and results[0]["reply"] is None
        assert results[1]["status"] == "not_reached"
        stt_spy.assert_not_awaited()
        assert play_calls["n"] == 2
        # Only ONE listen/record call before the replay-stop ends the survey
        # -- no spurious second listen (and its "listening" chime) after the
        # replay was already stopped.
        assert record_calls["n"] == 1

    async def test_skip_forward_during_repeat_replay_does_not_forfeit_answer(self):
        turns = _norm([{"ask": "q1"}])
        record_calls = {"n": 0}

        def fake_record(*_a, **_k):
            record_calls["n"] += 1
            if record_calls["n"] == 1:
                return (np.zeros(2400, dtype=np.int16), True)  # initial "repeat" capture
            # Second listen (post repeat replay): faithfully reproduce the
            # real record loop's behaviour -- an armed sticky skip_forward
            # ends recording on its very first poll.
            if get_control_state().snapshot().is_skip_forward:
                return (np.zeros(0, dtype=np.int16), False)
            return (np.zeros(2400, dtype=np.int16), True)

        stt_texts = ["repeat", "final answer"]

        async def fake_stt(*_a, **_k):
            return {"text": stt_texts.pop(0), "provider": "whisper-local"}

        play_calls = {"n": 0}

        async def fake_play(samples, sample_rate, control_state):
            play_calls["n"] += 1
            if play_calls["n"] == 1:
                return "played"  # initial question playback
            # The repeat replay -- barge in with skip_forward mid-replay.
            get_control_state().request_skip_forward()
            return "skip_forward"

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=fake_play), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert record_calls["n"] == 2
        assert results[0]["status"] == "answered" and results[0]["reply"] == "final answer"


# ---------------------------------------------------------------------------
# _ask_turns_pipeline -- keyword rescoping (repeat / wait / break)
# ---------------------------------------------------------------------------

class TestPipelineKeywords:
    async def test_should_repeat_replays_cached_samples_then_relistens(self):
        turns = _norm([{"ask": "q1"}])
        record_calls = {"n": 0}

        def fake_record(*_a, **_k):
            record_calls["n"] += 1
            return (np.zeros(2400, dtype=np.int16), True)

        stt_texts = ["repeat", "the real answer"]

        async def fake_stt(*_a, **_k):
            return {"text": stt_texts.pop(0), "provider": "whisper-local"}

        play_fn = _make_play_fn()
        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=play_fn), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert record_calls["n"] == 2
        assert len(play_fn.calls) == 2  # initial play + repeat replay
        assert results[0]["status"] == "answered" and results[0]["reply"] == "the real answer"

    async def test_should_wait_pauses_then_relistens(self):
        turns = _norm([{"ask": "q1"}])
        record_calls = {"n": 0}

        def fake_record(*_a, **_k):
            record_calls["n"] += 1
            return (np.zeros(2400, dtype=np.int16), True)

        stt_texts = ["wait", "ready now"]

        async def fake_stt(*_a, **_k):
            return {"text": stt_texts.pop(0), "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt), \
             patch("voice_mode.tools.converse.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert record_calls["n"] == 2
        assert results[0]["status"] == "answered" and results[0]["reply"] == "ready now"
        # WAIT_DURATION sleep was awaited (no replay for "wait", unlike repeat).
        from voice_mode.config import WAIT_DURATION
        assert any(c.args and c.args[0] == WAIT_DURATION for c in mock_sleep.await_args_list)

    async def test_spoken_break_ends_survey_reply_not_recorded(self):
        turns = _norm([{"ask": "q1"}, {"ask": "q2"}])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "break", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at == {"turn": 0, "phase": "listening", "reason": "spoken_break"}
        assert results[0]["status"] == "no_speech" and results[0]["reply"] is None
        assert results[1]["status"] == "not_reached"

    async def test_reply_merely_containing_break_word_is_not_treated_as_break(self):
        turns = _norm([{"ask": "q1"}, {"ask": "q2"}])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        stt_texts = ["I don't want to break up the work", "second answer"]

        async def fake_stt(*_a, **_k):
            return {"text": stt_texts.pop(0), "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert results[0]["status"] == "answered"
        assert results[0]["reply"] == "I don't want to break up the work"
        assert results[1]["status"] == "answered" and results[1]["reply"] == "second answer"


# ---------------------------------------------------------------------------
# _ask_turns_pipeline -- should_skip_tts (dev/test switch) still listens on ask
# ---------------------------------------------------------------------------

class TestPipelineSkipTts:
    async def test_skip_tts_plays_nothing_but_still_listens_on_ask(self):
        turns = _norm([{"say": "a"}, {"ask": "b"}])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "an answer", "provider": "whisper-local"}

        synth_spy = AsyncMock(side_effect=AssertionError("must not synthesize when should_skip_tts"))
        play_fn = _make_play_fn()
        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", new=synth_spy), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=play_fn), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(
                turns, **_pipeline_kwargs(should_skip_tts=True),
            )

        assert stopped_at is None
        synth_spy.assert_not_awaited()
        assert len(play_fn.calls) == 0  # skipped samples never call playback
        assert results[0]["status"] == "spoken"
        assert results[1]["status"] == "answered" and results[1]["reply"] == "an answer"


# ---------------------------------------------------------------------------
# _ask_turns_pipeline -- S8 (fable progress review): per-exchange
# conversation logging, so a killed/cancelled call still leaves every
# already-answered reply in the conversation logs (Decision 7).
# ---------------------------------------------------------------------------

class TestPipelineConversationLogging:
    async def test_each_ask_reply_is_logged_at_capture_time(self):
        """Every resolved ask-turn (answered or no_speech) calls
        conversation_logger.log_stt the moment it's captured, not batched at
        the end of the survey."""
        turns = _norm([{"ask": "Q1"}, {"say": "thanks"}, {"ask": "Q2"}])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        stt_calls = {"n": 0}

        async def fake_stt(*_a, **_k):
            stt_calls["n"] += 1
            texts = ["blue", "a swallow"]
            return {"text": texts[stt_calls["n"] - 1], "provider": "whisper-local"}

        fake_logger = MagicMock()
        with patch("voice_mode.tools.converse.get_conversation_logger", return_value=fake_logger), \
             patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert fake_logger.log_stt.call_count == 2  # one per ask turn, not per survey
        logged_texts = [c.kwargs.get("text") for c in fake_logger.log_stt.call_args_list]
        assert logged_texts == ["blue", "a swallow"]

    async def test_reply_logged_before_a_later_abort_survives(self):
        """The whole point: if the survey aborts on turn 1, turn 0's reply
        was already persisted to the conversation log before the abort --
        crash-persistence doesn't depend on the survey ever finishing."""
        turns = _norm([{"ask": "Q1"}, {"ask": "Q2"}])

        call_n = {"n": 0}

        def fake_record(*_a, **_k):
            call_n["n"] += 1
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            if call_n["n"] == 1:
                return {"text": "first answer", "provider": "whisper-local"}
            return {
                "error_type": "connection_failed",
                "attempted_endpoints": [{"endpoint": "http://x", "error": "refused"}],
            }

        fake_logger = MagicMock()
        with patch("voice_mode.tools.converse.get_conversation_logger", return_value=fake_logger), \
             patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at == {"turn": 1, "phase": "listening", "reason": "stt_connection_failed"}
        assert results[0]["status"] == "answered" and results[0]["reply"] == "first answer"
        assert results[1]["status"] == "stt_failed"
        # Only turn 0's reply was ever logged -- turn 1 aborted before
        # resolving, but turn 0's reply is already durably logged.
        assert fake_logger.log_stt.call_count == 1
        assert fake_logger.log_stt.call_args_list[0].kwargs.get("text") == "first answer"

    async def test_no_speech_reply_is_logged_as_no_speech_marker(self):
        turns = _norm([{"ask": "Q1"}])

        def fake_record(*_a, **_k):
            return (np.zeros(10, dtype=np.int16), False)  # no speech

        fake_logger = MagicMock()
        with patch("voice_mode.tools.converse.get_conversation_logger", return_value=fake_logger), \
             patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert results[0]["status"] == "no_speech"
        fake_logger.log_stt.assert_called_once()
        assert fake_logger.log_stt.call_args.kwargs.get("text") == "[no speech detected]"

    async def test_logging_failure_does_not_break_the_survey(self):
        """A conversation-log write failure must not abort the survey or
        lose the reply from the return value -- only the durability side
        effect is best-effort."""
        turns = _norm([{"ask": "Q1"}])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "an answer", "provider": "whisper-local"}

        fake_logger = MagicMock()
        fake_logger.log_stt.side_effect = OSError("disk full")
        with patch("voice_mode.tools.converse.get_conversation_logger", return_value=fake_logger), \
             patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        assert results[0]["status"] == "answered" and results[0]["reply"] == "an answer"

    async def test_ask_reply_logged_with_survey_transport_not_stt_transport(self):
        """F2 (fable pre-merge audit): the log entry's own "transport" label
        must be "survey" -- decoupled from the STT-transport parameter
        (always "local" today) -- so scripts/verify-survey.sh's
        conversation-log assertion (which filters on transport=="survey")
        can actually pass, and survey replies are queryable/distinguishable
        from single-message "local" entries."""
        turns = _norm([{"ask": "Q1"}])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "blue", "provider": "whisper-local"}

        fake_logger = MagicMock()
        with patch("voice_mode.tools.converse.get_conversation_logger", return_value=fake_logger), \
             patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs(transport="local"))

        assert stopped_at is None
        fake_logger.log_stt.assert_called_once()
        assert fake_logger.log_stt.call_args.kwargs.get("transport") == "survey"


# ---------------------------------------------------------------------------
# F4 (fable pre-merge audit): survey mode must not emit unpaired STT_START
# events -- reintroducing on the new surface the exact cardinality problem
# impl-003b's S5 fix cleaned up for the single-message repeat/wait re-listens.
# ---------------------------------------------------------------------------

class TestPipelineEventLogCardinality:
    async def test_ask_turn_listen_never_emits_recording_or_stt_events(self):
        turns = _norm([{"ask": "Q1"}, {"ask": "Q2"}])

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

        fake_event_logger = _FakeEventLogger()

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "an answer", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(
                turns, **_pipeline_kwargs(event_logger=fake_event_logger),
            )

        assert stopped_at is None
        assert all(r["status"] == "answered" for r in results)
        # A 2-ask survey used to ship >=2 unpaired STT_START / 0 STT_COMPLETE
        # -- now it emits none of the single-message path's per-listen events
        # from the survey pipeline at all.
        assert fake_event_logger.events == []


# ---------------------------------------------------------------------------
# _normalize_turns -- ack opt-in surface (VM-1859 R4)
# ---------------------------------------------------------------------------

class TestNormalizeAck:
    def test_ack_defaults_off(self):
        """No `ack` key and no call-level default => cue opt-in is False."""
        turns = _norm([{"ask": "q"}])
        assert turns[0]["ack"] is False

    def test_per_turn_ack_true(self):
        turns = _norm([{"ask": "q", "ack": True}])
        assert turns[0]["ack"] is True

    def test_call_level_default_switches_all_ask_turns_on(self):
        turns = _normalize_turns(
            [{"ask": "q1"}, {"say": "s"}, {"ask": "q2"}],
            default_voice="default", default_pause_after_ms=0,
            default_tts_instructions=None, default_speed=None,
            default_ack=True,
        )
        assert [t["ack"] for t in turns] == [True, True, True]

    def test_per_turn_ack_overrides_call_level_default(self):
        turns = _normalize_turns(
            [{"ask": "q1", "ack": False}, {"ask": "q2"}],
            default_voice="default", default_pause_after_ms=0,
            default_tts_instructions=None, default_speed=None,
            default_ack=True,
        )
        assert [t["ack"] for t in turns] == [False, True]

    def test_non_bool_ack_rejected(self):
        with pytest.raises(ValueError, match="'ack' must be a boolean"):
            _norm([{"ask": "q", "ack": "yes"}])


# ---------------------------------------------------------------------------
# _ask_turns_pipeline -- ack capture cue (VM-1859 R4)
# ---------------------------------------------------------------------------

class TestPipelineAckCue:
    """The opt-in, content-free "heard you" cue: fires on a captured answer,
    stays silent on timeout/no_speech, and is absent unless opted in."""

    async def _run(self, turns, *, record, stt=None):
        cue = AsyncMock(return_value=True)
        patches = [
            patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth),
            patch("voice_mode.tools.converse._play_samples_controllable", new=_make_play_fn()),
            patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback),
            patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=record),
            patch("voice_mode.tools.converse.play_chime_captured", new=cue),
        ]
        if stt is not None:
            patches.append(patch("voice_mode.tools.converse.speech_to_text", new=stt))
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())
        return results, stopped_at, cue

    async def test_cue_fires_on_captured_answer_when_ack_on(self):
        turns = _norm([{"ask": "q", "ack": True}])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "an answer", "provider": "whisper-local"}

        results, stopped_at, cue = await self._run(turns, record=fake_record, stt=fake_stt)
        assert results[0]["status"] == "answered"
        assert cue.await_count == 1

    async def test_cue_absent_on_timeout_even_when_ack_on(self):
        """SC3: a no_speech/timeout must NOT play the cue -- that silence IS
        the "didn't hear" signal that distinguishes it from a capture."""
        turns = _norm([{"ask": "q", "ack": True}])

        def fake_record(*_a, **_k):
            return (np.zeros(10, dtype=np.int16), False)  # no speech

        results, stopped_at, cue = await self._run(turns, record=fake_record)
        assert results[0]["status"] == "no_speech"
        assert cue.await_count == 0

    async def test_cue_not_fired_by_default_when_ack_off(self):
        """SC4: default OFF -- an answered turn plays no cue when ack absent."""
        turns = _norm([{"ask": "q"}])  # ack defaults False

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "an answer", "provider": "whisper-local"}

        results, stopped_at, cue = await self._run(turns, record=fake_record, stt=fake_stt)
        assert results[0]["status"] == "answered"
        assert cue.await_count == 0

    async def test_cue_fires_once_per_captured_answer_not_on_no_speech_turn(self):
        """Mixed survey: cue count tracks the captured answers only."""
        turns = _norm([
            {"ask": "q1", "ack": True},
            {"ask": "q2", "ack": True},
            {"ask": "q3", "ack": True},
        ])
        record_calls = {"n": 0}

        def fake_record(*_a, **_k):
            record_calls["n"] += 1
            # turn 2 (index 1) times out; the others capture.
            if record_calls["n"] == 2:
                return (np.zeros(10, dtype=np.int16), False)
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "reply", "provider": "whisper-local"}

        results, stopped_at, cue = await self._run(turns, record=fake_record, stt=fake_stt)
        assert [r["status"] for r in results] == ["answered", "no_speech", "answered"]
        assert cue.await_count == 2
