"""Unit tests for provider_discovery.detect_provider_type and is_local_provider."""

import pytest

from voice_mode.provider_discovery import detect_provider_type, is_local_provider


class TestDetectProviderType:
    """Cover the provider-type ladder including the mlx-audio branch (VM-1106)."""

    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://api.openai.com/v1", "openai"),
            ("http://127.0.0.1:8880/v1", "kokoro"),
            ("http://127.0.0.1:2022/v1", "whisper"),
            ("http://127.0.0.1:8890/v1", "mlx-audio"),
            ("http://localhost:8890", "mlx-audio"),
            # ElevenLabs — single base URL for both TTS and STT
            ("https://api.elevenlabs.io/v1", "elevenlabs"),
        ],
    )
    def test_known_provider_types(self, url, expected):
        assert detect_provider_type(url) == expected

    def test_mlx_audio_substring_fallback(self):
        # Reverse-proxied / non-default-port deployments still match via
        # host/path substring per VM-1106 design.
        assert detect_provider_type("http://example.com/mlx_audio/v1") == "mlx-audio"
        assert detect_provider_type("http://example.com/mlx-audio/v1") == "mlx-audio"

    def test_unknown_url_falls_through(self):
        # Non-localhost, non-OpenAI URLs without mlx-audio markers should
        # remain "unknown" -- this is the existing default behaviour.
        assert detect_provider_type("https://api.example.com/v1") == "unknown"

    def test_empty_base_url(self):
        assert detect_provider_type("") == "unknown"

    def test_generic_local_unchanged(self):
        # A localhost endpoint on an unrecognised port still falls back to
        # the generic "local" provider type (regression check).
        assert detect_provider_type("http://127.0.0.1:9999/v1") == "local"


class TestIsLocalProvider:
    """is_local_provider must treat mlx-audio as local (VM-1106 AC item 6)."""

    def test_mlx_audio_localhost_is_local(self):
        assert is_local_provider("http://127.0.0.1:8890/v1") is True

    def test_mlx_audio_reverse_proxy_is_local(self):
        # Even off-localhost mlx-audio endpoints should be classified local
        # via the provider_type allowlist.
        assert is_local_provider("http://example.com/mlx_audio/v1") is True

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1:8880/v1",
            "http://localhost:2022/v1",
            "http://127.0.0.1:9999/v1",
        ],
    )
    def test_existing_local_providers_unchanged(self, url):
        assert is_local_provider(url) is True

    def test_openai_is_not_local(self):
        assert is_local_provider("https://api.openai.com/v1") is False

    def test_empty_base_url_is_not_local(self):
        assert is_local_provider("") is False


