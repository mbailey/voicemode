"""Connect configuration helpers."""

import hashlib
import logging
import os
import subprocess

from voice_mode import config

logger = logging.getLogger("voicemode")


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


def _get_git_repo_name() -> str | None:
    """Get the git repo root directory name, if in a git repo.

    Uses `git rev-parse --show-toplevel` to find the repo root,
    then returns the basename. Returns None if not in a git repo.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=2,
        )
        if result.returncode == 0:
            return os.path.basename(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def get_project_name() -> str:
    """Get the project name where this MCP server is running.

    Detects the project from the git repo root, falling back to
    the current directory name. Used for device identity (not user
    identity — the user/agent name is a separate concern).

    Priority:
      1. Git repo root basename (if in a git repo)
      2. Current directory basename (final fallback)
    """
    git_name = _get_git_repo_name()
    if git_name:
        return git_name
    return os.path.basename(os.getcwd())


def get_device_id() -> str:
    """Generate a deterministic device ID from project+hostname.

    Same project on same machine = same device ID = connection takeover.
    Different project or machine = different device ID = coexists.

    The device represents WHERE an agent is running, not WHO the agent is.
    User identity (who) is handled by agent registration (hooks/CLI).

    Format: dev-{24 hex chars} (matches gateway regex: /^dev-[0-9a-f]{24}$/)
    """
    project = get_project_name()
    host = get_host()

    seed = f"{project}@{host}"
    hex_hash = hashlib.sha256(seed.encode()).hexdigest()[:24]
    return f"dev-{hex_hash}"


def get_device_name() -> str:
    """Get the human-readable device name for dashboard display.

    Shows where this instance is running: project@host.
    E.g., "voicemode@mba", "share-trading@mbp"
    """
    project = get_project_name()
    host = get_host()
    return f"{project}@{host}"


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
