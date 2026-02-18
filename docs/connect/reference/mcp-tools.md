# Connect CLI Reference

VoiceMode Connect commands for managing remote voice connections.

## CLI Commands

Agents and humans use the same CLI interface:

```bash
voicemode connect up       # Start connection to voicemode.dev
voicemode connect down     # Stop connection
voicemode connect status   # Show connection status and devices
voicemode connect login    # Authenticate with voicemode.dev
voicemode connect logout   # Clear stored credentials

voicemode connect user add <name>    # Register an agent user
voicemode connect user list          # List registered users
voicemode connect user remove <name> # Remove an agent user
```

### Prerequisites

All connect commands (except login/logout) require:

```bash
export VOICEMODE_CONNECT_ENABLED=true
```

VoiceMode does not connect to external services without explicit opt-in.

## voicemode connect up

Start the connection to voicemode.dev. This is a long-running process that:

- Connects via WebSocket to the voicemode.dev gateway
- Announces registered users to the platform
- Watches for user configuration changes
- Delivers incoming messages to agent inboxes
- Reconnects automatically on disconnection

Requires authentication (`voicemode connect login` first).

## voicemode connect status

Show current connection status, registered users, and connected remote devices.

```
VoiceMode Connect: enabled (not connected)
Gateway: wss://voicemode.dev/ws
Host: mba
Users:
  cora@mba (Cora 7)
```

## voicemode connect user add

Register an agent user for remote voice:

```bash
voicemode connect user add cora --name "Cora 7"
```

Names must be lowercase, start with a letter.

## Connect Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICEMODE_CONNECT_ENABLED` | `false` | Enable Connect features |
| `VOICEMODE_CONNECT_HOST` | hostname | Host identifier for user addresses |
| `VOICEMODE_CONNECT_WS_URL` | `wss://voicemode.dev/ws` | WebSocket gateway URL |

## voicemode.dev MCP Tools

The voicemode.dev platform also exposes MCP tools for agents connecting via `mcp-remote`. These are separate from the local CLI and documented at [voicemode.dev](https://voicemode.dev).

| Tool | Description |
|------|-------------|
| `status` | Check connected devices |
| `converse` | Have a voice conversation through a connected client |

See the voicemode.dev documentation for details on remote MCP tools.
