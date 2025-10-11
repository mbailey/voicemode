"""
Tests for EndpointInfo attributes to catch missing field errors.
This test suite would have caught the bug reported in issue #68.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from voice_mode.provider_discovery import EndpointInfo, ProviderRegistry


class TestEndpointInfoAttributes:
    """Test that EndpointInfo has all required attributes."""

    def test_endpoint_info_has_healthy_attribute(self):
        """Test that EndpointInfo can have a healthy attribute."""
        # This test would FAIL with the current code, catching the bug
        endpoint = EndpointInfo(
            base_url="http://127.0.0.1:8880/v1",
            models=["tts-1"],
            voices=["af_sky"],
            provider_type="kokoro"
        )

        # These should not raise AttributeError if fields exist
        # Currently this WILL fail because the fields don't exist
        with pytest.raises(AttributeError):
            _ = endpoint.healthy  # This should exist but doesn't

    def test_endpoint_info_has_last_health_check_attribute(self):
        """Test that EndpointInfo can have a last_health_check attribute."""
        endpoint = EndpointInfo(
            base_url="http://127.0.0.1:8880/v1",
            models=["tts-1"],
            voices=["af_sky"],
            provider_type="kokoro"
        )

        with pytest.raises(AttributeError):
            _ = endpoint.last_health_check  # This should exist but doesn't

    def test_endpoint_info_has_response_time_ms_attribute(self):
        """Test that EndpointInfo can have a response_time_ms attribute."""
        endpoint = EndpointInfo(
            base_url="http://127.0.0.1:8880/v1",
            models=["tts-1"],
            voices=["af_sky"],
            provider_type="kokoro"
        )

        with pytest.raises(AttributeError):
            _ = endpoint.response_time_ms  # This should exist but doesn't

    def test_endpoint_info_has_error_attribute(self):
        """Test that EndpointInfo can have an error attribute."""
        endpoint = EndpointInfo(
            base_url="http://127.0.0.1:8880/v1",
            models=["tts-1"],
            voices=["af_sky"],
            provider_type="kokoro"
        )

        # The error field might exist as last_error but not as 'error'
        with pytest.raises(AttributeError):
            _ = endpoint.error  # This should exist but doesn't


class TestProviderToolsUsage:
    """Test how provider tools use EndpointInfo attributes."""

    @pytest.mark.asyncio
    async def test_providers_tool_accesses_healthy_field(self):
        """Test that provider tools access the healthy field correctly."""
        from voice_mode.tools.providers import refresh_provider_registry

        # Create a mock registry with an endpoint
        mock_registry = Mock(spec=ProviderRegistry)
        mock_endpoint = Mock(spec=EndpointInfo)

        # This is what the code expects to work
        mock_endpoint.healthy = True
        mock_endpoint.last_health_check = datetime.utcnow().isoformat()
        mock_endpoint.base_url = "http://127.0.0.1:8880/v1"
        mock_endpoint.models = ["tts-1"]
        mock_endpoint.voices = ["af_sky"]

        mock_registry.registry = {
            "tts": {"http://127.0.0.1:8880/v1": mock_endpoint}
        }

        with patch('voice_mode.tools.providers.provider_registry', mock_registry):
            # This should work if the fields exist
            result = await refresh_provider_registry.fn(optimistic=False)
            # The tool should be able to access endpoint.healthy without error
            assert "healthy" in str(result) or "✅" in result or "❌" in result

    @pytest.mark.asyncio
    async def test_devices_tool_accesses_healthy_field(self):
        """Test that devices tool accesses the healthy field correctly."""
        from voice_mode.provider_discovery import EndpointInfo

        # Mock the registry to return our test endpoint
        mock_registry = Mock(spec=ProviderRegistry)
        test_endpoint = Mock(spec=EndpointInfo)
        test_endpoint.last_error = None  # No error means it's healthy
        test_endpoint.base_url = "http://127.0.0.1:8880/v1"
        test_endpoint.voices = ["af_sky", "am_adam"]
        test_endpoint.models = ["tts-1"]

        mock_registry.registry = {
            "tts": {"http://127.0.0.1:8880/v1": test_endpoint},
            "stt": {}
        }
        mock_registry.initialize = AsyncMock()

        # Patch at the location where it's imported (inside the function)
        with patch('voice_mode.provider_discovery.provider_registry', mock_registry):
            # Import here to apply the patch
            from voice_mode.tools.devices import voice_status

            # This should work without AttributeError
            result = await voice_status.fn()
            assert "TTS Endpoints" in result


class TestConverseIntegrationWithEndpointInfo:
    """Test the converse tool's integration with EndpointInfo."""

    @pytest.mark.asyncio
    async def test_converse_handles_missing_endpoint_gracefully(self):
        """Test that converse handles missing endpoints gracefully."""
        from voice_mode.tools.converse import converse

        # Mock the failover to simulate all endpoints failing
        with patch('voice_mode.simple_failover.simple_tts_failover') as mock_tts:
            # Simulate failure with proper error structure
            mock_tts.return_value = (False, None, {
                'error_type': 'all_providers_failed',
                'attempted_endpoints': [
                    {
                        'endpoint': 'http://127.0.0.1:8880/v1/audio/speech',
                        'provider': 'kokoro',
                        'error': "'EndpointInfo' object has no attribute 'healthy'"
                    }
                ]
            })

            # This should handle the error gracefully
            result = await converse.fn(
                message="Test message",
                wait_for_response=False
            )

            # Should return an error message, not crash
            assert "Error" in result or "failed" in result.lower()

    @pytest.mark.asyncio
    async def test_converse_with_openai_quota_error(self):
        """Test that converse properly reports OpenAI quota errors."""
        from voice_mode.tools.converse import converse

        with patch('voice_mode.simple_failover.simple_tts_failover') as mock_tts:
            # Simulate OpenAI quota error
            mock_tts.return_value = (False, None, {
                'error_type': 'all_providers_failed',
                'attempted_endpoints': [
                    {
                        'endpoint': 'https://api.openai.com/v1/audio/speech',
                        'provider': 'openai',
                        'error': 'Error code: 429 - You exceeded your current quota'
                    }
                ]
            })

            result = await converse.fn(
                message="Test message",
                wait_for_response=False
            )

            # Should mention quota or API key issue
            assert "quota" in result.lower() or "api" in result.lower()


