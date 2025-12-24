---
description: Start an ongoing voice conversation
argument-hint: [message]
---

# /voicemode:converse

Start an ongoing voice conversation with the user using the `mcp__voicemode__converse` tool.

## Example

```json
{
  "message": "Hello! What would you like to work on?",
  "wait_for_response": true
}
```

All other parameters have sensible defaults - just set the message.

## Troubleshooting

If voice services aren't working, load the `voicemode` skill for troubleshooting guidance and installation instructions.
