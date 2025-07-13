# Conversation Logging JSONL Specification

## Overview

A conversation-focused logging system for voice-mode that tracks all utterances (STT and TTS) in a structured, append-only format using JSON Lines (JSONL). This enables real-time conversation tracking, efficient processing, and seamless integration with the conversation browser.

## Version History

- **Version 1**: Initial schema with basic fields
- **Version 2**: Added transport type and silence detection configuration (backward compatible)

## File Format

### Structure
- **Format**: JSON Lines (JSONL) - one JSON object per line
- **Encoding**: UTF-8
- **File naming**: `exchanges_YYYY-MM-DD.jsonl` (daily rotation)
- **Location**: `~/.voicemode/logs/` directory

### Schema

Each line represents a single utterance with the following structure:

```json
{
  "version": 2,
  "timestamp": "2024-06-28T10:30:45.123Z",
  "conversation_id": "conv_20240628_103045_abc123",
  "type": "stt|tts",
  "project_path": "/home/user/projects/myproject",
  "text": "The transcribed or synthesized text",
  "audio_file": "path/to/audio/file.mp3",
  "duration_ms": 3450,
  "metadata": {
    "voice_mode_version": "0.7.12",
    "model": "whisper-1|tts-1",
    "voice": "alloy",
    "timing": "ttfa 1.2s, tts_gen 2.3s, total 5.6s",
    "provider": "openai|kokoro|whisper",
    "audio_format": "mp3|pcm|wav",
    "transport": "local",
    "silence_detection": {
      "enabled": true,
      "vad_aggressiveness": 2,
      "silence_threshold_ms": 1000
    }
  }
}
```

### Field Definitions

#### Required Fields
- **version**: Schema version number (currently 2)
- **timestamp**: ISO 8601 timestamp of when the utterance started
- **conversation_id**: Unique identifier for the conversation
- **type**: Either "stt" (speech-to-text) or "tts" (text-to-speech)
- **text**: The actual text content (transcribed for STT, synthesized for TTS)

#### Optional Fields
- **project_path**: Current working directory when utterance occurred (may be null)
- **audio_file**: Relative path to the saved audio file (null if audio not saved)
- **duration_ms**: Duration of the audio in milliseconds (null if not available)
- **metadata**: Additional context-specific information

#### Metadata Fields (all optional)
- **voice_mode_version**: Version of voice-mode that generated this utterance (e.g., "0.7.12")
- **model**: The AI model used (e.g., "whisper-1", "tts-1", "gpt-4o-mini-tts")
- **voice**: TTS voice name (e.g., "alloy", "nova", "af_sky")
- **timing**: Performance metrics string
- **provider**: Service provider (e.g., "openai", "kokoro", "whisper")
- **audio_format**: Audio file format (e.g., "mp3", "pcm", "wav")
- **language**: Language code if detected/specified (e.g., "en", "es", "fr")
- **emotion**: Emotional tone if using emotional TTS
- **error**: Error message if utterance failed
- **transport**: Transport method used ("local", "livekit", "speak-only") - v2+
- **silence_detection**: Object with VAD settings (STT only) - v2+
  - **enabled**: Whether silence detection was active
  - **vad_aggressiveness**: VAD aggressiveness level (0-3)
  - **silence_threshold_ms**: Silence threshold in milliseconds

## Conversation ID Generation

### Format
`conv_YYYYMMDD_HHMMSS_XXXXXX`

Where:
- `YYYYMMDD_HHMMSS`: Timestamp when conversation started
- `XXXXXX`: Random 6-character alphanumeric suffix

### Conversation Continuity Rules

1. **New conversation** starts when:
   - First utterance after voice-mode starts
   - More than 5 minutes since last utterance
   - Project path changes

