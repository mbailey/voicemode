"""VoiceMode Connect status and presence tool.

Provides a single MCP tool for checking connection status and
setting agent presence (available/away) on the Connect gateway.
Idempotent — ensures user exists and is registered before setting presence.
"""

import logging
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

    # Ensure we're connected
    if not client.is_connected and not client.is_connecting:
        await client.connect()

    # Handle presence change
    if set_presence:
        return await _set_presence(client, set_presence, username)

    # Default: return status
    return client.get_status_text()


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

        # Register on this WebSocket
        await client.register_user(user)
        logger.info(f"Registered user {username} on MCP server WebSocket")
        return [user]

    # No username — discover from filesystem
    # Look for users with inbox-live symlinks (set up by hooks)
    subscribed_users = [
        u for u in client.user_manager.list()
        if client.user_manager.is_subscribed(u.name)
    ]

    if subscribed_users:
        # Register the first subscribed user as our primary
        user = subscribed_users[0]
        await client.register_user(user)
        logger.info(
            f"Auto-registered user {user.name} on MCP server WebSocket"
        )
        return subscribed_users

    # No subscribed users — check for preconfigured users
    configured = connect_config.get_preconfigured_users()
    if configured:
        users = []
        for name in configured:
            user = client.user_manager.get(name)
            if user:
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
            "No Connect users found. Pass username parameter or ensure "
            "the PostToolUse hook created a user after TeamCreate."
        )

    # For "available", verify inbox-live symlink exists
    if presence == "available":
        any_subscribed = any(
            client.user_manager.is_subscribed(u.name) for u in my_users
        )
        if not any_subscribed:
            return (
                "Cannot go available: no inbox-live symlink found.\n"
                "Create a Claude Code team first (TeamCreate), then try again.\n"
                "The inbox-live symlink connects incoming messages to your team inbox."
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
                f"✅ Now Available (green dot). Users can call you.\n"
                f"Registered as: {user_names}"
            )
        else:
            return "✅ Now Away (amber dot). Messages will queue for later."

    except Exception as e:
        logger.error(f"Failed to set presence: {e}")
        return f"Failed to set presence: {e}"
