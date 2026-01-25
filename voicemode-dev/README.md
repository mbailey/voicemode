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
- **MCP Server**: Streamable HTTP MCP server (coming soon)
- **OAuth**: Auth0 integration for authentication (coming soon)

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

### Test WebSocket

```bash
# In another terminal while dev server is running
npm run test:ws
```

Or manually with wscat:

```bash
npx wscat -c ws://localhost:8787/ws/test-user
```

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
wss://voicemode.dev/ws/{userId}
```

Connect with WebSocket for real-time communication. Query param `?token=<jwt>` will be used for authentication (coming in ws-002).

#### Message Types

**Client → Server:**
- `heartbeat` - Keep connection alive, server responds with `heartbeat_ack`
- `ping` - Latency measurement, server responds with `pong`

**Server → Client:**
- `heartbeat_ack` - Response to heartbeat
- `pong` - Response to ping
- `echo` - Echoes unknown message types (for testing)
- `error` - Error response with code and message

## Project Structure

```
voicemode-dev/
├── src/
│   ├── index.ts              # Main worker entry point
│   └── durable-objects/
│       └── websocket-gateway.ts   # WebSocket Durable Object
├── scripts/
│   └── test-websocket.mjs    # WebSocket test script
├── wrangler.toml             # Cloudflare configuration
├── package.json
├── tsconfig.json
└── README.md
```

## Feature Status

| Feature | Status | Task |
|---------|--------|------|
| Durable Objects setup | ✅ Complete | ws-001 |
| JWT Authentication | ⏳ Pending | ws-002 |
| Message Protocol | ⏳ Pending | ws-003 |
| Heartbeat/Keepalive | ⏳ Pending | ws-004 |
| Session Resumption | ⏳ Pending | ws-005 |
| Integration Tests | ⏳ Pending | ws-006 |

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
