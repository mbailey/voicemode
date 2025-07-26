"""Service management prompts for whisper and kokoro."""

from voice_mode.server import mcp


@mcp.prompt(name="whisper")
def whisper_prompt(action: str = "status") -> str:
    """Manage Whisper speech-to-text service.
    
    Args:
        action: Service action (status, start, stop, restart, enable, disable, logs)
    """
    valid_actions = ["status", "start", "stop", "restart", "enable", "disable", "logs"]
    
    if action not in valid_actions:
        return f"Invalid action '{action}'. Use one of: {', '.join(valid_actions)}"
    
    if action == "logs":
        return f"Use the service tool with service_name='whisper' and action='logs' to view recent logs"
    else:
        return f"Use the service tool with service_name='whisper' and action='{action}'"


@mcp.prompt(name="kokoro")
def kokoro_prompt(action: str = "status") -> str:
    """Manage Kokoro text-to-speech service.
    
    Args:
        action: Service action (status, start, stop, restart, enable, disable, logs)
    """
    valid_actions = ["status", "start", "stop", "restart", "enable", "disable", "logs"]
    
    if action not in valid_actions:
        return f"Invalid action '{action}'. Use one of: {', '.join(valid_actions)}"
    
    if action == "logs":
        return f"Use the service tool with service_name='kokoro' and action='logs' to view recent logs"
    else:
        return f"Use the service tool with service_name='kokoro' and action='{action}'"