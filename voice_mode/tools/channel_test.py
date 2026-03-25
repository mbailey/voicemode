"""Test tool for VoiceMode channel notifications.

Sends a test channel notification to verify the claude/channel capability
is working end-to-end. Requires VOICEMODE_CHANNEL_ENABLED=1.

Load this tool via:
    VOICEMODE_TOOLS_ENABLED=converse,service,channel_test
or:
    VOICEMODE_TOOLS_DISABLED=
"""
import logging

from fastmcp import Context

from voice_mode.channel import send_channel_notification
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

    Requires VOICEMODE_CHANNEL_ENABLED=1.
    On success, a <channel> tag should appear in the Claude Code conversation.

    Args:
        message: The message content to send as a channel notification.
        caller: The caller name to include in the notification metadata.
    """
    if not CHANNEL_ENABLED:
        return (
            "Channel notifications are disabled. "
            "Set VOICEMODE_CHANNEL_ENABLED=1 and restart the MCP server."
        )

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
