"""Tests for voice-first provider selection logic."""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime, timezone

from voice_mode.provider_discovery import ProviderRegistry, EndpointInfo, detect_provider_type
from voice_mode.providers import get_tts_client_and_voice, _select_model_for_endpoint


class TestProviderTypeDetection:
    """Test provider type detection from URLs."""
    
    def test_detect_openai(self):
        assert detect_provider_type("https://api.openai.com/v1") == "openai"
        assert detect_provider_type("https://api.openai.com/v1/") == "openai"
    
    def test_detect_kokoro(self):
        assert detect_provider_type("http://127.0.0.1:8880/v1") == "kokoro"
        assert detect_provider_type("http://127.0.0.1:8880/v1") == "kokoro"
        assert detect_provider_type("http://192.168.1.100:8880/v1") == "kokoro"
    
    def test_detect_whisper(self):
        assert detect_provider_type("http://127.0.0.1:2022/v1") == "whisper"
        assert detect_provider_type("http://127.0.0.1:2022/v1") == "whisper"
    
    def test_detect_generic_local(self):
        assert detect_provider_type("http://127.0.0.1:9999/v1") == "local"
        assert detect_provider_type("http://127.0.0.1/api") == "local"
    
    def test_detect_unknown(self):
        assert detect_provider_type("https://example.com/api") == "unknown"
        assert detect_provider_type("http://external-server.com:8080/v1") == "unknown"


class TestVoiceFirstSelection:
    """Test the voice-first provider selection algorithm."""
    
    @pytest.fixture(autouse=True)
    def mock_voice_preferences(self):
        """Mock voice preferences to avoid test pollution."""
        with patch('voice_mode.providers.get_voice_preferences', return_value=[]):
            yield
    
    @pytest.fixture
    def mock_registry(self):
        """Create a mock provider registry with test data."""
        registry = ProviderRegistry()
        registry._initialized = True
        
        # Mock Kokoro endpoint with af_sky voice
        registry.registry["tts"]["http://127.0.0.1:8880/v1"] = EndpointInfo(
            base_url="http://127.0.0.1:8880/v1",
            healthy=True,
            models=["tts-1"],
            voices=["af_sky", "af_sarah", "am_adam"],
            last_health_check=datetime.now(timezone.utc).isoformat(),
            provider_type="kokoro"
        )
        
        # Mock OpenAI endpoint with standard voices
        registry.registry["tts"]["https://api.openai.com/v1"] = EndpointInfo(
            base_url="https://api.openai.com/v1",
            healthy=True,
            models=["tts-1", "tts-1-hd", "gpt-4o-mini-tts"],
            voices=["alloy", "echo", "fable", "nova", "onyx", "shimmer"],
            last_health_check=datetime.now(timezone.utc).isoformat(),
            provider_type="openai"
        )
        
        return registry
    
    @pytest.mark.asyncio
    async def test_voice_first_selects_kokoro_for_af_sky(self, mock_registry):
        """Test that af_sky voice preference selects Kokoro."""
        with patch('voice_mode.providers.provider_registry', mock_registry):
            with patch('voice_mode.providers.TTS_VOICES', ['af_sky', 'alloy']):
                with patch('voice_mode.providers.TTS_MODELS', ['tts-1', 'tts-1-hd']):
                    with patch('voice_mode.providers.TTS_BASE_URLS', [
                        'http://127.0.0.1:8880/v1',
                        'https://api.openai.com/v1'
                    ]):
                        client, voice, model, endpoint = await get_tts_client_and_voice()
                        
                        assert voice == "af_sky"
                        assert endpoint.provider_type == "kokoro"
                        assert endpoint.base_url == "http://127.0.0.1:8880/v1"
    
    @pytest.mark.asyncio
    async def test_voice_first_selects_openai_for_nova(self, mock_registry):
        """Test that nova voice preference selects OpenAI."""
        with patch('voice_mode.providers.provider_registry', mock_registry):
            with patch('voice_mode.providers.TTS_VOICES', ['nova', 'af_sky']):
                with patch('voice_mode.providers.TTS_MODELS', ['tts-1-hd', 'tts-1']):
                    with patch('voice_mode.providers.TTS_BASE_URLS', [
                        'http://127.0.0.1:8880/v1',
                        'https://api.openai.com/v1'
                    ]):
                        client, voice, model, endpoint = await get_tts_client_and_voice()
                        
                        assert voice == "nova"
                        assert endpoint.provider_type == "openai"
                        assert endpoint.base_url == "https://api.openai.com/v1"
                        assert model == "tts-1-hd"  # First available from preference
    
    @pytest.mark.asyncio
    async def test_specific_voice_overrides_preferences(self, mock_registry):
        """Test that specific voice request overrides preferences."""
        with patch('voice_mode.providers.provider_registry', mock_registry):
            with patch('voice_mode.providers.TTS_VOICES', ['nova', 'alloy']):
                with patch('voice_mode.providers.TTS_BASE_URLS', [
                    'http://127.0.0.1:8880/v1',
                    'https://api.openai.com/v1'
                ]):
                    client, voice, model, endpoint = await get_tts_client_and_voice(voice="af_sarah")
                    
                    assert voice == "af_sarah"
                    assert endpoint.provider_type == "kokoro"
    
    @pytest.mark.asyncio
    async def test_unhealthy_endpoint_skipped(self, mock_registry):
        """Test that unhealthy endpoints are skipped."""
        # Mark Kokoro as unhealthy
        mock_registry.registry["tts"]["http://127.0.0.1:8880/v1"].healthy = False
        
        with patch('voice_mode.providers.provider_registry', mock_registry):
            with patch('voice_mode.providers.TTS_VOICES', ['af_sky', 'nova']):
                with patch('voice_mode.providers.TTS_BASE_URLS', [
                    'http://127.0.0.1:8880/v1',
                    'https://api.openai.com/v1'
                ]):
                    client, voice, model, endpoint = await get_tts_client_and_voice()
                    
                    # Should skip to OpenAI and use nova (second preference)
                    assert voice == "nova"
                    assert endpoint.provider_type == "openai"
    
    @pytest.mark.asyncio
    async def test_model_selection_respects_provider_models(self, mock_registry):
        """Test that model selection respects what the provider supports."""
        with patch('voice_mode.providers.provider_registry', mock_registry):
            with patch('voice_mode.providers.TTS_VOICES', ['af_sky']):
                with patch('voice_mode.providers.TTS_MODELS', ['gpt-4o-mini-tts', 'tts-1-hd', 'tts-1']):
                    with patch('voice_mode.providers.TTS_BASE_URLS', [
                        'http://127.0.0.1:8880/v1',
                        'https://api.openai.com/v1'
                    ]):
                        client, voice, model, endpoint = await get_tts_client_and_voice()
                        
                        # Kokoro only supports tts-1, so it should select that
                        assert voice == "af_sky"
                        assert model == "tts-1"
                        assert endpoint.provider_type == "kokoro"


