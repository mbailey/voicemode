---
name: status
description: Check the status of VoiceMode services
---

# /voicemode:status

Check VoiceMode service status using the `mcp__plugin_voicemode_voicemode__service` MCP tool.

Check each service:
- `service_name: "whisper"`, `action: "status"` — Speech-to-text
- `service_name: "kokoro"`, `action: "status"` — Text-to-speech
- `service_name: "livekit"`, `action: "status"` — LiveKit (optional)

Report running status, endpoint availability, and any issues.