class TestElevenLabsProvider:
    """Detection and registry behaviour for the ElevenLabs provider."""

    # ----- detect_provider_type -----

    def test_elevenlabs_tts_endpoint(self):
        """Native TTS base URL is detected as elevenlabs."""
        assert detect_provider_type("https://api.elevenlabs.io/v1") == "elevenlabs"

    def test_elevenlabs_stt_endpoint(self):
        """Same base URL for STT is also detected as elevenlabs."""
        assert detect_provider_type("https://api.elevenlabs.io/v1") == "elevenlabs"

    def test_elevenlabs_not_local(self):
        """ElevenLabs is a cloud provider -- not local."""
        assert is_local_provider("https://api.elevenlabs.io/v1") is False

    # ----- ProviderRegistry.initialize() -----

    @pytest.mark.asyncio
    async def test_registry_initializes_elevenlabs_tts(self):
        """Registry seeds TTS voices from VOICEMODE_VOICES — accepts names and IDs."""
        from unittest.mock import patch
        from voice_mode.provider_discovery import ProviderRegistry

        el_tts_url = "https://api.elevenlabs.io/v1"
        registry = ProviderRegistry()
        with patch("voice_mode.provider_discovery.TTS_BASE_URLS", [el_tts_url]), \
             patch("voice_mode.provider_discovery.STT_BASE_URLS", []), \
             patch("voice_mode.provider_discovery.config.TTS_VOICES", ["21m00Tcm4TlvDq8ikWAM", "af_sky"]):
            await registry.initialize()

        endpoint = registry.registry["tts"].get(el_tts_url)
        assert endpoint is not None, "ElevenLabs TTS endpoint should be registered"
        assert endpoint.provider_type == "elevenlabs"
        assert len(endpoint.models) >= 1
        assert endpoint.models[0] in ("eleven_flash_v2_5", "eleven_multilingual_v2")
        # Voices come from TTS_VOICES filtered to 20-char IDs — af_sky excluded
        assert "21m00Tcm4TlvDq8ikWAM" in endpoint.voices
        assert "af_sky" not in endpoint.voices

    @pytest.mark.asyncio
    async def test_registry_initializes_elevenlabs_stt(self):
        """Registry registers the ElevenLabs STT endpoint correctly."""
        from unittest.mock import patch
        from voice_mode.provider_discovery import ProviderRegistry

        el_stt_url = "https://api.elevenlabs.io/v1"
        registry = ProviderRegistry()
        with patch("voice_mode.provider_discovery.TTS_BASE_URLS", []), \
             patch("voice_mode.provider_discovery.STT_BASE_URLS", [el_stt_url]):
            await registry.initialize()

        endpoint = registry.registry["stt"].get(el_stt_url)
        assert endpoint is not None, "ElevenLabs STT endpoint should be registered"
        assert endpoint.provider_type == "elevenlabs"
        # STT model should be a scribe variant, not whisper-1
        assert "scribe" in endpoint.models[0]

    # ----- config: per-provider model default -----

    def test_elevenlabs_model_default_in_config(self):
        """TTS_MODEL_PROVIDER_DEFAULTS maps elevenlabs to the configured default model."""
        from voice_mode.config import TTS_MODEL_PROVIDER_DEFAULTS, ELEVENLABS_MODEL
        assert "elevenlabs" in TTS_MODEL_PROVIDER_DEFAULTS
        assert TTS_MODEL_PROVIDER_DEFAULTS["elevenlabs"] == ELEVENLABS_MODEL

    def test_elevenlabs_stt_model_selection(self):
        """STT model selection returns scribe_v1 for elevenlabs provider, not whisper-1."""
        from voice_mode.providers import _select_stt_model_for_endpoint
        from voice_mode.provider_discovery import EndpointInfo
        endpoint = EndpointInfo(
            base_url="https://api.elevenlabs.io/v1",
            models=["scribe_v1"],
            voices=[],
            provider_type="elevenlabs",
        )
        assert _select_stt_model_for_endpoint(endpoint) == "scribe_v1"
        assert _select_stt_model_for_endpoint(endpoint, "scribe_v2") == "scribe_v2"

    # ----- no live API calls -----

    @pytest.mark.asyncio
    async def test_discover_endpoint_elevenlabs_no_http_calls(self):
        """_discover_endpoint for ElevenLabs takes the fast-path -- no HTTP calls."""
        from unittest.mock import patch
        from voice_mode.provider_discovery import ProviderRegistry

        el_url = "https://api.elevenlabs.io/v1"
        registry = ProviderRegistry()

        # If the fast-path is broken and falls through to the OpenAI probe path,
        # AsyncOpenAI or httpx will be called -- we assert they are NOT.
        with patch("voice_mode.provider_discovery.AsyncOpenAI") as mock_openai, \
             patch("httpx.AsyncClient") as mock_httpx:
            await registry._discover_endpoint("tts", el_url)

        mock_openai.assert_not_called()
        mock_httpx.assert_not_called()
        endpoint = registry.registry["tts"].get(el_url)
        assert endpoint is not None
        assert endpoint.provider_type == "elevenlabs"
