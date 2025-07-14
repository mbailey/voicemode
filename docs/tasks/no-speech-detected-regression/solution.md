# Solution: VAD Sample Rate Mismatch

## Root Cause Identified

The Voice Activity Detection (VAD) is failing because of incorrect audio chunk handling:

1. **Recording at 24kHz**: `SAMPLE_RATE = 24000`
2. **VAD expects 16kHz**: `vad_sample_rate = 16000`
3. **Chunk size mismatch**:
   - For 30ms: 24kHz needs 720 samples
   - For 30ms: 16kHz needs 480 samples
   - Code takes first 480 samples from 720-sample chunk
   - This gives VAD only 20ms of audio instead of 30ms

## The Bug

```python
# Line 897: This is wrong!
vad_chunk = chunk_flat[:vad_chunk_samples]
```

Taking the first 480 samples from a 24kHz recording gives only 20ms of audio.
VAD expects exactly 30ms (480 samples at 16kHz).

## Why It Worked Before

This code hasn't changed between branches. The issue must be either:
1. Environment difference (different webrtcvad version?)
2. Some other change affecting audio processing
3. The VAD was always broken but something else masked it

## Solution

Properly downsample from 24kHz to 16kHz before passing to VAD:

```python
# Simple downsampling: take every 1.5th sample (24/16 = 1.5)
# More proper would be to use scipy.signal.resample
indices = np.arange(0, len(chunk_flat), 1.5).astype(int)[:vad_chunk_samples]
vad_chunk = chunk_flat[indices]
```

## Testing

1. Fix the VAD chunk extraction
2. Test with voice input
3. Verify VAD correctly detects speech