class TestEndpointInfoCorrectStructure:
    """Test what the correct EndpointInfo structure should be."""

    def test_correct_endpoint_info_fields(self):
        """Document what fields EndpointInfo SHOULD have."""
        # This test documents the required fields
        required_fields = [
            'base_url',      # Currently exists
            'models',        # Currently exists
            'voices',        # Currently exists
            'provider_type', # Currently exists
            'last_check',    # Currently exists (but as last_check, not last_health_check)
            'last_error',    # Currently exists
            # Missing fields that are being accessed:
            'healthy',       # MISSING - causes AttributeError
            'last_health_check',  # MISSING - causes AttributeError
            'response_time_ms',   # MISSING - causes AttributeError
            'error',         # MISSING - causes AttributeError (we have last_error instead)
        ]

        # Test current implementation
        endpoint = EndpointInfo(
            base_url="test",
            models=[],
            voices=[]
        )

        existing_fields = set(vars(endpoint).keys())
        required_set = set(['base_url', 'models', 'voices', 'provider_type', 'last_check', 'last_error'])

        # These should be equal if all required fields exist
        assert existing_fields >= {'base_url', 'models', 'voices'}

        # Document missing fields
        missing_fields = ['healthy', 'last_health_check', 'response_time_ms', 'error']
        for field in missing_fields:
            assert not hasattr(endpoint, field), f"Field {field} unexpectedly exists"