---
name: converse
description: Start an ongoing voice conversation
argument-hint: "[voice] [message]"
---

# /voicemode:converse

Start an ongoing voice conversation with the user using the `voicemode:converse` MCP tool.

## Implementation

Call the `voicemode:converse` MCP tool. Argument handling:

- `$1` — optional voice name (e.g. `af_river`, `samantha`, `nova`). If non-empty, pass it as the `voice` parameter to the tool. If empty, omit `voice` so the tool uses its default.
- `$2` — optional initial message. If non-empty, use it as the message to speak. If empty, let the tool / Claude choose an appropriate opener.
- To discover voices, read the `voice://voices` MCP resource; to speak in character, first read the persona at `~/.voicemode/voices/<voice>/README.md` (index: `~/.voicemode/voices/PERSONAS.md`).

All other parameters have sensible defaults.

**Multi-agent turn-taking:** in a session where more than one agent shares the voice channel, pass `hold_conch=true` when your *next* converse call will continue the thread (you're asking a question you'll answer, or speaking across several turns). It keeps the floor so other agents wait instead of cutting in at the turn boundary; the default `false` releases it after the exchange.

### Examples

- `/voicemode:converse` — no args, default voice, Claude chooses opener
- `/voicemode:converse af_river` — use voice `af_river`, Claude chooses opener
- `/voicemode:converse af_river "let's plan the day"` — use voice `af_river`, open with the given message

If `$1` is provided but doesn't look like a known voice name (e.g. it contains spaces or punctuation that voices don't have), assume the user meant it as a message and pass it as the message instead — don't fail silently on a typo.

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
