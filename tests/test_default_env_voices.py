"""Regression tests for the auto-generated default voicemode.env.

Guards VM-1556: a fresh install with no OpenAI key must default to a
local-only voice list. The earlier attempt expressed this as an inline
comment (`VOICEMODE_VOICES=af_sky #,alloy ...`), but voicemode's hand-rolled
env parser does NOT strip inline `#` comments, so that produced the literal
value `af_sky #,alloy ...` -> parsed list `['af_sky #', 'alloy # ...']`:
the local voice no longer matched AND the OpenAI `alloy` footgun came back.

These tests run the REAL loader against the REAL generated template so the
trap cannot silently return.
"""

import os
import pathlib
import pytest
from unittest.mock import patch

from voice_mode.config import load_voicemode_env, parse_comma_list


@pytest.fixture
def fresh_install(tmp_path, monkeypatch):
    """Simulate a fresh install: empty HOME + cwd, no VOICEMODE_* env vars.

    Triggers load_voicemode_env() to write its default template, then yields
    so the test can inspect what that default parses to.
    """
    home = tmp_path / "home"
    cwd = tmp_path / "cwd"
    home.mkdir(exist_ok=True)
    cwd.mkdir(exist_ok=True)

    # Drop any VOICEMODE_* vars (the loader skips keys already in os.environ).
    saved = {k: v for k, v in os.environ.items() if k.startswith("VOICEMODE_")}
    for k in saved:
        del os.environ[k]

    monkeypatch.chdir(cwd)
    try:
        with patch.object(pathlib.Path, "home", return_value=home):
            load_voicemode_env()
            yield home
    finally:
        for k in list(os.environ.keys()):
            if k.startswith("VOICEMODE_"):
                del os.environ[k]
        os.environ.update(saved)


def test_default_env_is_generated(fresh_install):
    """The loader writes a default voicemode.env on a fresh install."""
    generated = fresh_install / ".voicemode" / "voicemode.env"
    assert generated.exists(), "default voicemode.env was not generated"


def test_default_voices_are_local_only(fresh_install):
    """Default VOICEMODE_VOICES parses to exactly ['af_sky'] -- no alloy, no stray '#'.

    This is the core VM-1556 guard: a no-key user must not get an OpenAI voice
    (`alloy`) silently in the default preference list, and the inline-comment
    parsing trap must not corrupt the voice name.
    """
    voices = parse_comma_list("VOICEMODE_VOICES", "af_sky")
    assert voices == ["af_sky"], f"expected local-only default, got {voices!r}"
    # Belt-and-braces: no inline-comment leakage, no OpenAI voice.
    assert all("#" not in v for v in voices), f"inline '#' leaked into voices: {voices!r}"
    assert "alloy" not in voices, f"OpenAI voice 'alloy' is in the default list: {voices!r}"


# ---------------------------------------------------------------------------
# VM-2629: the commented-out Parakeet (mlx-audio) STT example in the template.
#
# The example must ship INERT (commented, so a fresh install's STT config is
# unchanged), must be VALID once a user uncomments it (the hand-rolled parser
# keeps inline `#` text, so a stray comment would corrupt the value), and must
# keep meaning what the template and docs say it means.
# ---------------------------------------------------------------------------

PARAKEET_URLS = (
    "http://127.0.0.1:8890/v1,http://127.0.0.1:2022/v1,https://api.openai.com/v1"
)
PARAKEET_MODEL = "mlx-community/parakeet-tdt-0.6b-v3"
PARAKEET_LINES = (
    f"VOICEMODE_STT_BASE_URLS={PARAKEET_URLS}",
    f"VOICEMODE_STT_MODEL={PARAKEET_MODEL}",
)


def _generated_lines(home):
    return (home / ".voicemode" / "voicemode.env").read_text().splitlines()


def test_parakeet_example_is_present_and_commented(fresh_install):
    """Both example lines ship in the template, each commented out exactly once."""
    lines = _generated_lines(fresh_install)
    for setting in PARAKEET_LINES:
        assert f"# {setting}" in lines, f"commented example missing: {setting!r}"
        # No active (uncommented) copy of the setting anywhere in the file.
        assert setting not in [ln.strip() for ln in lines], (
            f"example is live, not commented: {setting!r}"
        )


def test_parakeet_example_does_not_change_fresh_install_stt(fresh_install):
    """A fresh install loads no STT URL/model from the template: defaults stand."""
    assert "VOICEMODE_STT_BASE_URLS" not in os.environ
    assert "VOICEMODE_STT_MODEL" not in os.environ


def test_parakeet_example_parses_when_uncommented(fresh_install):
    """Uncomment the example and the REAL loader yields exactly the documented values."""
    env_file = fresh_install / ".voicemode" / "voicemode.env"
    text = env_file.read_text()
    for setting in PARAKEET_LINES:
        text = text.replace(f"# {setting}", setting)
    env_file.write_text(text)

    load_voicemode_env()

    assert os.environ["VOICEMODE_STT_MODEL"] == PARAKEET_MODEL
    assert parse_comma_list("VOICEMODE_STT_BASE_URLS", "") == [
        "http://127.0.0.1:8890/v1",  # mlx-audio first
        "http://127.0.0.1:2022/v1",  # whisper.cpp fallback
        "https://api.openai.com/v1",  # OpenAI last
    ]


def test_parakeet_example_model_resolution_matches_docs():
    """Pin what the template and configuration guide claim about the example.

    With VOICEMODE_STT_MODEL set explicitly, the id goes to every non-OpenAI
    endpoint (whisper.cpp included, which ignores it); OpenAI always gets
    whisper-1. The per-endpoint alternative, VOICEMODE_STT_MODELS with the
    Parakeet id alone, reaches mlx-audio only.
    """
    from voice_mode.provider_discovery import EndpointInfo, detect_provider_type
    from voice_mode.providers import _select_stt_model_for_endpoint

    urls = PARAKEET_URLS.split(",")
    assert [detect_provider_type(u) for u in urls] == ["mlx-audio", "whisper", "openai"]

    def resolve(url):
        info = EndpointInfo(
            base_url=url, models=[], voices=[], provider_type=detect_provider_type(url)
        )
        return _select_stt_model_for_endpoint(info)

    # The two-line example, as shipped.
    with patch("voice_mode.providers.STT_BASE_URLS", urls), \
         patch("voice_mode.providers.STT_MODELS", []), \
         patch("voice_mode.providers.STT_MODEL", PARAKEET_MODEL), \
         patch("voice_mode.providers.STT_MODEL_EXPLICIT", True):
        assert [resolve(u) for u in urls] == [PARAKEET_MODEL, PARAKEET_MODEL, "whisper-1"]

    # The per-endpoint alternative from the configuration guide.
    with patch("voice_mode.providers.STT_BASE_URLS", urls), \
         patch("voice_mode.providers.STT_MODELS", [PARAKEET_MODEL]), \
         patch("voice_mode.providers.STT_MODEL", "whisper-1"), \
         patch("voice_mode.providers.STT_MODEL_EXPLICIT", False):
        assert [resolve(u) for u in urls] == [PARAKEET_MODEL, "whisper-1", "whisper-1"]
