"""Tests for the wire-level model kwarg in simple_stt_failover().

Covers VM-1100 acceptance criterion: the `model` field of the outbound
client.audio.transcriptions.create(...) request must be the per-endpoint
resolved model, not a hardcoded literal.

  - mlx-audio endpoint (8890) -> global VOICEMODE_STT_MODEL
  - OpenAI endpoint -> always 'whisper-1' (provider_type override)
  - whisper.cpp endpoint (2022) -> global STT_MODEL (passed but ignored
    by whisper.cpp at the wire; the value must still appear in kwargs)

VM-2342 adds: the mlx-audio STT default model when VOICEMODE_STT_MODEL is
unset, and no ``language`` kwarg to mlx-audio on auto.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_mode.simple_failover import simple_stt_failover


def _make_audio_file():
    """Return a MagicMock standing in for an open audio file."""
    return MagicMock()


async def _capture_kwargs_for_url(
    base_url: str,
    stt_model: str,
    stt_models=None,
    *,
    stt_model_explicit: bool = False,
    whisper_language: str = "auto",
    caller_model=None,
):
    """Run simple_stt_failover with a single STT endpoint and capture the
    kwargs passed to client.audio.transcriptions.create.

    ``stt_model_explicit`` stands for "the user set VOICEMODE_STT_MODEL"
    (VM-2342); the stock install leaves it False with STT_MODEL "whisper-1".
    """
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
        "voice_mode.providers.STT_MODEL_EXPLICIT", stt_model_explicit
    ), patch(
        "voice_mode.simple_failover.WHISPER_LANGUAGE", whisper_language
    ), patch(
        "voice_mode.simple_failover.AsyncOpenAI"
    ) as MockClient:
        mock_client = MockClient.return_value
        mock_client.audio.transcriptions.create = AsyncMock(side_effect=fake_create)
        await simple_stt_failover(_make_audio_file(), model=caller_model)

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


MLX_URL = "http://127.0.0.1:8890/v1"
CPP_URL = "http://127.0.0.1:2022/v1"
MLX_STT_DEFAULT = "mlx-community/whisper-large-v3-turbo-asr-4bit"


class TestMlxAudioSttDefaultModel:
    """VM-2342: a stock install (VOICEMODE_STT_MODEL unset -> "whisper-1")
    pointing STT at mlx-audio sends a repo id mlx-audio can load."""

    @pytest.mark.asyncio
    async def test_stock_install_sends_asr_4bit_to_mlx_audio(self):
        kwargs = await _capture_kwargs_for_url(MLX_URL, stt_model="whisper-1")
        assert kwargs["model"] == MLX_STT_DEFAULT
        # Never the bare turbo id: it 500s "Processor not found" (VM-2334).
        assert kwargs["model"] != "mlx-community/whisper-large-v3-turbo"

    @pytest.mark.asyncio
    async def test_explicit_voicemode_stt_model_still_wins(self):
        kwargs = await _capture_kwargs_for_url(
            MLX_URL, stt_model="whisper-1", stt_model_explicit=True
        )
        assert kwargs["model"] == "whisper-1"

    @pytest.mark.asyncio
    async def test_positional_stt_models_still_wins(self):
        kwargs = await _capture_kwargs_for_url(
            MLX_URL, stt_model="whisper-1", stt_models=["org/positional-asr"]
        )
        assert kwargs["model"] == "org/positional-asr"

    @pytest.mark.asyncio
    async def test_caller_model_still_wins(self):
        kwargs = await _capture_kwargs_for_url(
            MLX_URL, stt_model="whisper-1", caller_model="org/caller-asr"
        )
        assert kwargs["model"] == "org/caller-asr"

    @pytest.mark.asyncio
    async def test_whisper_cpp_stock_install_unchanged(self):
        kwargs = await _capture_kwargs_for_url(CPP_URL, stt_model="whisper-1")
        assert kwargs["model"] == "whisper-1"


class TestSttLanguageByProvider:
    """VM-2342 (folded VM-2334): mlx-audio turns language="auto" into
    <|endoftext|> and skips detection, so it gets NO language on auto."""

    @pytest.mark.asyncio
    async def test_mlx_audio_gets_no_language_on_auto(self):
        kwargs = await _capture_kwargs_for_url(MLX_URL, stt_model="whisper-1")
        assert "language" not in kwargs

    @pytest.mark.asyncio
    async def test_mlx_audio_gets_no_language_when_unset(self):
        kwargs = await _capture_kwargs_for_url(
            MLX_URL, stt_model="whisper-1", whisper_language=""
        )
        assert "language" not in kwargs

    @pytest.mark.asyncio
    async def test_whisper_cpp_still_gets_auto(self):
        kwargs = await _capture_kwargs_for_url(CPP_URL, stt_model="whisper-1")
        assert kwargs["language"] == "auto"

    @pytest.mark.asyncio
    async def test_explicit_language_goes_to_mlx_audio(self):
        kwargs = await _capture_kwargs_for_url(
            MLX_URL, stt_model="whisper-1", whisper_language="en"
        )
        assert kwargs["language"] == "en"

    @pytest.mark.asyncio
    async def test_openai_gets_no_language_on_auto(self):
        kwargs = await _capture_kwargs_for_url(
            "https://api.openai.com/v1", stt_model="whisper-1"
        )
        assert "language" not in kwargs
