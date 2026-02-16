"""VoiceMode Connect wakeable agent tools.

Allows an LLM agent to register itself as "wakeable" via VoiceMode Connect,
so that users can send messages to it from the web dashboard at app.voicemode.dev.

Messages are delivered to the agent's Claude Code team inbox via the `send-message`
script, which triggers FSEvents to wake the agent automatically.
"""

import logging

from voice_mode.server import mcp

logger = logging.getLogger("voicemode")


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
    from voice_mode.connect_registry import connect_registry

    await connect_registry.initialize()

    # If Connect is disabled or has no credentials (no background task started),
    # that's a real error. But if the task is running and just hasn't connected
    # yet, register_wakeable() will queue and send when the connection is ready.
    if not connect_registry.is_connected and not connect_registry.is_connecting:
        return (
            "Error: Not connected to VoiceMode Connect. "
            f"{connect_registry.status_message}"
        )

    await connect_registry.register_wakeable(team_name, agent_name, agent_platform)

    if connect_registry.is_connected:
        return f"Registered as wakeable: {agent_name} (team: {team_name})"
    else:
        return (
            f"Wakeable registration queued: {agent_name} (team: {team_name}). "
            f"Will activate when Connect finishes connecting."
        )


@mcp.tool()
async def unregister_wakeable() -> str:
    """Unregister this agent as wakeable. Stops receiving messages from the dashboard.

    Returns:
        Confirmation message.
    """
    from voice_mode.connect_registry import connect_registry

    await connect_registry.unregister_wakeable()
    return "Unregistered as wakeable"
