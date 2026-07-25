"""VM-1901 observability-001 — the requested-vs-resolved recording contract.

Promoted by super.voicemode from "half two" to the PRIMARY DEFECT of this
task: fix-001 stopped the wrong voice coming out; this slice makes the fix
OBSERVABLE, per design.md section 5 (task dir). Covers design.md section 9's
acceptance-mapped items for this slice:

  1. The repro, both halves: an undeclared cast errors loudly BEFORE the
     conch is ever touched (no TTS request issued, conch never acquired).
  8. Conch: payload carries requested+resolved+via; the clash rule (same
     resolved id at MEMBER level, never cast level, never on the request).
  9. Exchange log: v4 fields present on single AND turns[] paths (the
     blindness test — a 3-turn multi-voice call produces 3 tts records);
     is_fallback populated on a forced kokoro->openai failover and ONLY
     then; a v3 record renders with provenance-unknown, never a guessed
     `requested`.

Complements test_vm1901_alloy_fallback_repro.py (the five mouths) and
test_vm1901_resolver_core.py (fix-001's resolver core) — this file is the
observability half, not the resolution half.
"""

import importlib
import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from voice_mode.conch import Conch
from voice_mode.conch_queue import ConchQueue
from voice_mode.conversation_logger import ConversationLogger, get_conversation_logger
from voice_mode.exchanges.models import Exchange, ExchangeMetadata
from voice_mode.tools.converse import _speak_turns_pipeline, _normalize_turns


def _make_voice(parent, name, wav_bytes=b"riff", txt="transcript"):
    d = parent / name
    d.mkdir(parents=True)
    (d / "default.wav").write_bytes(wav_bytes)
    (d / "default.txt").write_text(txt)
    return d


