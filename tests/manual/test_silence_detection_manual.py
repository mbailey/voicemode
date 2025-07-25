#!/usr/bin/env python3
"""Manual test for silence detection feature.

This script allows testing the silence detection feature with real microphone input.

Usage:
    # Test with silence detection enabled (default)
    python test_silence_detection_manual.py
    
    # Test with silence detection disabled for comparison
    VOICEMODE_ENABLE_SILENCE_DETECTION=false python test_silence_detection_manual.py
    
    # Test with different VAD aggressiveness (0-3)
    VOICEMODE_VAD_AGGRESSIVENESS=3 python test_silence_detection_manual.py
    
    # Test with different silence threshold (ms)
    VOICEMODE_SILENCE_THRESHOLD_MS=500 python test_silence_detection_manual.py
"""

import os
import sys
import time
import asyncio
import numpy as np
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Set up test environment
os.environ.setdefault("VOICEMODE_DEBUG", "true")
os.environ.setdefault("VOICEMODE_ENABLE_SILENCE_DETECTION", "true")

from voice_mode.tools.converse import (
    record_audio_with_silence_detection,
    record_audio,
    VAD_AVAILABLE
)
from voice_mode.config import (
    ENABLE_SILENCE_DETECTION,
    VAD_AGGRESSIVENESS,
    SILENCE_THRESHOLD_MS,
    MIN_RECORDING_DURATION,
    logger
)


def print_config():
    """Print current configuration."""
    print("\n=== Silence Detection Configuration ===")
    print(f"Enabled: {ENABLE_SILENCE_DETECTION}")
    print(f"VAD Available: {VAD_AVAILABLE}")
    print(f"VAD Aggressiveness: {VAD_AGGRESSIVENESS} (0-3)")
    print(f"Silence Threshold: {SILENCE_THRESHOLD_MS}ms")
    print(f"Min Recording Duration: {MIN_RECORDING_DURATION}s")
    print("=====================================\n")


def test_scenarios():
    """Run different test scenarios."""
    scenarios = [
        {
            "name": "Short Answer Test",
            "instruction": "Say 'yes' or 'no' when prompted",
            "duration": 10.0,
            "expected": "Should stop recording shortly after you stop speaking"
        },
        {
            "name": "Sentence Test",
            "instruction": "Say a complete sentence when prompted",
            "duration": 15.0,
            "expected": "Should stop recording after you finish the sentence"
        },
        {
            "name": "Pause Test",
            "instruction": "Say something, pause for 1-2 seconds, then continue",
            "duration": 20.0,
            "expected": "Should handle natural pauses without cutting off"
        },
        {
            "name": "Silence Test",
            "instruction": "Don't say anything - just stay quiet",
            "duration": 10.0,
            "expected": "Should stop after detecting no speech"
        },
        {
            "name": "Continuous Speech Test",
            "instruction": "Keep talking continuously without long pauses",
            "duration": 10.0,
            "expected": "Should record until max duration is reached"
        }
    ]
    
    print_config()
    
    for i, scenario in enumerate(scenarios):
        print(f"\n[{i+1}/{len(scenarios)}] {scenario['name']}")
        print(f"Instructions: {scenario['instruction']}")
        print(f"Max duration: {scenario['duration']}s")
        print(f"Expected: {scenario['expected']}")
        
        input("\nPress Enter when ready to start recording...")
        
        print("\n🎤 Recording...")
        start_time = time.time()
        
        try:
            # Record audio
            audio_data = record_audio_with_silence_detection(scenario['duration'])
            
            elapsed = time.time() - start_time
            samples = len(audio_data)
            actual_duration = samples / 24000  # Sample rate
            
            print(f"\n✓ Recording complete!")
            print(f"Elapsed time: {elapsed:.1f}s")
            print(f"Audio duration: {actual_duration:.1f}s")
            print(f"Samples recorded: {samples}")
            
            # Calculate basic statistics
            if len(audio_data) > 0:
                rms = np.sqrt(np.mean(audio_data.astype(float) ** 2))
                print(f"RMS level: {rms:.2f}")
            
        except Exception as e:
            print(f"\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        
        if i < len(scenarios) - 1:
            input("\nPress Enter to continue to next test...")


def test_comparison():
    """Compare recording with and without silence detection."""
    print("\n=== Comparison Test ===")
    print("This test compares recording with and without silence detection.")
    
    test_duration = 10.0
    test_phrase = "Hello, this is a test"
    
    print(f"\nYou will be asked to say: '{test_phrase}'")
    print("The same recording will be done twice - with and without silence detection.\n")
    
    # Test with silence detection
    if ENABLE_SILENCE_DETECTION and VAD_AVAILABLE:
        input("Press Enter to record WITH silence detection...")
        print("\n🎤 Recording with silence detection...")
        start1 = time.time()
        audio1 = record_audio_with_silence_detection(test_duration)
        time1 = time.time() - start1
        duration1 = len(audio1) / 24000
        
        print(f"✓ With silence detection: {time1:.1f}s elapsed, {duration1:.1f}s audio")
    else:
        print("⚠️  Silence detection not available/enabled")
        audio1 = None
        time1 = 0
        duration1 = 0
    
    # Test without silence detection
    input("\nPress Enter to record WITHOUT silence detection (fixed duration)...")
    print("\n🎤 Recording without silence detection...")
    start2 = time.time()
    audio2 = record_audio(test_duration)
    time2 = time.time() - start2
    duration2 = len(audio2) / 24000
    
    print(f"✓ Without silence detection: {time2:.1f}s elapsed, {duration2:.1f}s audio")
    
    # Compare results
    print("\n=== Results ===")
    if audio1 is not None:
        time_saved = time2 - time1
        print(f"Time saved with silence detection: {time_saved:.1f}s ({time_saved/time2*100:.0f}%)")
        print(f"Audio length ratio: {duration1/duration2:.1%}")


def main():
    """Main test function."""
    print("Voice Mode - Silence Detection Manual Test")
    print("=========================================")
    
    if not VAD_AVAILABLE:
        print("\n⚠️  WARNING: webrtcvad is not installed!")
        print("Install it with: pip install webrtcvad")
        print("Continuing with fallback to fixed duration recording...\n")
    
    while True:
        print("\nSelect test type:")
        print("1. Run all test scenarios")
        print("2. Comparison test (with vs without)")
        print("3. Custom test (set your own duration)")
        print("4. Exit")
        
        choice = input("\nEnter choice (1-4): ").strip()
        
        if choice == "1":
            test_scenarios()
        elif choice == "2":
            test_comparison()
        elif choice == "3":
            duration = float(input("Enter max recording duration (seconds): "))
            print("\nRecording will stop early if silence is detected.")
            input("Press Enter to start recording...")
            
            print("\n🎤 Recording...")
            start = time.time()
            audio = record_audio_with_silence_detection(duration)
            elapsed = time.time() - start
            
            print(f"\n✓ Done! Recorded {len(audio)/24000:.1f}s of audio in {elapsed:.1f}s")
        elif choice == "4":
            break
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()