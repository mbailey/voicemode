# Stream Capture with Flow Control - Implementation Spec

## Overview

Extend the existing `feature/let-me-finish` branch to add cassette-deck-style flow control commands for voice recording. This enables users to control recording, pause for privacy, review transcriptions before sending, and manage the conversation flow entirely by voice.

## Use Cases

1. **Let Me Finish**: Disable VAD silence detection to speak at length without interruption
2. **Privacy Pause**: Temporarily stop recording for phone calls or sensitive conversations
3. **Transcription Review**: Listen to what was transcribed before sending to LLM (flotation tank use case)
4. **Hands-Free Control**: Manage entire conversation flow using voice commands

## Architecture

### Current State (feature/let-me-finish branch)

The branch already implements:
- `uninterrupted_mode` parameter in converse tool
- `record_with_whisper_stream()` function that uses whisper-stream subprocess
- End phrase detection ("i'm done", "go ahead", etc.)
- Deduplication of overlapping transcription segments

### Proposed Changes

#### 1. New `stream_capture()` Function

Create standalone function that replaces `record_with_whisper_stream()`:

```python
async def stream_capture(
    control_phrases: Dict[str, List[str]],
    max_duration: float = 600.0,
    model_path: Optional[Path] = None,
    initial_mode: str = "recording"  # or "paused"
) -> Dict[str, Any]:
    """
    Capture audio with whisper-stream and detect control commands.

    Args:
        control_phrases: Dict mapping control signals to trigger phrases
            Example: {
                "send": ["send", "i'm done", "go ahead"],
                "pause": ["pause", "hold on"],
                "resume": ["resume", "continue"],
                "play": ["play back", "repeat"],
                "stop": ["stop", "cancel", "discard"]
            }
        max_duration: Maximum capture duration in seconds
        model_path: Path to whisper model
        initial_mode: Start in "recording" or "paused" state

    Returns:
        {
            "text": "accumulated transcription",
            "control_signal": "send"|"pause"|"resume"|"play"|"stop"|None,
            "audio_chunks": [np.ndarray, ...],  # For potential playback
            "duration": float,
            "segments": List[str]  # Raw segments for debugging
        }
    """
```

**State Machine:**

```
┌─────────────┐
│  RECORDING  │ ←─────┐
└──────┬──────┘       │
       │              │
       │ "pause"      │ "resume"
       │              │
       ▼              │
┌─────────────┐       │
│   PAUSED    │───────┘
└──────┬──────┘
       │
       │ "send", "stop", "play"
       │
       ▼
    [RETURN]
```

- **RECORDING**: Actively capturing and transcribing audio
- **PAUSED**: Not recording audio, but whisper-stream still running
- **Terminal commands**: "send", "stop", "play" return control to caller

#### 2. Update `converse()` Tool

Modify converse to support the flow control loop:

```python
@mcp.tool()
async def converse(
    message: str,
    wait_for_response: bool = True,
    # ... existing parameters ...
    stream_mode: Union[bool, str] = False,  # Replaces uninterrupted_mode
    control_phrases: Optional[Dict[str, List[str]]] = None
) -> str:
```

**Flow:**

1. Speak TTS message as usual
2. If `stream_mode=True`, enter flow control loop:
   ```python
   accumulated_text = ""
   while True:
       result = await stream_capture(control_phrases, ...)

       if result["control_signal"] == "pause":
           # Play acknowledgment sound
           play_sound("paused.wav")
           # Loop continues but stream_capture starts in paused mode

       elif result["control_signal"] == "resume":
           # Play acknowledgment sound
           play_sound("recording.wav")
           # Continue capturing

       elif result["control_signal"] == "play":
           # Read back accumulated transcription via TTS
           await text_to_speech(accumulated_text)
           # Continue loop to let user send or re-record

       elif result["control_signal"] == "send":
           # Send to LLM (or just return the text)
           return result["text"]

       elif result["control_signal"] == "stop":
           return "Recording cancelled"
   ```

3. If `stream_mode=False`, use existing VAD-based recording

#### 3. CLI Command for Testing

Add new CLI command to test stream capture independently:

```bash
voicemode stream-capture --control-phrases control.json --max-duration 300
```

This allows testing the state machine without the full converse flow.

#### 4. Configuration

Default control phrases in config or environment variables:

```python
# .voicemode.env or config
VOICEMODE_CONTROL_PHRASE_SEND="send,i'm done,go ahead"
VOICEMODE_CONTROL_PHRASE_PAUSE="pause,hold on"
VOICEMODE_CONTROL_PHRASE_RESUME="resume,continue,unpause"
VOICEMODE_CONTROL_PHRASE_PLAY="play back,repeat,read that"
VOICEMODE_CONTROL_PHRASE_STOP="stop,cancel,discard"
```

