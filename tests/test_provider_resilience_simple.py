#!/usr/bin/env python3
"""Simple test script to verify provider resilience implementation."""

import asyncio
import sys
import os
import pytest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ensure ALWAYS_TRY_LOCAL is enabled for the test
os.environ['VOICEMODE_ALWAYS_TRY_LOCAL'] = 'true'

from voice_mode import config
from voice_mode import provider_discovery
from voice_mode.provider_discovery import ProviderRegistry, is_local_provider, detect_provider_type


# Documented defaults — pin so tests are isolated from user voicemode.env. See VM-1138.
DEFAULT_TTS_BASE_URLS = [
    "http://127.0.0.1:8880/v1",
    "https://api.openai.com/v1",
]
DEFAULT_STT_BASE_URLS = [
    "http://127.0.0.1:2022/v1",
    "https://api.openai.com/v1",
]


@pytest.fixture(autouse=True)
def pin_provider_urls(monkeypatch):
    """Isolate from user ~/.voicemode/voicemode.env. See VM-1138."""
    monkeypatch.setattr(config, "TTS_BASE_URLS", list(DEFAULT_TTS_BASE_URLS))
    monkeypatch.setattr(config, "STT_BASE_URLS", list(DEFAULT_STT_BASE_URLS))
    monkeypatch.setattr(provider_discovery, "TTS_BASE_URLS", list(DEFAULT_TTS_BASE_URLS))
    monkeypatch.setattr(provider_discovery, "STT_BASE_URLS", list(DEFAULT_STT_BASE_URLS))


@pytest.mark.asyncio
async def test_provider_resilience():
    """Test the provider resilience implementation."""
    print("Testing Provider Resilience Implementation")
    print("=" * 50)
    
    # Test 1: Local provider detection
    print("\n1. Testing local provider detection:")
    test_urls = [
        ("http://127.0.0.1:8880/v1", True),
        ("http://localhost:8880/v1", True),
        ("http://127.0.0.1:2022/v1", True),
        ("https://api.openai.com/v1", False),
    ]
    
    for url, expected in test_urls:
        result = is_local_provider(url)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {url}: {result} (expected: {expected})")
    
    # Test 2: Provider type detection
    print("\n2. Testing provider type detection:")
    type_tests = [
        ("http://127.0.0.1:8880/v1", "kokoro"),
        ("http://localhost:2022/v1", "whisper"),
        ("https://api.openai.com/v1", "openai"),
    ]
    
    for url, expected in type_tests:
        result = detect_provider_type(url)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {url}: {result} (expected: {expected})")
    
    # Test 3: Provider resilience with ALWAYS_TRY_LOCAL
    print("\n3. Testing provider resilience (ALWAYS_TRY_LOCAL=true):")
    registry = ProviderRegistry()
    await registry.initialize()
    
    # Try to mark local provider as unhealthy
    local_url = "http://127.0.0.1:8880/v1"
    print(f"  Initial state of {local_url}:")
    initial_info = registry.registry["tts"][local_url]
    print(f"    Last Error: {initial_info.last_error}")
    print(f"    Last Check: {initial_info.last_check}")
    
    # Mark as failed
    await registry.mark_failed("tts", local_url, "Connection refused")
    
    print(f"  After marking failed:")
    updated_info = registry.registry["tts"][local_url]
    print(f"    Last Error: {updated_info.last_error}")
    print(f"    Last Check: {updated_info.last_check}")
    
    # Test that it's still in available endpoints
    all_endpoints = registry.get_endpoints("tts")
    local_in_endpoints = any(ep.base_url == local_url for ep in all_endpoints)
    print(f"  Local provider still in available endpoints: {local_in_endpoints}")
    
    # Test 4: Remote provider behavior
    print("\n4. Testing remote provider behavior:")
    remote_url = "https://api.openai.com/v1"
    print(f"  Initial state of {remote_url}:")
    initial_remote = registry.registry["tts"][remote_url]
    print(f"    Last Error: {initial_remote.last_error}")
    
    # Mark as failed
    await registry.mark_failed("tts", remote_url, "API key invalid")
    
    print(f"  After marking failed:")
    updated_remote = registry.registry["tts"][remote_url]
    print(f"    Last Error: {updated_remote.last_error}")
    print(f"    Last Check: {updated_remote.last_check}")
    
    print("\n" + "=" * 50)
    print("Test completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_provider_resilience())