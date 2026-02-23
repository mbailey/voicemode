# Message Hub V1 Design

**Task**: VM-714 (expanded scope)
**Related**: VMD-102 (Wakeable Agents epic)
**Date**: 2026-02-16
**Status**: Implementation-ready

## Problem

Today, making an agent wakeable via VoiceMode Connect requires:

1. Agent creates a Claude Code team (TeamCreate)
2. Agent creates a symlink for a stable team name
3. Agent calls `register_wakeable` MCP tool with team name
4. Message delivery depends on `send-message` bash script being on PATH

Every session restart loses wakeable status. The bash script dependency is fragile (PATH issues, subprocess overhead, no library reuse).

## Design Decisions (from brainstorm session)

These were agreed in a ~45 minute voice session on 2026-02-16:

1. **Agent identity is VoiceMode-owned**, not tied to Claude Code teams. "cora" is a stable identity across sessions; the Claude team name is an ephemeral delivery detail.
2. **Wakeable is a live capability**, not a static attribute. VoiceMode announces it only after an agent registers.
3. **V1: local persistence only**. No server-side message storage. If agent is offline, voicemode.dev returns "agent offline".
4. **Python library replaces bash dependency**. `send-message` CLI becomes a thin wrapper. VoiceMode calls the library directly.
5. **Two layers**: stable identity (VoiceMode config) + ephemeral delivery target (per-session Claude team).

## Components

### 1. Configuration: `VOICEMODE_AGENT_NAME` env var

**File**: `voice_mode/config.py`

New config variables:

```python
# Agent identity for wakeable registration
AGENT_NAME = os.getenv("VOICEMODE_AGENT_NAME", "")
AGENT_PLATFORM = os.getenv("VOICEMODE_AGENT_PLATFORM", "claude-code")

# Auto-register as wakeable on startup (requires AGENT_NAME to be set)
AUTO_WAKEABLE = env_bool("VOICEMODE_AUTO_WAKEABLE", False)
```

Add to the default `voicemode.env` template:

```env
#############
# Agent Identity
#############

# Agent display name for VoiceMode Connect dashboard
# When set with AUTO_WAKEABLE, agent registers automatically on startup
# VOICEMODE_AGENT_NAME=Cora 7

# Agent platform identifier (default: claude-code)
# VOICEMODE_AGENT_PLATFORM=claude-code

# Auto-register as wakeable on MCP startup (true/false, default: false)
# Requires VOICEMODE_AGENT_NAME to be set
# VOICEMODE_AUTO_WAKEABLE=false
```

### 2. Python message delivery library

**New file**: `voice_mode/messaging.py`

Pure Python implementation of the `send-message` inbox injection protocol. No subprocess calls, no PATH dependency.

```python
"""Message delivery library for Claude Code agent inboxes.

Implements the same inbox file protocol as the send-message bash script,
but as a Python library callable from within VoiceMode directly.

Protocol: Write JSON messages to ~/.claude/teams/{team}/inboxes/{recipient}.json
Claude Code watches these files via FSEvents and wakes the agent automatically.
"""

def deliver_message(
    team_name: str,
    content: str,
    recipient: str = "team-lead",
    sender: str = "voicemode",
    summary: str | None = None,
) -> bool:
    """Deliver a message to a Claude Code agent's team inbox.

    Args:
        team_name: Team name (directory under ~/.claude/teams/)
        content: Message text
        recipient: Target agent name (default: team-lead)
        sender: Sender display name
        summary: Brief summary (default: first 50 chars of content)

    Returns:
        True if message was written successfully, False otherwise.
    """
```

Key implementation details:
- Reads existing inbox JSON, appends new message, writes atomically (write to temp, rename)
- Creates inbox directory if needed
- Follows same JSON schema as `send-message`: `{from, text, summary, timestamp, read}`
- Synchronous function (filesystem I/O only, no async needed)
- No external dependencies

### 3. Auto-register on startup

**File**: `voice_mode/connect_registry.py`

After the WebSocket connection is established and the `ready` message is sent, check if auto-wakeable is configured:

