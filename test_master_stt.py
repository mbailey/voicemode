#!/usr/bin/env python3
"""Test if STT works on master branch with a known audio file."""

import asyncio
import sys
from pathlib import Path
import numpy as np
from scipy.io import wavfile

sys.path.insert(0, str(Path(__file__).parent))

from voice_mode.tools.conversation import speech_to_text_with_failover, _speech_to_text_internal
from voice_mode.providers import get_stt_client

async def test():
    # Load a known good audio file
    audio_file = Path.home() / ".voicemode" / "audio" / "20250714_113239_377_571pob_stt.wav"
    
    if not audio_file.exists():
        print(f"Audio file not found: {audio_file}")
        return
    
    print(f"Testing on MASTER branch with: {audio_file.name}")
    
    # Read the audio file
    sample_rate, audio_data = wavfile.read(audio_file)
    print(f"Audio shape: {audio_data.shape}, dtype: {audio_data.dtype}")
    print(f"Max amplitude: {np.abs(audio_data).max()}")
    print(f"Would fail 0.001 threshold? {np.abs(audio_data).max() < 0.001}")
    
    # Test the speech_to_text_with_failover function
    print("\nTesting speech_to_text_with_failover...")
    result = await speech_to_text_with_failover(
        audio_data,
        save_audio=False,
        audio_dir=None,
        transport="test"
    )
    
    print(f"Result: {repr(result)}")
    
    if result:
        print("✅ Master branch STT works!")
    else:
        print("❌ Master branch STT also fails!")

if __name__ == "__main__":
    asyncio.run(test())