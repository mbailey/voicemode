# Exchange Logging Improvements

## Overview

Enhance the exchange JSONL logs to capture all relevant data for complete conversation reconstruction and analysis.

## Current State

The exchanges log (`~/.voicemode/logs/exchanges_YYYY-MM-DD.jsonl`) currently captures:
- ✅ Timestamp
- ✅ Conversation ID
- ✅ Type (STT/TTS)
- ✅ Full text
- ✅ Project path
- ✅ Audio file (TTS only)
- ✅ Provider and model
- ✅ Timing metrics (for TTS)
- ✅ Audio format (for STT)

## Missing Data

### High Priority
1. **STT Audio Filename** - Currently saves audio but doesn't link it in JSONL
2. **Voice Name** - Which TTS voice was used (nova, alloy, etc.)
3. **Transport Type** - local or livekit
4. **Silence Detection Settings** - If VAD was enabled and its parameters

### Medium Priority
5. **Timing Metrics Attribution** - Split timing between STT and TTS entries
   - STT should have: record time, STT processing time
   - TTS should have: TTFA, generation time, playback time
   - Remove total time from individual entries
6. **Error/Retry Information** - If request failed and was retried
7. **User/Session Info** - Optional user identifier if available
8. **Temperature/Model Settings** - For providers that support these
9. **Audio Duration** - Length of audio files

### Low Priority
9. **Cost Estimation** - Based on provider and usage
10. **Quality Metrics** - Audio quality indicators if available

## Implementation Details

### STT Audio File Investigation ✓
- STT audio files ARE being saved in `conversation.py` around line 506
- File naming format: `timestamp_conversationID_stt.extension` (e.g., `20250712_134742_909_pr6r6s_stt.wav`)
- The `save_debug_file()` function returns the filepath
- **Gap identified**: The audio filepath is not passed to the conversation logger

### Voice Parameter Investigation
- [ ] Check if voice parameter is available in logging context

## Implementation Tasks

- [x] ~~Investigate current STT audio file naming and saving~~ - Files are saved with conversation ID
- [x] ~~Check if voice parameter is available in logging context~~ - Already available and being logged
- [x] ~~Add STT audio filename to exchange logs~~ - Fixed undefined audio_path issue
- [x] ~~Include voice parameter in TTS metadata~~ - Already included
- [x] ~~Add transport type to all exchanges~~ - Added to both STT and TTS
- [x] ~~Log silence detection configuration~~ - Added to STT metadata
- [x] ~~Create schema documentation for exchange format~~ - Updated docs/specs/conversation-logging-jsonl.md for v2
- [x] ~~Split timing metrics between STT and TTS~~ - Each entry now has its relevant timings only
- [ ] Update conversation browser to support new fields
- [ ] Review all code that reads exchange logs
- [x] ~~Implement backward-compatible format (keep version 1)~~ - Updated to version 2, None fields are filtered
- [ ] Create migration script with:
  - User confirmation before changes
  - Backup of original files (e.g., exchanges_YYYY-MM-DD.jsonl.v1.backup)
  - Progress reporting
  - Validation of migrated data

## Benefits

- Complete conversation reconstruction capability
- Better debugging with full audio linkage
- Enhanced analytics possibilities
- Support for conversation export/import
- Foundation for advanced features (voice cloning detection, quality analysis)

## Example Enhanced Exchange Records

### STT Entry
```json
{
  "version": 2,
  "timestamp": "2025-07-12T13:47:42.909326+10:00",
  "conversation_id": "conv_20250712_114301_pr6r6s",
  "type": "stt",
  "text": "Hello, how are you?",
  "project_path": "/home/m/Code/github.com/mbailey/voicemode",
  "audio_file": "20250712_134742_909_pr6r6s_stt.wav",  // IMPLEMENTED
  "metadata": {
    "voice_mode_version": "2.12.0",
    "model": "whisper-1",
    "provider": "openai",
    "audio_format": "mp3",
    "transport": "local",  // IMPLEMENTED
    "timing": "record 3.2s, stt 1.4s",  // IMPLEMENTED - STT timings only
    "silence_detection": {  // IMPLEMENTED
      "enabled": true,
      "vad_aggressiveness": 2,
      "silence_threshold_ms": 1000
    }
  }
}
```

### TTS Entry
```json
{
  "version": 2,
  "timestamp": "2025-07-12T13:47:45.123456+10:00",
  "conversation_id": "conv_20250712_114301_pr6r6s",
  "type": "tts",
  "text": "I'm doing well, thank you! How can I help you today?",
  "project_path": "/home/m/Code/github.com/mbailey/voicemode",
  "audio_file": "20250712_134745_123_pr6r6s_tts.mp3",
  "metadata": {
    "voice_mode_version": "2.12.0",
    "model": "tts-1",
    "voice": "alloy",  // Already logged
    "provider": "openai",
    "audio_format": "pcm",
    "transport": "local",  // IMPLEMENTED
    "timing": "ttfa 1.2s, gen 2.3s, play 5.6s"  // IMPLEMENTED - TTS timings only
  }
}
```