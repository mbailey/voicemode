---
description: Stop VoiceMode voice services
argument-hint: [service]
---

# /voicemode:stop

Stop VoiceMode services.

## Usage

```
/voicemode:stop [service]
```

## Description

Stops VoiceMode services. Without arguments, stops both Whisper and Kokoro services.

## Examples

```
/voicemode:stop          # Stop all services
/voicemode:stop whisper  # Stop Whisper only
/voicemode:stop kokoro   # Stop Kokoro only
```

## Implementation

Use the `mcp__voicemode__service` tool:

```json
{
  "service_name": "whisper",
  "action": "stop"
}
```

To stop all services:

```bash
# Stop Whisper (STT)
mcp__voicemode__service service_name=whisper action=stop

# Stop Kokoro (TTS)
mcp__voicemode__service service_name=kokoro action=stop
```

## Notes

- Stopping services frees up memory and GPU resources
- Services can be restarted with `/voicemode:start`