2. **Continue existing conversation** when:
   - Less than 5 minutes since last utterance
   - Same project path
   - After voice-mode restart (check last line of current day's log)

### Startup Logic

```python
def get_conversation_id():
    from datetime import datetime, timedelta
    
    # Check today's log file first
    today = datetime.now().date()
    log_file = f"exchanges_{today.strftime('%Y-%m-%d')}.jsonl"
    
    # Try today's log
    last_entry = None
    if log_file.exists() and log_file.stat().st_size > 0:
        last_entry = read_last_line(log_file)
    else:
        # Check yesterday's log for midnight rollover case
        yesterday = today - timedelta(days=1)
        yesterday_log = f"exchanges_{yesterday.strftime('%Y-%m-%d')}.jsonl"
        if yesterday_log.exists():
            last_entry = read_last_line(yesterday_log)
    
    if last_entry:
        last_timestamp = parse_timestamp(last_entry['timestamp'])
        
        # Check if within conversation window
        if (datetime.now() - last_timestamp).seconds < 300:  # 5 minutes
            if last_entry['project_path'] == current_project_path:
                return last_entry['conversation_id']
    
    # Generate new conversation ID
    return generate_new_conversation_id()
```

## Implementation Benefits

1. **Streaming**: Append-only format allows real-time writing without parsing
2. **Efficiency**: No need to load/parse entire file for updates
3. **Reliability**: Crash-resistant - partial writes don't corrupt existing data
4. **Scalability**: Daily rotation prevents unbounded file growth
5. **Compatibility**: Standard format works with many tools (jq, pandas, etc.)
6. **Stateless**: Log file itself maintains conversation state

## Integration Points

### Voice Mode
- Write utterances as they occur
- Read last entry on startup for conversation continuity
- No need for separate state management

### Conversation Browser
- Tail JSONL files for live updates
- Group utterances by conversation_id
- Filter by date, project, or conversation

### Future MCP Tools
- `update_conversation_title`: Add custom titles to conversations
- `tag_conversation`: Add tags for categorization
- `export_conversation`: Export specific conversations

## Migration Path

1. Continue writing current transcription files (backward compatibility)
2. Start writing JSONL in parallel
3. Update conversation browser to prefer JSONL when available
4. Phase out individual transcription files in future version

## Example Usage

### Writing an utterance
```python
def log_utterance(utterance_data):
    log_file = get_today_log_file()
    with open(log_file, 'a') as f:
        f.write(json.dumps(utterance_data) + '\n')
```

### Reading conversations
```python
def get_conversations_for_date(date):
    log_file = f"exchanges_{date}.jsonl"
    conversations = defaultdict(list)
    
    with open(log_file, 'r') as f:
        for line in f:
            entry = json.loads(line)
            conversations[entry['conversation_id']].append(entry)
    
    return conversations
```

### Real-time monitoring
```python
def tail_conversations(log_file):
    """Generator that yields new utterances as they're logged"""
    with open(log_file, 'r') as f:
        # Go to end of file
        f.seek(0, 2)
        
        while True:
            line = f.readline()
            if line:
                yield json.loads(line)
            else:
                time.sleep(0.1)
```

## Open Questions

1. **Emotional TTS**: Should we include emotional parameters in metadata?
   - Proposed: Add `emotion` field when using gpt-4o-mini-tts model

2. **Multi-language**: How to handle conversations in multiple languages?
   - Proposed: Add `language` field to each utterance

3. **Compression**: Should we compress older log files automatically?
   - Proposed: Gzip files older than 7 days

4. **Token counts**: Include LLM token usage for cost tracking?
   - Proposed: Add `tokens` field in metadata for LLM interactions

5. **Privacy**: Should we support log encryption or redaction?
   - Proposed: Configuration option for PII redaction

## Relationship to Existing Event Logging

This specification complements the existing unified event logging system:
- **Event logs**: Low-level system events for debugging and performance
- **Conversation logs**: High-level utterance tracking for browsing and analysis

Both systems can coexist, with conversation logs focusing on user-facing content and event logs focusing on system behavior.