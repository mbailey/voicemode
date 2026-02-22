"""VoiceMode Connect status and presence tool.

Provides a single MCP tool for checking connection status and
setting agent presence (available/away) on the Connect gateway.
"""

import logging
from typing import Optional

from voice_mode.server import mcp

logger = logging.getLogger("voicemode")


@mcp.tool()
async def connect_status(
    set_presence: Optional[str] = None,
) -> str:
    """VoiceMode Connect status and presence.

    Check connection status and who's online, or set your availability.

    Args:
        set_presence: Optional. Set to "available" (green dot - ready for calls)
            or "away" (amber dot - connected but not accepting calls).
            Omit to just check status.

    Returns:
        Connection status, online contacts, and presence state.

    Examples:
        connect_status()                        # Check status
        connect_status(set_presence="available") # Go available (green dot)
        connect_status(set_presence="away")      # Go away (amber dot)
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
        return await _set_presence(client, set_presence)

    # Default: return status
    return client.get_status_text()


def _get_my_users(client) -> list:
    """Get only the users that belong to this agent process.

    Scopes to the primary user (set via register_user) or to users
    configured in VOICEMODE_CONNECT_USERS. Falls back to all users
    only if neither is available.
    """
    from voice_mode.connect import config as connect_config

    # 1. Primary user registered by this process (set by register_user())
    if client._primary_user:
        user = client.user_manager.get(client._primary_user.name)
        if user:
            return [user]

    # 2. Users configured in VOICEMODE_CONNECT_USERS env var
    configured = connect_config.get_preconfigured_users()
    if configured:
        users = []
        for name in configured:
            user = client.user_manager.get(name)
            if user:
                users.append(user)
        if users:
            return users

    # 3. Fallback: all registered users (shared connect up process)
    return client.user_manager.list()


async def _set_presence(client, presence: str) -> str:
    """Set presence on the Connect gateway."""
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

    # Get only this agent's users (not all users on the system)
    my_users = _get_my_users(client)

    if not my_users:
        return (
            "No Connect users registered. "
            "Register with: voicemode connect user add <name>"
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
