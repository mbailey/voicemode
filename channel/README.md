# VoiceMode Channel Server

A TypeScript MCP channel server that pushes inbound voice events into a
Claude Code session. This enables users to speak to Claude via the VoiceMode
web/mobile app and have Claude respond conversationally.

## How it works

```
User speaks on phone/web -> VoiceMode gateway -> Channel server -> Claude Code
                                                                       |
User hears TTS response  <- Channel reply tool <----------------------+
```

The channel server declares the experimental `claude/channel` capability and
sends `notifications/claude/channel` notifications. Claude sees these as
`<channel source="voicemode-channel" caller="NAME">TRANSCRIPT</channel>`
messages in its session.

## Setup

```bash
# 1. Install channel server dependencies
cd channel
npm install

# 2. Authenticate with VoiceMode Connect (opens browser for Auth0 login)
voicemode connect auth login

# 3. Verify auth is working
voicemode connect auth status
```

This saves your credentials to `~/.voicemode/credentials`. The channel
server reads these to connect to the VoiceMode gateway.

## Running

The channel server is already registered in VoiceMode's `.mcp.json` -- no
manual MCP configuration needed if you installed VoiceMode as a plugin.

### Enable and start Claude Code

```bash
# VOICEMODE_CHANNEL_ENABLED=true is required (explicit opt-in)
VOICEMODE_CHANNEL_ENABLED=true claude --dangerously-load-development-channels server:voicemode-channel
```

### Make a call

Open **[app.voicemode.dev](https://app.voicemode.dev)** on your phone or
browser. Sign in with the same account, tap the call button, and speak.
Claude will respond and you'll hear TTS audio playback.

## Testing

The server starts a local HTTP endpoint on port 8787 (configurable via
`VOICEMODE_CHANNEL_PORT`) for simulating inbound voice events.

```bash
# Send a test voice event
curl -X POST http://localhost:8787/event \
  -H 'Content-Type: application/json' \
  -d '{"caller": "mike", "transcript": "Hey Claude, what time is it?", "device_id": "abc123"}'

# Health check
curl http://localhost:8787/health
```

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `VOICEMODE_CHANNEL_ENABLED` | `false` | **Required.** Must be `true` to enable. Server exits immediately otherwise. |
| `VOICEMODE_CHANNEL_PORT` | `8787` | HTTP test server port |
| `VOICEMODE_CHANNEL_DEBUG` | `false` | Enable debug logging |
| `VOICEMODE_CONNECT_WS_URL` | `wss://voicemode.dev/ws` | WebSocket gateway URL |
| `VOICEMODE_AGENT_NAME` | `voicemode` | Agent identity for gateway registration |
| `VOICEMODE_AGENT_DISPLAY_NAME` | `Claude Code` | Display name shown to users |

## Prerequisites

- Node.js 20+
- VoiceMode Connect credentials (`~/.voicemode/credentials`)
  - Run `voicemode connect login` to authenticate

## Architecture

This is a standalone MCP server (separate from the Python VoiceMode MCP
server). It runs as a subprocess of Claude Code and communicates via stdio.

- **MCP transport**: stdio (stdin/stdout JSON-RPC)
- **Channel capability**: `experimental: { 'claude/channel': {} }`
- **Reply tool**: Sends responses back through the WebSocket gateway
- **No local voice**: All STT/TTS happens on the user's device (phone/web app)

## Status

Research preview. Requires both:
1. `--dangerously-load-development-channels` flag on Claude Code
2. `VOICEMODE_CHANNEL_ENABLED=true` environment variable (explicit opt-in)
