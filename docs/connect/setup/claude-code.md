# Claude Code Setup

Enable VoiceMode Connect for Claude Code.

## Prerequisites

- Claude Code installed
- Node.js (for npx)
- voicemode.dev account

## Add the MCP Server

Add this to your Claude Code MCP settings (`~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "voicemode-dev": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://voicemode.dev/mcp"]
    }
  }
}
```

Restart Claude Code after making changes.

## Authenticate

The first time you use a Connect tool (`status` or `converse`), you'll be prompted to authenticate via OAuth. Sign in with your voicemode.dev account.

Authentication is handled by mcp-remote and persists across sessions.

## Verify Setup

Ask Claude Code to check your connection status:

```
What's my VoiceMode Connect status?
```

This will call the `status` tool and show any connected devices.

## Connect a Client

For voice to work, you also need a client connected:

1. **iOS App**: Download from App Store, sign in with same account
2. **Web Dashboard**: Visit voicemode.dev/dashboard, sign in

Once connected, you can use `converse` for voice conversations.

## Local Device Visibility (Optional)

If you have VoiceMode installed locally, you can also see remote devices from the local MCP server's service tool. This is useful for monitoring without switching to the voicemode.dev dashboard.

Enable the in-process WebSocket client:

```bash
export VOICEMODE_CONNECT_AUTO=true
```

Then check status:

```
service("connect", "status")
```

Or from the CLI:

```bash
voicemode connect status
```

The CLI command always shows remote devices when you're logged in, without needing the environment variable (since running the command is an explicit user action).

## Troubleshooting

**"No connected clients"**
: Open the iOS app or web dashboard and sign in

**OAuth popup doesn't appear**
: Try restarting Claude Code, or check browser popup blockers

**mcp-remote errors**
: Ensure Node.js is installed and `npx` is in your PATH

## See Also

- [MCP Tools Reference](../reference/mcp-tools.md) - Tool parameters
- [Architecture](../architecture.md) - How Connect works
