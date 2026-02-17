"""VoiceMode Connect MCP tools.

Manage Connect mailboxes, read inboxes, and check connection status.
Backward-compatible register/unregister_wakeable wrappers are included
for existing integrations.
"""

import logging

from voice_mode.server import mcp
from voice_mode.connect import config as connect_config
from voice_mode.connect.client import get_client
from voice_mode.connect.messaging import read_inbox

logger = logging.getLogger("voicemode")

DISABLED_MSG = (
    "VoiceMode Connect is not enabled. "
    "Set VOICEMODE_CONNECT_ENABLED=true in your voicemode.env to enable it."
)


@mcp.tool()
async def connect_inbox(
    name: str = "",
    limit: int = 10,
) -> str:
    """Read messages from a mailbox's persistent inbox.

    Args:
        name: Mailbox name (default: first configured user)
        limit: Maximum messages to return
    """
    if not connect_config.is_enabled():
        return DISABLED_MSG

    client = get_client()

    # Resolve user name
    if not name:
        users = client.user_manager.list()
        if not users:
            return "No users configured. Use connect_user_add to create a mailbox."
        name = users[0].name

    user = client.user_manager.get(name)
    if not user:
        return f"User '{name}' not found."

    user_dir = client.user_manager._user_dir(name)
    messages = read_inbox(user_dir, limit=limit)

    if not messages:
        return f"Inbox for '{name}' is empty."

    lines = [f"Inbox for '{name}' ({len(messages)} message(s)):"]
    for msg in messages:
        sender = msg.get("from", "unknown")
        text = msg.get("text", "")
        ts = msg.get("timestamp", "")
        lines.append(f"  [{ts}] {sender}: {text}")

    return "\n".join(lines)


@mcp.tool()
async def connect_status() -> str:
    """Show VoiceMode Connect status including users and presence."""
    if not connect_config.is_enabled():
        return DISABLED_MSG

    client = get_client()
    return client.get_status_text()


@mcp.tool()
async def connect_user_add(
    name: str,
    display_name: str = "",
    subscribe_team: str = "",
) -> str:
    """Add a mailbox to VoiceMode Connect.

    Creates a user/mailbox that can receive messages from the dashboard.
    Optionally subscribes to a Claude Code team for real-time delivery.

    Args:
        name: Mailbox name (lowercase, e.g., "voicemode", "cora")
        display_name: Name shown in dashboard (e.g., "Cora 7")
        subscribe_team: Claude team name for live inbox symlink
    """
    if not connect_config.is_enabled():
        return DISABLED_MSG

    client = get_client()
    await client.connect()

    user = client.user_manager.add(
        name,
        display_name=display_name,
        subscribe_team=subscribe_team or None,
    )
    await client.register_user(user)

    parts = [f"Added mailbox '{name}'"]
    if display_name:
        parts.append(f" (display: {display_name})")
    if subscribe_team:
        parts.append(f", subscribed to team '{subscribe_team}'")
    parts.append(".")

    return "".join(parts)


@mcp.tool()
async def connect_user_remove(name: str) -> str:
    """Remove a mailbox from VoiceMode Connect.

    Args:
        name: Mailbox name to remove
    """
    if not connect_config.is_enabled():
        return DISABLED_MSG

    client = get_client()

    removed = client.user_manager.remove(name)
    if not removed:
        return f"User '{name}' not found."

    await client.unregister_user(name)
    return f"Removed mailbox '{name}'."


# --- Backward-compatible wrappers ---


@mcp.tool()
async def register_wakeable(
    team_name: str,
    agent_name: str = "Claude Code",
    agent_platform: str = "claude-code",
) -> str:
    """Register this agent as wakeable via VoiceMode Connect.

    Once registered, users can send text messages to this agent from the
    VoiceMode web app (app.voicemode.dev). Messages are delivered to the
    agent's team inbox and the agent wakes up automatically.

    Args:
        team_name: Claude Code team name (used by send-message for delivery)
        agent_name: Display name shown in the VoiceMode dashboard
        agent_platform: Platform identifier (default: claude-code)

    Returns:
        Confirmation message or error description.
    """
    return await connect_user_add.fn(
        name=team_name,
        display_name=agent_name,
        subscribe_team=team_name,
    )


@mcp.tool()
async def unregister_wakeable() -> str:
    """Unregister this agent as wakeable. Stops receiving messages from the dashboard.

    Returns:
        Confirmation message.
    """
    if not connect_config.is_enabled():
        return DISABLED_MSG

    client = get_client()
    users = client.user_manager.list()

    if not users:
        return "No users registered."

    # Remove all users (backward compat: old API had a single registration)
    for user in users:
        client.user_manager.remove(user.name)
        await client.unregister_user(user.name)

    return "Unregistered as wakeable."
