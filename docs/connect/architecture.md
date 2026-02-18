# VoiceMode Connect Architecture

How agents and clients connect through voicemode.dev.

## Overview

```
┌─────────────────┐              ┌─────────────────┐
│   AI Agent      │              │     Client      │
│  (Claude Code)  │              │  (iOS/Web App)  │
└────────┬────────┘              └────────┬────────┘
         │ CLI                           │ WebSocket
         │                               │
         └────────────┬──────────────────┘
                      │
              ┌───────┴───────┐
              │ voicemode.dev │
              │   Platform    │
              └───────────────┘
```

## Components

### Agents

AI assistants that want to have voice conversations. They use CLI commands (`voicemode connect up/down/status`) to manage the connection and interact with the platform.

- Connect using `voicemode connect up` to establish a WebSocket connection
- Authenticate via `voicemode connect login` (Auth0 OAuth)
- CLI is the common interface for both humans and agents

### Clients

Devices that handle the actual voice I/O (microphone/speaker). They connect via WebSocket.

- iOS app - native mobile client
- Web app - browser-based dashboard at voicemode.dev
- Future: macOS menu bar app, browser extension

### Local Connect Process

The `voicemode connect up` command starts a long-running process that:

- Connects to voicemode.dev via WebSocket
- Announces registered users/agents to the gateway
- Watches for user configuration changes and announces updates
- Delivers incoming messages to agent inboxes
- Requires `VOICEMODE_CONNECT_ENABLED=true` (no external connections without explicit opt-in)

### Platform

The voicemode.dev backend routes messages between agents and clients.

- User accounts link agents and clients
- WebSocket connections for real-time voice delivery
- OAuth authentication via Auth0

## Connection Flow

1. **User enables Connect**: Sets `VOICEMODE_CONNECT_ENABLED=true` in voicemode.env
2. **User logs in**: `voicemode connect login` authenticates with voicemode.dev
3. **User registers agents**: `voicemode connect user add cora --name "Cora 7"`
4. **Connect starts**: `voicemode connect up` establishes WebSocket connection
5. **Client connects**: User opens iOS/web app and signs in with same account
6. **Messages flow**: Platform routes messages between agents and clients

## Authentication

Both agents and clients authenticate against the same voicemode.dev account:

- **Agents**: OAuth flow via `voicemode connect login`
- **Clients**: Standard login flow in app/web

The platform matches agents to clients by user account.

## Protocol Notes

- WebSocket: persistent connection for both agents and clients
- Voice data: handled by clients, not transmitted through platform (clients use their own TTS/STT)
- CLI tools: agents use `voicemode connect` CLI commands, guided by the voicemode-connect skill

## See Also

- [MCP Protocol](https://modelcontextprotocol.io/) - Model Context Protocol specification
- [Auth0](https://auth0.com/) - Authentication provider
