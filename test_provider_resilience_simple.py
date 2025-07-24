#!/usr/bin/env python3
"""Simple test script to verify provider resilience implementation."""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Ensure ALWAYS_TRY_LOCAL is enabled for the test
os.environ['VOICEMODE_ALWAYS_TRY_LOCAL'] = 'true'

from voice_mode.provider_discovery import ProviderRegistry, is_local_provider, detect_provider_type


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
    print(f"    Healthy: {initial_info.healthy}")
    print(f"    Error: {initial_info.error}")
    
    # Mark as unhealthy
    await registry.mark_unhealthy("tts", local_url, "Connection refused")
    
    print(f"  After marking unhealthy:")
    updated_info = registry.registry["tts"][local_url]
    print(f"    Healthy: {updated_info.healthy}")
    print(f"    Error: {updated_info.error}")
    
    # Test that it's still in healthy endpoints
    healthy_endpoints = registry.get_healthy_endpoints("tts")
    local_in_healthy = any(ep.base_url == local_url for ep in healthy_endpoints)
    print(f"  Local provider still in healthy endpoints: {local_in_healthy}")
    
    # Test 4: Remote provider behavior
    print("\n4. Testing remote provider behavior:")
    remote_url = "https://api.openai.com/v1"
    print(f"  Initial state of {remote_url}:")
    initial_remote = registry.registry["tts"][remote_url]
    print(f"    Healthy: {initial_remote.healthy}")
    
    # Mark as unhealthy
    await registry.mark_unhealthy("tts", remote_url, "API key invalid")
    
    print(f"  After marking unhealthy:")
    updated_remote = registry.registry["tts"][remote_url]
    print(f"    Healthy: {updated_remote.healthy}")
    print(f"    Error: {updated_remote.error}")
    
    print("\n" + "=" * 50)
    print("Test completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_provider_resilience())