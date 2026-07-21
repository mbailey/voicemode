"""Tests for the survey JSON return contract (VM-1775 impl-003).

Slice 3 builds on impl-002's `_ask_turns_pipeline` (which returns plain
`(results, stopped_at)` Python data) to add:

  * `_format_survey_result` -- the serializer:
    `json.dumps({"survey": {...}}, ensure_ascii=False, indent=2)`, always
    length-N/index-aligned `turns`, `timing` omitted at metrics_level=minimal.
  * `converse()` turns-branch dispatch -- no-ask turns[] stays on the
    untouched VM-1772 speak-only path (byte-identical); any-ask turns[]
    goes through `_ask_turns_pipeline` + `_format_survey_result` instead.
  * The partial-JSON-on-error guarantee for a plain (non-cancellation)
    exception, including `_ask_turns_pipeline`'s own `except Exception`
    handler, which still captures partial results/stopped_at and returns
    normally.
    NOTE (VM-2015): impl-003 originally gave `asyncio.CancelledError` the
    same "capture and return normally" treatment. That was reverted by
    VM-2015 -- swallowing cancellation there doesn't clear the anyio
    CancelScope wrapping the request, so the pipeline's own cleanup
    (`await producer_task` in its `finally`) got handed a fresh, uncaught
    CancelledError, which is what actually wedged the server. See
    `TestPipelineCancelledErrorGuarantee` below: on cancellation the
    pipeline now re-raises (impl-002's original behaviour), same as
    `_converse_core`/`converse()`.

Golden-test note on the 3 worked examples (README ## Design / the Fable
design report, reviews/2026-07-06-fable-design-report.md Decision 3): the
`completed`/`asked`/`answered`/`stopped_at`/`turns` fields (the actual
alignment-invariant contract under test) are reproduced verbatim. The
report's free-text `timing` field is illustrative prose written by hand and
is internally inconsistent in 2 of its 3 examples (example 2's stated
component sum is 27.0s but its total reads 27.5s; example 3's sum is 43.5s
but its total reads 44.0s -- only example 1's total already agrees with its
own component sum). This implementation defines `timing`'s total
deterministically as `gen + play + record + stt` (verified self-consistent
by example 1, which needed no adjustment); the synthetic per-turn metrics
below are chosen so every example's components sum to the example's own
total, rather than reproducing the doc's two arithmetic slips.
"""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from voice_mode.control_channel import get_control_state
from voice_mode.tools.converse import (
    _ask_turns_pipeline,
    _format_survey_result,
    _normalize_turns,
    converse,
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


def _ok_synth(*, message, voice, **_kw):
    return (True, _samples(), 24000, {"generation": 0.0}, {})


@pytest.fixture(autouse=True)
def reset_control_state():
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


# ---------------------------------------------------------------------------
# _format_survey_result -- golden worked examples
# ---------------------------------------------------------------------------

class TestFormatSurveyResultGolden:
    def test_worked_example_1_full_completion(self):
        """3 turns, 2 ask, both answered, no break -- README Return contract
        worked example 1."""
        results = [
            {"index": 0, "verb": "ask", "status": "answered",
             "reply": "Blue. No, yellow!",
             "generation": 1.0, "playback": 3.0, "record": 9.9, "stt": 0.9},
            {"index": 1, "verb": "say", "status": "spoken",
             "generation": 1.0, "playback": 3.0, "record": 0.0, "stt": 0.0},
            {"index": 2, "verb": "ask", "status": "answered",
             "reply": "An African or a European swallow?",
             "generation": 1.2, "playback": 5.4, "record": 9.9, "stt": 0.8},
        ]

        result, success = _format_survey_result(results, None, n_ask=2, metrics_level="summary")

        assert success is True
        parsed = json.loads(result)
        assert parsed == {
            "survey": {
                "completed": True,
                "asked": 2,
                "answered": 2,
                "stopped_at": None,
                "turns": [
                    {"turn": 0, "verb": "ask", "status": "answered",
                     "reply": "Blue. No, yellow!"},
                    {"turn": 1, "verb": "say", "status": "spoken"},
                    {"turn": 2, "verb": "ask", "status": "answered",
                     "reply": "An African or a European swallow?"},
                ],
                "timing": "gen 3.2s, play 11.4s, record 19.8s, stt 1.7s, total 36.1s",
            }
        }
        # Byte-for-byte: exact json.dumps(ensure_ascii=False, indent=2) shape.
        assert result == (
            '{\n'
            '  "survey": {\n'
            '    "completed": true,\n'
            '    "asked": 2,\n'
            '    "answered": 2,\n'
            '    "stopped_at": null,\n'
            '    "turns": [\n'
            '      {\n'
            '        "turn": 0,\n'
            '        "verb": "ask",\n'
            '        "status": "answered",\n'
            '        "reply": "Blue. No, yellow!"\n'
            '      },\n'
            '      {\n'
            '        "turn": 1,\n'
            '        "verb": "say",\n'
            '        "status": "spoken"\n'
            '      },\n'
            '      {\n'
            '        "turn": 2,\n'
            '        "verb": "ask",\n'
            '        "status": "answered",\n'
            '        "reply": "An African or a European swallow?"\n'
            '      }\n'
            '    ],\n'
            '    "timing": "gen 3.2s, play 11.4s, record 19.8s, stt 1.7s, total 36.1s"\n'
            '  }\n'
            '}'
        )

    def test_worked_example_2_mid_survey_break(self):
        """5 turns; stop pressed while listening on turn 2 -- worked example 2.
        turns 3/4 never reached -> not_reached, alignment invariant (len 5)."""
        results = [
            {"index": 0, "verb": "ask", "status": "answered",
             "reply": "Arthur, King of the Britons.",
             "generation": 0.8, "playback": 2.5, "record": 4.0, "stt": 0.4},
            {"index": 1, "verb": "ask", "status": "answered",
             "reply": "To seek the Holy Grail.",
             "generation": 0.9, "playback": 2.8, "record": 4.5, "stt": 0.4},
            {"index": 2, "verb": "ask", "status": "no_speech", "reply": None,
             "generation": 1.2, "playback": 3.5, "record": 5.7, "stt": 0.3},
            {"index": 3, "verb": "say", "status": "not_reached",
             "generation": 0.0, "playback": 0.0, "record": 0.0, "stt": 0.0},
            {"index": 4, "verb": "ask", "status": "not_reached", "reply": None,
             "generation": 0.0, "playback": 0.0, "record": 0.0, "stt": 0.0},
        ]
        stopped_at = {"turn": 2, "phase": "listening", "reason": "stop"}

        result, success = _format_survey_result(results, stopped_at, n_ask=4, metrics_level="summary")

        assert success is True  # partial, but replies were collected -- not a hard failure
        parsed = json.loads(result)
        assert parsed["survey"]["completed"] is False
        assert parsed["survey"]["asked"] == 4
        assert parsed["survey"]["answered"] == 2
        assert parsed["survey"]["stopped_at"] == stopped_at
        assert len(parsed["survey"]["turns"]) == 5  # alignment invariant
        assert parsed["survey"]["turns"] == [
            {"turn": 0, "verb": "ask", "status": "answered",
             "reply": "Arthur, King of the Britons."},
            {"turn": 1, "verb": "ask", "status": "answered",
             "reply": "To seek the Holy Grail."},
            {"turn": 2, "verb": "ask", "status": "no_speech", "reply": None},
            {"turn": 3, "verb": "say", "status": "not_reached"},
            {"turn": 4, "verb": "ask", "status": "not_reached", "reply": None},
        ]
        assert parsed["survey"]["timing"] == "gen 2.9s, play 8.8s, record 14.2s, stt 1.1s, total 27.0s"

    def test_worked_example_3_stt_trouble_alignment_preserved(self):
        """Silence on turn 1, STT connection failure on turn 3 aborts with
        partials -- worked example 3."""
        results = [
            {"index": 0, "verb": "ask", "status": "answered", "reply": "Fine, thanks.",
             "generation": 0.7, "playback": 2.0, "record": 9.0, "stt": 0.3},
            {"index": 1, "verb": "ask", "status": "no_speech", "reply": None,
             "generation": 0.8, "playback": 2.3, "record": 21.5, "stt": 0.0},
            {"index": 2, "verb": "say", "status": "spoken",
             "generation": 0.9, "playback": 2.6, "record": 0.0, "stt": 0.0},
            {"index": 3, "verb": "ask", "status": "stt_failed", "reply": None,
             "generation": 0.6, "playback": 2.2, "record": 0.5, "stt": 0.1},
        ]
        stopped_at = {"turn": 3, "phase": "listening", "reason": "stt_connection_failed"}

        result, success = _format_survey_result(results, stopped_at, n_ask=3, metrics_level="summary")

        assert success is True
        parsed = json.loads(result)
        assert parsed["survey"]["completed"] is False
        assert parsed["survey"]["asked"] == 3
        assert parsed["survey"]["answered"] == 1
        assert parsed["survey"]["stopped_at"] == stopped_at
        assert len(parsed["survey"]["turns"]) == 4
        assert parsed["survey"]["turns"] == [
            {"turn": 0, "verb": "ask", "status": "answered", "reply": "Fine, thanks."},
            {"turn": 1, "verb": "ask", "status": "no_speech", "reply": None},
            {"turn": 2, "verb": "say", "status": "spoken"},
            {"turn": 3, "verb": "ask", "status": "stt_failed", "reply": None},
        ]
        assert parsed["survey"]["timing"] == "gen 3.0s, play 9.1s, record 31.0s, stt 0.4s, total 43.5s"


# ---------------------------------------------------------------------------
# _format_survey_result -- structural / metrics-level behaviour
# ---------------------------------------------------------------------------

class TestFormatSurveyResultStructural:
    def test_minimal_metrics_omits_timing(self):
        results = [
            {"index": 0, "verb": "ask", "status": "answered", "reply": "ok",
             "generation": 1.0, "playback": 1.0, "record": 1.0, "stt": 1.0},
        ]
        result, _ = _format_survey_result(results, None, n_ask=1, metrics_level="minimal")
        parsed = json.loads(result)
        assert "timing" not in parsed["survey"]

    def test_serialization_is_json_dumps_ensure_ascii_false_indent_2(self):
        """Non-ASCII text must pass through unescaped (ensure_ascii=False)."""
        results = [
            {"index": 0, "verb": "ask", "status": "answered", "reply": "café résumé"},
        ]
        result, _ = _format_survey_result(results, None, n_ask=1, metrics_level="minimal")
        assert "café résumé" in result
        assert "\\u" not in result
        assert result.startswith("{\n  \"survey\": {\n")

    def test_turns_array_always_length_n_say_only_entry_has_no_reply_key(self):
        results = [
            {"index": 0, "verb": "say", "status": "spoken"},
            {"index": 1, "verb": "ask", "status": "no_speech", "reply": None},
        ]
        result, _ = _format_survey_result(results, None, n_ask=1, metrics_level="minimal")
        parsed = json.loads(result)
        assert len(parsed["survey"]["turns"]) == 2
        assert "reply" not in parsed["survey"]["turns"][0]
        assert parsed["survey"]["turns"][1]["reply"] is None

    def test_success_false_only_when_nothing_was_ever_reached(self):
        """A survey aborted before turn 0 ever resolved (e.g. the very first
        turn's synthesis+playback+listen never completed) is the one case
        with zero collected progress -- everything else (even a single
        spoken/answered/no_speech turn) counts as partial success, per the
        'never a bare error once >=1 reply is held' guarantee (which this
        function generalizes slightly to 'once any turn made progress')."""
        results = [
            {"index": 0, "verb": "ask", "status": "not_reached", "reply": None},
            {"index": 1, "verb": "ask", "status": "not_reached", "reply": None},
        ]
        stopped_at = {"turn": 0, "phase": "speaking", "reason": "error"}
        result, success = _format_survey_result(results, stopped_at, n_ask=2, metrics_level="minimal")
        assert success is False
        parsed = json.loads(result)
        assert parsed["survey"]["completed"] is False
        assert parsed["survey"]["answered"] == 0


# ---------------------------------------------------------------------------
# converse() dispatch -- no-ask stays byte-identical; any-ask returns survey JSON
# ---------------------------------------------------------------------------

class TestConverseDispatch:
    async def test_no_ask_turns_dispatch_unchanged_speak_only_summary(self):
        """Back-compat: a turns[] call with NO ask turn must still return the
        exact VM-1772 speak-only summary string, untouched by this slice."""
        synth = AsyncMock(return_value=(True, _samples(), 24000, {"generation": 0.0}, {}))
        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", new=synth), \
             patch("voice_mode.tools.converse._play_samples_blocking"), \
             patch("voice_mode.tools.converse.asyncio.sleep", new=AsyncMock()):
            result = await getattr(converse, "fn", converse)(
                turns=[{"say": "one"}, {"say": "two"}],
                wait_for_response=False,
                skip_conch=True,
                metrics_level="minimal",
            )
        assert result == "✓ Spoke 2/2 turns"
        assert not result.startswith("{")

    async def test_any_ask_turn_returns_survey_json(self):
        turns = [
            {"ask": "First: how did the demo land?"},
            {"say": "Thank you very much."},
        ]

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "It landed great.", "provider": "whisper-local"}

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable",
                   new=AsyncMock(return_value="played")), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            result = await getattr(converse, "fn", converse)(
                turns=turns,
                wait_for_response=False,  # deliberately ignored in turns mode
                skip_conch=True,
                metrics_level="minimal",
            )

        assert result.startswith("{")
        parsed = json.loads(result)
        survey = parsed["survey"]
        assert survey["completed"] is True
        assert survey["asked"] == 1
        assert survey["answered"] == 1
        assert survey["stopped_at"] is None
        assert survey["turns"] == [
            {"turn": 0, "verb": "ask", "status": "answered", "reply": "It landed great."},
            {"turn": 1, "verb": "say", "status": "spoken"},
        ]

    async def test_stop_mid_survey_returns_partial_json_with_stopped_at(self):
        turns = [{"ask": "q1"}, {"ask": "q2"}]

        def fake_record(*_a, **_k):
            get_control_state().request_stop()
            return (np.zeros(2400, dtype=np.int16), True)

        stt_spy = AsyncMock(side_effect=AssertionError("STT must be skipped on stop"))
        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable",
                   new=AsyncMock(return_value="played")), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=stt_spy):
            result = await getattr(converse, "fn", converse)(
                turns=turns, wait_for_response=False, skip_conch=True, metrics_level="minimal",
            )

        parsed = json.loads(result)
        survey = parsed["survey"]
        assert survey["completed"] is False
        assert survey["stopped_at"] == {"turn": 0, "phase": "listening", "reason": "stop"}
        assert len(survey["turns"]) == 2  # alignment invariant even mid-call
        assert survey["turns"][1]["status"] == "not_reached"
        stt_spy.assert_not_awaited()


