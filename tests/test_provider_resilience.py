"""Tests for provider resilience and health checking."""

import pytest
import asyncio
from unittest.mock import patch

from voice_mode import config
from voice_mode import provider_discovery
from voice_mode.provider_discovery import ProviderRegistry, is_local_provider, detect_provider_type


# Documented defaults — tests assert against these literal URLs / providers, so
# pin them here regardless of what the developer has in ~/.voicemode/voicemode.env.
# See VM-1138.
DEFAULT_TTS_BASE_URLS = [
    "http://127.0.0.1:8880/v1",      # Kokoro (local TTS)
    "https://api.openai.com/v1",     # OpenAI (remote)
]
DEFAULT_STT_BASE_URLS = [
    "http://127.0.0.1:2022/v1",      # Whisper (local STT)
    "https://api.openai.com/v1",     # OpenAI (remote)
]


@pytest.fixture(autouse=True)
def pin_provider_urls(monkeypatch):
    """Pin TTS/STT base URLs to documented defaults so tests are isolated from
    the user's ~/.voicemode/voicemode.env. Without this, tests asserting on
    'http://127.0.0.1:8880/v1' or provider 'whisper' fail when the user has
    overridden the URL list (e.g. mlx-audio at 8890 first).

    Both `config` and `provider_discovery` carry their own bound names because
    `provider_discovery` does `from .config import TTS_BASE_URLS, STT_BASE_URLS`
    at module load — patch both.
    """
    monkeypatch.setattr(config, "TTS_BASE_URLS", list(DEFAULT_TTS_BASE_URLS))
    monkeypatch.setattr(config, "STT_BASE_URLS", list(DEFAULT_STT_BASE_URLS))
    monkeypatch.setattr(provider_discovery, "TTS_BASE_URLS", list(DEFAULT_TTS_BASE_URLS))
    monkeypatch.setattr(provider_discovery, "STT_BASE_URLS", list(DEFAULT_STT_BASE_URLS))


class TestProviderResilience:
    """Test provider resilience features."""

    def test_is_local_provider(self):
        """Test detection of local vs remote providers."""
        # Local providers
        assert is_local_provider("http://127.0.0.1:8880/v1") is True
        assert is_local_provider("http://localhost:8880/v1") is True
        assert is_local_provider("http://127.0.0.1:2022/v1") is True

        # Remote providers
        assert is_local_provider("https://api.openai.com/v1") is False
        assert is_local_provider("https://api.anthropic.com/v1") is False

    def test_detect_provider_type(self):
        """Test provider type detection."""
        assert detect_provider_type("https://api.openai.com/v1") == "openai"
        assert detect_provider_type("http://127.0.0.1:8880/v1") == "kokoro"
        assert detect_provider_type("http://127.0.0.1:2022/v1") == "whisper"
        assert detect_provider_type("http://localhost:8880/v1") == "kokoro"
        assert detect_provider_type("http://127.0.0.1:9999/v1") == "local"
        assert detect_provider_type("https://api.example.com/v1") == "unknown"

    @pytest.mark.asyncio
    async def test_mark_failed_records_error(self):
        """Test that mark_failed records error information without preventing retry."""
        registry = ProviderRegistry()
        await registry.initialize()

        # Get initial state of local TTS endpoint
        local_url = "http://127.0.0.1:8880/v1"
        assert local_url in registry.registry["tts"]
        initial_info = registry.registry["tts"][local_url]
        assert initial_info.last_error is None

        # Add small delay to ensure timestamp changes
        await asyncio.sleep(0.01)

        # Mark it as failed
        await registry.mark_failed("tts", local_url, "Connection refused")

        # Check that error is recorded but endpoint is still available
        updated_info = registry.registry["tts"][local_url]
        assert updated_info.last_error == "Connection refused"
        assert updated_info.last_check is not None
        # Endpoint should still be returned by get_endpoints
        endpoints = registry.get_endpoints("tts")
        assert any(e.base_url == local_url for e in endpoints)

    @pytest.mark.asyncio
    async def test_endpoints_always_retried(self):
        """Test that endpoints are always available for retry regardless of errors."""
        registry = ProviderRegistry()
        await registry.initialize()

        # Get initial list of endpoints
        initial_endpoints = registry.get_endpoints("tts")
        initial_count = len(initial_endpoints)

        # Mark multiple endpoints as failed
        for endpoint in initial_endpoints[:2]:  # Mark first two as failed
            await registry.mark_failed("tts", endpoint.base_url, "Test error")

        # Check that all endpoints are still available
        updated_endpoints = registry.get_endpoints("tts")
        assert len(updated_endpoints) == initial_count

        # Check that errors were recorded
        for endpoint in updated_endpoints[:2]:
            assert endpoint.last_error == "Test error"

    @pytest.mark.asyncio
    async def test_error_tracking_for_all_providers(self):
        """Test that errors are tracked for both local and remote providers."""
        registry = ProviderRegistry()
        await registry.initialize()

        # Test with both local and remote URLs
        test_urls = [
            ("http://127.0.0.1:8880/v1", "Local service error"),
            ("https://api.openai.com/v1", "API key invalid")
        ]

        for url, error in test_urls:
            # Mark as failed
            await registry.mark_failed("tts", url, error)

            # Check that error is recorded
            endpoint_info = registry.registry["tts"][url]
            assert endpoint_info.last_error == error
            assert endpoint_info.last_check is not None

    @pytest.mark.asyncio
    async def test_get_endpoints_returns_all(self):
        """Test that get_endpoints returns all endpoints regardless of errors."""
        registry = ProviderRegistry()
        await registry.initialize()

        local_url = "http://127.0.0.1:8880/v1"

        # Mark local endpoint as failed
        await registry.mark_failed("tts", local_url, "Service unavailable")

        # Get all endpoints
        all_endpoints = registry.get_endpoints("tts")

        # Local endpoint should still be included
        assert any(endpoint.base_url == local_url for endpoint in all_endpoints)
        # And it should have the error recorded
        local_endpoint = next(e for e in all_endpoints if e.base_url == local_url)
        assert local_endpoint.last_error == "Service unavailable"

    @pytest.mark.asyncio
    async def test_endpoint_order_maintained(self):
        """Test that endpoint order is maintained regardless of failures."""
        with patch.object(config, 'TTS_BASE_URLS', [
            "http://127.0.0.1:8880/v1",  # Kokoro (local)
            "https://api.openai.com/v1",  # OpenAI (remote)
            "http://127.0.0.1:2022/v1"    # Whisper (local)
        ]):
            registry = ProviderRegistry()
            await registry.initialize()

            test_urls = config.TTS_BASE_URLS

            # Mark first two as failed
            await registry.mark_failed("tts", test_urls[0], "Local service down")
            await registry.mark_failed("tts", test_urls[1], "API limit reached")

            # Get all endpoints
            endpoints = registry.get_endpoints("tts")

            # Check we have at least 2 endpoints (some might not be initialized)
            assert len(endpoints) >= 2

            # Check that marked endpoints have their errors recorded
            for endpoint in endpoints:
                if endpoint.base_url == test_urls[0]:
                    assert endpoint.last_error == "Local service down"
                elif endpoint.base_url == test_urls[1]:
                    assert endpoint.last_error == "API limit reached"