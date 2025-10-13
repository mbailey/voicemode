# Parameter Analysis for voice_mode/tools/converse.py

## Executive Summary

After thorough analysis of the `converse()` function in `voice_mode/tools/converse.py`, I've identified several parameters that are either unused, legacy code, or have misleading names. This analysis provides detailed findings with code references and recommendations for cleanup.

## 1. Unused Parameters

### `audio_feedback_style` parameter
- **Status**: NOT USED (legacy code)
- **Evidence**:
  - Defined at line 1208
  - Passed to `play_audio_feedback()` at lines 1646 and 1677 as `audio_feedback_style or "whisper"`
  - However, in `play_audio_feedback()` function (line 574-625), the `style` parameter is documented as "Kept for compatibility, not used" (line 591)
  - The function completely ignores this parameter and only uses the `text` parameter to determine which chime to play

### Parameters in `play_audio_feedback()` that are ignored:
- `style` (line 578): Documented as "not used"
- `feedback_type` (line 579): Documented as "not used"
- `voice` (line 580): Documented as "not used"
- `model` (line 581): Documented as "not used"

## 2. Dead Code

### `_speech_to_text_internal()` function
- **Status**: DEAD CODE - Never called
- **Evidence**:
  - Defined at line 332-572
  - A grep search shows it's only defined, never called anywhere in the codebase
  - This is a large function (240 lines) that appears to be legacy code from before the failover refactoring
  - The actual speech-to-text functionality now uses `speech_to_text()` which delegates to `simple_stt_failover()`

## 3. Parameters with Misleading Names

### `pip_leading_silence` and `pip_trailing_silence` parameters
- **What they actually do**: Control silence padding around audio feedback chimes
- **Evidence**:
  - Used at lines 1214-1215 in `converse()` function signature
  - Passed to `play_audio_feedback()` at lines 1647-1648 and 1678-1679
  - `play_audio_feedback()` passes them to `play_chime_start()` and `play_chime_end()` (lines 613-616, 644-648)
  - In `generate_chime()` (voice_mode/core.py lines 591-604), these control:
    - `leading_silence`: Adds silence BEFORE the chime plays (prevents Bluetooth cutoff)
    - `trailing_silence`: Adds silence AFTER the chime plays (prevents end cutoff)
- **Why "pip"?**: Likely refers to the chime sound itself (a "pip" or beep), but this is not obvious from the parameter names

### Recommendations for pip parameters:
- Rename to `chime_leading_silence` and `chime_trailing_silence` for clarity
- Or `audio_feedback_pre_delay` and `audio_feedback_post_delay`
- Add better documentation explaining these control silence padding around chimes

## 4. Actually Used Parameters

### `vad_aggressiveness` parameter
- **Status**: ACTIVELY USED
- **Evidence**:
  - Defined at line 1212
  - Validated at lines 1260-1263
  - Converted from string to int at lines 1229-1236
  - Passed to `record_audio_with_silence_detection()` at line 1661
  - Used in `record_audio_with_silence_detection()` at line 776 to initialize WebRTC VAD
  - Controls the Voice Activity Detection sensitivity (0-3, where 3 is most aggressive)

### Other actively used parameters:
- `message`: The text to speak
- `wait_for_response`: Whether to listen for a response
- `listen_duration`: How long to listen
- `min_listen_duration`: Minimum time before silence detection can stop
- `transport`: Communication method (auto/local/livekit)
- `room_name`: LiveKit room name
- `timeout`: LiveKit timeout (though it uses `listen_duration` instead at line 1512)
- `voice`: TTS voice selection
- `tts_provider`: TTS provider selection
- `tts_model`: TTS model selection
- `tts_instructions`: Instructions for TTS (only works with gpt-4o-mini-tts)
- `audio_feedback`: Whether to play chimes
- `audio_format`: Audio format for TTS
- `disable_silence_detection`: Disable VAD-based silence detection
- `speed`: TTS playback speed
- `skip_tts`: Skip TTS entirely (for faster testing)

## 5. Recommendations

### High Priority (Remove unused code):
1. **Remove `audio_feedback_style` parameter** from `converse()` - it does nothing
2. **Remove the entire `_speech_to_text_internal()` function** (lines 332-572) - 240 lines of dead code
3. **Remove unused parameters from `play_audio_feedback()`**: `style`, `feedback_type`, `voice`, `model`

### Medium Priority (Improve naming):
1. **Rename pip parameters** to be more descriptive:
   - `pip_leading_silence` → `chime_pre_delay` or `audio_feedback_leading_silence`
   - `pip_trailing_silence` → `chime_post_delay` or `audio_feedback_trailing_silence`

### Low Priority (Documentation):
1. **Add clearer documentation** for the chime delay parameters explaining they control silence padding to prevent Bluetooth audio cutoff
2. **Document that `timeout` parameter** is only used for LiveKit transport, not local

## Impact Analysis

Removing these unused parameters and dead code would:
- Reduce the tool description size by approximately 500+ characters
- Remove 240+ lines of dead code
- Make the API clearer and less confusing
- Reduce maintenance burden

The `audio_feedback_style` parameter is particularly confusing because it suggests you can control the style of feedback (whisper vs shout), but it actually does nothing at all.