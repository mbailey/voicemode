"""Test TTS error handling with detailed endpoint reporting."""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import httpx
from voice_mode.simple_failover import simple_tts_failover


class TestTTSErrorHandling:
    """Test suite for TTS error handling with detailed error reporting."""

    @pytest.mark.asyncio
    async def test_connection_refused_all_endpoints(self):
        """Test when all TTS endpoints refuse connection."""
        with patch('voice_mode.simple_failover.TTS_BASE_URLS', ['http://localhost:8880/v1', 'https://api.openai.com/v1']), \
             patch('voice_mode.simple_failover.OPENAI_API_KEY', 'test-key'), \
             patch('voice_mode.core.text_to_speech') as mock_tts:

            # Simulate connection refused for both endpoints
            mock_tts.side_effect = [
                Exception("Connection refused"),
                Exception("Connection error")
            ]

            success, metrics, config = await simple_tts_failover(
                text="Hello world",
                voice="nova",
                model="tts-1"
            )

            assert success is False
            assert config['error_type'] == 'all_providers_failed'
            assert len(config['attempted_endpoints']) == 2
            assert config['attempted_endpoints'][0]['endpoint'] == 'http://localhost:8880/v1/audio/speech'
            assert 'Connection refused' in config['attempted_endpoints'][0]['error']
            assert config['attempted_endpoints'][1]['endpoint'] == 'https://api.openai.com/v1/audio/speech'
            assert 'Connection error' in config['attempted_endpoints'][1]['error']

    @pytest.mark.asyncio
    async def test_authentication_error_openai(self):
        """Test authentication error on OpenAI endpoint."""
        with patch('voice_mode.simple_failover.TTS_BASE_URLS', ['https://api.openai.com/v1']), \
             patch('voice_mode.simple_failover.OPENAI_API_KEY', 'invalid-key'), \
             patch('voice_mode.core.text_to_speech') as mock_tts:

            # Simulate auth error
            mock_tts.side_effect = Exception("Incorrect API key provided")

            success, metrics, config = await simple_tts_failover(
                text="Hello world",
                voice="nova",
                model="tts-1"
            )

            assert success is False
            assert config['error_type'] == 'all_providers_failed'
            assert len(config['attempted_endpoints']) == 1
            assert 'Incorrect API key' in config['attempted_endpoints'][0]['error']

    @pytest.mark.asyncio
    async def test_no_api_key_error(self):
        """Test missing API key for cloud endpoint."""
        with patch('voice_mode.simple_failover.TTS_BASE_URLS', ['https://api.openai.com/v1']), \
             patch('voice_mode.simple_failover.OPENAI_API_KEY', None):

            success, metrics, config = await simple_tts_failover(
                text="Hello world",
                voice="nova",
                model="tts-1"
            )

            assert success is False
            # We don't even attempt the endpoint without API key
            assert config is not None

    @pytest.mark.asyncio
    async def test_successful_tts(self):
        """Test successful TTS with provider info."""
        with patch('voice_mode.simple_failover.TTS_BASE_URLS', ['http://localhost:8880/v1']), \
             patch('voice_mode.simple_failover.OPENAI_API_KEY', None), \
             patch('voice_mode.core.text_to_speech') as mock_tts:

            # Simulate successful TTS
            mock_tts.return_value = (True, {'duration': 1.5})

            success, metrics, config = await simple_tts_failover(
                text="Hello world",
                voice="af_sky",
                model="tts-1"
            )

            assert success is True
            assert metrics == {'duration': 1.5}
            assert config['provider'] == 'kokoro'
            assert config['endpoint'] == 'http://localhost:8880/v1/audio/speech'
            assert config['voice'] == 'af_sky'

    @pytest.mark.asyncio
    async def test_fallback_to_openai(self):
        """Test falling back from local to OpenAI."""
        with patch('voice_mode.simple_failover.TTS_BASE_URLS', ['http://localhost:8880/v1', 'https://api.openai.com/v1']), \
             patch('voice_mode.simple_failover.OPENAI_API_KEY', 'valid-key'), \
             patch('voice_mode.core.text_to_speech') as mock_tts:

            # First fails, second succeeds
            mock_tts.side_effect = [
                Exception("Service unavailable"),
                (True, {'duration': 2.0})
            ]

            success, metrics, config = await simple_tts_failover(
                text="Hello world",
                voice="nova",
                model="tts-1"
            )

            assert success is True
            assert config['provider'] == 'openai'
            assert config['base_url'] == 'https://api.openai.com/v1'

    @pytest.mark.asyncio
    async def test_voice_mapping(self):
        """Test that voices are mapped correctly for different providers."""
        with patch('voice_mode.simple_failover.TTS_BASE_URLS', ['https://api.openai.com/v1']), \
             patch('voice_mode.simple_failover.OPENAI_API_KEY', 'test-key'), \
             patch('voice_mode.core.text_to_speech') as mock_tts:

            # Simulate successful TTS
            mock_tts.return_value = (True, {})

            # Try with a Kokoro voice that should be mapped to OpenAI
            success, metrics, config = await simple_tts_failover(
                text="Test",
                voice="af_sky",  # Kokoro voice
                model="tts-1"
            )

            # Check that af_sky was mapped to nova for OpenAI
            mock_tts.assert_called_once()
            call_args = mock_tts.call_args
            assert call_args[1]['tts_voice'] == 'nova'  # af_sky maps to nova

    @pytest.mark.asyncio
    async def test_detailed_error_info(self):
        """Test that detailed error info is included for each endpoint."""
        with patch('voice_mode.simple_failover.TTS_BASE_URLS', ['http://localhost:8880/v1', 'https://api.openai.com/v1']), \
             patch('voice_mode.simple_failover.OPENAI_API_KEY', 'test-key'), \
             patch('voice_mode.core.text_to_speech') as mock_tts:

            # Different errors for each endpoint
            mock_tts.side_effect = [
                Exception("404 Not Found"),
                Exception("Rate limit exceeded")
            ]

            success, metrics, config = await simple_tts_failover(
                text="Hello",
                voice="nova",
                model="tts-1-hd"
            )

            assert success is False
            assert config['error_type'] == 'all_providers_failed'

            # Check first endpoint error details
            endpoint1 = config['attempted_endpoints'][0]
            assert endpoint1['provider'] == 'kokoro'
            assert endpoint1['voice'] == 'nova'
            assert endpoint1['model'] == 'tts-1-hd'
            assert '404 Not Found' in endpoint1['error']

            # Check second endpoint error details
            endpoint2 = config['attempted_endpoints'][1]
            assert endpoint2['provider'] == 'openai'
            assert endpoint2['voice'] == 'nova'
            assert 'Rate limit' in endpoint2['error']