#!/usr/bin/env python3
"""Test script for the listen mode implementation."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from voice_mode.whisper_stream import extract_command_after_wake
from voice_mode.listen_mode import SimpleCommandRouter
from voice_mode.tools.listen import test_wake_word_detection


async def test_wake_word_extraction():
    """Test wake word extraction logic."""
    print("Testing wake word extraction...")
    
    test_cases = [
        ("hey voicemode what time is it", "hey voicemode", "what time is it"),
        ("hey claude explain quantum physics", "hey claude", "explain quantum physics"),
        ("computer open safari", "computer", "open safari"),
        ("hello there", None, None),  # No wake word
    ]
    
    for text, expected_wake, expected_cmd in test_cases:
        result = await test_wake_word_detection(text)
        
        if expected_wake:
            assert result["detected"], f"Failed to detect wake word in: {text}"
            assert result["wake_word"] == expected_wake.lower(), f"Wrong wake word detected: {result['wake_word']}"
            if expected_cmd:
                assert result["command"] == expected_cmd, f"Wrong command extracted: {result['command']}"
            print(f"✓ '{text}' -> wake:'{result['wake_word']}', cmd:'{result['command']}'")
        else:
            assert not result["detected"], f"False positive wake word in: {text}"
            print(f"✓ '{text}' -> no wake word detected")
    
    print("Wake word extraction tests passed!\n")


async def test_command_router():
    """Test the command router."""
    print("Testing command router...")
    
    router = SimpleCommandRouter()
    router.tts_enabled = False  # Disable TTS for testing
    
    # Test time command
    print("Testing time command...")
    await router.route("hey voicemode", "what time is it")
    
    # Test date command
    print("Testing date command...")
    await router.route("hey voicemode", "what's the date")
    
    # Test battery command
    print("Testing battery command...")
    await router.route("hey voicemode", "battery status")
    
    # Test complex query detection
    print("Testing complex query detection...")
    assert router._is_complex_query("explain quantum physics")
    assert router._is_complex_query("how does photosynthesis work")
    assert not router._is_complex_query("what time is it")
    assert not router._is_complex_query("open safari")
    
    print("Command router tests passed!\n")


async def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")
    
    try:
        from voice_mode.whisper_stream import (
            continuous_listen_with_whisper_stream,
            check_whisper_stream_available
        )
        print("✓ whisper_stream imports successful")
    except ImportError as e:
        print(f"✗ Failed to import whisper_stream: {e}")
        return False
    
    try:
        from voice_mode.listen_mode import (
            SimpleCommandRouter,
            ListenerConfig,
            run_listener
        )
        print("✓ listen_mode imports successful")
    except ImportError as e:
        print(f"✗ Failed to import listen_mode: {e}")
        return False
    
    try:
        from voice_mode.tools.listen import (
            start_listener,
            stop_listener,
            listener_status,
            test_wake_word_detection
        )
        print("✓ MCP tools imports successful")
    except ImportError as e:
        print(f"✗ Failed to import MCP tools: {e}")
        return False
    
    print("All imports successful!\n")
    return True


async def main():
    """Run all tests."""
    print("=" * 50)
    print("VoiceMode Listen Mode Test Suite")
    print("=" * 50 + "\n")
    
    # Test imports
    if not await test_imports():
        print("Import tests failed, skipping other tests")
        return
    
    # Test wake word extraction
    await test_wake_word_extraction()
    
    # Test command router
    await test_command_router()
    
    # Check whisper-stream availability
    from voice_mode.whisper_stream import check_whisper_stream_available
    if check_whisper_stream_available():
        print("✓ whisper-stream is available")
    else:
        print("⚠ whisper-stream not found - install it to use listen mode")
    
    print("\n" + "=" * 50)
    print("All tests completed!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())