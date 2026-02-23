"""VoiceMode Connect status and presence tool.

Provides a single MCP tool for checking connection status and
setting agent presence (available/away) on the Connect gateway.
Idempotent — ensures user exists and is registered before setting presence.

WebSocket connection is lazy — only established on first connect_status() call.
Inbox directory is created when presence is first set.
"""

import logging
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

    # Handle presence change
    if set_presence:
        return await _set_presence(client, set_presence, username)

    # Default: return status
    return client.get_status_text()


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

        if presence == "available":
            user_names = ", ".join(u.display_name or u.name for u in my_users)
            return (
                f"Now Available (green dot). Users can call you.\n"
                f"Registered as: {user_names}"
            )
        else:
            return "Now Away (amber dot). Messages will queue for later."

    except Exception as e:
        logger.error(f"Failed to set presence: {e}")
        return f"Failed to set presence: {e}"
