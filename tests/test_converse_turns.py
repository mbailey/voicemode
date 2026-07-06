"""Tests for the multi-utterance `turns` feature on converse (VM-1772).

P1 = speak-only multivoice, pipelined synth→playback, per-turn pause_after_ms.

Coverage:
  * `_normalize_turns` — schema validation, precedence-ready defaults, pause &
    speed selection, reserved-key rejection.
  * `_speak_turns_pipeline` — ordering, per-turn voice, pause application,
    graceful per-turn failure (mock synth + mock playback, no audio device).
  * `_format_turns_result` — summary strings per metrics level.
  * `converse()` — turns wins over message; neither → error.
  * CLI `--say` / `--script` parsing into a `turns` list.
"""

from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
from click.testing import CliRunner

from voice_mode.tools.converse import (
    _normalize_turns,
    _speak_turns_pipeline,
    _format_turns_result,
    converse,
)


def _samples():
    return np.zeros(16, dtype=np.float32)


# ---------------------------------------------------------------------------
# _normalize_turns
# ---------------------------------------------------------------------------

class TestNormalizeTurns:
    def test_basic_fields_and_voice_fallback(self):
        turns = _normalize_turns(
            [{"say": "one", "voice": "alpha"}, {"say": "two"}],
            default_voice="callvoice",
            default_pause_after_ms=150,
            default_tts_instructions=None,
            default_speed=None,
        )
        assert turns[0]["say"] == "one"
        assert turns[0]["voice"] == "alpha"        # per-turn voice
        assert turns[1]["voice"] == "callvoice"    # falls back to call voice

    def test_pause_selection_per_turn_overrides_default(self):
        turns = _normalize_turns(
            [{"say": "a", "pause_after_ms": 400}, {"say": "b"}],
            default_voice=None,
            default_pause_after_ms=150,
            default_tts_instructions=None,
            default_speed=None,
        )
        assert turns[0]["pause_after_ms"] == 400   # per-turn wins
        assert turns[1]["pause_after_ms"] == 150   # call default

    def test_speed_and_instructions_fallback(self):
        turns = _normalize_turns(
            [{"say": "a"}, {"say": "b", "speed": 1.5, "tts_instructions": "whisper"}],
            default_voice=None,
            default_pause_after_ms=0,
            default_tts_instructions="calm",
            default_speed=2.0,
        )
        assert turns[0]["speed"] == 2.0
        assert turns[0]["tts_instructions"] == "calm"
        assert turns[1]["speed"] == 1.5
        assert turns[1]["tts_instructions"] == "whisper"

    def test_single_dict_is_wrapped(self):
        turns = _normalize_turns(
            {"say": "solo"},
            default_voice=None, default_pause_after_ms=150,
            default_tts_instructions=None, default_speed=None,
        )
        assert len(turns) == 1 and turns[0]["say"] == "solo"

    @pytest.mark.parametrize("bad", [
        [{"voice": "x"}],                       # missing say/ask
        [{"say": ""}],                          # empty say
        [{"say": "   "}],                       # whitespace say
        [{"say": "ok", "pause_after_ms": -5}],  # negative pause
        [{"say": "ok", "pause_after_ms": "x"}], # non-int pause
        [{"say": "ok", "speed": 9}],            # speed out of range
        [{"say": "ok", "play": "file.wav"}],    # reserved P3 key
        [{"ask": ""}],                          # empty ask
        [{"say": "a", "ask": "b"}],              # both verbs
        [{"ask": "a", "wait_for_response": True}],   # wfr alongside ask (error regardless of value)
        [{"ask": "a", "wait_for_response": False}],  # wfr alongside ask, still an error
        [{"say": "a", "wait_for_response": "true"}],  # wfr must be bool, not string
        [{"say": "ok", "listen_duration_max": 0}],    # non-positive
        [{"say": "ok", "listen_duration_min": -1}],   # negative
        [{"say": "ok", "vad_aggressiveness": 9}],     # out of range
        [{"say": "ok", "vad_aggressiveness": "x"}],   # not an int
        [{"say": "ok", "message": "nested"}],   # not a turn key (no nested converse call)
        [{"say": "ok", "turns": []}],           # not a turn key
        [{"say": "ok", "conch": True}],         # not a turn key
        [{"say": "ok", "session": "x"}],        # not a turn key
        [{"say": "ok", "bogus": 1}],            # generic unknown key
        ["just a string"],                      # not an object
    ])
    def test_invalid_turns_raise(self, bad):
        with pytest.raises(ValueError):
            _normalize_turns(
                bad,
                default_voice=None, default_pause_after_ms=150,
                default_tts_instructions=None, default_speed=None,
            )

    def test_ask_verb_selected_and_text_captured(self):
        turns = _normalize_turns(
            [{"ask": "how are you?"}],
            default_voice=None, default_pause_after_ms=150,
            default_tts_instructions=None, default_speed=None,
        )
        assert turns[0]["verb"] == "ask"
        assert turns[0]["say"] == "how are you?"

    def test_say_verb_default(self):
        turns = _normalize_turns(
            [{"say": "hi"}],
            default_voice=None, default_pause_after_ms=150,
            default_tts_instructions=None, default_speed=None,
        )
        assert turns[0]["verb"] == "say"

    def test_wait_for_response_true_is_ask_alias(self):
        turns = _normalize_turns(
            [{"say": "how are you?", "wait_for_response": True}],
            default_voice=None, default_pause_after_ms=150,
            default_tts_instructions=None, default_speed=None,
        )
        assert turns[0]["verb"] == "ask"
        assert turns[0]["say"] == "how are you?"

    def test_wait_for_response_false_stays_say(self):
        turns = _normalize_turns(
            [{"say": "hi", "wait_for_response": False}],
            default_voice=None, default_pause_after_ms=150,
            default_tts_instructions=None, default_speed=None,
        )
        assert turns[0]["verb"] == "say"

    def test_listen_fields_inherit_call_level_defaults(self):
        turns = _normalize_turns(
            [{"ask": "a"}, {"ask": "b", "listen_duration_max": 45, "listen_duration_min": 5, "vad_aggressiveness": 1}],
            default_voice=None, default_pause_after_ms=150,
            default_tts_instructions=None, default_speed=None,
            default_listen_duration_max=30, default_listen_duration_min=2,
            default_vad_aggressiveness=2,
        )
        assert turns[0]["listen_duration_max"] == 30    # call default
        assert turns[0]["listen_duration_min"] == 2
        assert turns[0]["vad_aggressiveness"] == 2
        assert turns[1]["listen_duration_max"] == 45    # per-turn override
        assert turns[1]["listen_duration_min"] == 5
        assert turns[1]["vad_aggressiveness"] == 1

    def test_listen_fields_present_on_say_turns_too(self):
        # Normalized uniformly (harmless on say turns) so a later say -> ask
        # edit doesn't need to add them.
        turns = _normalize_turns(
            [{"say": "hi"}],
            default_voice=None, default_pause_after_ms=150,
            default_tts_instructions=None, default_speed=None,
            default_listen_duration_max=30, default_listen_duration_min=2,
            default_vad_aggressiveness=None,
        )
        assert turns[0]["listen_duration_max"] == 30
        assert turns[0]["listen_duration_min"] == 2
        assert turns[0]["vad_aggressiveness"] is None

    def test_listen_duration_min_clamped_to_max(self):
        turns = _normalize_turns(
            [{"ask": "a", "listen_duration_min": 100, "listen_duration_max": 30}],
            default_voice=None, default_pause_after_ms=150,
            default_tts_instructions=None, default_speed=None,
        )
        assert turns[0]["listen_duration_min"] == 30

    # ---------------------------------------------------------------------
    # P1 speak-only back-compat matrix -- every P1-valid speak-only turns
    # call keeps behaving exactly as before (verb defaults to "say", no
    # listen fields required, reserved-key/unknown-key semantics preserved
    # for the keys P1 already covered).
    # ---------------------------------------------------------------------
    @pytest.mark.parametrize("good", [
        [{"say": "one"}],
        [{"say": "one", "voice": "alpha"}, {"say": "two"}],
        [{"say": "a", "pause_after_ms": 400}, {"say": "b"}],
        [{"say": "a"}, {"say": "b", "speed": 1.5, "tts_instructions": "whisper"}],
    ])
    def test_p1_back_compat_matrix_still_all_say(self, good):
        turns = _normalize_turns(
            good,
            default_voice="callvoice", default_pause_after_ms=150,
            default_tts_instructions=None, default_speed=None,
        )
        assert all(t["verb"] == "say" for t in turns)


