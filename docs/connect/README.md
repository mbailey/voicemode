# VoiceMode Connect

Voice conversations through the voicemode.dev cloud platform.

## What is VoiceMode Connect?

VoiceMode Connect lets AI agents (like Claude Code) have voice conversations through mobile or web clients, without requiring local STT/TTS services.

**Agents** connect via MCP to voicemode.dev and use tools like `status` and `converse`.
**Clients** (iOS app, web app) connect via WebSocket and handle the actual voice I/O.

## When to Use Connect vs Local VoiceMode

| Scenario | Recommendation |
|----------|----------------|
| Desktop with microphone | Local VoiceMode (lower latency) |
| Mobile voice interaction | VoiceMode Connect |
| No local service setup desired | VoiceMode Connect |
| Offline usage | Local VoiceMode |

You can use both - they serve different use cases.

## Quick Start

1. Add the MCP server to Claude Code ([setup guide](setup/claude-code.md))
2. Sign in when prompted (OAuth via voicemode.dev)
3. Open a client (iOS app or web dashboard)
4. Use `status` to verify connection, `converse` to talk

## Documentation

- [Architecture](architecture.md) - How agents and clients connect
- [Claude Code Setup](setup/claude-code.md) - Enable Connect for Claude Code
- [MCP Tools Reference](reference/mcp-tools.md) - Tool parameters and usage

## Open Questions

These are areas we're still figuring out as the platform matures:

- Multi-agent coordination (multiple Claude Code sessions on one account)
- Client selection when multiple devices are connected
- Message delivery confirmation and error handling

We'll update these docs as patterns emerge.
