---
description: Start an ongoing voice conversation
argument-hint: [message]
---

# /voicemode:converse

Start an ongoing voice conversation with the user using the `voicemode:converse` MCP tool.

## Implementation

Use the `voicemode:converse` tool with the user's message. All parameters have sensible defaults.

## If MCP Connection Fails

If the MCP server isn't connected or the tool isn't available:

1. **Run the install command:**
   ```
   /voicemode:install
   ```
   This installs VoiceMode CLI, FFmpeg, and local voice services.

2. **Or install manually via CLI:**
   ```bash
   uvx voice-mode-install --yes
   voicemode whisper service install
   voicemode kokoro install
   ```

3. **Check service status:**
   ```bash
   voicemode whisper service status
   voicemode kokoro status
   ```

4. **Reconnect MCP server after install:**
   Run `/mcp`, select voicemode, click "Reconnect" (or restart Claude Code)

For complete documentation, load the `voicemode` skill.