# ---------------------------------------------------------------------------
# _speak_turns_pipeline
# ---------------------------------------------------------------------------

def _norm(items, default_pause=150, default_voice="default"):
    return _normalize_turns(
        items, default_voice=default_voice, default_pause_after_ms=default_pause,
        default_tts_instructions=None, default_speed=None,
    )


@pytest.mark.asyncio
async def test_pipeline_plays_all_turns_in_order():
    turns = _norm([
        {"say": "one", "voice": "alpha"},
        {"say": "two", "voice": "beta"},
        {"say": "three"},  # falls back to default voice
    ])
    synth_calls, play_calls = [], []

    async def fake_synth(*, message, voice, **kw):
        synth_calls.append((message, voice))
        return (True, _samples(), 24000, {"generation": 0.01}, {})

    def fake_play(samples, sr):
        play_calls.append((len(samples), sr))

    with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=fake_synth), \
         patch("voice_mode.tools.converse._play_samples_blocking", side_effect=fake_play), \
         patch("voice_mode.tools.converse.asyncio.sleep", new=AsyncMock()) as mock_sleep:
        results = await _speak_turns_pipeline(
            turns, tts_model=None, tts_provider=None, audio_format=None,
            resolved_ref_text=None, should_skip_tts=False,
        )

    # Synthesis happened for every turn, in order, with the resolved voice.
    assert [c[0] for c in synth_calls] == ["one", "two", "three"]
    assert [c[1] for c in synth_calls] == ["alpha", "beta", "default"]
    # Playback covered every turn, in order.
    assert len(play_calls) == 3
    assert [r["index"] for r in results] == [0, 1, 2]
    assert [r["voice"] for r in results] == ["alpha", "beta", "default"]
    assert all(r["success"] for r in results)
    # Pause applied after each turn EXCEPT the last (2 of 3).
    assert mock_sleep.await_count == 2
    # Pause durations are seconds derived from ms.
    assert mock_sleep.await_args_list[0].args[0] == pytest.approx(0.15)


