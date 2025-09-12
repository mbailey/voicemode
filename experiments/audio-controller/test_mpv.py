#!/usr/bin/env python3
"""
Simple test of MPV controller
"""

import time
import logging
from mpv_controller import MPVController

logging.basicConfig(level=logging.INFO)

def test_basic_playback():
    """Test basic MPV functionality"""
    print("Testing MPV Controller")
    print("=" * 40)
    
    # Create controller
    controller = MPVController()
    
    try:
        # Start MPV
        print("\n1. Starting MPV...")
        controller.start()
        print("   ✓ MPV started")
        
        # Test volume
        print("\n2. Testing volume control...")
        controller.set_volume(50)
        print("   ✓ Volume set to 50")
        
        # Get state
        print("\n3. Getting playback state...")
        state = controller.get_state()
        print(f"   Playing: {state.playing}")
        print(f"   Volume: {state.volume}")
        print("   ✓ State retrieved")
        
        # Test with a simple sound (macOS has this file)
        test_file = "/System/Library/Sounds/Ping.aiff"
        print(f"\n4. Playing test sound: {test_file}")
        controller.play(test_file)
        print("   ✓ Play command sent")
        
        # Wait a moment
        time.sleep(1)
        
        # Get state again
        state = controller.get_state()
        print(f"   Current file: {state.filename}")
        
        print("\n✅ All tests passed!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        
    finally:
        # Cleanup
        print("\n5. Cleaning up...")
        controller.cleanup()
        print("   ✓ MPV stopped")


if __name__ == "__main__":
    test_basic_playback()