"""Kokoro TTS service management prompts."""

from voice_mode.mcp_instance import mcp


@mcp.prompt(name="kokoro-start")
def kokoro_start() -> str:
    """Start the local Kokoro TTS service."""
    return "Use the kokoro_start tool to start the Kokoro TTS service. After starting, confirm that Kokoro is running and ready for local TTS."


@mcp.prompt(name="kokoro-stop")
def kokoro_stop() -> str:
    """Stop the running Kokoro TTS service."""
    return "Use the kokoro_stop tool to stop the Kokoro TTS service. Confirm that the service has been stopped successfully."


@mcp.prompt(name="kokoro-status")
def kokoro_status() -> str:
    """Check if Kokoro TTS is running and show its status."""
    return "Use the kokoro_status tool to check if the Kokoro TTS service is running. Report the status including process details, CPU/memory usage if available."