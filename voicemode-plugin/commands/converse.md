---
description: Start a voice conversation with Claude Code
argument-hint: [message]
---

# /voicemode:converse

Start a voice conversation with Claude Code.

## Usage

```
/voicemode:converse [message]
```

## Description

Initiates a voice conversation using local speech-to-text (Whisper) and text-to-speech (Kokoro) services. Claude speaks the message and listens for your response.

## Examples

```
/voicemode:converse Hello, how can I help you today?
/voicemode:converse
```

## Implementation

Use the `mcp__voicemode__converse` tool:

```json
{
  "message": "Hello, how can I help you today?",
  "wait_for_response": true
}
```

## Parameters

- **message**: The text for Claude to speak
- **wait_for_response**: Whether to listen for a response (default: true)
- **voice**: TTS voice name (optional, auto-selected)
- **listen_duration_max**: Maximum recording time in seconds (default: 120)
- **vad_aggressiveness**: Voice detection strictness 0-3 (default: 2)
