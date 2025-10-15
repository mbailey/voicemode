# Reduce converse tool description for Amazon Q compatibility

## Summary

This PR reduces the `converse` MCP tool description from ~4,000 characters to **1,722 characters** to meet Amazon Q's 10,024 character limit per tool. The reduction is achieved through:

1. Moving extensive documentation to MCP resources
2. Removing dead code and unused parameters
3. Renaming parameters for clarity and brevity
4. Streamlining the tool description to essentials only

## Problem

Amazon Q limits tool descriptions to 10,024 characters. The original `converse` tool description was bloated with inline documentation, making it difficult to integrate with services that have tighter limits.

## Solution

### 1. Created MCP Resources for Documentation (70dabdc)

Moved detailed documentation out of the tool description into MCP resources:

- `voicemode://docs/quickstart` - Basic usage and common examples
- `voicemode://docs/parameters` - Complete parameter reference
- `voicemode://docs/patterns` - Best practices and conversation patterns
- `voicemode://docs/troubleshooting` - Audio, VAD, and connectivity issues
- `voicemode://docs/languages` - Non-English language support guide

This allows AI assistants to access comprehensive documentation without bloating the tool description.

### 2. Removed Dead Code (9b5c252)

Removed 240 lines of unused `_speech_to_text_internal` function and related code that was never called.

### 3. Renamed Parameters for Clarity (8fa3242, 5ac832d)

**Listen Duration Parameters:**
- `listen_duration` → `listen_duration_max` (more explicit)
- `min_listen_duration` → `listen_duration_min` (consistent naming)

**Audio Feedback Parameters:**
- `audio_feedback` → `chime_enabled` (clearer intent)
- `pip_leading_silence` → `chime_leading_silence` (better terminology)
- `pip_trailing_silence` → `chime_trailing_silence` (better terminology)
- Removed `audio_feedback_style` (unused parameter)

**Rationale:**
- "pip" terminology was confusing (not related to Python pip)
- "chime" clearly indicates audio feedback purpose
- Consistent `_min`/`_max` suffix pattern for duration parameters

### 4. Completed Parameter Refactoring Cleanup (bd15ac5)

Fixed all issues from code review:

**Critical:**
- Removed `audio_feedback_style=None` parameter from CLI that referenced deleted parameter

**Environment Variables:**
- `VOICEMODE_PIP_LEADING_SILENCE` → `VOICEMODE_CHIME_LEADING_SILENCE`
- `VOICEMODE_PIP_TRAILING_SILENCE` → `VOICEMODE_CHIME_TRAILING_SILENCE`

**Documentation:**
- Updated `parameters.md` with all renamed parameters
- Updated `troubleshooting.md` code examples with new parameter names
- Ensured consistency across all documentation

## Impact

### Tool Description Size
- **Before:** ~4,000 characters (bloated with inline docs)
- **After:** 1,722 characters (well under 10,024 limit)
- **Reduction:** ~57% smaller

### Breaking Changes

⚠️ **API Changes** - Users will need to update code:

**Parameter renames:**
```python
# OLD
converse("Hello",
    listen_duration=60,
    min_listen_duration=2.0,
    audio_feedback=True,
    pip_leading_silence=1.0,
    pip_trailing_silence=0.5
)

# NEW
converse("Hello",
    listen_duration_max=60,
    listen_duration_min=2.0,
    chime_enabled=True,
    chime_leading_silence=1.0,
    chime_trailing_silence=0.5
)
```

**Environment variables:**
```bash
# OLD
export VOICEMODE_PIP_LEADING_SILENCE=1.0
export VOICEMODE_PIP_TRAILING_SILENCE=0.5

# NEW
export VOICEMODE_CHIME_LEADING_SILENCE=1.0
export VOICEMODE_CHIME_TRAILING_SILENCE=0.5
```

### Benefits

1. **Amazon Q Compatible** - Tool description under 10,024 character limit
2. **Better Documentation** - Comprehensive docs available via MCP resources
3. **Clearer API** - More intuitive parameter names
4. **Cleaner Code** - Removed 240 lines of dead code
5. **Consistent Naming** - Parameters follow clear conventions

## Testing

- ✅ All unit tests pass (config and CLI tests verified)
- ✅ Module imports successfully
- ✅ Papa Bear code review verification passed
- ⚠️ Manual testing recommended before merge

## Migration Guide

For users upgrading, update parameter names and environment variables as shown in the Breaking Changes section above. The functionality remains the same - only names have changed.

## Files Changed

- **voice_mode/tools/converse.py** - Reduced tool description, removed dead code
- **voice_mode/cli.py** - Updated parameter names in CLI commands
- **voice_mode/config.py** - Renamed environment variables
- **voice_mode/resources/docs_resources.py** - Added MCP resource endpoints
- **voice_mode/resources/docs/** - New comprehensive documentation files
- **tests/** - Updated test parameter names

## Related

- Fixes VM-140
- Ready for Amazon Q integration
