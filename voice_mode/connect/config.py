"""Connect configuration helpers."""

from voice_mode import config


def is_enabled() -> bool:
    """Check if Connect is enabled."""
    return config.CONNECT_ENABLED


def get_host() -> str:
    """Get the effective hostname for addressing."""
    return config.CONNECT_HOST


def get_preconfigured_users() -> list[str]:
    """Get mailbox names from VOICEMODE_CONNECT_USERS."""
    return [u for u in config.CONNECT_USERS if u]


def get_agent_name() -> str:
    """Get the display name for the agent."""
    return config.AGENT_NAME


def get_ws_url() -> str:
    """Get the WebSocket URL for the gateway."""
    return config.CONNECT_WS_URL


def require_enabled() -> None:
    """Raise if Connect is not enabled."""
    if not is_enabled():
        raise ConnectDisabledError(
            "VoiceMode Connect is not enabled. "
            "Set VOICEMODE_CONNECT_ENABLED=true in your voicemode.env to enable it."
        )


class ConnectDisabledError(Exception):
    """Raised when a Connect operation is attempted but Connect is disabled."""
    pass
