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
