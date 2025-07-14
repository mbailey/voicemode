"""LiveKit integration tools."""

import logging
from typing import Optional

from voice_mode.mcp_instance import mcp
from voice_mode.shared import LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def check_room_status() -> str:
    """Check LiveKit room status and participants"""
    # This will be implemented - moved from server.py
    return "LiveKit room status check not yet implemented in refactored structure"