```python
# In _connection_loop(), after sending ready message:
if self._wakeable_team_name:
    # Re-registration (existing behavior)
    await self._send_wakeable_registration(ws)
elif AUTO_WAKEABLE and AGENT_NAME:
    # Auto-registration on first connect
    # Note: team_name comes from the agent at runtime, not config
    # Auto-wakeable only pre-configures the agent name
    logger.info(f"Auto-wakeable configured but no team registered yet "
                f"(agent: {AGENT_NAME})")
```

The flow is:
1. VoiceMode MCP starts, ConnectRegistry connects to voicemode.dev
2. VoiceMode announces TTS/STT capabilities (existing behavior)
3. Agent starts, creates team, calls `register_wakeable` with team name
4. VoiceMode announces wakeable capability with agent name

**Why not fully automatic?** The team name is ephemeral and created by the agent at runtime. VoiceMode can't know it ahead of time. What auto-wakeable does is:
- Pre-configure the agent name so `register_wakeable` doesn't need to provide it
- In future: if VoiceMode owns message storage (V2), it can auto-register without a team name at all

For V1, `register_wakeable` is still called by the agent, but it's simpler because the name defaults from config:

```python
@mcp.tool()
async def register_wakeable(
    team_name: str,
    agent_name: str = "",  # Empty = use VOICEMODE_AGENT_NAME config
    agent_platform: str = "",  # Empty = use VOICEMODE_AGENT_PLATFORM config
) -> str:
```

### 4. Wire `_handle_agent_message` to use library

**File**: `voice_mode/connect_registry.py`

Replace the subprocess call to `send-message` with a direct call to the messaging library:

```python
async def _handle_agent_message(self, text: str, sender: str):
    """Handle an incoming agent_message by delivering to team inbox."""
    from .messaging import deliver_message

    team_name = self._wakeable_team_name
    if not team_name:
        logger.warning("Received agent_message but not registered as wakeable")
        return

    if not text.strip():
        logger.warning("Received empty agent_message, ignoring")
        return

    success = await asyncio.to_thread(
        deliver_message,
        team_name=team_name,
        content=text,
        sender=sender,
    )

    if success:
        logger.info(f"Message delivered to team '{team_name}' from '{sender}'")
    else:
        logger.error(f"Failed to deliver message to team '{team_name}'")
```

This eliminates the `shutil.which("send-message")` dependency and the `subprocess.run` overhead.

## Files Changed

| File | Change |
|------|--------|
| `voice_mode/config.py` | Add `AGENT_NAME`, `AGENT_PLATFORM`, `AUTO_WAKEABLE` config vars |
| `voice_mode/messaging.py` | **New** - Python message delivery library |
| `voice_mode/connect_registry.py` | Wire `_handle_agent_message` to use `messaging.deliver_message` |
| `voice_mode/tools/connect.py` | Default `agent_name`/`agent_platform` from config |
| `tests/test_messaging.py` | **New** - Unit tests for messaging library |
| `tests/test_connect_registry.py` | Update tests for new message delivery path |

## Implementation Order

1. **`voice_mode/messaging.py`** + tests - standalone, no dependencies on other changes
2. **`voice_mode/config.py`** - add new config vars
3. **`voice_mode/connect_registry.py`** - replace subprocess with messaging library
4. **`voice_mode/tools/connect.py`** - default params from config

Steps 1-2 can be done in parallel. Steps 3-4 depend on both.

## Testing Strategy

- `test_messaging.py`: Test deliver_message with temp directories (create inbox, append to existing, handle missing team, atomic write)
- `test_connect_registry.py`: Test `_handle_agent_message` calls `deliver_message` instead of subprocess
- `test_config.py`: Verify new env vars are parsed correctly
- Manual: Set `VOICEMODE_AGENT_NAME=Test` in voicemode.env, start MCP, verify register_wakeable uses the name

## Out of Scope (V2+)

- Server-side message storage on voicemode.dev
- E2E encryption for stored messages
- VoiceMode-owned message directory (`~/.voicemode/messages/`)
- Pluggable delivery backends (WhatsApp, etc.)
- DNS-style agent addressing (`cora.mike.connect.voicemode.dev`)
- Message expiry / read receipts / QoS levels
- Auto-registration without agent needing to provide team name
