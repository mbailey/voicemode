# Actual Solution: Audio Silence Threshold Bug

## Real Root Cause

The STT function was incorrectly rejecting all audio as "silent" due to a threshold bug:

1. **Audio format**: Recording produces int16 audio (values -32768 to 32767)
2. **Threshold bug**: Code checks if `max_amplitude < 0.001`
3. **Problem**: 0.001 is appropriate for float audio (-1.0 to 1.0), not int16
4. **Result**: All audio with amplitude < 0.001 rejected as silent (basically everything!)

## The Fix

```python
# Before: Always rejects int16 audio as silent
if np.abs(audio_data).max() < 0.001:
    logger.warning("Audio appears to be silent")
    return None

# After: Use appropriate threshold based on audio format
if audio_data.dtype == np.int16:
    silence_threshold = 33  # ~0.1% of max int16 value
else:
    silence_threshold = 0.001
    
if max_amplitude < silence_threshold:
    logger.warning(f"Audio appears to be silent")
    return None
```

## Why It Worked on Master

This bug wasn't in master - it was introduced in the feature branch when adding debug logging or other changes to the STT function.

## Testing

- Audio file with max amplitude 32767 now passes threshold of 33
- STT correctly processes the audio and returns transcription
- Confirmed with integration test using real audio files