def _reload_voice_profiles(voices_dir, monkeypatch, **env):
    monkeypatch.setenv("VOICEMODE_VOICES_DIR", str(voices_dir))
    monkeypatch.delenv("VOICEMODE_REMOTE_VOICES_DIR", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from voice_mode import voice_profiles

    importlib.reload(voice_profiles)
    return voice_profiles


# ---------------------------------------------------------------------------
# Item 8 (part 1) — the conch payload carries requested + resolved + via
# ---------------------------------------------------------------------------

class TestConchProvenance:
    def test_try_acquire_writes_requested_and_via_additively(self, clean_conch_file):
        conch = Conch(
            agent_name="cora", voice="blackadder/blackadder",
            voice_requested="blackadder", voice_via="cast-default:blackadder",
        )
        assert conch.try_acquire() is True
        data = json.loads(Conch.LOCK_FILE.read_text())
        # `voice` keeps meaning "what will sound" (VM-914); the two new
        # fields are additive, not a replacement.
        assert data["voice"] == "blackadder/blackadder"
        assert data["voice_requested"] == "blackadder"
        assert data["voice_via"] == "cast-default:blackadder"
        conch.release()

    def test_fields_null_when_not_provided(self, clean_conch_file):
        conch = Conch(agent_name="cora", voice="af_sky")
        assert conch.try_acquire() is True
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["voice_requested"] is None
        assert data["voice_via"] is None
        conch.release()

    def test_hold_carries_the_same_additive_fields(self, clean_conch_file):
        conch = Conch(
            agent_name="cora", voice="blackadder/blackadder",
            voice_requested="blackadder", voice_via="cast-default:blackadder",
        )
        assert conch.try_acquire() is True
        conch.release(hold=True)
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["held"] is True
        assert data["voice_requested"] == "blackadder"
        assert data["voice_via"] == "cast-default:blackadder"

    def test_write_hold_classmethod_accepts_the_additive_fields(self, clean_conch_file):
        Conch.write_hold(
            "pause_conversation", voice="blackadder/baldrick",
            voice_requested="blackadder/baldrick", voice_via="qualified",
        )
        data = json.loads(Conch.LOCK_FILE.read_text())
        assert data["voice_requested"] == "blackadder/baldrick"
        assert data["voice_via"] == "qualified"


@pytest.fixture
def clean_conch_file():
    if Conch.LOCK_FILE.exists():
        Conch.LOCK_FILE.unlink()
    yield
    if Conch.LOCK_FILE.exists():
        Conch.LOCK_FILE.unlink()


class TestConchQueueProvenance:
    def test_register_carries_requested_and_via(self):
        ConchQueue.register(
            "sess-a", agent="converse", voice="blackadder/blackadder",
            voice_requested="blackadder", voice_via="cast-default:blackadder",
        )
        waiters = ConchQueue.list()
        assert len(waiters) == 1
        assert waiters[0].voice == "blackadder/blackadder"
        assert waiters[0].voice_requested == "blackadder"
        assert waiters[0].voice_via == "cast-default:blackadder"
        ConchQueue.deregister("sess-a")


# ---------------------------------------------------------------------------
# Item 8 (part 2) — the clash rule (design.md §5.2, Q4), made checkable
# ---------------------------------------------------------------------------

class TestVoicesClashRule:
    def test_same_resolved_member_via_different_expressions_is_a_clash(self):
        """Agent A named the CAST (resolves to its default member); agent B
        named that SAME member explicitly. Same resolved id -> a real
        clash -- exactly what comparing the raw requests would miss."""
        resolved_a = "blackadder/blackadder"  # requested "blackadder" (cast)
        resolved_b = "blackadder/blackadder"  # requested "blackadder/blackadder"
        assert Conch.voices_clash(resolved_a, resolved_b) is True

    def test_sibling_members_of_the_same_cast_are_not_a_clash(self):
        """Distinct members, distinct reference audio -- genuinely different
        voices, not a clash, even though they share a cast."""
        assert Conch.voices_clash("blackadder/blackadder", "blackadder/baldrick") is False

    def test_comparing_requested_strings_would_have_missed_the_clash(self):
        """The point of the rule: comparing the RAW requests ("blackadder" vs
        "blackadder/blackadder") looks like no clash, which is the original
        bug restated. The resolved ids agree; requested strings do not."""
        requested_a, resolved_a = "blackadder", "blackadder/blackadder"
        requested_b, resolved_b = "blackadder/blackadder", "blackadder/blackadder"
        assert requested_a != requested_b
        assert Conch.voices_clash(resolved_a, resolved_b) is True

    def test_unresolved_or_absent_voices_never_clash(self):
        assert Conch.voices_clash(None, None) is False
        assert Conch.voices_clash(None, "blackadder/blackadder") is False
        assert Conch.voices_clash("blackadder/blackadder", None) is False


# ---------------------------------------------------------------------------
# Item 9 (part 1) — SCHEMA_VERSION 4, requested/resolved/via on log_tts
# ---------------------------------------------------------------------------

class TestExchangeLogSchemaV4:
    def test_schema_version_is_4(self):
        assert ConversationLogger.SCHEMA_VERSION == 4

    def test_log_tts_records_requested_resolved_and_via(self, tmp_path):
        logger = ConversationLogger(base_dir=tmp_path)
        logger.log_tts(
            "hello", voice="blackadder/blackadder", voice_requested="blackadder",
            voice_via="cast-default:blackadder",
        )
        log_file = logger._get_log_file_path(__import__("datetime").date.today())
        entry = json.loads(log_file.read_text().strip().splitlines()[-1])
        assert entry["version"] == 4
        assert entry["metadata"]["voice"] == "blackadder/blackadder"
        assert entry["metadata"]["voice_requested"] == "blackadder"
        assert entry["metadata"]["voice_via"] == "cast-default:blackadder"


class TestReaderRuleForLegacyRecords:
    """design.md §5.3: a v<=3 record is result-only, provenance unknown --
    NEVER backfill a guessed `requested`, even though the field is absent
    the same way an unset v4 field would be."""

    def test_v3_record_renders_as_provenance_unknown(self):
        exchange = Exchange(
            version=3, timestamp=__import__("datetime").datetime.now(),
            conversation_id="c1", type="tts", text="hi",
            metadata=ExchangeMetadata(voice_mode_version="8.0.0", voice="alloy"),
        )
        rendered = exchange.voice_provenance
        assert "alloy" in rendered
        assert "unknown" in rendered.lower()
        # Never a guessed requested value, even though voice_requested is
        # simply absent on this record (same shape as an unset v4 field).
        assert "requested 'alloy'" not in rendered

    def test_v4_record_with_matching_provenance_renders_plainly(self):
        exchange = Exchange(
            version=4, timestamp=__import__("datetime").datetime.now(),
            conversation_id="c1", type="tts", text="hi",
            metadata=ExchangeMetadata(
                voice_mode_version="8.0.0", voice="alloy",
                voice_requested="alloy", voice_via="provider-native",
            ),
        )
        assert exchange.voice_provenance == "alloy"

    def test_v4_record_with_differing_provenance_shows_both(self):
        exchange = Exchange(
            version=4, timestamp=__import__("datetime").datetime.now(),
            conversation_id="c1", type="tts", text="hi",
            metadata=ExchangeMetadata(
                voice_mode_version="8.0.0", voice="blackadder/blackadder",
                voice_requested="blackadder", voice_via="cast-default:blackadder",
            ),
        )
        rendered = exchange.voice_provenance
        assert "blackadder/blackadder" in rendered
        assert "blackadder" in rendered
        assert "cast-default:blackadder" in rendered


# ---------------------------------------------------------------------------
# Item 9 (part 2) — the turns[] blindness fix: a 3-turn multi-voice call
# must produce 3 tts exchange-log records, not zero (design.md §5.4).
# ---------------------------------------------------------------------------

class TestTurnsBlindnessFix:
    async def test_speak_only_pipeline_logs_every_turn(self):
        """Before this slice, `_speak_turns_pipeline` discarded `_config`
        entirely (the underscore WAS the hole) -- turns[] speech never
        appeared in the exchange log at all. Now each turn logs through the
        same enriched log_tts, with its OWN resolution."""
        turns = _normalize_turns(
            [
                {"say": "one", "voice": "blackadder"},
                {"say": "two", "voice": "peep-show"},
                {"say": "three", "voice": "alloy"},
            ],
            default_voice=None, default_pause_after_ms=0,
            default_tts_instructions=None, default_speed=None,
        )

        async def fake_synth(*, message, voice, **kw):
            configs = {
                "blackadder": {
                    "voice": "blackadder/blackadder", "voice_requested": "blackadder",
                    "voice_via": "cast-default:blackadder", "provider": "mlx-audio",
                },
                "peep-show": {
                    "voice": "peep-show/mark", "voice_requested": "peep-show",
                    "voice_via": "cast-default:mark", "provider": "mlx-audio",
                },
                "alloy": {
                    "voice": "alloy", "voice_requested": "alloy",
                    "voice_via": "provider-native", "provider": "openai",
                },
            }
            import numpy as np
            return (True, np.zeros(16, dtype="float32"), 24000, {"generation": 0.1}, configs[voice])

        fake_logger = MagicMock()
        with patch("voice_mode.tools.converse.get_conversation_logger", return_value=fake_logger), \
             patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=fake_synth), \
             patch("voice_mode.tools.converse._play_samples_blocking"), \
             patch("voice_mode.tools.converse.asyncio.sleep", new=AsyncMock()):
            await _speak_turns_pipeline(
                turns, tts_model=None, tts_provider=None, audio_format=None,
                resolved_ref_text=None, should_skip_tts=False,
            )

        # THE BLINDNESS TEST: a 3-turn multi-voice call produces 3 tts records.
        assert fake_logger.log_tts.call_count == 3
        logged = {c.kwargs["text"]: c.kwargs for c in fake_logger.log_tts.call_args_list}
        assert logged["one"]["voice"] == "blackadder/blackadder"
        assert logged["one"]["voice_requested"] == "blackadder"
        assert logged["two"]["voice"] == "peep-show/mark"
        assert logged["two"]["voice_requested"] == "peep-show"
        assert logged["three"]["voice"] == "alloy"
        assert logged["three"]["voice_via"] == "provider-native"

    async def test_failed_turn_is_not_logged(self):
        """A turn that never spoke has nothing true to record -- parity with
        the single-message path, which only logs on tts_success."""
        turns = _normalize_turns(
            [{"say": "ok"}, {"say": "boom"}],
            default_voice="default", default_pause_after_ms=0,
            default_tts_instructions=None, default_speed=None,
        )

        async def fake_synth(*, message, voice, **kw):
            import numpy as np
            if message == "boom":
                return (False, None, None, {}, {"error_type": "all_providers_failed"})
            return (True, np.zeros(16, dtype="float32"), 24000, {"generation": 0.0}, {"voice": voice})

        fake_logger = MagicMock()
        with patch("voice_mode.tools.converse.get_conversation_logger", return_value=fake_logger), \
             patch("voice_mode.tools.converse.synthesize_turn_with_failover", side_effect=fake_synth), \
             patch("voice_mode.tools.converse._play_samples_blocking"), \
             patch("voice_mode.tools.converse.asyncio.sleep", new=AsyncMock()):
            await _speak_turns_pipeline(
                turns, tts_model=None, tts_provider=None, audio_format=None,
                resolved_ref_text=None, should_skip_tts=False,
            )

        assert fake_logger.log_tts.call_count == 1
        assert fake_logger.log_tts.call_args_list[0].kwargs["text"] == "ok"


