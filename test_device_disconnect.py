#!/usr/bin/env python3
"""Test what happens when audio device disconnects during stream."""

import sounddevice as sd
import numpy as np
import time
import threading

def monitor_devices():
    """Monitor device changes in background."""
    last_devices = sd.query_devices()
    print(f"Initial devices: {len(last_devices)} devices")
    
    while monitoring:
        time.sleep(1)
        try:
            current_devices = sd.query_devices()
            if len(current_devices) != len(last_devices):
                print(f"\n🔄 DEVICE CHANGE DETECTED!")
                print(f"   Before: {len(last_devices)} devices")
                print(f"   After: {len(current_devices)} devices")
                
                # Find what changed
                last_names = {d['name'] for d in last_devices}
                current_names = {d['name'] for d in current_devices}
                
                added = current_names - last_names
                removed = last_names - current_names
                
                if added:
                    print(f"   ➕ Added: {added}")
                if removed:
                    print(f"   ➖ Removed: {removed}")
                    
                last_devices = current_devices
        except Exception as e:
            print(f"Monitor error: {e}")

def test_stream_with_device():
    """Test what happens to an active stream when device disconnects."""
    print("\n=== Testing Stream Behavior on Device Disconnect ===\n")
    
    # Show current devices
    devices = sd.query_devices()
    print("Current audio devices:")
    for i, d in enumerate(devices):
        marker = ""
        if i == sd.default.device[0]:
            marker = " [DEFAULT INPUT]"
        if i == sd.default.device[1]:
            marker = " [DEFAULT OUTPUT]"
        print(f"  {i}: {d['name']}{marker}")
    
    print(f"\nUsing default input device: {sd.query_devices(kind='input')['name']}")
    print("\n📱 Please connect/disconnect your AirPods during the test...")
    print("Stream will run for 30 seconds or until interrupted.\n")
    
    # Start device monitor
    global monitoring
    monitoring = True
    monitor_thread = threading.Thread(target=monitor_devices)
    monitor_thread.start()
    
    # Create a simple recording stream
    stream = None
    try:
        def audio_callback(indata, frames, time_info, status):
            """Callback to detect stream status."""
            if status:
                print(f"⚠️  Stream status: {status}")
        
        stream = sd.InputStream(
            callback=audio_callback,
            channels=1,
            samplerate=16000,
            blocksize=1024
        )
        
        print("✅ Stream created successfully")
        stream.start()
        print("🎤 Stream started - monitoring for 30 seconds...")
        
        # Monitor for 30 seconds
        for i in range(30):
            time.sleep(1)
            if stream.active:
                print(f"   {i+1}s - Stream active: ✓", end="\r")
            else:
                print(f"\n❌ Stream became inactive at {i+1} seconds!")
                break
                
    except sd.PortAudioError as e:
        print(f"\n❌ PortAudioError: {e}")
        print(f"   Error code: {e.args}")
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        
    finally:
        monitoring = False
        monitor_thread.join()
        
        if stream:
            try:
                stream.stop()
                stream.close()
                print("\n✅ Stream closed successfully")
            except Exception as e:
                print(f"\n⚠️  Error closing stream: {e}")

if __name__ == "__main__":
    test_stream_with_device()
    print("\n=== Test Complete ===")