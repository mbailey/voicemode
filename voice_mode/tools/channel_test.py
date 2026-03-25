"""Test and management tools for VoiceMode channel notifications.

Tools:
- channel_test: Send a test channel notification
- channel_connect: Start the gateway WebSocket connection

Load via: VOICEMODE_TOOLS_ENABLED=converse,service,channel_test
"""

import logging
from typing import Optional

from fastmcp import Context

from voice_mode.channel import (
    capture_session,
    get_gateway,
    send_channel_notification,
    start_gateway,
)
from voice_mode.config import CHANNEL_ENABLED
from voice_mode.server import mcp

logger = logging.getLogger("voicemode")


@mcp.tool()
async def channel_test(
    ctx: Context,
    message: str = "Hello from VoiceMode channel!",
    caller: str = "test",
) -> str:
    """Send a test channel notification to verify claude/channel capability.

    Requires VOICEMODE_CHANNEL_ENABLED=true and
    --dangerously-load-development-channels on Claude Code.

    Args:
        message: The message content to send as a channel notification.
        caller: The caller name to include in the notification metadata.
    """
    if not CHANNEL_ENABLED:
        return (
            "Channel notifications are disabled. "
            "Set VOICEMODE_CHANNEL_ENABLED=true and restart the MCP server."
        )

    # Capture session for background use (idempotent)
    capture_session(ctx.session)

    try:
        await send_channel_notification(
            ctx.session,
            content=message,
            meta={"source": "voicemode", "caller": caller},
        )
        return f"Channel notification sent: {message!r} (caller={caller!r})"
    except Exception as e:
        logger.error("channel_test failed: %s", e)
        return f"Failed to send channel notification: {e}"


@mcp.tool()
async def channel_connect(ctx: Context) -> str:
    """Connect to VoiceMode Connect gateway for inbound voice events.

    Starts a WebSocket connection to the VoiceMode Connect gateway.
    Inbound voice events from phones/web apps will appear as <channel>
    tags in the Claude Code conversation.

    Requires:
    - VOICEMODE_CHANNEL_ENABLED=true
    - Valid credentials (~/.voicemode/credentials)
    - Claude Code started with --dangerously-load-development-channels
    """
    if not CHANNEL_ENABLED:
        return (
            "Channel notifications are disabled. "
            "Set VOICEMODE_CHANNEL_ENABLED=true and restart the MCP server."
        )

    # Capture session for background notifications
    capture_session(ctx.session)

    # Check if already connected
    gw = get_gateway()
    if gw is not None:
        return f"Gateway already running (state: {gw.state})"

    # Start the gateway
    try:
        gw = start_gateway()
        return (
            f"Gateway started (state: {gw.state}). "
            "Inbound voice events from VoiceMode Connect will appear as channel notifications. "
            "The gateway will auto-reconnect if disconnected."
        )
    except Exception as e:
        logger.error("channel_connect failed: %s", e)
        return f"Failed to start gateway: {e}"


@mcp.tool()
async def channel_status(ctx: Context) -> str:
    """Check the status of channel notifications and gateway connection."""
    if not CHANNEL_ENABLED:
        return "Channel notifications: disabled (VOICEMODE_CHANNEL_ENABLED is not set)"

    from voice_mode.channel import get_active_session

    session_captured = get_active_session() is not None
    gw = get_gateway()
    gw_state = gw.state if gw else "not started"

    # Capture session while we're here
    capture_session(ctx.session)

    return (
        f"Channel notifications: enabled\n"
        f"MCP session captured: {session_captured}\n"
        f"Gateway: {gw_state}\n"
        f"Tip: Call channel_connect to start the gateway"
    )
