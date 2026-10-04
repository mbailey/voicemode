---
name: recovery
description: When voice is not working; the converse tool missing or dropped, permission prompts, services down, an empty transcription, misheard words, where configuration lives.
---
No converse tool: `/voicemode:install`, then `voicemode reconnect`. An empty reply after they spoke: transcribe `~/.voicemode/audio/latest-STT.wav` yourself.

# Recovery

**The tool is not in your list** (first run, or the server failed to register): `/voicemode:install` installs the CLI, FFmpeg and the local services (by hand: `uvx voice-mode-install --yes`, `voicemode service install whisper`, `voicemode service install kokoro`). Then reconnect, below.

**Voice dropped mid-session** (`-32000 Connection closed`): the MCP tools vanish, so recover from Bash, which survives. Inside tmux, one call drives the whole `/mcp` reconnect dance on your own pane:

    voicemode reconnect     # RESULT: reconnected (exit 0) · already-connected (10) · not-found (11) · timeout (12) · not-in-tmux (13)

Then run the `ToolSearch select:…` line it prints to reload the tool schema, and carry on. Not in tmux: `/mcp`, select voicemode, Reconnect; or restart Claude Code. Flags: `--pane`, `--server`, `--timeout`, `--dry-run`.

**Permission prompts** on `voicemode:converse` or `voicemode:service` in every project: add `mcp__voicemode__converse` and `mcp__voicemode__service` to `permissions.allow` in `~/.claude/settings.json` (every project), `.claude/settings.json` (the team, committed) or `.claude/settings.local.json` (you, this project). Do not allow `mcp__voicemode__*`: the install tools download and compile software and deserve their prompt.

**Services**: the `service` tool (`service("whisper", "status")`; actions status, start, stop, restart, enable, disable, logs) or `voicemode service status [whisper|kokoro|mlx_audio]`. Whisper is STT on port 2022, Kokoro TTS on 8880. A first start downloads models and takes minutes.

**The reply came back empty but the user spoke**: with audio saving on (`VOICEMODE_SAVE_AUDIO=true`, `VOICEMODE_SAVE_ALL=true` or `VOICEMODE_DEBUG=true` in `~/.voicemode/voicemode.env`) the recording is at `~/.voicemode/audio/latest-STT.wav`, and `whisper-cli ~/.voicemode/audio/latest-STT.wav` recovers it without asking them to repeat. Otherwise, ask again.

**Names and jargon misheard**: `VOICEMODE_STT_PROMPT="tmux, Tali, kubectl"` biases Whisper toward them. The rest: `voicemode://docs/troubleshooting`.

**Configuration** lives in `~/.voicemode/voicemode.env`: `voicemode config list`, `voicemode config set KEY VALUE`, `voicemode config edit`. The CLI is for install, configuration and diagnostics (`voicemode diag info`, `voicemode deps`); the MCP tools are for conversing and for the services.
