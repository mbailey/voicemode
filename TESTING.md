# Testing Stream Mode - VM-194

## Implementation Complete

Phase 1 MVP of stream-capture with control phrases is ready for testing.

## What's Implemented

1. **stream_capture module** (`voice_mode/stream_capture.py`):
   - Whisper-stream subprocess management
   - Control phrase detection (send, pause, resume, play, stop)
   - Segment deduplication
   - Returns structured results

2. **converse integration** (`voice_mode/tools/converse.py`):
   - New `stream_mode` parameter (default: false)
   - Validates whisper-stream availability
   - Uses stream_capture when enabled
   - Skips separate STT (done during capture)

3. **CLI support** (`voice_mode/cli.py`):
   - New `--stream-mode` flag
   - Works with all converse modes (single and continuous)

## Testing Instructions

### Prerequisite

Ensure whisper-stream is installed and in PATH:
```bash
which whisper-stream
```

### Option 1: Standalone Test

Test stream_capture module directly:
```bash
cd /Users/admin/tasks/projects/voicemode/VM-194_feat_implement-stream-capture-with-cassette-deck-flow-controls/worktree
python test_stream_capture.py
```

Speak and say "send" or "i'm done" to finish.

### Option 2: CLI Test

Install from the worktree and test:
```bash
cd /Users/admin/tasks/projects/voicemode/VM-194_feat_implement-stream-capture-with-cassette-deck-flow-controls/worktree
uv tool install --force --editable .
voicemode converse --stream-mode
```

Speak and say "send" or "i'm done" to finish.

### Option 3: MCP Tool Test

From Claude Code with voicemode MCP server configured:
```
Use the converse tool with stream_mode=true
```

## Expected Behavior

1. TTS speaks your message
2. Whisper-stream starts capturing
3. You speak freely - no VAD cutoff
4. When you say "send", "i'm done", or "go ahead":
   - Capture stops
   - Text is returned (with control phrase stripped)
   - Shows control signal detected

## Control Phrases (Phase 1 MVP)

Currently implemented:
- **send**: "send", "i'm done", "go ahead", "that's all"
- **stop**: "stop", "cancel", "discard"
- **pause**: "pause", "hold on"
- **resume**: "resume", "continue", "unpause"
- **play**: "play back", "repeat", "read that"

Note: Only "send" fully tested in Phase 1. Other commands detected but not yet fully integrated with converse loop.

## Known Limitations

- Whisper-stream device selection uses default (may not match system default)
- No audio file saving yet in stream mode
- Pause/resume/play/stop signals detected but not yet handled in converse
- No configuration for custom control phrases yet (uses defaults)

## Next Steps (Future Phases)

- Phase 2: Implement pause/resume handling in converse
- Phase 3: Implement play (TTS playback of accumulated text)
- Phase 4: Implement stop (discard and exit)
- Phase 5: Add configuration for custom control phrases
- Phase 6: Add audio device selection for whisper-stream

## Git Status

Branch: `feat/VM-194-implement-stream-capture-with-cassette-deck-flow`

Commits:
- 3e92d5e: SDL2 dependencies and spec
- 662d6fc: stream_capture module
- 50f86df: test script
- f18f0be: converse integration
- 6d0c25d: CLI flag

Ready for testing!
