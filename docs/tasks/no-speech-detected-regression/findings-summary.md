# No Speech Detected Regression - Investigation Summary

## Problem Description
The `feature/conversation-browser-library-broken` branch has a regression where voice mode always returns "No speech detected" when called through the MCP tool interface, despite audio being recorded and STT services working correctly.

## Investigation Process

### 1. Initial Hypotheses (Incorrect)
- **VAD Bug**: Thought VAD was incorrectly downsampling audio chunks
  - Added downsample fix but issue persisted
  - VAD was working correctly all along

- **Silence Threshold Bug**: Thought 0.001 threshold was wrong for int16 audio
  - Added dtype-specific thresholds
  - Master branch works fine with same 0.001 threshold
  - Not the actual issue

### 2. Key Findings

#### What Works
- Recording function works correctly when tested directly
- STT function works correctly with saved audio files
- Audio files contain valid speech (not silent)
- The exact same code works on master branch

#### What Fails
- Only fails when called through MCP tool interface (`transport: "local"`)
- Works when called directly in tests (`transport: "test"`)
- Fails after commit b8efb9f which changed imports from `voice_mode.server` to `voice_mode.mcp_instance`

### 3. Root Cause Analysis

The regression was introduced by the refactoring that moved the MCP instance from `server.py` to `mcp_instance.py`:

```python
# Before (working):
from voice_mode.server import mcp

# After (broken):
from voice_mode.mcp_instance import mcp
```

This change affects how the MCP server runtime environment is set up, particularly around stdio handling.

### 4. Why It Breaks in MCP Context

1. **MCP uses stdio for communication** - stdin/stdout are redirected for the MCP protocol
2. **Audio recording may depend on stdio** - The sounddevice library might output to stderr
3. **Runtime environment differs** - When running through MCP vs direct execution

The code attempts to save/restore stdio streams during recording, but this may not be sufficient when the entire process has redirected stdio for MCP communication.

## Evidence

1. **Timing patterns in logs**:
   - Successful: `"transport": "test"` 
   - Failed: `"transport": "local"` with `"[no speech detected]"`

2. **STT is being called** (takes normal time ~4s) but returns empty
3. **Recording completes** (takes normal time ~10-15s) but audio might be corrupted

## Lessons Learned

1. **Always reproduce the exact failure mode first** - I spent time fixing hypothetical bugs without confirming they were the actual issue
2. **Test in the same context** - Direct tests passed but MCP context failed
3. **Refactoring module structure can have subtle effects** - Moving imports changed the runtime behavior

## Next Steps

To properly fix this issue:
1. Test the MCP server in isolation to understand stdio handling
2. Add logging to capture what happens to audio data in MCP context
3. Consider if audio recording needs to be isolated from stdio
4. Potentially revert the import refactoring until the issue is understood

## Files Modified During Investigation

- `voice_mode/tools/conversation.py` - Added debug logging
- `test_audio_debug.py` - Audio file analysis
- `test_stt_direct.py` - Direct STT testing  
- `test_speech_to_text_integration.py` - Integration testing
- `test_recording_issue.py` - Recording function testing
- `test_master_stt.py` - Cross-branch testing
- `tests/test_vad_regression.py` - VAD regression tests (not actually needed)