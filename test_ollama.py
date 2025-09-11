#!/usr/bin/env python3
"""Test Ollama integration with listen mode."""

import asyncio
import os
import sys
from pathlib import Path
import aiohttp

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from voice_mode.listen_mode import SimpleCommandRouter


async def check_ollama_server():
    """Check if Ollama server is running."""
    ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ollama_url}/api/tags", timeout=2) as response:
                if response.status == 200:
                    data = await response.json()
                    models = data.get("models", [])
                    return True, models
    except:
        return False, []
    
    return False, []


async def test_ollama():
    """Test Ollama integration."""
    
    print("Ollama Integration Test")
    print("=" * 50)
    
    # Check if Ollama is running
    is_running, models = await check_ollama_server()
    
    if not is_running:
        print("❌ Ollama server not running")
        print("\nTo start Ollama:")
        print("1. Install Ollama from https://ollama.ai")
        print("2. Run: ollama run gemma3:4b")
        print("3. The server will start automatically")
        return
    
    print("✅ Ollama server is running")
    
    if models:
        print("\nAvailable models:")
        for model in models:
            name = model.get("name", "unknown")
            size = model.get("size", 0) / (1024**3)  # Convert to GB
            print(f"  - {name} ({size:.1f} GB)")
    
    # Check model configuration
    ollama_model = os.getenv("OLLAMA_MODEL", "gemma3:4b")
    print(f"\n✅ Using model: {ollama_model}")
    print("   (Set OLLAMA_MODEL env var to change)")
    
    # Test with the router
    router = SimpleCommandRouter()
    router.tts_enabled = False  # Disable TTS for testing
    
    # Test some complex queries that should go to Ollama
    test_queries = [
        "explain quantum computing in simple terms",
        "what is the meaning of life",
        "how does photosynthesis work"
    ]
    
    print("\n" + "=" * 50)
    print("Testing complex query routing to Ollama...")
    
    for query in test_queries:
        print(f"\nQuery: '{query}'")
        
        # Check if it's detected as complex
        is_complex = router._is_complex_query(query.lower())
        print(f"Complex query: {'Yes' if is_complex else 'No'}")
        
        if is_complex:
            # Try to get Ollama response
            print("Sending to Ollama...")
            response = await router._try_ollama(query)
            
            if response:
                print(f"Response: {response[:200]}...")  # Show first 200 chars
            else:
                print("No response from Ollama")
        
        print("-" * 30)
    
    # Test the full command flow
    print("\n" + "=" * 50)
    print("Testing full voice command simulation...")
    print("\nSimulating: 'hey voicemode, explain how batteries work'")
    await router.route("hey voicemode", "explain how batteries work")


if __name__ == "__main__":
    asyncio.run(test_ollama())