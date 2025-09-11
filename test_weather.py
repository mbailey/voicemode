#!/usr/bin/env python3
"""Test weather API integration."""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from voice_mode.listen_mode import SimpleCommandRouter


async def test_weather():
    """Test the weather functionality."""
    
    print("Weather API Test")
    print("=" * 50)
    
    # Check if API key is set
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if api_key:
        print(f"✓ API key found (starts with: {api_key[:8]}...)")
    else:
        print("✗ No API key found")
        print("\nTo use weather features:")
        print("1. Sign up at https://openweathermap.org/api")
        print("2. Get your free API key")
        print("3. Set environment variable:")
        print("   export OPENWEATHER_API_KEY='your-key-here'")
        print("4. Optionally set location:")
        print("   export WEATHER_LOCATION='Melbourne,AU'")
        return
    
    # Check location setting
    location = os.getenv("WEATHER_LOCATION", "Melbourne,AU")
    print(f"✓ Location: {location}")
    
    # Test the weather command
    router = SimpleCommandRouter()
    router.tts_enabled = False  # Disable TTS for testing
    
    print("\nFetching weather...")
    response = await router._get_weather()
    print(f"\nResponse: {response}")
    
    # Simulate the full command flow
    print("\n" + "=" * 50)
    print("Simulating voice command: 'hey voicemode, what's the weather'")
    await router.route("hey voicemode", "what's the weather")


if __name__ == "__main__":
    asyncio.run(test_weather())