# ---------------------------------------------------------------------------
# _ask_turns_pipeline -- CancelledError returns partial survey data instead
# of propagating (impl-003 changes impl-002's re-raise)
# ---------------------------------------------------------------------------

class TestPipelineCancelledErrorGuarantee:
    """VM-2015 supersedes VM-1775 impl-003's "capture partial results and
    return normally" guarantee. Swallowing CancelledError inside the
    pipeline (instead of re-raising) doesn't clear the anyio CancelScope
    wrapping the request -- it stays cancelled, so the very next `await`
    (e.g. the `finally` block's own `await producer_task`) gets handed a
    FRESH, uncaught CancelledError. That's what actually escaped the request
    boundary and wedged the server (see the VM-2015 RCA). The correct
    contract is now the opposite: `_ask_turns_pipeline` must let
    CancelledError propagate, so the MCP SDK's own per-request cancel
    handling absorbs it exactly once. Every already-collected reply is still
    safe -- it was persisted to the conversation log at capture time -- only
    the tool's partial-results return VALUE is no longer available on this
    path (see test_converse_cancellation.py for the same contract at the
    `converse()`/`_converse_core` level)."""

    async def test_cancelled_during_listen_reraises(self):
        turns = _norm([{"ask": "q1"}, {"ask": "q2"}])

        listen_spy = AsyncMock(side_effect=asyncio.CancelledError())
        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable",
                   new=AsyncMock(return_value="played")), \
             patch("voice_mode.tools.converse.listen_and_transcribe", new=listen_spy):
            with pytest.raises(asyncio.CancelledError):
                await _ask_turns_pipeline(turns, **_pipeline_kwargs())

    async def test_cancelled_during_speaking_reraises(self):
        turns = _norm([{"say": "a"}, {"ask": "b"}])

        play_spy = AsyncMock(side_effect=asyncio.CancelledError())
        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable", new=play_spy):
            with pytest.raises(asyncio.CancelledError):
                await _ask_turns_pipeline(turns, **_pipeline_kwargs())

    async def test_cancelled_after_one_reply_already_held_still_reraises(self):
        """Even once >=1 reply is already held (and durably logged), a later
        cancellation must still propagate -- the reply's safety comes from
        conversation-log persistence at capture time, not from converting
        the cancellation into a normal return."""
        turns = _norm([{"ask": "q1"}, {"ask": "q2"}])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        call_count = {"n": 0}

        async def flaky_stt(*_a, **_k):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"text": "first answer", "provider": "whisper-local"}
            raise asyncio.CancelledError()

        with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable",
                   new=AsyncMock(return_value="played")), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=flaky_stt):
            with pytest.raises(asyncio.CancelledError):
                await _ask_turns_pipeline(turns, **_pipeline_kwargs())
