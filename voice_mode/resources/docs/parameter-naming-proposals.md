# Parameter Naming Proposals

This document proposes better parameter names for the voicemode converse tool to improve clarity and reduce the need for extensive documentation.

## Context

This analysis was performed **without access to the codebase** - purely from the perspective of someone reading the tool description and trying to understand what each parameter does. This represents the experience of:
- An LLM trying to use the tool with minimal context
- A new user reading the documentation
- A developer integrating the tool

The questions and confusions noted here reflect **genuine user experience** when encountering unclear parameter names.

## Key Findings

**Most confusing parameters (can't understand without code inspection):**
1. `pip_leading_silence` / `pip_trailing_silence` - What is "pip"?
2. `audio_feedback_style` ("whisper" vs "shout") - What do these values mean?
3. `audio_feedback` - What does this control?
4. `vad_aggressiveness` - Technical jargon, unclear scale meaning

## Naming Principles

1. **Self-documenting** - Name should hint at purpose
2. **Consistent prefixes** - Group related parameters with common prefixes
3. **Avoid jargon** - Use plain language over technical terms
4. **Explicit over implicit** - Clear beats clever

## Core Parameters

### ✅ Good as-is
- `message` - Clear
- `wait_for_response` - Self-explanatory
- `voice` - Clear
- `speed` - Simple and obvious

### ⚠️ Could improve
- `listen_duration` → Consider: `max_listen_seconds` or `listen_timeout_seconds`
  - More explicit that it's a maximum/timeout

- `min_listen_duration` → Consider: `min_listen_seconds` or `min_recording_time`
  - Consistency with duration vs seconds
  - "recording_time" might be clearer

## Transport Parameters

### ✅ Good as-is
- `transport` - Clear enough with enum values
- `room_name` - Clear for LiveKit context

### ⚠️ Could improve
- `timeout` (DEPRECATED) - Already being replaced by `listen_duration` ✓

## TTS Parameters

### ✅ Good as-is
- `tts_provider` - Clear (openai, kokoro)
- `tts_model` - Clear
- `tts_instructions` - Clear purpose

## Audio Format Parameters

### ✅ Good as-is
- `audio_format` - Clear

### ❌ Confusing - Need better names

**Current:** `skip_tts`
- **Issue:** Negative naming ("skip") requires mental inversion
- **Proposed:** `text_only_mode` or `enable_tts`
  - `text_only_mode=True` - Clearer intent
  - `enable_tts=False` - More explicit
- **Recommendation:** `text_only_mode` (positive framing)

## Audio Feedback Parameters

### ❌ Very confusing - Need better names

**Current:** `audio_feedback`
- **Issue:** What is "audio feedback"? Not clear what this enables/disables
- **Question:** What does this actually do?
  - Confirmation beeps?
  - Echo/monitoring?
  - Status sounds?
- **Need:** Description of actual behavior before proposing name

**Current:** `audio_feedback_style` with values "whisper" | "shout"
- **Issue:** Completely unclear what whisper vs shout means
  - Volume level?
  - Tone/pitch?
  - Different sound effects?
- **Question:** What's the actual difference?
- **Proposed alternatives (once we know what it does):**
  - If it's volume: `feedback_volume` ("quiet" | "loud")
  - If it's intensity: `feedback_intensity` ("subtle" | "prominent")
  - If it's different sounds: `feedback_sound_type` ("soft" | "sharp")

## Silence Detection Parameters

### ⚠️ Technical jargon - Needs improvement

**Current:** `disable_silence_detection`
- **Issue:** Negative naming
- **Proposed:** `auto_stop_on_silence` (default: true)
  - Positive framing
  - Clearer what it does
- **Alternative:** `silence_detection_enabled` (default: true)

**Current:** `vad_aggressiveness` (0-3)
- **Issue:** "VAD" (Voice Activity Detection) is technical jargon
- **Issue:** "aggressiveness" is vague - aggressive at what?
- **Proposed:** `silence_detection_sensitivity` (0-3)
  - 0 = "lenient" or "permissive"
  - 3 = "strict" or "sensitive"
- **Alternative:** `noise_filtering_level` (0-3)
  - 0 = minimal filtering
  - 3 = maximum filtering
- **Better with enum:** `silence_detection_mode`
  - "very_permissive" (0)
  - "permissive" (1)
  - "balanced" (2)
  - "strict" (3)
- **Recommendation:** `silence_detection_sensitivity` with numeric 0-3, document as "0=permissive, 3=strict"

## Audio Chime Timing Parameters

### ❌ Very confusing - Need better names

**Current:** `pip_leading_silence`
- **Issue:** What is "pip"? (Likely means the chime/beep sound)
- **Issue:** "leading silence" is unclear
- **Proposed:** `chime_delay_before` or `pre_chime_silence`
  - Makes it clear it's about the chime timing
  - "before" is clearer than "leading"
- **Alternative:** `chime_start_delay`
- **Recommendation:** `chime_delay_before_seconds`

**Current:** `pip_trailing_silence`
- **Issue:** Same "pip" confusion
- **Issue:** "trailing silence" is unclear
- **Proposed:** `chime_delay_after` or `post_chime_silence`
  - Parallel with leading/trailing
  - Clearer purpose
- **Alternative:** `chime_end_padding`
- **Recommendation:** `chime_delay_after_seconds`

**Alternative approach - group with prefix:**
- `chime_padding_before`
- `chime_padding_after`

## Summary of Key Changes

### High Priority (Very Confusing)

| Current | Proposed | Reason |
|---------|----------|--------|
| `pip_leading_silence` | `chime_delay_before_seconds` | "pip" is unclear, better describes purpose |
| `pip_trailing_silence` | `chime_delay_after_seconds` | Parallel with above |
| `audio_feedback_style` | **[NEED CLARIFICATION]** | Don't know what whisper/shout means |
| `vad_aggressiveness` | `silence_detection_sensitivity` | Avoid jargon, clearer scale meaning |

### Medium Priority (Could Be Clearer)

| Current | Proposed | Reason |
|---------|----------|--------|
| `skip_tts` | `text_only_mode` | Positive framing, clearer intent |
| `disable_silence_detection` | `auto_stop_on_silence` | Positive framing |
| `min_listen_duration` | `min_recording_seconds` | More explicit |

### Low Priority (Minor Improvements)

| Current | Proposed | Reason |
|---------|----------|--------|
| `listen_duration` | `listen_timeout_seconds` | More explicit about max/timeout |

## Parameter Grouping

Consider using consistent prefixes for related parameters:

### Chime-related
- `chime_delay_before_seconds`
- `chime_delay_after_seconds`

### Silence detection
- `silence_detection_enabled` (or `auto_stop_on_silence`)
- `silence_detection_sensitivity`

### TTS-related
- `tts_provider`
- `tts_model`
- `tts_instructions`
- `text_only_mode` (or keep as `skip_tts`)

### Audio-related
- `audio_format`
- `audio_feedback` → **[NEED CLARIFICATION]**
- `audio_feedback_style` → **[NEED CLARIFICATION]**

### Timing-related
- `listen_timeout_seconds`
- `min_recording_seconds`

## Questions for Clarification

**These questions MUST be answered by examining the codebase:**

### CRITICAL: audio_feedback and audio_feedback_style

**Current state:** Completely unclear from external perspective

**Questions:**
1. **audio_feedback**: What does this actually enable/disable?
   - Beeps/chimes during conversation?
   - Recording monitoring?
   - Status sounds?
   - When is it played (start, end, during recording)?

2. **audio_feedback_style "whisper" vs "shout"**: What's the actual difference?
   - Volume levels (quiet vs loud)?
   - Different sound effects (soft beep vs sharp beep)?
   - Pitch/tone changes (low tone vs high tone)?
   - Duration (short vs long)?

**Need from codebase:**
- Find where these parameters are used
- Listen to/describe the actual audio played
- Understand the use case for each option
- Then propose better names based on actual behavior

### CRITICAL: pip (chime timing parameters)

**Current state:** Term is opaque

**Questions:**
1. What does "pip" mean?
   - Industry standard term (BBC pips, etc.)?
   - Legacy naming from another system?
   - Just means "beep" or "chime"?
   - Is it tied to a specific audio file or implementation?

2. What is the actual use case?
   - Why would someone need leading/trailing silence?
   - What problems does it solve?
   - When should users adjust these values?

**Need from codebase:**
- Find origin of "pip" terminology
- Understand why these timings are configurable
- Determine if "chime" is accurate or if there's a better term

### MODERATE: vad_aggressiveness scale

**Current state:** Technical jargon, unclear what each level does

**Questions:**
1. What is the actual behavior at each level (0-3)?
   - What makes level 3 "more aggressive" than level 0?
   - Is it threshold-based? Algorithm-based?
   - What are the practical differences in user experience?

2. Are the levels from an external library (WebRTC VAD)?
   - If so, are we stuck with their scale?
   - Can we add a mapping layer?

**Need from codebase:**
- Find VAD implementation
- Document what each level actually does
- Test each level to describe user-facing behavior

## Implementation Strategy

### Phase 1: Critical changes (breaking changes)
- Rename most confusing parameters
- Provide deprecation warnings for old names
- Update all documentation

### Phase 2: Support both old and new names
- Keep old names as aliases
- Log deprecation warnings
- Give users time to migrate

### Phase 3: Remove old names
- After suitable deprecation period
- Major version bump
- Clear migration guide

## Backward Compatibility

To avoid breaking existing code, consider:
- Accept both old and new parameter names
- Internally map old → new
- Eventually deprecate old names
- Provide clear migration guide

---

## TODO: When Re-analyzing With Codebase Access

**Step 1: Search for parameter usage**
```bash
# Find where these confusing parameters are used
grep -r "audio_feedback" .
grep -r "pip_leading_silence" .
grep -r "pip_trailing_silence" .
grep -r "vad_aggressiveness" .
```

**Step 2: Understand audio_feedback**
- Find the audio files or sound generation code
- Determine what "whisper" vs "shout" actually means
- Document the user-facing behavior
- Test both modes to describe the difference
- Propose accurate names based on actual behavior

**Step 3: Understand pip terminology**
- Find the origin/source of the term "pip"
- Check if it's from an external library or standard
- Document why leading/trailing silence is needed
- Propose better names (likely "chime_delay_before/after")

**Step 4: Understand VAD implementation**
- Identify the VAD library being used
- Document what each aggressiveness level (0-3) does
- Test each level and describe practical differences
- Decide if we can add a cleaner abstraction layer

**Step 5: Update this document**
- Add findings from codebase analysis
- Finalize naming recommendations with confidence
- Create migration guide for parameter renames
- Update resource files with better parameter documentation

**Step 6: Verify with context optimization**
- Calculate actual token savings after implementing minimal description
- Confirm LLM can successfully use tool with minimal description + resources
- Measure how often resources need to be fetched vs auto-completion working
