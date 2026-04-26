"""Tests for the wire-level model kwarg in simple_stt_failover().

Covers VM-1100 acceptance criterion: the `model` field of the outbound
client.audio.transcriptions.create(...) request must be the per-endpoint
resolved model, not a hardcoded literal.

  - mlx-audio endpoint (8890) -> global VOICEMODE_STT_MODEL
  - OpenAI endpoint -> always 'whisper-1' (provider_type override)
  - whisper.cpp endpoint (2022) -> global STT_MODEL (passed but ignored
    by whisper.cpp at the wire; the value must still appear in kwargs)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_mode.simple_failover import simple_stt_failover


def _make_audio_file():
    """Return a MagicMock standing in for an open audio file."""
    return MagicMock()


async def _capture_kwargs_for_url(base_url: str, stt_model: str, stt_models=None):
    """Run simple_stt_failover with a single STT endpoint and capture the
    kwargs passed to client.audio.transcriptions.create."""
    if stt_models is None:
        stt_models = []

    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return "ok"

    with patch(
        "voice_mode.simple_failover.STT_BASE_URLS", [base_url]
    ), patch(
        "voice_mode.providers.STT_BASE_URLS", [base_url]
    ), patch(
        "voice_mode.providers.STT_MODEL", stt_model
    ), patch(
        "voice_mode.providers.STT_MODELS", stt_models
    ), patch(
        "voice_mode.simple_failover.AsyncOpenAI"
    ) as MockClient:
        mock_client = MockClient.return_value
        mock_client.audio.transcriptions.create = AsyncMock(side_effect=fake_create)
        await simple_stt_failover(_make_audio_file())

    return captured


class TestSttFailoverWireModel:
    """Verify the resolved model lands in transcription_kwargs at the wire."""

    @pytest.mark.asyncio
    async def test_mlx_audio_endpoint_uses_global_stt_model(self):
        """An mlx-audio endpoint with VOICEMODE_STT_MODEL set should send
        that model in the outbound request body."""
        kwargs = await _capture_kwargs_for_url(
            base_url="http://127.0.0.1:8890/v1",
            stt_model="mlx-community/whisper-large-v3-turbo",
        )
        assert kwargs["model"] == "mlx-community/whisper-large-v3-turbo"

    @pytest.mark.asyncio
    async def test_openai_endpoint_overrides_to_whisper_1(self):
        """An OpenAI endpoint always sends model='whisper-1', regardless of
        what VOICEMODE_STT_MODEL is configured to."""
        kwargs = await _capture_kwargs_for_url(
            base_url="https://api.openai.com/v1",
            stt_model="mlx-community/whisper-large-v3-turbo",
        )
        assert kwargs["model"] == "whisper-1"

    @pytest.mark.asyncio
    async def test_whisper_cpp_endpoint_passes_configured_stt_model(self):
        """whisper.cpp ignores the model field at the wire, but the resolved
        global STT_MODEL must still be present in transcription_kwargs."""
        kwargs = await _capture_kwargs_for_url(
            base_url="http://127.0.0.1:2022/v1",
            stt_model="custom-cpp-model",
        )
        assert kwargs["model"] == "custom-cpp-model"
