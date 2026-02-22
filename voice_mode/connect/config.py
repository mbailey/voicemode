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
    """Get the project name for this MCP server instance.

    Priority:
      1. VOICEMODE_CONNECT_USER env var (explicit single user override)
      2. VOICEMODE_CONNECT_USERS[0] (legacy plural, first entry)
      3. Git repo root basename (if in a git repo)
      4. Current directory basename (final fallback)
    """
    # 1. Explicit single-user override
    single_user = os.environ.get("VOICEMODE_CONNECT_USER", "").strip()
    if single_user:
        return single_user

    # 2. Legacy plural users list
    configured = get_preconfigured_users()
    if configured:
        return configured[0]

    # 3. Git repo root name
    git_name = _get_git_repo_name()
    if git_name:
        return git_name

    # 4. Fallback to cwd basename
    return os.path.basename(os.getcwd())


def get_device_id() -> str:
    """Generate a deterministic device ID from project+hostname.

    Same project on same machine = same device ID = connection takeover.
    Different project or machine = different device ID = coexists.

    Format: dev-{24 hex chars} (matches gateway regex: /^dev-[0-9a-f]{24}$/)
    """
    project = get_project_name()
    host = get_host()

    seed = f"{project}@{host}"
    hex_hash = hashlib.sha256(seed.encode()).hexdigest()[:24]
    return f"dev-{hex_hash}"


def get_device_name() -> str:
    """Get the human-readable device name for dashboard display.

    Format: {project}@{host} (e.g., "voicemode@mba")
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