@pytest.mark.asyncio
async def test_pipeline_continues_past_a_failed_turn():
    turns = _norm([
        {"say": "one"},
        {"say": "two"},   # this one fails to synthesize
        {"say": "three"},
    ])
    play_calls = []

    async def fake_synth(*, message, voice, **kw):
        if message == "two":
            return (False, None, None, {}, {"error_type": "all_providers_failed"})
        return (True, _samples(), 24000, {"generation": 0.0}, {})

    with patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=fake_synth), \
         patch("voice_mode.tools.converse._play_samples_blocking", side_effect=lambda s, sr: play_calls.append(sr)), \
         patch("voice_mode.tools.converse.asyncio.sleep", new=AsyncMock()):
        results = await _speak_turns_pipeline(
            turns, tts_model=None, tts_provider=None, audio_format=None,
            resolved_ref_text=None, should_skip_tts=False,
        )

    # Only the two good turns played; the sequence did NOT abort.
    assert len(play_calls) == 2
    assert results[1]["success"] is False
    assert results[0]["success"] and results[2]["success"]


@pytest.mark.asyncio
async def test_pipeline_skip_tts_plays_nothing():
    turns = _norm([{"say": "a"}, {"say": "b"}])
    with patch("voice_mode.tools.converse.synthesize_turn_with_failover", new=AsyncMock()) as msynth, \
         patch("voice_mode.tools.converse._play_samples_blocking") as mplay, \
         patch("voice_mode.tools.converse.asyncio.sleep", new=AsyncMock()):
        results = await _speak_turns_pipeline(
            turns, tts_model=None, tts_provider=None, audio_format=None,
            resolved_ref_text=None, should_skip_tts=True,
        )
    msynth.assert_not_awaited()
    mplay.assert_not_called()
    assert all(r.get("skipped") for r in results)


# ---------------------------------------------------------------------------
# _format_turns_result
# ---------------------------------------------------------------------------

class TestFormatTurnsResult:
    def _results(self, oks):
        return [
            {"index": i, "voice": "v", "success": ok, "generation": 0.1,
             "playback": 0.2, "pause_after_ms": 150}
            for i, ok in enumerate(oks)
        ]

    def test_all_ok_summary(self):
        result, success = _format_turns_result(self._results([True, True]), "summary")
        assert success is True
        assert "2/2" in result

    def test_partial_failure_noted(self):
        result, success = _format_turns_result(self._results([True, False]), "summary")
        assert success is True            # at least one spoke
        assert "1/2" in result and "failed" in result

    def test_all_failed_is_error(self):
        result, success = _format_turns_result(self._results([False, False]), "summary")
        assert success is False
        assert result.lower().startswith("error")

    def test_verbose_lists_each_turn(self):
        result, _ = _format_turns_result(self._results([True, True]), "verbose")
        assert "turn 1" in result and "turn 2" in result

    def test_minimal_is_compact(self):
        result, _ = _format_turns_result(self._results([True]), "minimal")
        assert "gen" not in result and "1/1" in result


