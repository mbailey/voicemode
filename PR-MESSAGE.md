# Fix: Reduce converse tool description for Amazon Q compatibility

Fixes VM-140

## Summary

Reduces the `converse` MCP tool description from ~4,000 characters to **1,738 characters** (57% reduction) to meet Amazon Q's 10,024 character limit.

## Changes

### 1. Documentation → MCP Resources
Moved extensive inline docs to MCP resources:
- `voicemode://docs/quickstart` - Basic usage and examples
- `voicemode://docs/parameters` - Complete parameter reference
- `voicemode://docs/patterns` - Best practices
- `voicemode://docs/troubleshooting` - Audio/VAD issues
- `voicemode://docs/languages` - Non-English support

### 2. Code Cleanup
- Removed 240 lines of unused `_speech_to_text_internal` function

### 3. Parameter Renames (Breaking)

**Listen Duration:**
- `listen_duration` → `listen_duration_max`
- `min_listen_duration` → `listen_duration_min`

**Audio Feedback:**
- `audio_feedback` → `chime_enabled`
- `pip_leading_silence` → `chime_leading_silence`
- `pip_trailing_silence` → `chime_trailing_silence`
- Removed unused `audio_feedback_style`

**Environment Variables:**
- `VOICEMODE_PIP_LEADING_SILENCE` → `VOICEMODE_CHIME_LEADING_SILENCE`
- `VOICEMODE_PIP_TRAILING_SILENCE` → `VOICEMODE_CHIME_TRAILING_SILENCE`

### 4. Prompt Enhancement
Added `context` parameter to `/voicemode:converse` prompt for proper slash command argument handling

### 5. Documentation Fixes
Corrected environment variable names in docs to match actual implementation

## Migration

```python
# Before
converse("Hello",
    listen_duration=60,
    min_listen_duration=2.0,
    audio_feedback=True,
    pip_leading_silence=1.0)

# After
converse("Hello",
    listen_duration_max=60,
    listen_duration_min=2.0,
    chime_enabled=True,
    chime_leading_silence=1.0)
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

## Testing
- ✅ All unit tests pass
- ✅ Papa Bear code review passed
- ⚠️ Manual testing recommended

## Benefits
1. Amazon Q compatible (under 10,024 char limit)
2. Better organized documentation via MCP resources
3. Clearer, more intuitive parameter names
4. Cleaner codebase (-240 lines dead code)
5. Accurate documentation matching implementation