# ---------------------------------------------------------------------------
# Item 9 (part 3) — is_fallback populated ONLY for legitimate
# endpoint-failover substitution, never for the (now-impossible) unresolved
# -> alloy case (design.md §5.3).
# ---------------------------------------------------------------------------

class TestIsFallbackOnlyForLegitimateSubstitution:
    async def test_kokoro_voice_on_openai_endpoint_is_the_one_legitimate_fallback(self):
        from voice_mode.simple_failover import simple_tts_failover
        import voice_mode.simple_failover as sf

        async def fake_tts(**kwargs):
            return True, {"generation": 0.1}

        with patch.object(sf, "TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.core.text_to_speech", side_effect=fake_tts):
            success, metrics, config = await simple_tts_failover(text="hi", voice="af_sky")

        assert success is True
        assert config["is_fallback"] is True
        assert "af_sky" in config["fallback_reason"] and "nova" in config["fallback_reason"]
        assert config["voice_requested"] == "af_sky"
        assert config["voice_resolved"] == "af_sky"  # provider-native: resolved == requested
        assert config["voice_via"] == "provider-native"

    async def test_provider_native_voice_used_on_purpose_is_not_a_fallback(self):
        """Asking for alloy ON PURPOSE (already an OpenAI-native name) must
        NOT be flagged as a fallback -- that would conflate legitimate usage
        with substitution."""
        from voice_mode.simple_failover import simple_tts_failover
        import voice_mode.simple_failover as sf

        async def fake_tts(**kwargs):
            return True, {"generation": 0.1}

        with patch.object(sf, "TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.core.text_to_speech", side_effect=fake_tts):
            success, metrics, config = await simple_tts_failover(text="hi", voice="alloy")

        assert success is True
        assert config["is_fallback"] is False
        assert config["fallback_reason"] is None
        assert config["voice_via"] == "provider-native"

    async def test_clone_voice_is_never_a_fallback(self, tmp_path, monkeypatch):
        _make_voice(tmp_path / "voices", "laurie")
        _reload_voice_profiles(tmp_path / "voices", monkeypatch)

        from voice_mode.simple_failover import simple_tts_failover
        import voice_mode.simple_failover as sf

        async def fake_tts(**kwargs):
            return True, {"generation": 0.1}

        with patch.object(sf, "TTS_BASE_URLS", ["https://api.openai.com/v1"]), \
             patch("voice_mode.core.text_to_speech", side_effect=fake_tts):
            success, metrics, config = await simple_tts_failover(text="hi", voice="laurie")

        assert success is True
        assert config["is_fallback"] is False
        assert config["voice_resolved"] == "laurie"
        assert config["voice_via"] == "leaf"


