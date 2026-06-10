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
