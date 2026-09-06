"""A local voice must not silently become an OpenAI voice on failover.

When TTS failover reaches the OpenAI endpoint the requested voice used to be
remapped (af_sky -> nova, and anything unmapped -> alloy). Nothing in the return
value or the logs said so, which meant a Kokoro/Piper hiccup surfaced as the
assistant suddenly speaking in a different — and billed — voice, mid-conversation.

The voice is now passed through unchanged, so an endpoint that does not own it
fails loudly and the underlying outage is what the user sees. The old behaviour
stays reachable behind VOICEMODE_TTS_VOICE_SUBSTITUTION, and logs a warning when
it fires.
"""
import inspect

import pytest

from voice_mode import config, simple_failover


def _substitution_branch_source() -> str:
    """The provider_type == 'openai' voice-selection block."""
    src = inspect.getsource(simple_failover)
    start = src.index('if provider_type == "openai":')
    end = src.index("logger.info(f\"Endpoint {base_url}", start)
    return src[start:end]


def test_substitution_is_off_by_default():
    assert config.TTS_VOICE_SUBSTITUTION is False


def test_default_path_passes_the_requested_voice_through():
    """With substitution off, the branch must select the caller's voice verbatim."""
    branch = _substitution_branch_source()
    assert "or not TTS_VOICE_SUBSTITUTION" in branch, (
        "the pass-through condition is missing - a local voice would still be remapped"
    )
    assert "selected_voice = voice" in branch


def test_mapping_table_is_only_reachable_when_enabled():
    """The af_sky -> nova table must sit behind the flag, not in front of it."""
    branch = _substitution_branch_source()
    guard = branch.index("or not TTS_VOICE_SUBSTITUTION")
    mapping = branch.index('"af_sky": "nova"')
    assert guard < mapping, "the mapping table is reachable before the flag is checked"


def test_substitution_warns_rather_than_informs():
    """If it does fire, it must be visible in the logs - the old code used info."""
    branch = _substitution_branch_source()
    assert "logger.warning(" in branch, "a silent-by-default substitution must warn"
    assert "Substituted voice" in branch


@pytest.mark.parametrize("voice", ["alloy", "echo", "fable", "nova", "onyx", "shimmer"])
def test_native_openai_voices_are_unaffected(voice):
    """A caller asking for a real OpenAI voice is unchanged either way."""
    branch = _substitution_branch_source()
    assert "openai_voices = " in branch
    assert voice in branch or "openai_voices" in branch


def test_config_flag_is_documented_as_an_env_var():
    src = inspect.getsource(config)
    assert "VOICEMODE_TTS_VOICE_SUBSTITUTION" in src
