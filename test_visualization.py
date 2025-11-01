#!/usr/bin/env python3
"""
Simple test script for recording visualization.

This simulates a recording session with speech detection and silence.
"""

import time
import numpy as np
from voice_mode.recording_visualization import create_visualizer


def simulate_recording():
    """Simulate a recording session with various states."""

    # Configuration
    max_duration = 10.0
    silence_threshold_ms = 1000.0
    min_duration = 2.0

    # Create visualizer
    visualizer = create_visualizer(
        max_duration=max_duration,
        silence_threshold_ms=silence_threshold_ms,
        min_duration=min_duration,
        enabled=True
    )

    print("Starting recording visualization test...")
    print("This will simulate:")
    print("1. Waiting for speech (low audio levels)")
    print("2. Speech detected (high audio levels)")
    print("3. Silence after speech (accumulating silence)")
    print()

    visualizer.start()

    try:
        duration = 0.0
        dt = 0.1  # Update every 100ms
        speech_detected = False
        silence_ms = 0.0

        # Phase 1: Waiting for speech (2 seconds)
        print("Phase 1: Waiting for speech...")
        while duration < 2.0:
            # Low audio level (background noise)
            audio_level = np.random.uniform(50, 150)

            visualizer.update(
                duration=duration,
                audio_level=audio_level,
                speech_detected=False,
                silence_ms=0.0,
                state="WAITING"
            )

            time.sleep(dt)
            duration += dt

        # Phase 2: Speech active (3 seconds)
        print("Phase 2: Speech detected - active recording...")
        speech_detected = True
        speech_duration = 0.0
        while speech_duration < 3.0:
            # High audio level (speech)
            audio_level = np.random.uniform(500, 2000)

            visualizer.update(
                duration=duration,
                audio_level=audio_level,
                speech_detected=True,
                silence_ms=0.0,
                state="ACTIVE"
            )

            time.sleep(dt)
            duration += dt
            speech_duration += dt

        # Phase 3: Silence after speech (until threshold)
        print("Phase 3: Silence after speech - accumulating...")
        while silence_ms < silence_threshold_ms and duration < max_duration:
            # Low audio level (silence)
            audio_level = np.random.uniform(20, 80)
            silence_ms += (dt * 1000)  # Convert to ms

            visualizer.update(
                duration=duration,
                audio_level=audio_level,
                speech_detected=True,
                silence_ms=silence_ms,
                state="SILENCE"
            )

            time.sleep(dt)
            duration += dt

        print(f"\nRecording complete! Duration: {duration:.1f}s")

    finally:
        visualizer.stop()
        print("\nVisualization test complete!")


if __name__ == "__main__":
    try:
        simulate_recording()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
    except Exception as e:
        print(f"\n\nError during test: {e}")
        import traceback
        traceback.print_exc()
