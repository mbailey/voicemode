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
cd channel
npm install
```

## Running

### As a development channel in Claude Code

```bash
# From the voicemode repo root
claude --dangerously-load-development-channels server:voicemode-channel
```

The MCP server must be registered in `.mcp.json`:

```json
{
  "mcpServers": {
    "voicemode-channel": {
      "type": "stdio",
      "command": "npx",
      "args": ["tsx", "channel/index.ts"]
    }
  }
}
```

### Standalone

```bash
npx tsx channel/index.ts
```

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

Research preview. Requires `--dangerously-load-development-channels` flag.
