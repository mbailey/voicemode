"""VoiceMode Connect status and presence tool.

Provides a single MCP tool for checking connection status and
setting agent presence (available/away) on the Connect gateway.
Idempotent — ensures user exists and is registered before setting presence.

WebSocket connection is lazy — only established on first connect_status() call.
Inbox directory is created when presence is first set.
Inbox-live symlink is set up for wake-from-idle when team_name is available.
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

from voice_mode.server import mcp

logger = logging.getLogger("voicemode")


@mcp.tool()
async def connect_status(
    set_presence: Optional[str] = None,
    username: Optional[str] = None,
) -> str:
    """VoiceMode Connect status and presence.

    Check connection status and who's online, or set your availability.
    Idempotent — safe to call multiple times. Creates user if needed.

    Args:
        set_presence: Optional. Set to "available" (green dot - ready for calls)
            or "away" (amber dot - connected but not accepting calls).
            Omit to just check status.
        username: Optional. Your Connect username (e.g., "cora", "astrid").
            Used to identify which user to register on this WebSocket.
            The PostToolUse hook provides this in its systemMessage.

    Returns:
        Connection status, online contacts, and presence state.

    Examples:
        connect_status()                                         # Check status
        connect_status(set_presence="available", username="cora") # Go available
        connect_status(set_presence="away")                       # Go away
    """
    from voice_mode.connect.client import get_client
    from voice_mode.connect import config as connect_config

    if not connect_config.is_enabled():
        return (
            "VoiceMode Connect is disabled.\n"
            "Set VOICEMODE_CONNECT_ENABLED=true in .voicemode.env to enable."
        )

    client = get_client()

    # Lazy WebSocket connect — only on first call
    if not client.is_connected and not client.is_connecting:
        logger.info("Connect: lazy WebSocket connect on first connect_status call")
        await client.connect()
        # Wait for connection to actually be established
        connected = await client.wait_connected(timeout=10.0)
        if not connected:
            return (
                f"Failed to connect to VoiceMode Connect gateway.\n"
                f"Status: {client.status_message}\n"
                f"Check credentials with: voicemode connect auth status"
            )

    # Handle presence change
    if set_presence:
        return await _set_presence(client, set_presence, username)

    # Default: return status
    return client.get_status_text()


def _get_session_data() -> dict:
    """Read session identity data from the session file.

    Uses CLAUDE_SESSION_ID env var to find the session file written
    by the SessionStart hook at ~/.voicemode/sessions/{session_id}.json.
    Returns empty dict if not available.
    """
    session_id = os.environ.get("CLAUDE_SESSION_ID", "")
    if not session_id:
        return {}

    session_file = Path.home() / ".voicemode" / "sessions" / f"{session_id}.json"
    if not session_file.exists():
        return {}

    try:
        return json.loads(session_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to read session file: {e}")
        return {}


def _ensure_inbox(username: str) -> None:
    """Ensure inbox directory and file exist for a user.

    Creates ~/.voicemode/connect/users/{username}/inbox if missing.
    """
    inbox_dir = Path.home() / ".voicemode" / "connect" / "users" / username
    inbox_dir.mkdir(parents=True, exist_ok=True)
    inbox_file = inbox_dir / "inbox"
    if not inbox_file.exists():
        inbox_file.touch()
        logger.info(f"Created inbox for user: {username}")


def _ensure_inbox_live_symlink(username: str, team_name: str) -> bool:
    """Set up inbox-live symlink for wake-from-idle capability.

    Creates a symlink from the VoiceMode user inbox to the Claude Code
    team inbox. When messages arrive via Connect, they're written to both
    the VoiceMode inbox (for hook-based delivery) and the team inbox
    (for wake-from-idle via Claude Code Teams).

    Args:
        username: The agent's Connect username.
        team_name: The Claude Code team name (directory under ~/.claude/teams/).

    Returns:
        True if symlink was created/exists, False if team dir doesn't exist.
    """
    team_inbox = Path.home() / ".claude" / "teams" / team_name / "inboxes" / "team-lead.json"
    user_dir = Path.home() / ".voicemode" / "connect" / "users" / username
    symlink_path = user_dir / "inbox-live"

    # Verify team directory exists (agent actually created the team)
    team_dir = Path.home() / ".claude" / "teams" / team_name
    if not team_dir.exists():
        logger.debug(f"Team directory doesn't exist: {team_dir}")
        return False

    # Ensure inboxes directory exists
    team_inbox.parent.mkdir(parents=True, exist_ok=True)

    # Create or update symlink
    try:
        if symlink_path.is_symlink():
            # Update if pointing to different target
            if symlink_path.resolve() != team_inbox:
                symlink_path.unlink()
                symlink_path.symlink_to(team_inbox)
                logger.info(f"Updated inbox-live symlink: {symlink_path} -> {team_inbox}")
        else:
            symlink_path.symlink_to(team_inbox)
            logger.info(f"Created inbox-live symlink: {symlink_path} -> {team_inbox}")
        return True
    except OSError as e:
        logger.warning(f"Failed to create inbox-live symlink: {e}")
        return False


async def _ensure_user_registered(client, username: Optional[str] = None) -> list:
    """Ensure this agent's user is registered on the MCP server's WebSocket.

    Idempotent — if already registered, returns existing user. If username
    is provided and user doesn't exist on filesystem, creates it.

    Args:
        client: The ConnectClient instance.
        username: Optional explicit username. If provided and no filesystem
            user exists, creates one with display name from VOICEMODE_AGENT_NAME.

    Returns list of this agent's users.
    """
    from voice_mode.connect import config as connect_config

    # Already registered — return it
    if client._primary_user:
        user = client.user_manager.get(client._primary_user.name)
        if user:
            return [user]

    # Explicit username provided — find or create
    if username:
        username = username.lower().strip()
        user = client.user_manager.get(username)
        if not user:
            # Create user on filesystem (idempotent)
            display_name = connect_config.get_agent_name() or username
            user = client.user_manager.add(
                name=username,
                display_name=display_name,
            )
            logger.info(f"Created Connect user: {username}")

        # Ensure inbox exists for this user
        _ensure_inbox(username)

        # Register on this WebSocket
        await client.register_user(user)
        logger.info(f"Registered user {username} on MCP server WebSocket")
        return [user]

    # No username — discover from filesystem
    all_users = client.user_manager.list()

    if all_users:
        # Register the first user as our primary
        user = all_users[0]
        _ensure_inbox(user.name)
        await client.register_user(user)
        logger.info(f"Auto-registered user {user.name} on MCP server WebSocket")
        return all_users

    # No users — check for preconfigured users
    configured = connect_config.get_preconfigured_users()
    if configured:
        users = []
        for name in configured:
            user = client.user_manager.get(name)
            if user:
                _ensure_inbox(user.name)
                users.append(user)
        if users:
            await client.register_user(users[0])
            return users

    # No users found at all — return empty
    return []


async def _set_presence(client, presence: str, username: Optional[str] = None) -> str:
    """Set presence on the Connect gateway. Idempotent."""
    presence = presence.lower().strip()

    # Accept common aliases
    if presence in ("unavailable", "busy", "dnd"):
        presence = "away"

    if presence not in ("available", "away"):
        return (
            f"Invalid presence: '{presence}'. "
            "Use 'available' (green dot) or 'away' (amber dot)."
        )

    if not client.is_connected:
        return (
            "Not connected to VoiceMode Connect gateway. "
            "Cannot set presence while disconnected."
        )

    # Ensure user is registered (idempotent, creates if needed)
    my_users = await _ensure_user_registered(client, username)

    if not my_users:
        return (
            "No Connect users found. Pass username parameter to register."
        )

    # Auto-discover team_name from session file and set up wake symlink
    downgraded_from_available = False
    if presence == "available":
        session_data = _get_session_data()
        team_name = session_data.get("team_name", "")
        if team_name and my_users:
            agent_name = my_users[0].name
            if _ensure_inbox_live_symlink(agent_name, team_name):
                logger.info(
                    f"Wake-from-idle enabled: {agent_name} -> team {team_name}"
                )

        # Check if wake-from-idle is actually set up
        if my_users:
            symlink = Path.home() / ".voicemode" / "connect" / "users" / my_users[0].name / "inbox-live"
            if not symlink.is_symlink():
                # Downgrade to "away" — can't be truly available without wake
                presence = "away"
                downgraded_from_available = True
                logger.info(
                    "Downgraded presence from available to away "
                    "(no wake-from-idle capability)"
                )

    # Build presence update for only this agent's users
    user_entries = []
    for user in my_users:
        # Map "away" to "online" for the wire protocol (gateway treats
        # anything != "available" as not-available, shows amber dot)
        wire_presence = presence if presence == "available" else "online"
        user_entries.append({
            "name": user.name,
            "host": user.host,
            "display_name": user.display_name,
            "presence": wire_presence,
        })

    try:
        import json
        msg = {
            "type": "capabilities_update",
            "users": user_entries,
            "platform": "claude-code",
        }
        await client._ws.send(json.dumps(msg))

        if downgraded_from_available:
            return (
                "Set to Away (amber dot) instead of Available.\n"
                "Available requires wake-from-idle capability.\n"
                "To enable: create a team with TeamCreate, then set presence again.\n"
                "Messages will be delivered when you're active."
            )
        elif presence == "available":
            user_names = ", ".join(u.display_name or u.name for u in my_users)
            return (
                f"Now Available (green dot). Users can call you.\n"
                f"Registered as: {user_names}\n"
                f"Wake-from-idle: enabled (team inbox linked)"
            )
        else:
            return "Now Away (amber dot). Messages will queue for later."

    except Exception as e:
        logger.error(f"Failed to set presence: {e}")
        return f"Failed to set presence: {e}"
