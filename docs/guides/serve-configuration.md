# Remote Access Configuration

VoiceMode can run as an HTTP server, enabling remote access from Claude Desktop, Claude Code, Claude.ai, and other MCP clients. This guide covers how to configure different clients to connect to a VoiceMode server.

## Overview

The `voicemode serve` command starts VoiceMode as an HTTP server instead of the default stdio transport. This enables:

- **Local network access** - Connect from other machines on your network
- **Cloud access** - Connect from Claude.ai and Claude Cowork via Tailscale Funnel
- **Multiple clients** - Share one VoiceMode instance across devices

```bash
# Start the server (localhost only by default)
voicemode serve

# Server starts at http://127.0.0.1:8765/mcp
```

## Quick Start

### Local Development

For local development, start the server and connect from your client:

```bash
# Terminal 1: Start server
voicemode serve

# Server runs at http://127.0.0.1:8765/mcp
```

Then configure your client to connect (see client-specific sections below).

### Remote Access (Same Network)

To allow connections from other devices on your network:

```bash
# Bind to all interfaces
voicemode serve --host 0.0.0.0

# Or allow specific IP ranges
voicemode serve --host 0.0.0.0 --allow-ip 192.168.1.0/24
```

### Remote Access (Tailscale)

For connections over Tailscale:

```bash
# Allow Tailscale IP range
voicemode serve --host 0.0.0.0 --allow-tailscale
```

## Client Configuration

### Claude Desktop (via mcp-remote)

