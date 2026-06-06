"""Tests for the in-process Parakeet STT backend.

Parakeet is selected by a ``parakeet://`` URL in ``VOICEMODE_STT_BASE_URLS``.
Unlike the HTTP STT providers it transcribes in-process via ``parakeet-mlx``
(an optional, Apple-Silicon-only dependency). These tests stub that dependency
so they run on any platform without MLX installed, and verify:

1. ``parakeet://`` is detected as a local provider.
2. ``transcribe_parakeet`` loads the model once (caches), preserves the audio
   file's read position, and returns the transcript text.
3. The STT failover loop dispatches ``parakeet://`` to the in-process backend
   and returns a well-formed result dict.
4. A backend failure (e.g. missing dependency) is caught and the loop treats
   the endpoint as failed -- i.e. it falls through to the next endpoint.
"""

import io
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from voice_mode.provider_discovery import detect_provider_type, is_local_provider


def test_parakeet_url_detected_as_local_provider():
    assert detect_provider_type("parakeet://local") == "parakeet"
    assert is_local_provider("parakeet://local") is True


def _install_fake_parakeet(monkeypatch, text="hello world", record=None):
    """Inject a fake ``parakeet_mlx`` module whose model returns ``text``.

    If ``record`` (a list) is given, each from_pretrained call appends its
    model id -- lets a test assert the load-once caching behaviour.
    """
    fake = types.ModuleType("parakeet_mlx")

    def from_pretrained(model_id):
        if record is not None:
            record.append(model_id)
        model = MagicMock()
        model.transcribe.return_value = types.SimpleNamespace(text=text)
        return model

    fake.from_pretrained = from_pretrained
    monkeypatch.setitem(sys.modules, "parakeet_mlx", fake)
    # Reset the module-level model cache so each test starts clean.
    import voice_mode.stt_backends.parakeet as pk
    monkeypatch.setattr(pk, "_MODELS", {})
    return fake


@pytest.mark.asyncio
async def test_transcribe_parakeet_returns_text_and_preserves_position(monkeypatch):
    _install_fake_parakeet(monkeypatch, text="the quick brown fox")
    from voice_mode.stt_backends.parakeet import transcribe_parakeet

    audio = io.BytesIO(b"RIFF....fake wav bytes....")
    audio.seek(4)  # non-zero starting position to prove we restore it

    text = await transcribe_parakeet(audio, "mlx-community/parakeet-tdt-0.6b-v3")

    assert text == "the quick brown fox"
    assert audio.tell() == 4  # position preserved


@pytest.mark.asyncio
async def test_transcribe_parakeet_caches_model(monkeypatch):
    loads = []
    _install_fake_parakeet(monkeypatch, text="hi", record=loads)
    from voice_mode.stt_backends.parakeet import transcribe_parakeet

    audio = io.BytesIO(b"abc")
    await transcribe_parakeet(audio, "model-x")
    await transcribe_parakeet(audio, "model-x")

    assert loads == ["model-x"]  # loaded once, not twice


@pytest.mark.asyncio
async def test_failover_dispatches_to_parakeet(monkeypatch):
    _install_fake_parakeet(monkeypatch, text="transcribed via parakeet")
    monkeypatch.setattr(
        "voice_mode.simple_failover.STT_BASE_URLS", ["parakeet://local"]
    )
    from voice_mode.simple_failover import simple_stt_failover

    audio = io.BytesIO(b"some audio bytes")
    result = await simple_stt_failover(audio)

    assert result is not None
    assert result.get("text") == "transcribed via parakeet"
    assert result.get("provider") == "parakeet"
    assert result.get("endpoint") == "parakeet://local"
    assert result["metrics"]["is_local"] is True


@pytest.mark.asyncio
async def test_failover_handles_parakeet_backend_failure(monkeypatch):
    # Simulate a backend that raises (e.g. parakeet-mlx not installed).
    async def boom(audio_file, model_id):
        raise ImportError("No module named 'parakeet_mlx'")

    monkeypatch.setattr(
        "voice_mode.stt_backends.parakeet.transcribe_parakeet", boom
    )
    monkeypatch.setattr(
        "voice_mode.simple_failover.STT_BASE_URLS", ["parakeet://local"]
    )
    from voice_mode.simple_failover import simple_stt_failover

    audio = io.BytesIO(b"some audio bytes")
    result = await simple_stt_failover(audio)

    # Only endpoint failed -> connection_failed, proving the exception was
    # caught by the failover loop rather than propagating.
    assert result is not None
    assert result.get("error_type") == "connection_failed"
