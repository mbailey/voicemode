"""Tests for STT_MODEL / STT_MODELS config and reload_configuration() round-trip.

Covers VM-1100 acceptance criteria:
  - `from voice_mode.config import STT_MODEL, STT_MODELS` succeeds.
  - reload_configuration() picks up changes to VOICEMODE_STT_MODEL /
    VOICEMODE_STT_MODELS without a process restart.
"""

import os

import pytest


def test_import_stt_model_and_stt_models():
    """Smoke test: STT_MODEL and STT_MODELS are importable from voice_mode.config."""
    from voice_mode.config import STT_MODEL, STT_MODELS

    assert isinstance(STT_MODEL, str)
    assert isinstance(STT_MODELS, list)


@pytest.fixture
def isolated_reload(monkeypatch):
    """Yield a reload_configuration callable that does not read voicemode.env files.

    The real reload_configuration() calls load_voicemode_env() which reads
    ~/.voicemode/voicemode.env. We patch that to a no-op so tests only see
    values set in os.environ.
    """
    import voice_mode.config as cfg

    monkeypatch.setattr(cfg, "load_voicemode_env", lambda: None)
    monkeypatch.delenv("VOICEMODE_STT_MODEL", raising=False)
    monkeypatch.delenv("VOICEMODE_STT_MODELS", raising=False)
    yield cfg


def test_reload_picks_up_stt_model_change(isolated_reload, monkeypatch):
    """Mutating VOICEMODE_STT_MODEL and calling reload_configuration() updates STT_MODEL."""
    cfg = isolated_reload

    monkeypatch.setenv("VOICEMODE_STT_MODEL", "mlx-community/whisper-large-v3-turbo")
    cfg.reload_configuration()
    assert cfg.STT_MODEL == "mlx-community/whisper-large-v3-turbo"

    monkeypatch.setenv("VOICEMODE_STT_MODEL", "whisper-1")
    cfg.reload_configuration()
    assert cfg.STT_MODEL == "whisper-1"


def test_reload_picks_up_stt_models_comma_list(isolated_reload, monkeypatch):
    """VOICEMODE_STT_MODELS as comma-separated list is parsed on reload."""
    cfg = isolated_reload

    monkeypatch.setenv(
        "VOICEMODE_STT_MODELS",
        "mlx-community/whisper-large-v3-turbo,custom-cpp-model,whisper-1",
    )
    cfg.reload_configuration()
    assert cfg.STT_MODELS == [
        "mlx-community/whisper-large-v3-turbo",
        "custom-cpp-model",
        "whisper-1",
    ]

    # Whitespace around entries is stripped, empty entries dropped (parse_comma_list).
    monkeypatch.setenv("VOICEMODE_STT_MODELS", " a , b ,, c ")
    cfg.reload_configuration()
    assert cfg.STT_MODELS == ["a", "b", "c"]


def test_defaults_when_env_unset(isolated_reload):
    """With VOICEMODE_STT_MODEL[S] absent, defaults are 'whisper-1' and []."""
    cfg = isolated_reload

    assert "VOICEMODE_STT_MODEL" not in os.environ
    assert "VOICEMODE_STT_MODELS" not in os.environ

    cfg.reload_configuration()
    assert cfg.STT_MODEL == "whisper-1"
    assert cfg.STT_MODELS == []
