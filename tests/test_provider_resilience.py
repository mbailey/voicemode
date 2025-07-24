"""Test provider resilience and always-try-local behavior."""

import pytest
import asyncio
import os
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone

from voice_mode.provider_discovery import (
    ProviderRegistry, 
    is_local_provider,
    detect_provider_type
)
from voice_mode import config


class TestProviderResilience:
    """Test suite for provider resilience features."""
    
    def test_is_local_provider(self):
        """Test local provider detection."""
        # Local providers
        assert is_local_provider("http://127.0.0.1:8880/v1") is True
        assert is_local_provider("http://localhost:8880/v1") is True
        assert is_local_provider("http://127.0.0.1:2022/v1") is True
        assert is_local_provider("http://localhost:2022/v1") is True
        
        # Remote providers
        assert is_local_provider("https://api.openai.com/v1") is False
        assert is_local_provider("https://example.com/v1") is False
    
    def test_detect_provider_type(self):
        """Test provider type detection."""
        assert detect_provider_type("http://127.0.0.1:8880/v1") == "kokoro"
        assert detect_provider_type("http://localhost:8880/v1") == "kokoro"
        assert detect_provider_type("http://127.0.0.1:2022/v1") == "whisper"
        assert detect_provider_type("http://localhost:2022/v1") == "whisper"
        assert detect_provider_type("https://api.openai.com/v1") == "openai"
        assert detect_provider_type("http://127.0.0.1:9999/v1") == "local"
    
    @pytest.mark.asyncio
    async def test_mark_unhealthy_with_always_try_local_enabled(self):
        """Test that local providers are not marked unhealthy when ALWAYS_TRY_LOCAL is enabled."""
        # Ensure ALWAYS_TRY_LOCAL is enabled
        with patch.object(config, 'ALWAYS_TRY_LOCAL', True):
            registry = ProviderRegistry()
            await registry.initialize()
            
            # Get initial state of local TTS endpoint
            local_url = "http://127.0.0.1:8880/v1"
            assert local_url in registry.registry["tts"]
            initial_info = registry.registry["tts"][local_url]
            assert initial_info.healthy is True
            
            # Try to mark it as unhealthy
            await registry.mark_unhealthy("tts", local_url, "Connection refused")
            
            # Check that it's still marked as healthy
            updated_info = registry.registry["tts"][local_url]
            assert updated_info.healthy is True
            assert "will retry" in updated_info.error
            assert updated_info.last_health_check != initial_info.last_health_check
    
    @pytest.mark.asyncio
    async def test_mark_unhealthy_with_always_try_local_disabled(self):
        """Test normal behavior when ALWAYS_TRY_LOCAL is disabled."""
        # Disable ALWAYS_TRY_LOCAL
        with patch.object(config, 'ALWAYS_TRY_LOCAL', False):
            registry = ProviderRegistry()
            await registry.initialize()
            
            # Get initial state of local TTS endpoint
            local_url = "http://127.0.0.1:8880/v1"
            assert local_url in registry.registry["tts"]
            initial_info = registry.registry["tts"][local_url]
            assert initial_info.healthy is True
            
            # Try to mark it as unhealthy
            await registry.mark_unhealthy("tts", local_url, "Connection refused")
            
            # Check that it's now marked as unhealthy
            updated_info = registry.registry["tts"][local_url]
            assert updated_info.healthy is False
            assert updated_info.error == "Connection refused"
            assert updated_info.last_health_check != initial_info.last_health_check
    
    @pytest.mark.asyncio
    async def test_remote_providers_always_marked_unhealthy(self):
        """Test that remote providers are always marked unhealthy regardless of ALWAYS_TRY_LOCAL."""
        # Enable ALWAYS_TRY_LOCAL
        with patch.object(config, 'ALWAYS_TRY_LOCAL', True):
            registry = ProviderRegistry()
            await registry.initialize()
            
            # Get initial state of OpenAI endpoint
            openai_url = "https://api.openai.com/v1"
            assert openai_url in registry.registry["tts"]
            initial_info = registry.registry["tts"][openai_url]
            assert initial_info.healthy is True
            
            # Try to mark it as unhealthy
            await registry.mark_unhealthy("tts", openai_url, "API key invalid")
            
            # Check that it's marked as unhealthy (normal behavior for remote)
            updated_info = registry.registry["tts"][openai_url]
            assert updated_info.healthy is False
            assert updated_info.error == "API key invalid"
    
    @pytest.mark.asyncio
    async def test_get_healthy_endpoints_with_resilient_local(self):
        """Test that local endpoints are returned even after failures when ALWAYS_TRY_LOCAL is enabled."""
        with patch.object(config, 'ALWAYS_TRY_LOCAL', True):
            registry = ProviderRegistry()
            await registry.initialize()
            
            # Mark local endpoint as failed
            local_url = "http://127.0.0.1:8880/v1"
            await registry.mark_unhealthy("tts", local_url, "Service unavailable")
            
            # Get healthy endpoints
            healthy_endpoints = registry.get_healthy_endpoints("tts")
            
            # Local endpoint should still be included
            endpoint_urls = [ep.base_url for ep in healthy_endpoints]
            assert local_url in endpoint_urls
            
            # Find the local endpoint and check its state
            local_endpoint = next(ep for ep in healthy_endpoints if ep.base_url == local_url)
            assert local_endpoint.healthy is True
            assert "will retry" in local_endpoint.error
    
    @pytest.mark.asyncio
    async def test_provider_selection_order_maintained(self):
        """Test that provider selection order is maintained with resilience enabled."""
        # Set up specific provider order
        test_urls = ["http://127.0.0.1:8880/v1", "https://api.openai.com/v1"]
        with patch.object(config, 'TTS_BASE_URLS', test_urls):
            with patch.object(config, 'ALWAYS_TRY_LOCAL', True):
                registry = ProviderRegistry()
                await registry.initialize()
                
                # Mark both as having errors
                await registry.mark_unhealthy("tts", test_urls[0], "Local service down")
                await registry.mark_unhealthy("tts", test_urls[1], "API limit reached")
                
                # Get healthy endpoints
                healthy_endpoints = registry.get_healthy_endpoints("tts")
                
                # Should have one endpoint (local stays healthy, remote marked unhealthy)
                assert len(healthy_endpoints) == 1
                assert healthy_endpoints[0].base_url == test_urls[0]  # Local endpoint