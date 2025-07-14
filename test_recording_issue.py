#!/usr/bin/env python3
"""Test to reproduce the recording issue where no speech is detected."""

import sys
from pathlib import Path
import numpy as np
import asyncio

sys.path.insert(0, str(Path(__file__).parent))

from voice_mode.tools.conversation import record_audio_with_silence_detection, speech_to_text_with_failover

def test_recording():
    """Test the recording function to see what it returns."""
    print("Testing record_audio_with_silence_detection...")
    print("Please speak within 10 seconds...")
    
    # Record audio
    audio_data = record_audio_with_silence_detection(
        max_duration=10.0,
        disable_silence_detection=False,
        min_duration=0.5
    )
    
    print(f"\nRecording complete!")
    print(f"Audio shape: {audio_data.shape}")
    print(f"Audio dtype: {audio_data.dtype}")
    print(f"Max amplitude: {np.abs(audio_data).max()}")
    print(f"Audio length: {len(audio_data)} samples ({len(audio_data)/24000:.2f} seconds)")
    
    # Save the recording for analysis
    from scipy.io import wavfile
    test_file = Path("test_recording.wav")
    wavfile.write(test_file, 24000, audio_data)
    print(f"Saved recording to: {test_file}")
    
    return audio_data

async def test_stt_on_recording(audio_data):
    """Test STT on the recorded audio."""
    print("\nTesting STT on recorded audio...")
    
    result = await speech_to_text_with_failover(
        audio_data,
        save_audio=False,
        audio_dir=None,
        transport="test"
    )
    
    print(f"STT Result: {repr(result)}")
    
    if result:
        print("✅ STT worked on recording!")
    else:
        print("❌ STT failed on recording!")
    
    return result

def main():
    # First test recording
    audio_data = test_recording()
    
    if len(audio_data) == 0:
        print("\n❌ ERROR: No audio was recorded!")
        return
    
    # Then test STT on the recording
    asyncio.run(test_stt_on_recording(audio_data))

if __name__ == "__main__":
    main()