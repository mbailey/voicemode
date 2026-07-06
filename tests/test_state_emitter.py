"""Tests for the VM-1793 phase emitter (VM-1775 impl-005).

`_emit_converse_state` atomically writes `~/.voicemode/state.json` on each
speaking/listening transition of the survey loop (design report Decision 9):
`{phase, ts, session, conch_holder, survey?}`. This slice covers:

  * `_emit_converse_state` itself -- payload shape, the `survey` key present
    only when a turn is given (omitted, not null, on `idle`), atomic write
    (final file always valid JSON, no partial/tmp file left behind), and
    that every failure is swallowed (never raises).
  * `_ask_turns_pipeline` wiring -- emits `speaking` at survey start and the
    top of every turn, `listening` before each ask turn's LISTEN phase, a
    final `idle` on every exit path (completion, break, abort), and that the
    cumulative `replies_answered` count only reflects turns already resolved
    at the time of each call.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from voice_mode.conch import Conch
from voice_mode.control_channel import get_control_state
from voice_mode.tools.converse import _ask_turns_pipeline, _emit_converse_state, _normalize_turns


def _samples():
    return np.zeros(16, dtype=np.float32)


def _norm(items):
    return _normalize_turns(
        items, default_voice="default", default_pause_after_ms=0,
        default_tts_instructions=None, default_speed=None,
    )


async def _noop_feedback(*_a, **_k):
    return None


def _ok_synth(*, message, voice, **_kw):
    return (True, _samples(), 24000, {"generation": 0.0}, {})


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


@pytest.fixture(autouse=True)
def reset_control_state():
    get_control_state().reset()
    yield
    get_control_state().reset()


# ---------------------------------------------------------------------------
# _emit_converse_state -- payload shape, atomicity, failure-swallowing
# ---------------------------------------------------------------------------

class TestEmitConverseState:
    def test_writes_expected_payload_with_survey(self, tmp_path):
        state_path = tmp_path / "state.json"
        with patch("voice_mode.tools.converse.BASE_DIR", tmp_path), \
             patch.object(Conch, "get_holder", return_value={"agent": "converse", "pid": 123}):
            _emit_converse_state(
                "listening", session_id="sess-1", turn=2, n_turns=5,
                verb="ask", replies_answered=1,
            )

        assert state_path.exists()
        payload = json.loads(state_path.read_text())
        assert payload["phase"] == "listening"
        assert payload["session"] == "sess-1"
        assert payload["conch_holder"] == "converse"
        assert payload["survey"] == {
            "turn": 2, "n_turns": 5, "verb": "ask", "answered": 1,
        }
        # A real timestamp was stamped (ISO-parseable), not a placeholder.
        from datetime import datetime
        datetime.fromisoformat(payload["ts"])

    def test_idle_phase_omits_survey_key_entirely(self, tmp_path):
        state_path = tmp_path / "state.json"
        with patch("voice_mode.tools.converse.BASE_DIR", tmp_path), \
             patch.object(Conch, "get_holder", return_value=None):
            _emit_converse_state("idle", session_id="sess-1")

        payload = json.loads(state_path.read_text())
        assert payload["phase"] == "idle"
        assert "survey" not in payload
        assert payload["conch_holder"] is None

    def test_conch_holder_none_when_conch_free(self, tmp_path):
        state_path = tmp_path / "state.json"
        with patch("voice_mode.tools.converse.BASE_DIR", tmp_path), \
             patch.object(Conch, "get_holder", return_value=None):
            _emit_converse_state("speaking", session_id=None, turn=0, n_turns=1, verb="say", replies_answered=0)

        payload = json.loads(state_path.read_text())
        assert payload["conch_holder"] is None
        assert payload["session"] is None

    def test_write_is_atomic_no_tmp_file_left_behind(self, tmp_path):
        state_path = tmp_path / "state.json"
        with patch("voice_mode.tools.converse.BASE_DIR", tmp_path), \
             patch.object(Conch, "get_holder", return_value=None):
            _emit_converse_state("speaking", turn=0, n_turns=1, verb="say", replies_answered=0)

        # No leftover .tmp sibling next to the final file (the isolated-home
        # fixture may leave its own unrelated entries in tmp_path, so only
        # check for our own tmp artifact by name).
        leftover = [p for p in tmp_path.iterdir() if p.name.startswith(".state.json.tmp")]
        assert leftover == []
        assert state_path.exists()

    def test_creates_parent_directory_if_missing(self, tmp_path):
        base_dir = tmp_path / "does" / "not" / "exist" / "yet"
        with patch("voice_mode.tools.converse.BASE_DIR", base_dir), \
             patch.object(Conch, "get_holder", return_value=None):
            _emit_converse_state("idle")

        assert (base_dir / "state.json").exists()

    def test_failure_is_swallowed_never_raises(self, tmp_path):
        """A disk/permission failure while writing state.json must never
        propagate -- it would otherwise abort a live voice call over a
        best-effort breadcrumb."""
        with patch("voice_mode.tools.converse.BASE_DIR", tmp_path), \
             patch.object(Conch, "get_holder", side_effect=OSError("boom")):
            _emit_converse_state("speaking", turn=0, n_turns=1, verb="say", replies_answered=0)
        # No exception raised, and (since the failure happened before any
        # write) no file was created either -- both are acceptable outcomes
        # for a swallowed failure; the only hard requirement is "no raise".

    def test_write_failure_is_swallowed(self, tmp_path):
        with patch("voice_mode.tools.converse.BASE_DIR", tmp_path), \
             patch.object(Conch, "get_holder", return_value=None), \
             patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            _emit_converse_state("idle")  # must not raise


# ---------------------------------------------------------------------------
# _ask_turns_pipeline -- phase-emitter wiring
# ---------------------------------------------------------------------------

class TestPipelineEmitsPhaseTransitions:
    async def test_full_survey_emits_speaking_listening_then_idle(self):
        turns = _norm([{"say": "Welcome."}, {"ask": "Color?"}, {"ask": "Animal?"}])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        stt_calls = {"n": 0}

        async def fake_stt(*_a, **_k):
            stt_calls["n"] += 1
            texts = ["blue", "a swallow"]
            return {"text": texts[stt_calls["n"] - 1], "provider": "whisper-local"}

        emit_spy = MagicMock()
        with patch("voice_mode.tools.converse._emit_converse_state", new=emit_spy), \
             patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable",
                   new=AsyncMock(return_value="played")), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(
                turns, **_pipeline_kwargs(session_id="sess-42"),
            )

        assert stopped_at is None
        calls = emit_spy.call_args_list
        # First call: survey start -- speaking, turn 0, nothing answered yet.
        phase, kwargs = calls[0].args[0], calls[0].kwargs
        assert phase == "speaking"
        assert kwargs["session_id"] == "sess-42"
        assert kwargs["turn"] == 0 and kwargs["n_turns"] == 3 and kwargs["replies_answered"] == 0

        # A "listening" call precedes each ask turn's LISTEN phase.
        listening_calls = [c for c in calls if c.args[0] == "listening"]
        assert [c.kwargs["turn"] for c in listening_calls] == [1, 2]
        assert [c.kwargs["verb"] for c in listening_calls] == ["ask", "ask"]
        # Turn 2's listening emit reflects turn 1 already answered.
        assert listening_calls[0].kwargs["replies_answered"] == 0
        assert listening_calls[1].kwargs["replies_answered"] == 1

        # Speaking emits happen once per turn, in order, 0/1/2.
        speaking_calls = [c for c in calls if c.args[0] == "speaking"]
        assert [c.kwargs["turn"] for c in speaking_calls] == [0, 1, 2]

        # Exactly one terminal idle emit, last in the sequence, with no
        # turn/survey info attached.
        assert calls[-1].args[0] == "idle"
        assert calls[-1].kwargs.get("turn") is None
        idle_calls = [c for c in calls if c.args[0] == "idle"]
        assert len(idle_calls) == 1

    async def test_abort_still_emits_terminal_idle(self):
        """Even when the survey aborts partway (STT connection failure), the
        finally-block guarantees one last idle emit -- a reader must never
        be left believing a dead call is still speaking/listening."""
        turns = _norm([{"ask": "Q1"}, {"ask": "Q2"}])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {
                "error_type": "connection_failed",
                "attempted_endpoints": [{"endpoint": "http://x", "error": "refused"}],
            }

        emit_spy = MagicMock()
        with patch("voice_mode.tools.converse._emit_converse_state", new=emit_spy), \
             patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable",
                   new=AsyncMock(return_value="played")), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at["reason"] == "stt_connection_failed"
        assert emit_spy.call_args_list[-1].args[0] == "idle"

    async def test_answered_count_is_cumulative_not_per_turn(self):
        """replies_answered on turn 2's emits reflects BOTH prior ask turns
        once answered, not just the immediately preceding one."""
        turns = _norm([{"ask": "Q1"}, {"ask": "Q2"}, {"ask": "Q3"}])

        def fake_record(*_a, **_k):
            return (np.zeros(2400, dtype=np.int16), True)

        async def fake_stt(*_a, **_k):
            return {"text": "yes", "provider": "whisper-local"}

        emit_spy = MagicMock()
        with patch("voice_mode.tools.converse._emit_converse_state", new=emit_spy), \
             patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=_ok_synth), \
             patch("voice_mode.tools.converse._play_samples_controllable",
                   new=AsyncMock(return_value="played")), \
             patch("voice_mode.tools.converse.play_audio_feedback", new=_noop_feedback), \
             patch("voice_mode.tools.converse.record_audio_with_silence_detection", new=fake_record), \
             patch("voice_mode.tools.converse.speech_to_text", new=fake_stt):
            results, stopped_at = await _ask_turns_pipeline(turns, **_pipeline_kwargs())

        assert stopped_at is None
        speaking_calls = [c for c in emit_spy.call_args_list if c.args[0] == "speaking"]
        assert [c.kwargs["replies_answered"] for c in speaking_calls] == [0, 1, 2]
