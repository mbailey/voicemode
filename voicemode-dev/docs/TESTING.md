# Testing Guide

This document describes how to test the voicemode.dev WebSocket gateway.

## Test Types

### Unit Tests

Unit tests run without a server using Vitest and test individual modules in isolation.

```bash
# Run all unit tests
npm test

# Run tests in watch mode
npm test -- --watch

# Run specific test file
npm test -- src/auth/jwt.test.ts
npm test -- src/websocket/protocol.test.ts
```

**Current test coverage:**
- `src/auth/jwt.test.ts` - JWT validation, JWKS fetching, error handling (9 tests)
- `src/websocket/protocol.test.ts` - Protocol types, message validation, factories (46 tests)

### Integration Tests

Integration tests require a running dev server and test the full WebSocket flow.

```bash
# Terminal 1: Start the dev server
npm run dev

# Terminal 2: Run integration tests
npm run test:ws
```

The test script (`scripts/test-websocket.mjs`) runs 12 integration tests:

| # | Test | Description |
|---|------|-------------|
| 1 | Health Check | Verifies HTTP `/health` endpoint |
| 2 | Endpoint Info | Verifies `/ws` endpoint documentation |
| 3 | Anonymous Connection | Tests connection without JWT (dev mode) |
| 4 | Authenticated Connection | Tests connection with JWT token |
| 5 | Invalid Token | Verifies rejection of invalid tokens |
| 6 | Heartbeat | Tests heartbeat/heartbeat_ack flow |
| 7 | Ready Message | Tests ready message protocol |
| 8 | Transcription | Tests transcription message handling |
| 9 | Unknown Type | Verifies graceful handling of unknown types |
| 10 | Invalid Format | Tests parse error handling |
| 11 | Session Resumption | Tests disconnect/reconnect with session token |
| 12 | Invalid Session | Verifies rejection of invalid session tokens |

### Manual Testing with wscat

For interactive testing, use wscat:

```bash
# Install wscat globally (optional)
npm install -g wscat

# Or use npx
npx wscat -c ws://localhost:8787/ws?user=manual-test
```

#### Example Session

```
Connected (press CTRL+C to quit)
< {"type":"connected","sessionId":"sess-abc123...","authenticated":false}

# Send a heartbeat
> {"type":"heartbeat"}
< {"type":"heartbeat_ack","serverTime":"..."}

# Send a ready message
> {"type":"ready","id":"r1","device":{"platform":"manual"},"capabilities":{"tts":true}}
< {"type":"ack","id":"r1","status":"ok"}

# Send a transcription
> {"type":"transcription","id":"t1","text":"Hello world","confidence":0.95}
< {"type":"ack","id":"t1","status":"ok"}

# Test session resumption (copy sessionId from welcome message)
# Disconnect and reconnect, then send:
> {"type":"resume","sessionToken":"sess-abc123..."}
< {"type":"session_resumed","previousSessionId":"...","disconnectedDuration":1234,"queuedMessageCount":0}
```

#### Testing Authentication

To test with a JWT token:

```bash
# Set JWT_TOKEN environment variable
export JWT_TOKEN="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."

# Run integration tests
npm run test:ws

# Or connect with wscat
npx wscat -c "ws://localhost:8787/ws?token=$JWT_TOKEN"
```

## Test Environment

### Development Mode

When running locally with `npm run dev`, the server operates in development mode:
- Anonymous connections are allowed (no JWT required)
- Auth0 validation is bypassed if credentials aren't configured
- Useful for testing protocol without Auth0 setup

### Production Mode

In production or with Auth0 credentials configured:
- JWT token is required (`?token=<jwt>` query param)
- Invalid tokens result in HTTP 401 response
- Anonymous connections are rejected

## Message Protocol Reference

### Client → Server Messages

```typescript
// Ready - Announce client capabilities
{
  type: "ready",
  id: "unique-message-id",
  device?: { platform, appVersion, model, osVersion },
  capabilities?: { tts, stt, maxAudioDuration }
}

// Transcription - Send transcribed speech
{
  type: "transcription",
  id: "unique-message-id",
  text: "transcribed text",
  confidence?: 0.0-1.0,
  duration?: number,
  language?: "en"
}

// Heartbeat - Keep connection alive
{ type: "heartbeat" }

// Resume - Reconnect with session token
{
  type: "resume",
  sessionToken: "sess-..."
}

// Auth - Authenticate after connect
{
  type: "auth",
  token: "jwt-token"
}
```

### Server → Client Messages

```typescript
// Connected - Initial welcome
{
  type: "connected",
  sessionId: "sess-...",
  authenticated: boolean,
  userId?: "user-id"
}

// Ack - Acknowledge client message
{
  type: "ack",
  id: "message-id",
  status: "ok" | "error",
  error?: { code, message }
}

// Heartbeat - Server-initiated heartbeat
{
  type: "heartbeat",
  serverTime: "ISO timestamp"
}

// Heartbeat Ack - Response to client heartbeat
{
  type: "heartbeat_ack",
  serverTime: "ISO timestamp"
}

// Session Resumed - Successful reconnection
{
  type: "session_resumed",
  previousSessionId: "sess-...",
  disconnectedDuration: 1234,
  queuedMessageCount: 0
}

// Error - Protocol or session errors
{
  type: "error",
  code: "PARSE_ERROR" | "SESSION_NOT_FOUND" | "SESSION_EXPIRED" | "UNKNOWN_TYPE",
  message: "Human-readable message"
}

// Commands (for future MCP integration)
{ type: "speak", text: "...", voice?: "...", speed?: 1.0 }
{ type: "listen", maxDuration?: 30, language?: "en" }
{ type: "stop", action: "speak" | "listen" | "all" }
```

## Troubleshooting

### "ECONNREFUSED" Error

The dev server isn't running:
```bash
npm run dev
```

### Tests Hang or Timeout

Check that:
1. Dev server is running and healthy: `curl http://localhost:8787/health`
2. Port 8787 isn't in use by another process
3. WebSocket connections aren't blocked by firewall

### Authentication Test Fails

In dev mode without Auth0 credentials:
- Test 3 (Anonymous) should pass
- Test 4 (Authenticated) will be skipped if JWT_TOKEN not set
- Test 5 (Invalid Token) passes (connection allowed in dev mode)

With Auth0 configured:
- Anonymous connections may be rejected
- Valid JWT required for successful connection
- Invalid tokens return HTTP 401

### Session Resumption Test Fails

Session tokens expire after 24 hours. The test creates a new session and immediately reconnects, so this should always pass. If failing:
1. Check Durable Object storage is working
2. Verify session token format (starts with `sess-`)
3. Check server logs for storage errors

## CI/CD Integration

For automated testing in CI:

```bash
# Run unit tests (no server needed)
npm test -- --run

# Start server in background, run integration tests, then cleanup
npm run dev &
DEV_PID=$!
sleep 3  # Wait for server startup
npm run test:ws
kill $DEV_PID
```
