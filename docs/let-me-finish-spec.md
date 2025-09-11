# Let Me Finish - Uninterrupted Mode Specification

## Overview
Add an "uninterrupted mode" to VoiceMode's converse function that allows users to speak at length without automatic processing after silence detection. The mode uses trigger phrases for control.

## User Experience

### Activation
- User says: "Let me finish" (configurable wake phrase)
- System enters buffering mode, continues recording without processing
- Visual/audio indicator confirms mode is active

### Speaking Phase
- User can speak freely with natural pauses
- No automatic processing on silence
- All speech is buffered locally
- No token limits during collection

### Completion
- User says: "I'm done" / "Go ahead" / "That's all" (configurable end phrases)
- System processes entire buffered speech as one request
- Returns to normal conversational mode

## Implementation Architecture

### 1. New Parameter for converse()
```python
async def converse(
    message: str,
    wait_for_response: bool = True,
    uninterrupted_mode: bool = False,  # NEW
    end_phrases: List[str] = None,     # NEW (default: ["I'm done", "go ahead", "that's all"])
    # ... existing parameters
)
```

### 2. Recording Method Selection
```python
if uninterrupted_mode:
    audio_data, transcribed_text = await record_with_whisper_stream(
        end_phrases=end_phrases,
        max_duration=max_duration
    )
else:
    # Existing silence detection logic
    audio_data, speech_detected = record_audio_with_silence_detection(...)
```

### 3. Whisper-Stream Integration

#### New Function: `record_with_whisper_stream()`
```python
async def record_with_whisper_stream(
    end_phrases: List[str],
    max_duration: float = 600.0  # 10 minutes max
) -> Tuple[np.ndarray, str]:
    """
    Record using whisper-stream subprocess with wake word detection.
    
    Returns:
        - audio_data: Combined audio buffer
        - transcribed_text: Full transcription
    """
    
    # Launch whisper-stream with VAD mode
    process = subprocess.Popen(
        [
            "whisper-stream",
            "-m", model_path,
            "--step", "0",  # VAD mode
            "--save-audio",  # Save audio chunks
            "-t", "6"
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Collect transcriptions until end phrase detected
    full_text = []
    audio_files = []
    
    while True:
        line = process.stdout.readline()
        if not line:
            break
            
        text = line.strip()
        full_text.append(text)
        
        # Check for end phrases
        if any(phrase.lower() in text.lower() for phrase in end_phrases):
            break
            
        # Check max duration
        if elapsed_time > max_duration:
            break
    
    # Terminate whisper-stream
    process.terminate()
    
    # Combine audio files if saved
    # Return combined audio and full transcription
    return combined_audio, " ".join(full_text)
```

### 4. CLI Integration
```bash
# Add --uninterrupted flag
voicemode converse --uninterrupted

# Or with custom end phrase
voicemode converse --uninterrupted --end-phrase "okay process that"
```

### 5. MCP Tool Update
Add parameters to the MCP tool definition for API access.

## Alternative Approaches Considered

### A. Python-based continuous recording
- More complex, requires streaming STT
- Higher latency for phrase detection
- More resource intensive

### B. Modified silence detection
- Doesn't solve the core problem
- Still interrupts on longer pauses
- Complex timeout logic

### C. Fixed long duration
- Poor UX - user doesn't know when it will process
- Wastes time if user finishes early
- Token limits still apply

## Benefits of Whisper-Stream Approach

1. **Simplicity** - Leverages existing whisper-stream binary
2. **Efficiency** - VAD built-in, optimized C++ processing  
3. **Real-time** - Continuous transcription for phrase detection
4. **Reliability** - Proven whisper.cpp codebase
5. **Flexibility** - Easy to configure models, parameters

## Configuration

### Environment Variables
```bash
VOICEMODE_UNINTERRUPTED_END_PHRASES="I'm done,go ahead,that's all,process that"
VOICEMODE_UNINTERRUPTED_MAX_DURATION=600  # seconds
VOICEMODE_WHISPER_STREAM_MODEL="large-v2"
```

### Config File
```yaml
uninterrupted_mode:
  end_phrases:
    - "I'm done"
    - "go ahead"
    - "that's all"
  max_duration: 600
  whisper_model: "large-v2"
```

## Migration Path

1. **Phase 1**: Add subprocess-based recording function
2. **Phase 2**: Wire up to converse() with feature flag
3. **Phase 3**: Add CLI support
4. **Phase 4**: Polish UX (indicators, feedback)

## Testing Strategy

1. Unit tests for phrase detection logic
2. Integration tests with mock whisper-stream
3. End-to-end tests with real audio
4. Performance benchmarks vs standard mode

## Future Enhancements

1. **Visual indicators** - Show buffering status in terminal
2. **Partial processing** - Stream partial results for long speeches
3. **Command mode** - "Save that", "Cancel", "Start over"
4. **Multiple speakers** - Use diarization for conversations
5. **Pause/Resume** - "Hold on" to pause, "continue" to resume

## Summary

This specification provides a clean, maintainable way to add uninterrupted speaking mode to VoiceMode by:
- Leveraging whisper-stream for continuous local transcription
- Using natural trigger phrases for mode control
- Maintaining backward compatibility
- Providing a simple implementation path

The approach prioritizes user experience and implementation simplicity over complex technical solutions.