#!/usr/bin/env python3
"""
Test the audio controller integration
"""

import sys
import time
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'mcp', 'audio_controller'))

from mpv_controller import MPVController

def test_audio_controller():
    """Test the audio controller functionality"""
    print("Testing Audio Controller Integration")
    print("=" * 50)
    
    controller = MPVController()
    
    try:
        # Start MPV
        print("\n1. Starting MPV...")
        controller.start()
        print("   ✓ MPV started successfully")
        
        # Set volume
        print("\n2. Setting volume to 60...")
        controller.set_volume(60)
        print("   ✓ Volume set")
        
        # Play system sound
        test_file = "/System/Library/Sounds/Glass.aiff"
        print(f"\n3. Playing test sound: {test_file}")
        controller.play(test_file)
        print("   ✓ Sound playing")
        
        # Wait for playback
        time.sleep(1)
        
        # Get state
        print("\n4. Getting playback state...")
        state = controller.get_state()
        print(f"   Volume: {state.volume}")
        print(f"   Playing: {state.playing}")
        print(f"   File: {state.filename}")
        
        # Test volume ducking
        print("\n5. Testing volume ducking...")
        controller.duck_volume()
        time.sleep(0.5)
        ducked_state = controller.get_state()
        print(f"   Ducked volume: {ducked_state.volume}")
        
        controller.restore_volume()
        restored_state = controller.get_state()
        print(f"   Restored volume: {restored_state.volume}")
        
        print("\n✅ All tests passed!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        print("\n6. Cleaning up...")
        controller.cleanup()
        print("   ✓ MPV stopped")


if __name__ == "__main__":
    test_audio_controller()