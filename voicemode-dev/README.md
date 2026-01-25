# voicemode.dev

Cloudflare Worker for voicemode.dev - MCP server with WebSocket gateway for Claude.ai mobile voice interaction.

## Architecture

```
┌─────────────┐     MCP/HTTP      ┌──────────────────┐     WebSocket      ┌─────────────────┐
│  Claude.ai  │ ─────────────────▶│  voicemode.dev   │◀──────────────────▶│ VoiceMode iOS   │
│  (cloud)    │                   │  Cloudflare      │                    │ App             │
└─────────────┘                   │  Worker + DO     │                    └─────────────────┘
                                  └──────────────────┘
```

## Features

- **WebSocket Gateway**: Durable Objects for per-user WebSocket connection state
- **JWT Authentication**: Auth0 JWT validation with JWKS support
- **Message Protocol**: Typed message protocol for client-server communication
- **Heartbeat/Keepalive**: Server-initiated heartbeat with stale connection detection
- **Session Resumption**: Reconnection support with message queueing
- **MCP Server**: Streamable HTTP MCP server (coming soon)

## Development

### Prerequisites

- Node.js 18+
- Wrangler CLI (installed via npm)

### Setup

```bash
npm install
```

### Run locally

```bash
npm run dev
```

This starts a local development server at `http://localhost:8787`.

### Run tests

```bash
# Unit tests (no server required)
npm test

# Integration tests (requires dev server running)
npm run test:ws

# Manual testing with wscat
npx wscat -c "ws://localhost:8787/ws?user=test"
```

See [docs/TESTING.md](docs/TESTING.md) for comprehensive testing documentation.

### Type checking

```bash
npm run typecheck
```

### Deploy

```bash
npm run deploy
```

## API Endpoints

### Health Check

```
GET /health
```

Returns service status and feature flags.

### WebSocket Gateway

```
wss://voicemode.dev/ws?token=<jwt>&user=<userId>
```

Connect with WebSocket for real-time communication:
- `token` - JWT token for authentication (required in production)
- `user` - User identifier (optional, for tracking in dev mode)

#### Message Types

**Client → Server:**
- `ready` - Announce client device info and capabilities
- `transcription` - Send transcribed speech text
- `heartbeat` - Keep connection alive, server responds with `heartbeat_ack`
- `resume` - Reconnect using previous session token
- `auth` - Authenticate with JWT after connection

**Server → Client:**
- `connected` - Welcome message with session token and auth status
- `ack` - Acknowledge client message (status: ok/error)
- `heartbeat` - Server-initiated keepalive (30s interval)
- `heartbeat_ack` - Response to client heartbeat
- `session_resumed` - Successful session resumption
- `speak` - Command to speak text (for MCP integration)
- `listen` - Command to start listening
- `stop` - Command to stop speak/listen
- `error` - Error response with code and message

See [docs/TESTING.md](docs/TESTING.md) for full message protocol reference.

## Project Structure

```
voicemode-dev/
├── src/
│   ├── index.ts              # Main worker entry point
│   ├── auth/
│   │   ├── jwt.ts            # JWT validation with Auth0 JWKS
│   │   └── jwt.test.ts       # JWT unit tests
│   ├── websocket/
│   │   ├── protocol.ts       # Message protocol types and validation
│   │   └── protocol.test.ts  # Protocol unit tests
│   └── durable-objects/
│       └── websocket-gateway.ts   # WebSocket Durable Object
├── scripts/
│   └── test-websocket.mjs    # WebSocket integration test script
├── docs/
│   └── TESTING.md            # Testing guide
├── wrangler.toml             # Cloudflare configuration
├── package.json
├── tsconfig.json
└── README.md
```

## Feature Status

| Feature | Status | Task |
|---------|--------|------|
| Durable Objects setup | ✅ Complete | ws-001 |
| JWT Authentication | ✅ Complete | ws-002 |
| Message Protocol | ✅ Complete | ws-003 |
| Heartbeat/Keepalive | ✅ Complete | ws-004 |
| Session Resumption | ✅ Complete | ws-005 |
| Integration Tests | ✅ Complete | ws-006 |

## Environment Variables

Set via `wrangler secret` or Cloudflare dashboard:

| Variable | Description |
|----------|-------------|
| `AUTH0_DOMAIN` | Auth0 tenant domain |
| `AUTH0_CLIENT_ID` | Auth0 application client ID |
| `AUTH0_CLIENT_SECRET` | Auth0 client secret (for token validation) |
| `AUTH0_AUDIENCE` | Auth0 API identifier |

## License

MIT
