"""Status check prompts for voice services."""

from voice_mode.mcp_instance import mcp


@mcp.prompt(name="voice-status")
def voice_status() -> str:
    """Check the status of all voice services (TTS, STT, LiveKit, devices)."""
    return "Use the voice_status tool to check the status of all voice services. This will show TTS/STT providers, LiveKit status, audio devices, and recommendations for optimal configuration."