"""
Claude Code Channel notification support for VoiceMode.

Enables VoiceMode's Python MCP server to send channel notifications
(notifications/claude/channel) natively, without requiring a separate
TypeScript MCP server.

The Python MCP SDK doesn't support generic/custom notifications -- its
send_notification() requires a typed ServerNotification (discriminated union
of standard notification types). We bypass this by constructing
JSONRPCNotification directly and writing to the session's write stream.

When the Python SDK adds generic notification support (issue #741),
migrate to the public API.

Usage:
    Set VOICEMODE_CHANNEL_ENABLED=true to enable channel notifications.
    Channel messages appear as <channel> tags in Claude Code conversation.
"""

import logging
from typing import Any

from mcp.server.session import ServerSession
from mcp.shared.message import JSONRPCMessage, SessionMessage
from mcp.types import JSONRPCNotification

logger = logging.getLogger("voicemode.channel")

# Experimental capability declaration for Claude Code channels
CHANNEL_EXPERIMENTAL_CAPABILITY = {"claude/channel": {}}

# Instructions injected into the MCP server when channel is enabled
CHANNEL_INSTRUCTIONS = (
    'Events from VoiceMode appear as <channel source="voicemode" caller="NAME">TRANSCRIPT</channel>. '
    "These are inbound voice messages from a user speaking on their phone or web app. "
    "Respond using the voicemode reply tool (NOT the converse tool). "
    "The reply tool sends your response back through the same channel connection, "
    "keeping the conversation in the same thread on the user's device. "
    "Address the caller by name. "
    "Keep responses concise -- the user is listening via text-to-speech."
)

# Prefix for channel messages (matches voicemode-channel TypeScript server)
EXTERNAL_MESSAGE_PREFIX = "[VoiceMode Connect - External Message]: "


async def send_channel_notification(
    session: ServerSession,
    content: str,
    meta: dict[str, str] | None = None,
) -> None:
    """Send a channel notification to Claude Code.

    Bypasses the Python MCP SDK's typed notification system by constructing
    a JSONRPCNotification directly and writing to the session's write stream.

    Args:
        session: The MCP ServerSession to send through.
        content: The message content (will be prefixed with EXTERNAL_MESSAGE_PREFIX).
        meta: Optional metadata dict (e.g. {"caller": "Mike", "device_id": "..."}).

    Raises:
        RuntimeError: If the session write stream is not available.
    """
    params: dict[str, Any] = {"content": f"{EXTERNAL_MESSAGE_PREFIX}{content}"}
    if meta:
        params["meta"] = meta

    notification = JSONRPCNotification(
        jsonrpc="2.0",
        method="notifications/claude/channel",
        params=params,
    )
    message = SessionMessage(message=JSONRPCMessage(notification))

    # Write directly to the session's write stream, bypassing the typed
    # send_notification() which rejects custom notification methods.
    try:
        await session._write_stream.send(message)
        caller = meta.get("caller", "unknown") if meta else "unknown"
        logger.debug("Channel notification sent: caller=%s len=%d", caller, len(content))
    except Exception as e:
        logger.error("Failed to send channel notification: %s", e)
        raise


def patch_experimental_capabilities(mcp_server: Any) -> None:
    """Patch a FastMCP server to declare the claude/channel experimental capability.

    FastMCP doesn't pass experimental_capabilities when calling
    create_initialization_options(). This patches the low-level server's
    method to inject our channel capability.

    Args:
        mcp_server: A FastMCP instance (the `mcp` object from server.py).
    """
    low_level = mcp_server._mcp_server
    original_create_init_opts = low_level.create_initialization_options

    def patched_create_init_opts(
        notification_options=None,
        experimental_capabilities=None,
        **kwargs: Any,
    ):
        if experimental_capabilities is None:
            experimental_capabilities = {}
        experimental_capabilities.update(CHANNEL_EXPERIMENTAL_CAPABILITY)
        return original_create_init_opts(
            notification_options=notification_options,
            experimental_capabilities=experimental_capabilities,
            **kwargs,
        )

    low_level.create_initialization_options = patched_create_init_opts
    logger.info("Channel capability registered: experimental['claude/channel']")
