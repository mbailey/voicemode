# Root Cause Analysis

## The Issue
Users are speaking but voice-mode always returns "No speech detected" on the `feature/conversation-browser-library-broken` branch.

## Key Evidence

### 1. Audio Files Have Content
- Saved STT audio files contain speech (verified with audio analysis)
- Max amplitudes range from 0.0044 to 0.0945 (well above 0.001 threshold)

### 2. STT Service Works
- Direct API calls to STT return correct transcriptions
- Both OpenAI and local Whisper work correctly

### 3. Pattern in Failures
All "[no speech detected]" entries show:
- Recording time: ~4-5 seconds (matches INITIAL_SILENCE_GRACE_PERIOD = 4.0s)
- STT time: 0.0-0.1s (very fast, suggesting no actual API call)
- This indicates VAD is not detecting speech, so recording stops after grace period

## Root Cause Hypothesis

The Voice Activity Detection (VAD) is not detecting speech even when users are speaking. This causes:

1. VAD reports no speech detected
2. Recording stops after 4 second grace period
3. Audio is recorded but marked as "no speech"
4. STT is either skipped or returns empty

## Possible Causes

1. **Audio callback issue**: The audio data might not be properly passed to VAD
2. **VAD configuration**: VAD parameters might be incorrect for the audio format
3. **Audio format mismatch**: VAD expects specific sample rate/format
4. **Threading/async issue**: Audio chunks might not be processed correctly

## Next Steps

1. Add logging to VAD processing to see if it's receiving audio chunks
2. Check if audio format passed to VAD matches expectations
3. Test VAD directly with known good audio
4. Compare VAD implementation between master and broken branch