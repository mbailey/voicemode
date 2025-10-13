# Voicemode Troubleshooting

## Audio Issues

### User being cut off mid-sentence

**Problem:** Silence detection stops recording too early.

**Solutions:**
1. Increase `listen_duration_min`:
   ```python
   converse("What's on your mind?", listen_duration_min=5.0)
   ```

2. Decrease VAD aggressiveness:
   ```python
   converse("Tell me more", vad_aggressiveness=0)
   ```

3. Disable silence detection entirely:
   ```python
   converse("Please describe in detail", disable_silence_detection=True)
   ```

### Background noise triggering false starts

**Problem:** VAD detects non-speech as speech.

**Solutions:**
1. Increase VAD aggressiveness:
   ```python
   converse("Can you hear me?", vad_aggressiveness=3)
   ```

2. Check environment noise levels
3. Use better quality microphone

### Audio chimes getting cut off

**Problem:** Bluetooth or audio system delays.

**Solutions:**
1. Add leading silence:
   ```python
   converse("Hello", chime_leading_silence=1.0)
   ```

2. Add trailing silence:
   ```python
   converse("Hello", chime_trailing_silence=0.5)
   ```

3. Add both:
   ```python
   converse("Hello", chime_leading_silence=1.0, chime_trailing_silence=0.5)
   ```

### No audio output

**Problem:** TTS not playing.

**Solutions:**
1. Check if `skip_tts` is enabled
2. Verify VOICEMODE_SKIP_TTS env var
3. Force TTS:
   ```python
   converse("Test message", skip_tts=False)
   ```
4. Check audio output device settings
5. Verify TTS service endpoint

## Voice Activity Detection (VAD)

### Understanding VAD levels

- **0 (Least aggressive):** Captures everything, including background noise
- **1 (Low):** Slightly stricter, good for quiet environments
- **2 (Balanced - default):** Good for normal home/office
- **3 (Most aggressive):** Strict speech detection, filters most noise

### When to adjust VAD

| Environment | Recommended Setting | Reason |
|-------------|-------------------|---------|
| Silent room | 0-1 | Don't miss soft speech |
| Home office | 2 | Balanced (default) |
| Busy office | 2-3 | Filter typing, conversations |
| Cafe/public | 3 | Filter heavy background noise |
| Outdoors | 3 | Filter wind, traffic |
| Dictation mode | 0-1 + high listen_duration_min | Allow thinking pauses |

## Connection Issues

### STT/TTS endpoint errors

**Problem:** Cannot connect to speech services.

**Check:**
1. Services expose OpenAI-compatible endpoints:
   - `/v1/audio/transcriptions` (STT)
   - `/v1/audio/speech` (TTS)

2. Environment variables are set correctly:
   - `OPENAI_API_KEY` (if using OpenAI)
   - Service URLs for Whisper/Kokoro

3. Network connectivity to services

4. Service logs for errors

### Transport issues

**Problem:** LiveKit or local transport failing.

**Solutions:**
1. Try different transport:
   ```python
   # Force local transport
   converse("Test", transport="local")

   # Force LiveKit
   converse("Test", transport="livekit")
   ```

2. Check LiveKit room configuration
3. Verify microphone permissions

### Timeout issues

**Problem:** Operations timing out.

**Solutions:**
1. Increase listen duration:
   ```python
   converse("Please elaborate", listen_duration_max=300)
   ```

2. Check network latency to services
3. Verify services are responding

## Voice Quality Issues

### Incorrect pronunciation

**Problem:** Words mispronounced, especially for non-English.

**Solutions:**
1. For non-English, use Kokoro with appropriate voice:
   ```python
   converse("Bonjour", voice="ff_siwis", tts_provider="kokoro")
   ```

2. See `voicemode-languages` resource for language-specific voices

### Robotic/unnatural voice

**Problem:** Voice sounds too mechanical.

**Solutions:**
1. Try different voice:
   ```python
   converse("Hello", voice="nova")  # OpenAI
   converse("Hello", voice="af_sky", tts_provider="kokoro")
   ```

2. Use HD model for better quality:
   ```python
   converse("Hello", tts_model="tts-1-hd")
   ```

3. Add emotional context:
   ```python
   converse(
       "I'm excited to help!",
       tts_model="gpt-4o-mini-tts",
       tts_instructions="Sound warm and friendly"
   )
   ```

### Speech too fast/slow

**Problem:** Default speed doesn't match user preference.

**Solution:** Adjust speed:
```python
# Slower
converse("Complex information", speed=0.8)

# Faster
converse("Quick update", speed=1.5)
```

## Recognition Issues

### STT not recognizing speech

**Problem:** Speech not being transcribed.

**Solutions:**
1. Check microphone is working
2. Verify microphone permissions
3. Increase recording duration:
   ```python
   converse("What do you think?", listen_duration_min=5.0)
   ```
4. Disable silence detection to see if it's a VAD issue:
   ```python
   converse("Testing", disable_silence_detection=True, listen_duration_max=10)
   ```

### Incorrect transcriptions

**Problem:** Speech transcribed wrong.

**Solutions:**
1. Speak more clearly
2. Reduce background noise
3. Adjust VAD for your environment
4. Use better quality microphone
5. Check STT service configuration

## Performance Issues

### Slow response times

**Problem:** Long delays between speaking and response.

**Causes:**
1. Network latency to STT/TTS services
2. Heavy service load
3. Large audio files

**Solutions:**
1. Use lower quality audio format if possible
2. Check service response times
3. Consider local STT/TTS services
4. Use `skip_tts=True` for development:
   ```python
   converse("Quick test", skip_tts=True)
   ```

## Common Mistakes

### Using coral voice
❌ **Don't:** `voice="coral"` - Not supported
✅ **Do:** Use supported voices (nova, shimmer, af_sky, etc.)

### Not specifying voice for non-English
❌ **Don't:** `converse("Bonjour")`
✅ **Do:** `converse("Bonjour", voice="ff_siwis", tts_provider="kokoro")`

### Setting listen_duration_max too low
❌ **Don't:** `listen_duration_max=5` for complex questions
✅ **Do:** Use default (120) or higher for long responses

### Overriding defaults unnecessarily
❌ **Don't:** Specify `voice`, `tts_provider`, `tts_model` without reason
✅ **Do:** Let system auto-select unless specific need

## Getting More Help

If issues persist:
1. Check service logs for errors
2. Verify environment configuration
3. Test with minimal parameters first
4. Add parameters one at a time to isolate issue

## See Also
- `voicemode-parameters` - Full parameter reference
- `voicemode-patterns` - Best practices
- `voicemode-languages` - Language-specific configuration
