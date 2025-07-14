# Investigation Notes

## Summary
The `feature/conversation-browser-library-broken` branch has a regression where STT always returns "No speech detected" even though:
- Audio is being recorded
- Audio files are saved
- TTS service is working

## Key Changes in Branch
1. Import changes: `voice_mode.server` → `voice_mode.mcp_instance`
2. New files added:
   - tests/test_cli_exchanges.py
   - tests/test_exchanges_integration.py
   - tests/test_exchanges_library.py
   - voice_mode/cli_commands/conversations.py
   - voice_mode/completion.py
   - voice_mode/metadata.py
   - voice_mode/resources/conversations.py
   - voice_mode/tools/metadata.py

## STT Flow Analysis

### Current Flow
1. `converse()` calls `record_audio_with_silence_detection()`
2. Audio is recorded and saved
3. `speech_to_text_with_failover()` is called with audio data
4. It tries each STT endpoint using `_speech_to_text_internal()`
5. `_speech_to_text_internal()` returns None when:
   - Audio is silent (max < 0.001)
   - STT API returns empty text
   - Exception occurs

### Potential Issues
1. **Silent audio check**: Line 481-483 returns None if `np.abs(audio_data).max() < 0.001`
2. **No speech after grace period**: Lines 924-926 stop recording if no speech detected after INITIAL_SILENCE_GRACE_PERIOD
3. **Empty transcription**: Lines 633-635 return None if STT returns empty text

## Key Findings

### Audio Recording Works
- Saved audio files contain speech (not silent)
- Audio levels are above silence threshold (0.001)
- Example: max amplitude 0.0945, RMS 0.011

### STT Service Works
Direct test with saved audio files shows STT returns correct transcriptions:
- OpenAI: "Thank you so much for watching !"
- Local Whisper: "Hello, can you hear my voice?"

### Issue is in Code
The problem is in the broken branch's code, not the audio or STT service.

## Root Cause Investigation

Need to check:
1. How transcription result is processed in `_speech_to_text_internal`
2. Whether there's an issue with response parsing
3. If the result is being lost somewhere in the call chain

## Next Steps
1. Add debug logging to trace transcription result
2. Check if response format handling has changed
3. Verify the return path from STT to converse function