## Implementation Plan

### Phase 1: Core stream_capture Function (MVP)

**Files to modify:**
- `voice_mode/whisper_stream.py` - Rename and extend `record_with_whisper_stream()` to `stream_capture()`
- `voice_mode/tools/converse.py` - Update to call new function

**Changes:**
1. Extend whisper_stream.py:
   - Add control phrase detection (not just end phrases)
   - Implement RECORDING/PAUSED state machine
   - Return structured dict with control signals
   - Keep audio chunks for potential playback

2. Minimal converse changes:
   - Add `stream_mode` parameter
   - For MVP: only support "send" command (existing behavior)
   - Return transcription when "send" detected

**Test:**
```bash
# Start voicemode
voicemode converse "Tell me what you're thinking" --stream-mode true

# User speaks: "I was thinking about the jack pack idea <pause> and send"
# Should return: "I was thinking about the jack pack idea"
```

### Phase 2: Pause/Resume Control

**Files to modify:**
- `voice_mode/whisper_stream.py` - Add pause state handling
- `voice_mode/tools/converse.py` - Add loop for handling pause/resume

**Changes:**
1. Implement pause state in stream_capture:
   - Stop audio capture but keep whisper-stream running
   - Listen only for "resume" command
   - Play acknowledgment sounds

2. Add control loop in converse:
   - Handle pause/resume signals
   - Continue accumulating text across pauses

**Test:**
```bash
# User: "This is sensitive <pause> [private conversation] <resume> and send"
# Should only transcribe: "This is sensitive and send"
```

### Phase 3: Play/Review

**Files to modify:**
- `voice_mode/tools/converse.py` - Add playback handling

**Changes:**
1. When "play" detected:
   - Use TTS to read back accumulated text
   - Return to recording mode
   - User can then say "send" or continue adding

**Test:**
```bash
# User: "Add this to the context <play> <wait for playback> send"
# Should: speak text back, then submit on "send"
```

### Phase 4: Stop/Discard

**Changes:**
1. Add "stop" handling:
   - Discard accumulated text
   - Return "Recording cancelled" message

### Phase 5: CLI Command & Configuration

**Files to add:**
- `voice_mode/cli_stream_capture.py` - CLI command implementation

**Changes:**
1. Add `voicemode stream-capture` command
2. Load control phrases from config
3. Environment variable support

## Testing Strategy

1. **Unit tests** for whisper_stream.py:
   - Mock whisper-stream subprocess
   - Test control phrase detection
   - Test state transitions

2. **Integration tests** for converse flow:
   - Pre-recorded audio files with control phrases
   - Verify correct handling of each command

3. **Manual testing** scenarios:
   - Long-form dictation with pauses
   - Pause during phone call, resume after
   - Review transcription before sending
   - Cancel/discard unwanted recording

## Compatibility

- **Backward compatible**: stream_mode defaults to False, preserving existing VAD behavior
- **Graceful degradation**: If whisper-stream not available, fall back to regular recording
- **Future-proof**: stream_capture() can be used by audio intelligence system (VM-186)

## Migration from feature/let-me-finish

1. Rebase feature/let-me-finish onto current master
2. Rename `record_with_whisper_stream()` → `stream_capture()`
3. Extend with control phrase detection (not just end phrases)
4. Update converse to use stream_mode parameter
5. Keep existing uninterrupted_mode for backward compatibility (map to stream_mode)

## Open Questions

1. **Audio acknowledgment sounds**: Use system sounds or TTS for "paused", "recording"?
   - **Recommendation**: Use simple chime sounds (similar to existing feedback)

2. **Playback of audio vs TTS of text**: Should "play" replay audio or speak transcription?
   - **Recommendation**: Speak transcription via TTS (lower latency, consistent voice)

3. **Handling of control phrases in transcription**: Strip them from final text or keep?
   - **Recommendation**: Strip control phrases from returned text

4. **Max accumulated text length**: Limit for very long recordings?
   - **Recommendation**: Start with no limit, add if needed based on testing

## Success Criteria

- [ ] User can speak continuously without VAD cutting them off
- [ ] User can pause recording for privacy
- [ ] User can review transcription before sending
- [ ] User can cancel unwanted recording
- [ ] All controls work hands-free via voice commands
- [ ] Backward compatible with existing converse behavior
- [ ] No regression in normal VAD-based recording mode
