"""A local voice must not silently become an OpenAI voice on failover (#533).

When TTS failover reached the OpenAI endpoint the requested voice used to be
remapped (af_sky -> nova). Nothing in the return value or the logs said so,
which meant a Kokoro/Piper hiccup surfaced as the assistant suddenly speaking
in a different, and billed, voice, mid-conversation.

By default the OpenAI endpoint now speaks only OpenAI voices: any other voice
is a loud skip (UnmappedProviderVoiceError, no request made), so the
underlying outage is what the user sees. The old mapping stays reachable
behind VOICEMODE_TTS_VOICE_SUBSTITUTION, and warns when it fires.

Originally contributed by Robert Wunsch (#538) as source-inspection tests;
rewritten to drive _prepare_tts_endpoint itself (VM-2536).
"""
import logging
from unittest.mock import patch

import pytest

from voice_mode import config
from voice_mode.simple_failover import UnmappedProviderVoiceError, _prepare_tts_endpoint

OPENAI = "https://api.openai.com/v1"
KOKORO = "http://127.0.0.1:8880/v1"
OPENAI_VOICES = ["alloy", "echo", "fable", "nova", "onyx", "shimmer"]


def _prepare(voice, base_url=OPENAI):
    _client, selected_voice, _model, provider_type, is_fallback, reason = _prepare_tts_endpoint(
        base_url=base_url, voice=voice, model="tts-1", clone_profile=None,
    )
    return selected_voice, provider_type, is_fallback, reason


@pytest.fixture
def substitution(request):
    with patch("voice_mode.simple_failover.TTS_VOICE_SUBSTITUTION", request.param):
        yield request.param


def test_substitution_is_off_by_default(monkeypatch):
    monkeypatch.delenv("VOICEMODE_TTS_VOICE_SUBSTITUTION", raising=False)
    assert config.env_bool("VOICEMODE_TTS_VOICE_SUBSTITUTION", False) is False
    assert config.TTS_VOICE_SUBSTITUTION is False


@pytest.mark.parametrize("substitution", [False], indirect=True)
@pytest.mark.parametrize("voice", ["af_sky", "af_sarah", "am_adam", "bm_fable"])
def test_default_kokoro_voice_on_openai_is_a_loud_skip(substitution, voice):
    """Off: a mapped Kokoro voice is refused, never turned into nova/onyx/..."""
    with pytest.raises(UnmappedProviderVoiceError) as exc:
        _prepare(voice)
    assert voice in str(exc.value)
    assert "VOICEMODE_TTS_VOICE_SUBSTITUTION" in str(exc.value)


@pytest.mark.parametrize("substitution", [True], indirect=True)
def test_enabled_maps_and_warns(substitution, caplog):
    """On: the old mapping, recorded as a fallback, and logged at WARNING."""
    with caplog.at_level(logging.INFO, logger="voicemode"):
        selected, provider, is_fallback, reason = _prepare("af_sky")
    assert (selected, provider, is_fallback) == ("nova", "openai", True)
    assert "af_sky" in reason and "nova" in reason
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Substituted voice af_sky -> nova" in r.getMessage() for r in warnings)


@pytest.mark.parametrize("substitution", [True], indirect=True)
def test_enabled_never_invents_alloy_for_an_unmapped_voice(substitution):
    """On or off, a voice with no mapping is never defaulted to alloy (VM-1901)."""
    with pytest.raises(UnmappedProviderVoiceError):
        _prepare("af_nicole")


@pytest.mark.parametrize("substitution", [False, True], indirect=True)
@pytest.mark.parametrize("voice", OPENAI_VOICES)
def test_native_openai_voices_are_unaffected(substitution, voice):
    """A caller asking for a real OpenAI voice gets it, flag on or off."""
    assert _prepare(voice)[:3] == (voice, "openai", False)


@pytest.mark.parametrize("substitution", [False, True], indirect=True)
def test_kokoro_endpoint_keeps_the_kokoro_voice(substitution):
    assert _prepare("af_sky", base_url=KOKORO)[:3] == ("af_sky", "kokoro", False)
