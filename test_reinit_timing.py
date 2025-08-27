#!/usr/bin/env python3
"""Test timing of sounddevice reinitialize."""

import sounddevice as sd
import time
import statistics

def time_reinit():
    """Time how long terminate/initialize takes."""
    start = time.perf_counter()
    sd._terminate()
    sd._initialize()
    end = time.perf_counter()
    return (end - start) * 1000  # Convert to milliseconds

def time_query_devices():
    """Time how long query_devices takes."""
    start = time.perf_counter()
    devices = sd.query_devices()
    end = time.perf_counter()
    return (end - start) * 1000  # Convert to milliseconds

def main():
    print("Testing sounddevice reinitialize timing...")
    print("=" * 50)
    
    # Warm up
    sd.query_devices()
    
    # Test reinitialize timing
    print("\n1. Testing sd._terminate() + sd._initialize():")
    reinit_times = []
    for i in range(10):
        ms = time_reinit()
        reinit_times.append(ms)
        print(f"   Run {i+1}: {ms:.2f} ms")
    
    print(f"\n   Average: {statistics.mean(reinit_times):.2f} ms")
    print(f"   Min: {min(reinit_times):.2f} ms")
    print(f"   Max: {max(reinit_times):.2f} ms")
    
    # Test query_devices timing for comparison
    print("\n2. Testing sd.query_devices() for comparison:")
    query_times = []
    for i in range(10):
        ms = time_query_devices()
        query_times.append(ms)
        print(f"   Run {i+1}: {ms:.2f} ms")
    
    print(f"\n   Average: {statistics.mean(query_times):.2f} ms")
    print(f"   Min: {min(query_times):.2f} ms")
    print(f"   Max: {max(query_times):.2f} ms")
    
    # Test if it actually picks up device changes
    print("\n3. Testing if default device updates after reinit:")
    print(f"   Before: Default input = {sd.default.device[0]}")
    print(f"           Default output = {sd.default.device[1]}")
    
    sd._terminate()
    sd._initialize()
    
    print(f"   After:  Default input = {sd.default.device[0]}")
    print(f"           Default output = {sd.default.device[1]}")
    
    print("\n" + "=" * 50)
    print("SUMMARY:")
    print(f"Reinitialize takes ~{statistics.mean(reinit_times):.0f} ms on average")
    print(f"This is {'fast enough' if statistics.mean(reinit_times) < 100 else 'a bit slow'} to do on every converse call")
    
    if statistics.mean(reinit_times) < 50:
        print("✅ Could definitely do this on every call!")
    elif statistics.mean(reinit_times) < 100:
        print("⚠️  Borderline - might add slight latency")
    else:
        print("❌ Too slow for every call - use reconnect tool instead")

if __name__ == "__main__":
    main()