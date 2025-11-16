#!/usr/bin/env python3
"""Test script for conversation mode functionality."""

import asyncio
import logging
from voice_mode.listen_mode import SimpleCommandRouter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test-conversation")


async def test_conversation_mode():
    """Test conversation mode transitions and functionality."""
    router = SimpleCommandRouter()
    
    print("\n=== Testing Conversation Mode ===\n")
    
    # Test 1: Normal mode initially
    assert not router.conversation_mode, "Should start in normal mode"
    print("✅ Test 1: Starts in normal mode")
    
    # Test 2: Enter conversation mode
    print("\n🎤 Simulating: 'hey robot, let's chat'")
    await router.route("hey robot", "let's chat")
    assert router.conversation_mode, "Should enter conversation mode"
    assert len(router.conversation_history) == 0, "History should be empty initially"
    print("✅ Test 2: Entered conversation mode")
    
    # Test 3: Process conversation without wake word
    print("\n🎤 Simulating conversation: 'What is the weather like?'")
    await router.route("", "What is the weather like?")
    assert router.conversation_mode, "Should still be in conversation mode"
    assert len(router.conversation_history) > 0, "History should have messages"
    print(f"✅ Test 3: Processed conversation (history: {len(router.conversation_history)} messages)")
    
    # Test 4: Continue conversation
    print("\n🎤 Simulating: 'Tell me more'")
    await router.route("", "Tell me more")
    assert router.conversation_mode, "Should still be in conversation mode"
    print(f"✅ Test 4: Continued conversation (history: {len(router.conversation_history)} messages)")
    
    # Test 5: Exit conversation mode
    print("\n🎤 Simulating: 'stop conversation'")
    await router.route("", "stop conversation")
    assert not router.conversation_mode, "Should exit conversation mode"
    assert len(router.conversation_history) == 0, "History should be cleared"
    print("✅ Test 5: Exited conversation mode")
    
    # Test 6: Back to normal mode with wake word
    print("\n🎤 Simulating: 'hey robot, what time is it?'")
    await router.route("hey robot", "what time is it?")
    assert not router.conversation_mode, "Should remain in normal mode"
    print("✅ Test 6: Normal mode command processed")
    
    print("\n✨ All tests passed!")


if __name__ == "__main__":
    asyncio.run(test_conversation_mode())