# No Speech Detected Regression

## Overview
Fix critical regression on `feature/conversation-browser-library-broken` branch where user audio is recorded and saved but always results in "No speech detected" despite working TTS.

## Status
🟡 **INVESTIGATED** - Root cause identified but not fixed

## Goals
1. ✅ Identify root cause of "No speech detected" issue
2. ✅ Understand goals behind changes in the broken branch
3. ❌ Fix the regression while preserving intended functionality
4. ✅ Document findings and solution

## Investigation Notes

### Symptoms
- User audio is being recorded
- Audio files are saved
- STT service is available and working
- But always returns "No speech detected"

### Next Steps
1. Compare branches to identify changes
2. Examine STT processing code
3. Check audio format/encoding issues
4. Test with saved audio files
5. Write tests to prevent future regressions

## Links
- Branch: `feature/conversation-browser-library-broken`
- Related: Conversation browser improvements

## Investigation Summary

The regression is caused by the refactoring that moved MCP instance from `server.py` to `mcp_instance.py` in commit b8efb9f.

### Key Findings:
- Recording and STT work correctly when tested directly
- Only fails when called through MCP tool interface
- Issue is related to stdio handling in MCP context affecting audio recording

### Attempted Fixes (Unsuccessful):
1. VAD downsampling fix - not the issue
2. Audio silence threshold fix - not the issue

### Root Cause:
MCP servers use stdio for communication, which interferes with audio recording when imports were restructured.

See detailed analysis:
- [findings-summary.md](./findings-summary.md) - Complete investigation summary
- [real-root-cause.md](./real-root-cause.md) - Actual cause analysis
- [investigation.md](./investigation.md) - Initial investigation notes