# ---------------------------------------------------------------------------
# Item 1 — the repro, both halves: resolution now runs BEFORE the conch is
# ever touched (design.md §5.1). An unresolvable/undeclared voice must raise
# loudly with NO conch construction, NO TTS request, NO queue registration.
# ---------------------------------------------------------------------------

class TestResolutionRunsBeforeConch:
    async def test_unresolvable_voice_never_constructs_the_conch(self):
        """A caller must never take the floor, or a queue position, merely
        to say nothing (design.md §5.1) -- this is what "resolve before the
        conch" means, checked directly against the Conch constructor."""
        from voice_mode.tools.converse import converse

        with patch("voice_mode.tools.converse.Conch") as mock_conch_cls, \
             patch("voice_mode.tools.converse.text_to_speech_with_failover", new_callable=AsyncMock) as mock_tts:
            result = await getattr(converse, "fn", converse)(
                message="hello", wait_for_response=False, voice="not-a-real-voice",
            )

        assert "not-a-real-voice" in result
        assert "❌ Error" in result
        mock_conch_cls.assert_not_called()
        mock_tts.assert_not_awaited()

    async def test_undeclared_cast_errors_before_conch_and_lists_members(self, tmp_path, monkeypatch):
        """The design's own headline repro: naming an undeclared group must
        error loudly, listing members, before the conch is touched."""
        from voice_mode.tools.converse import converse

        voices = tmp_path / "voices"
        voices.mkdir()
        _make_voice(voices, "peep-show/mark")
        _make_voice(voices, "peep-show/jez")
        _reload_voice_profiles(voices, monkeypatch)

        with patch("voice_mode.tools.converse.Conch") as mock_conch_cls, \
             patch("voice_mode.tools.converse.text_to_speech_with_failover", new_callable=AsyncMock) as mock_tts:
            result = await getattr(converse, "fn", converse)(
                message="hello", wait_for_response=False, voice="peep-show",
            )

        assert "peep-show" in result
        assert "mark" in result and "jez" in result  # members named, per Mike's acceptance
        mock_conch_cls.assert_not_called()
        mock_tts.assert_not_awaited()

    async def test_resolvable_voice_still_proceeds_to_the_conch(self):
        """The totality fix must not become an over-fix: a resolvable voice
        (provider-native, no filesystem lookup needed) still reaches the
        conch and TTS exactly as before."""
        from voice_mode.tools.converse import converse

        with patch(
            "voice_mode.tools.converse.text_to_speech_with_failover", new_callable=AsyncMock
        ) as mock_tts:
            mock_tts.return_value = (True, {"generation": 0.1, "playback": 0.1}, {"voice": "alloy"})
            result = await getattr(converse, "fn", converse)(
                message="hello", wait_for_response=False, voice="alloy",
            )

        assert "❌ Error" not in result
        mock_tts.assert_awaited()
