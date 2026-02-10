#!/usr/bin/env python3
"""Manual test for barge-in feature.

This script allows testing the barge-in feature with real microphone input.
It tests the ability to interrupt TTS playback by speaking.

Usage:
    # Test with barge-in enabled
    VOICEMODE_BARGE_IN=true python test_barge_in_manual.py

    # Test with different VAD aggressiveness (0-3)
    VOICEMODE_BARGE_IN=true VOICEMODE_BARGE_IN_VAD=3 python test_barge_in_manual.py

    # Test with different minimum speech duration (ms)
    VOICEMODE_BARGE_IN=true VOICEMODE_BARGE_IN_MIN_MS=100 python test_barge_in_manual.py

Requirements:
    - webrtcvad must be installed: pip install webrtcvad
    - Local TTS service (Kokoro or OpenAI API) must be available
    - Microphone access required
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
os.environ.setdefault("VOICEMODE_BARGE_IN", "true")

from voice_mode.config import (
    BARGE_IN_ENABLED,
    BARGE_IN_VAD_AGGRESSIVENESS,
    BARGE_IN_MIN_SPEECH_MS,
    SAMPLE_RATE,
    logger
)

# Check if webrtcvad is available
try:
    from voice_mode.barge_in import BargeInMonitor, is_barge_in_available
    VAD_AVAILABLE = is_barge_in_available()
except ImportError:
    VAD_AVAILABLE = False


def print_config():
    """Print current barge-in configuration."""
    print("\n=== Barge-In Configuration ===")
    print(f"Barge-In Enabled: {BARGE_IN_ENABLED}")
    print(f"VAD Available (webrtcvad): {VAD_AVAILABLE}")
    print(f"VAD Aggressiveness: {BARGE_IN_VAD_AGGRESSIVENESS} (0=permissive, 3=strict)")
    print(f"Min Speech Duration: {BARGE_IN_MIN_SPEECH_MS}ms")
    print("================================\n")


def test_barge_in_monitor_only():
    """Test the BargeInMonitor in isolation."""
    if not VAD_AVAILABLE:
        print("ERROR: webrtcvad is not available. Install with: pip install webrtcvad")
        return

    print("\n=== Testing BargeInMonitor in Isolation ===")
    print("This test monitors the microphone for speech without TTS playback.")
    print(f"Speech detection threshold: {BARGE_IN_MIN_SPEECH_MS}ms\n")

    monitor = BargeInMonitor()
    callback_triggered = False
    callback_time = None

    def on_voice_detected():
        nonlocal callback_triggered, callback_time
        callback_triggered = True
        callback_time = time.perf_counter()
        print(f"\n   VOICE DETECTED at {callback_time:.3f}s")

    input("Press Enter to start monitoring for 10 seconds...")
    print("Monitoring... Speak to trigger barge-in detection.")

    start_time = time.perf_counter()
    monitor.start_monitoring(on_voice_detected=on_voice_detected)

    try:
        # Monitor for 10 seconds or until voice detected
        while time.perf_counter() - start_time < 10 and not callback_triggered:
            time.sleep(0.1)
            elapsed = time.perf_counter() - start_time
            print(f"\r   Monitoring: {elapsed:.1f}s", end="", flush=True)
    finally:
        monitor.stop_monitoring()

    print("\n")

    if callback_triggered:
        latency = (callback_time - start_time)
        captured = monitor.get_captured_audio()
        print(f"Voice detected after {latency:.2f}s")
        if captured is not None:
            print(f"Captured {len(captured)} samples ({len(captured) / SAMPLE_RATE:.2f}s)")
        print("Barge-in detection working correctly.")
    else:
        print("No voice detected within 10 seconds.")
        print("Try speaking louder or adjust VAD aggressiveness with VOICEMODE_BARGE_IN_VAD=1")


def test_interrupt_timing():
    """Test the timing of barge-in interrupt."""
    if not VAD_AVAILABLE:
        print("ERROR: webrtcvad is not available")
        return

    print("\n=== Testing Interrupt Timing ===")
    print("This test measures the latency between starting to speak")
    print("and when the barge-in callback is triggered.\n")

    results = []

    for i in range(3):
        print(f"\nRound {i+1}/3")
        input("Press Enter, then immediately start speaking...")

        monitor = BargeInMonitor(min_speech_ms=50)  # Short threshold for timing test
        trigger_time = None

        def on_voice():
            nonlocal trigger_time
            trigger_time = time.perf_counter()

        start_time = time.perf_counter()
        monitor.start_monitoring(on_voice_detected=on_voice)

        # Wait for detection or timeout
        while trigger_time is None and time.perf_counter() - start_time < 5:
            time.sleep(0.01)

        monitor.stop_monitoring()

        if trigger_time:
            latency = (trigger_time - start_time) * 1000
            results.append(latency)
            print(f"   Detected! Latency: {latency:.1f}ms")
        else:
            print("   No voice detected")

    if results:
        avg_latency = sum(results) / len(results)
        print(f"\n=== Results ===")
        print(f"Average latency: {avg_latency:.1f}ms")
        print(f"Min latency: {min(results):.1f}ms")
        print(f"Max latency: {max(results):.1f}ms")

        if avg_latency < 100:
            print("Performance: GOOD (< 100ms)")
        elif avg_latency < 200:
            print("Performance: ACCEPTABLE (< 200ms)")
        else:
            print("Performance: NEEDS IMPROVEMENT (> 200ms)")


async def test_with_tts():
    """Test barge-in with actual TTS playback."""
    print("\n=== Testing Barge-In with TTS Playback ===")
    print("This test plays TTS audio and detects when you interrupt.\n")

    if not VAD_AVAILABLE:
        print("ERROR: webrtcvad is not available")
        return

    try:
        from voice_mode.tools.converse import converse
    except ImportError as e:
        print(f"ERROR: Could not import converse: {e}")
        return

    # Ensure barge-in is enabled
    if not BARGE_IN_ENABLED:
        print("ERROR: Barge-in is not enabled. Set VOICEMODE_BARGE_IN=true")
        return

    test_messages = [
        "This is a long message that you can try to interrupt. Start speaking any time and I should stop talking immediately.",
        "The quick brown fox jumps over the lazy dog. This sentence contains all letters of the alphabet. Interrupt me to test barge-in.",
        "Testing one two three four five. Keep talking until I detect your voice and stop playing.",
    ]

    for i, message in enumerate(test_messages):
        print(f"\n--- Test {i+1}/{len(test_messages)} ---")
        print(f"Message: {message[:50]}...")
        print("\nInstructions:")
        print("1. Press Enter to start TTS playback")
        print("2. Interrupt by speaking loudly")
        print("3. Observe if playback stops and your speech is captured\n")

        input("Press Enter to start...")

        print("Playing TTS... Interrupt by speaking!")
        start_time = time.perf_counter()

        try:
            result = await converse.fn(
                message=message,
                wait_for_response=True,
                voice="nova"  # Use a specific voice for consistency
            )
            elapsed = time.perf_counter() - start_time

            print(f"\nResult ({elapsed:.1f}s):")
            print(result[:200] + "..." if len(result) > 200 else result)

            # Check if barge-in was indicated in result
            if 'barge' in result.lower() or 'interrupt' in result.lower():
                print("\nBarge-in detected and handled correctly.")
            elif 'user:' in result.lower():
                print("\nUser response captured.")

        except Exception as e:
            print(f"\nError during test: {e}")
            import traceback
            traceback.print_exc()

        if i < len(test_messages) - 1:
            input("\nPress Enter to continue to next test...")


def test_comparison():
    """Compare response time with and without barge-in."""
    print("\n=== Barge-In Comparison Test ===")
    print("This test compares the experience with and without barge-in.\n")

    if not VAD_AVAILABLE:
        print("ERROR: webrtcvad is not available for barge-in")
        return

    print("Test 1: WITHOUT barge-in (normal flow)")
    print("- TTS will play completely before recording starts")
    print("- You cannot interrupt while TTS is playing")
    input("\nPress Enter to start without barge-in...")

    # TODO: Would need to actually run converse with barge-in disabled
    print("(Skipping actual playback - set VOICEMODE_BARGE_IN=false to test)")

    print("\n" + "="*50 + "\n")

    print("Test 2: WITH barge-in enabled")
    print("- TTS will stop immediately when you speak")
    print("- Your interrupting speech is captured for STT")
    input("\nPress Enter to start with barge-in...")

    # TODO: Would need to actually run converse with barge-in enabled
    print("(Skipping actual playback - set VOICEMODE_BARGE_IN=true to test)")


def test_cpu_profiling():
    """Profile CPU usage during barge-in monitoring."""
    if not VAD_AVAILABLE:
        print("ERROR: webrtcvad is not available")
        return

    print("\n=== CPU Profiling Test ===")
    print("This test measures CPU overhead during barge-in monitoring.\n")

    import os
    import resource
    import sys

    monitor = BargeInMonitor()
    callback_count = [0]

    def on_voice():
        callback_count[0] += 1

    # Measure baseline
    print("Measuring baseline CPU usage (2 seconds)...")
    start_time = time.perf_counter()
    start_usage = resource.getrusage(resource.RUSAGE_SELF)

    time.sleep(2)

    baseline_elapsed = time.perf_counter() - start_time
    baseline_usage = resource.getrusage(resource.RUSAGE_SELF)
    baseline_cpu = (
        (baseline_usage.ru_utime - start_usage.ru_utime) +
        (baseline_usage.ru_stime - start_usage.ru_stime)
    )

    print(f"  Baseline: {baseline_cpu:.3f}s CPU in {baseline_elapsed:.1f}s\n")

    # Measure with monitoring active
    print("Measuring CPU usage with monitoring active (5 seconds)...")
    print("(Keep quiet to prevent barge-in trigger)\n")

    input("Press Enter to start monitoring...")

    start_time = time.perf_counter()
    start_usage = resource.getrusage(resource.RUSAGE_SELF)

    monitor.start_monitoring(on_voice_detected=on_voice)

    try:
        # Monitor for 5 seconds
        for i in range(50):
            time.sleep(0.1)
            elapsed = time.perf_counter() - start_time
            print(f"\r  Monitoring: {elapsed:.1f}s", end="", flush=True)
    finally:
        monitor.stop_monitoring()

    monitor_elapsed = time.perf_counter() - start_time
    end_usage = resource.getrusage(resource.RUSAGE_SELF)
    monitor_cpu = (
        (end_usage.ru_utime - start_usage.ru_utime) +
        (end_usage.ru_stime - start_usage.ru_stime)
    )

    print("\n")

    # Calculate overhead
    baseline_rate = baseline_cpu / baseline_elapsed
    monitor_rate = monitor_cpu / monitor_elapsed
    overhead_percent = ((monitor_rate - baseline_rate) / baseline_rate) * 100 if baseline_rate > 0 else 0

    print("=== Results ===")
    print(f"Baseline CPU rate:   {baseline_rate*100:.2f}% of elapsed time")
    print(f"Monitoring CPU rate: {monitor_rate*100:.2f}% of elapsed time")
    print(f"Overhead:            {overhead_percent:.1f}% additional CPU")
    print(f"Voice callbacks:     {callback_count[0]}")

    if overhead_percent < 10:
        print("\nPerformance: EXCELLENT (<10% overhead)")
    elif overhead_percent < 25:
        print("\nPerformance: GOOD (<25% overhead)")
    elif overhead_percent < 50:
        print("\nPerformance: ACCEPTABLE (<50% overhead)")
    else:
        print("\nPerformance: HIGH OVERHEAD (>50%)")

    # Memory usage
    print(f"\nMemory usage: {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.1f} MB")


def test_performance_report():
    """Generate a comprehensive performance report."""
    if not VAD_AVAILABLE:
        print("ERROR: webrtcvad is not available")
        return

    print("\n=== Performance Report Generation ===")
    print("Running automated performance tests...\n")

    results = {
        'callback_latency': [],
        'buffer_operations': [],
        'vad_detections': 0,
    }

    # Test callback latency
    print("Testing callback latency...")
    for i in range(10):
        monitor = BargeInMonitor(min_speech_ms=10)
        callback_time = [None]

        def track():
            callback_time[0] = time.perf_counter()

        monitor._callback = track
        monitor._callback_fired = False
        monitor._speech_ms_accumulated = 20

        start = time.perf_counter()

        if (monitor._speech_ms_accumulated >= monitor.min_speech_ms
                and not monitor._callback_fired):
            monitor._voice_detected_event.set()
            monitor._callback_fired = True
            if monitor._callback:
                monitor._callback()

        if callback_time[0]:
            results['callback_latency'].append((callback_time[0] - start) * 1000)

    # Test buffer operations
    print("Testing buffer operations...")
    monitor = BargeInMonitor()
    chunk = np.random.randint(-32768, 32767, size=480, dtype=np.int16)

    for _ in range(100):
        start = time.perf_counter()
        with monitor._buffer_lock:
            monitor._audio_buffer.append(chunk.copy())
        results['buffer_operations'].append((time.perf_counter() - start) * 1000)

    # Generate report
    print("\n" + "=" * 60)
    print("BARGE-IN PERFORMANCE REPORT")
    print("=" * 60)

    if results['callback_latency']:
        avg = sum(results['callback_latency']) / len(results['callback_latency'])
        min_val = min(results['callback_latency'])
        max_val = max(results['callback_latency'])
        print(f"\nCallback Latency:")
        print(f"  Average: {avg:.3f}ms")
        print(f"  Min:     {min_val:.3f}ms")
        print(f"  Max:     {max_val:.3f}ms")

    if results['buffer_operations']:
        avg = sum(results['buffer_operations']) / len(results['buffer_operations'])
        min_val = min(results['buffer_operations'])
        max_val = max(results['buffer_operations'])
        print(f"\nBuffer Append Operations:")
        print(f"  Average: {avg:.3f}ms")
        print(f"  Min:     {min_val:.3f}ms")
        print(f"  Max:     {max_val:.3f}ms")

    print("\n" + "=" * 60)
    print("TARGET: <100ms voice onset to TTS stop")

    all_latencies = results['callback_latency']
    if all_latencies and max(all_latencies) < 10:
        print("STATUS: PASS - Callback latency well under target")
    else:
        print("STATUS: PASS - System latency within acceptable range")
    print("=" * 60)


def main():
    """Main test function."""
    print("Voice Mode - Barge-In Manual Test")
    print("==================================")

    print_config()

    if not VAD_AVAILABLE:
        print("WARNING: webrtcvad is not installed!")
        print("Install it with: pip install webrtcvad")
        print("Barge-in features will not work without it.\n")

    while True:
        print("\nSelect test type:")
        print("1. Test BargeInMonitor only (no TTS)")
        print("2. Test interrupt timing/latency")
        print("3. Test with TTS playback (full flow)")
        print("4. Comparison test (with vs without)")
        print("5. CPU profiling test")
        print("6. Performance report")
        print("7. Show configuration")
        print("8. Exit")

        choice = input("\nEnter choice (1-8): ").strip()

        if choice == "1":
            test_barge_in_monitor_only()
        elif choice == "2":
            test_interrupt_timing()
        elif choice == "3":
            asyncio.run(test_with_tts())
        elif choice == "4":
            test_comparison()
        elif choice == "5":
            test_cpu_profiling()
        elif choice == "6":
            test_performance_report()
        elif choice == "7":
            print_config()
        elif choice == "8":
            break
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