Claude Desktop uses stdio transport by default. To connect to a remote VoiceMode server, use [mcp-remote](https://github.com/anthropics/mcp-remote) as a bridge.

#### Setup

1. Start the VoiceMode server:
   ```bash
   voicemode serve
   ```

2. Add to Claude Desktop's MCP configuration (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

   ```json
   {
     "mcpServers": {
       "voicemode": {
         "command": "npx",
         "args": ["-y", "mcp-remote", "http://127.0.0.1:8765/mcp"]
       }
     }
   }
   ```

3. Restart Claude Desktop.

#### Remote Server

For a remote server (e.g., on another machine):

```json
{
  "mcpServers": {
    "voicemode": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://192.168.1.100:8765/mcp"]
    }
  }
}
```

#### With Authentication

If using token authentication:

```json
{
  "mcpServers": {
    "voicemode": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "http://127.0.0.1:8765/mcp",
        "--header", "Authorization: Bearer your-secret-token"
      ]
    }
  }
}
```

### Claude Code

Claude Code can connect to VoiceMode in two ways: direct stdio transport (recommended for local use) or HTTP transport for remote servers.

#### Local Setup (Recommended)

For local development, use stdio transport directly in `.claude/mcp.json`:

```json
{
  "mcpServers": {
    "voicemode": {
      "command": "uvx",
      "args": ["voice-mode"]
    }
  }
}
```

This is simpler and doesn't require running a separate server.

#### Remote Server

To connect to a remote VoiceMode server, use mcp-remote:

```json
{
  "mcpServers": {
    "voicemode": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://your-server:8765/mcp"]
    }
  }
}
```

#### With VoiceMode Plugin

If using the VoiceMode plugin for Claude Code, it automatically configures stdio transport. For remote access, modify the plugin's MCP configuration to use mcp-remote instead.

### Claude.ai and Claude Cowork

Claude.ai and Claude Cowork can connect to MCP servers via custom connectors. This requires your VoiceMode server to be accessible from the internet.

#### Prerequisites

1. **Public accessibility**: Your server must be reachable from Anthropic's IP ranges
2. **HTTPS**: Production deployments should use HTTPS (via reverse proxy or Tailscale Funnel)
3. **Authentication**: Strongly recommended for internet-exposed servers

#### Setup with Tailscale Funnel

Tailscale Funnel exposes your local server to the internet with automatic HTTPS:

1. Install and configure Tailscale:
   ```bash
   # macOS
   brew install tailscale

   # Start Tailscale
   sudo tailscale up
   ```

2. Enable Funnel for your machine:
   ```bash
   # Enable Funnel (requires Tailscale admin approval)
   tailscale funnel 8765
   ```

3. Start VoiceMode with Anthropic IP allowlist:
   ```bash
   # Allow Anthropic's outbound IPs
   voicemode serve --allow-anthropic --secret your-secret-uuid
   ```

4. In Claude.ai settings, add a custom MCP connector:
   - **URL**: `https://your-machine.tail12345.ts.net/mcp/your-secret-uuid`
   - **Name**: VoiceMode

#### Direct Setup (No Tailscale)

If you have a public IP and domain:

1. Set up a reverse proxy (nginx, Caddy) with HTTPS
2. Configure the proxy to forward to `localhost:8765`
3. Start VoiceMode:
   ```bash
   voicemode serve --allow-anthropic --token your-secret-token
   ```

4. Add the custom connector in Claude.ai with your domain.

#### Anthropic IP Ranges

The `--allow-anthropic` flag adds Anthropic's outbound IP ranges (`160.79.104.0/21`) to the allowlist. This is required for Claude.ai and Claude Cowork connections.

## Security Best Practices

### Defense in Depth

Combine multiple security layers:

```bash
# IP allowlist + token authentication
voicemode serve --allow-anthropic --token your-secret-token

# IP allowlist + URL secret
voicemode serve --allow-anthropic --secret your-secret-uuid
```

### Authentication Options

| Method | Best For | Notes |
|--------|----------|-------|
| `--secret` | Claude.ai | URL-embedded secret, returns 404 for wrong path |
| `--token` | API clients | Standard Bearer token, returns 401 for invalid |
| Both | Maximum security | Combine for defense in depth |

### Generating Secrets

```bash
# Generate a random UUID for --secret
uuidgen

# Generate a random token
openssl rand -hex 32
```

### Network Security

1. **Default binding**: Server binds to `127.0.0.1` by default (localhost only)
2. **Explicit allowlists**: Use `--allow-ip` for specific ranges
3. **Tailscale**: Use `--allow-tailscale` for Tailscale-only access
4. **No public binding**: Avoid `--host 0.0.0.0` without IP restrictions

### Token Management

- Use environment variables for tokens in scripts
- Rotate tokens periodically
- Never commit tokens to version control
- Use different tokens for different clients

```bash
# Use environment variable
export VOICEMODE_TOKEN="your-secret-token"
voicemode serve --allow-anthropic --token "$VOICEMODE_TOKEN"
```

## Transport Options

VoiceMode supports two HTTP transports:

### Streamable HTTP (Recommended)

The default and recommended transport:

```bash
voicemode serve --transport streamable-http
# Endpoint: http://127.0.0.1:8765/mcp
```

- Better performance and reliability
- Supports bidirectional streaming
- Modern MCP transport standard

### SSE (Legacy)

Server-Sent Events transport for backward compatibility:

```bash
voicemode serve --transport sse
# Endpoint: http://127.0.0.1:8765/sse
```

- One-way server-to-client streaming
- Shows deprecation warning
- Consider migrating to streamable-http

## Troubleshooting

### Connection Refused

**Symptom**: Client cannot connect to the server.

**Solutions**:
1. Verify server is running: `curl http://127.0.0.1:8765/mcp`
2. Check firewall settings
3. Verify correct host/port in client config
4. Enable debug logging: `voicemode serve --log-level debug`

### 401 Unauthorized

**Symptom**: Server rejects requests with 401.

**Solutions**:
1. Verify token is correct in client config
2. Check for typos in Authorization header
3. Ensure token matches server `--token` value

### 403 Forbidden

**Symptom**: Server rejects requests with 403.

**Solutions**:
1. Client IP not in allowlist
2. Add appropriate `--allow-*` flag or `--allow-ip`
3. Check client's actual IP (may differ behind NAT)

### 404 Not Found

**Symptom**: Server returns 404 for endpoint.

**Solutions**:
1. Check endpoint path matches transport (`/mcp` vs `/sse`)
2. If using `--secret`, verify secret is in URL path
3. Verify server transport matches client expectation

### Tailscale Funnel Not Working

**Symptom**: Cannot access server via Tailscale Funnel URL.

**Solutions**:
1. Verify Funnel is enabled: `tailscale funnel status`
2. Check Funnel is allowed in Tailscale admin console
3. Ensure correct port: `tailscale funnel 8765`
4. Wait a few minutes for DNS propagation

### Claude.ai Cannot Connect

**Symptom**: Claude.ai custom connector fails.

**Solutions**:
1. Verify `--allow-anthropic` flag is set
2. Confirm server is accessible via HTTPS
3. Test URL in browser first
4. Check Tailscale Funnel status if using
5. Verify secret/token in connector URL

### Voice Services Not Available

**Symptom**: VoiceMode connects but voice tools fail.

**Solutions**:
1. Ensure Whisper and Kokoro services are running on the server
2. Check service status: `voicemode whisper status` and `voicemode kokoro status`
3. Services must run on the same machine as `voicemode serve`

## Environment Variables

Server behavior can be configured via environment variables:

```bash
# Default transport
export VOICEMODE_SERVE_TRANSPORT=streamable-http

# Default port
export VOICEMODE_SERVE_PORT=8765

# Default host
export VOICEMODE_SERVE_HOST=127.0.0.1
```

CLI options take precedence over environment variables.

## See Also

- [CLI Reference](../reference/cli.md) - Complete serve command documentation
- [Configuration Guide](configuration.md) - VoiceMode configuration options
- [Claude Code Plugin](claude-code-plugin.md) - Plugin installation for Claude Code