# ---------------------------------------------------------------------------
# converse() end-to-end routing (mock synth + playback, no audio device)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_turns_take_precedence_over_message():
    synth = AsyncMock(return_value=(True, _samples(), 24000, {"generation": 0.0}, {}))
    with patch("voice_mode.tools.converse.synthesize_turn_with_failover", new=synth), \
         patch("voice_mode.tools.converse._play_samples_blocking"), \
         patch("voice_mode.tools.converse.asyncio.sleep", new=AsyncMock()):
        result = await getattr(converse, "fn", converse)(
            message="SCALAR SHOULD BE IGNORED",
            turns=[{"say": "from turns", "voice": "nova"}],
            wait_for_response=False,
            skip_conch=True,
        )
    spoken = [c.kwargs.get("message") for c in synth.await_args_list]
    assert "from turns" in spoken
    assert "SCALAR SHOULD BE IGNORED" not in spoken
    assert "1/1" in result


@pytest.mark.asyncio
async def test_turns_with_call_level_wait_for_response_default_true_stays_speak_only():
    """S7a (fable progress review): the back-compat invariant of Decision 1
    rule 4 -- turns present + call-level ``wait_for_response`` left at its
    default ``True`` must still be speak-only when no turn asks. Every other
    turns-mode test in this module passes ``wait_for_response=False``
    explicitly; this is the one that actually exercises the True default
    (the commit message that first claimed this coverage overclaimed it --
    the peer review caught it, this test closes the gap)."""
    synth = AsyncMock(return_value=(True, _samples(), 24000, {"generation": 0.0}, {}))
    stt_spy = AsyncMock(side_effect=AssertionError("must never listen -- no turn asks"))
    with patch("voice_mode.tools.converse.synthesize_turn_with_failover", new=synth), \
         patch("voice_mode.tools.converse._play_samples_blocking"), \
         patch("voice_mode.tools.converse.asyncio.sleep", new=AsyncMock()), \
         patch("voice_mode.tools.converse.listen_and_transcribe", new=stt_spy):
        result = await getattr(converse, "fn", converse)(
            turns=[{"say": "one"}, {"say": "two"}],
            skip_conch=True,
            metrics_level="minimal",
            # wait_for_response deliberately OMITTED -- exercises the True default,
            # not an explicit False.
        )
    assert result == "✓ Spoke 2/2 turns"
    stt_spy.assert_not_awaited()


@pytest.mark.asyncio
async def test_speak_only_turns_summary_is_byte_exact():
    """S7b (fable progress review): this module's own turns-summary tests
    (``TestFormatTurnsResult`` above) asserted substrings only ("1/1",
    "failed"); the requirement is byte-for-byte, since impl-003's dispatch
    ("no-ask turns[] calls fall through byte-identical") needs exactly this
    net to prove it changed nothing."""
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


@pytest.mark.asyncio
async def test_converse_errors_with_neither_message_nor_turns():
    result = await getattr(converse, "fn", converse)(
        wait_for_response=False, skip_conch=True,
    )
    assert "Error" in result and "turns" in result


@pytest.mark.asyncio
async def test_converse_rejects_malformed_turn():
    result = await getattr(converse, "fn", converse)(
        turns=[{"voice": "nova"}],   # missing 'say'
        wait_for_response=False, skip_conch=True,
    )
    assert "Error" in result and "say" in result


@pytest.mark.asyncio
async def test_converse_rejects_neither_verb_with_exactly_one_of_message():
    """N2 (fable progress review): a turn with NEITHER 'say' nor 'ask' reports
    the actual requirement, not the misleading P1-era "'say' is required"."""
    result = await getattr(converse, "fn", converse)(
        turns=[{"voice": "nova"}],
        wait_for_response=False, skip_conch=True,
    )
    assert "exactly one of 'say' or 'ask'" in result


