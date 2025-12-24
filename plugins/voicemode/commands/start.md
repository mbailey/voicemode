---
description: Start VoiceMode voice services
argument-hint: [service]
---

# /voicemode:start

Start VoiceMode services.

## Usage

```
/voicemode:start [service]
```

## Description

Starts VoiceMode services. Without arguments, starts both Whisper and Kokoro services.

## Examples

```
/voicemode:start          # Start all services
/voicemode:start whisper  # Start Whisper only
/voicemode:start kokoro   # Start Kokoro only
```

## Implementation

Use the `mcp__voicemode__service` tool:

```json
{
  "service_name": "whisper",
  "action": "start"
}
```

To start all services:

```bash
# Start Whisper (STT)
mcp__voicemode__service service_name=whisper action=start

# Start Kokoro (TTS)
mcp__voicemode__service service_name=kokoro action=start
```

## Notes

- Services may take a few seconds to start and load models
- Check status with `/voicemode:status` after starting
