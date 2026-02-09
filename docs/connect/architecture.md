# VoiceMode Connect Architecture

How agents and clients connect through voicemode.dev.

## Overview

```
┌─────────────────┐              ┌─────────────────┐
│   AI Agent      │              │     Client      │
│  (Claude Code)  │              │  (iOS/Web App)  │
└────────┬────────┘              └────────┬────────┘
         │ MCP                            │ WebSocket
         │                                │
         └────────────┬───────────────────┘
                      │
              ┌───────┴───────┐
              │ voicemode.dev │
              │   Platform    │
              └───────────────┘
```

## Components

### Agents

AI assistants that want to have voice conversations. They connect via MCP (Model Context Protocol) and use tools like `status` and `converse`.

- Connect using `mcp-remote` to `https://voicemode.dev/mcp`
- Authenticate via OAuth
- Call MCP tools to interact with the platform

### Clients

Devices that handle the actual voice I/O (microphone/speaker). They connect via WebSocket.

- iOS app - native mobile client
- Web app - browser-based dashboard at voicemode.dev
- Future: macOS menu bar app, browser extension

### Local MCP Server

The local VoiceMode MCP server can also connect to voicemode.dev to monitor remote devices. This provides device visibility without requiring the remote MCP server.

Two connection methods are available:

- **Standalone standby process** (`voicemode connect standby`) - a long-running CLI process that listens for wake signals and starts agents
- **In-process WebSocket client** - a background connection within the MCP server that tracks connected devices (opt-in via `VOICEMODE_CONNECT_AUTO=true`)

The in-process client is disabled by default. VoiceMode does not connect to external services without explicit user opt-in.

### Platform

The voicemode.dev backend routes messages between agents and clients.

- User accounts link agents and clients
- WebSocket connections for real-time voice delivery
- OAuth authentication via Auth0

## Connection Flow

1. **Agent connects**: Claude Code adds the MCP server and authenticates
2. **Client connects**: User opens iOS/web app and signs in with same account
3. **Agent sends message**: Uses `converse` tool with text to speak
4. **Platform routes**: Message delivered to connected client(s)
5. **Client speaks**: TTS plays on device, STT captures response
6. **Response returns**: User's voice response sent back to agent

## Authentication

Both agents and clients authenticate against the same voicemode.dev account:

- **Agents**: OAuth flow triggered when MCP tools are first used
- **Clients**: Standard login flow in app/web

The platform matches agents to clients by user account.

## Protocol Notes

- MCP transport: stdio to mcp-remote, which handles HTTP/SSE
- WebSocket: persistent connection for clients
- Voice data: handled by clients, not transmitted through platform (clients use their own TTS/STT)

## See Also

- [MCP Protocol](https://modelcontextprotocol.io/) - Model Context Protocol specification
- [Auth0](https://auth0.com/) - Authentication provider