@pytest.mark.asyncio
async def test_converse_unknown_turn_key_lists_allowed_keys():
    """N2 (fable progress review): the unknown-key error names the allowed
    keys (Decision 1 rule 5), instead of just naming the bad one."""
    result = await getattr(converse, "fn", converse)(
        turns=[{"say": "hi", "typo_field": 1}],
        wait_for_response=False, skip_conch=True,
    )
    assert "unknown key 'typo_field'" in result
    assert "allowed:" in result
    assert "ask" in result and "vad_aggressiveness" in result


@pytest.mark.asyncio
async def test_call_level_vad_aggressiveness_error_not_blamed_on_turn_zero():
    """N4 (fable progress review): an out-of-range CALL-LEVEL
    vad_aggressiveness with turns present must be reported as a call-level
    error, not misattributed to "turn 0" by the per-turn inheritance
    validation running first."""
    result = await getattr(converse, "fn", converse)(
        turns=[{"say": "hi"}],
        vad_aggressiveness=9,  # out of range (0-3)
        wait_for_response=False, skip_conch=True,
    )
    assert "vad_aggressiveness must be an integer between 0 and 3" in result
    assert "turn 0" not in result


# ---------------------------------------------------------------------------
# CLI --say / --script
# ---------------------------------------------------------------------------

from voice_mode.cli import voice_mode_main_cli


@pytest.fixture
def patched_converse():
    async_mock = AsyncMock(return_value="✓ Spoke 2/2 turns")
    with patch(
        "voice_mode.utils.dependencies.checker.check_component_dependencies",
        return_value={"core": True},
    ), patch("voice_mode.tools.converse.converse") as mock_tool:
        mock_tool.fn = async_mock
        yield async_mock


def test_cli_say_builds_turns_in_order(patched_converse):
    runner = CliRunner()
    result = runner.invoke(
        voice_mode_main_cli,
        ["converse", "--say", "nova:one", "--say", "two"],
    )
    assert result.exit_code == 0, result.output
    turns = patched_converse.await_args.kwargs["turns"]
    assert turns == [
        {"say": "one", "voice": "nova"},
        {"say": "two", "voice": None},   # no VOICE: prefix, no --voice → default
    ]


def test_cli_say_first_colon_only(patched_converse):
    runner = CliRunner()
    result = runner.invoke(
        voice_mode_main_cli,
        ["converse", "--say", "nova:it is 5:30 now"],
    )
    assert result.exit_code == 0, result.output
    turns = patched_converse.await_args.kwargs["turns"]
    assert turns == [{"say": "it is 5:30 now", "voice": "nova"}]


def test_cli_say_uses_voice_flag_as_default(patched_converse):
    runner = CliRunner()
    result = runner.invoke(
        voice_mode_main_cli,
        ["converse", "--voice", "shimmer", "--say", "plain text"],
    )
    assert result.exit_code == 0, result.output
    turns = patched_converse.await_args.kwargs["turns"]
    assert turns == [{"say": "plain text", "voice": "shimmer"}]


def test_cli_script_stdin(patched_converse):
    runner = CliRunner()
    result = runner.invoke(
        voice_mode_main_cli,
        ["converse", "--script", "-"],
        input='[{"say":"hi","voice":"nova"},{"say":"there"}]',
    )
    assert result.exit_code == 0, result.output
    turns = patched_converse.await_args.kwargs["turns"]
    assert turns[0] == {"say": "hi", "voice": "nova"}
    assert turns[1]["say"] == "there"


def test_cli_pause_after_ms_passed_through(patched_converse):
    runner = CliRunner()
    result = runner.invoke(
        voice_mode_main_cli,
        ["converse", "--say", "one", "--pause-after-ms", "300"],
    )
    assert result.exit_code == 0, result.output
    assert patched_converse.await_args.kwargs["pause_after_ms"] == 300


def test_cli_say_and_script_conflict(patched_converse):
    runner = CliRunner()
    result = runner.invoke(
        voice_mode_main_cli,
        ["converse", "--say", "one", "--script", "-"],
        input="[]",
    )
    assert result.exit_code != 0
    assert "not both" in result.output.lower()


def test_cli_say_with_positional_message_conflict(patched_converse):
    runner = CliRunner()
    result = runner.invoke(
        voice_mode_main_cli,
        ["converse", "hello", "--say", "one"],
    )
    assert result.exit_code != 0


def test_cli_script_not_a_list_errors(patched_converse):
    runner = CliRunner()
    result = runner.invoke(
        voice_mode_main_cli,
        ["converse", "--script", "-"],
        input='{"say":"hi"}',
    )
    assert result.exit_code != 0
    assert "array" in result.output.lower()