class TestModelSelection:
    """Test model selection for endpoints."""
    
    def test_select_requested_model_if_available(self):
        endpoint = EndpointInfo(
            base_url="test",
            healthy=True,
            models=["tts-1", "tts-1-hd"],
            voices=[],
            last_health_check="",
            provider_type="test"
        )
        
        assert _select_model_for_endpoint(endpoint, "tts-1-hd") == "tts-1-hd"
    
    def test_select_preferred_model(self):
        endpoint = EndpointInfo(
            base_url="test",
            healthy=True,
            models=["tts-1", "tts-1-hd"],
            voices=[],
            last_health_check="",
            provider_type="test"
        )
        
        with patch('voice_mode.providers.TTS_MODELS', ['gpt-4o-mini-tts', 'tts-1-hd', 'tts-1']):
            # Should pick tts-1-hd as it's the first available from preferences
            assert _select_model_for_endpoint(endpoint) == "tts-1-hd"
    
    def test_fallback_to_first_available(self):
        endpoint = EndpointInfo(
            base_url="test",
            healthy=True,
            models=["custom-model"],
            voices=[],
            last_health_check="",
            provider_type="test"
        )
        
        with patch('voice_mode.providers.TTS_MODELS', ['tts-1', 'tts-1-hd']):
            # No preferred models available, use first
            assert _select_model_for_endpoint(endpoint) == "custom-model"
    
    def test_default_fallback(self):
        endpoint = EndpointInfo(
            base_url="test",
            healthy=True,
            models=[],
            voices=[],
            last_health_check="",
            provider_type="test"
        )
        
        # No models at all, fallback to tts-1
        assert _select_model_for_endpoint(endpoint) == "tts-1"