"""Agent inbox messaging for VoiceMode Connect.

Delivers messages to agent inboxes as JSON arrays, with optional
live-inbox symlink support for Claude Code team integration.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("voicemode")

AGENTS_DIR = Path.home() / ".voicemode" / "agents"


def deliver_message(agent_name: str, text: str, sender: str = "user", summary: str | None = None) -> dict:
    """Deliver a message to an agent's inbox (and live-inbox if linked).

    Args:
        agent_name: Target agent name.
        text: Message content.
        sender: Who sent the message.
        summary: Short summary (auto-generated from text if not provided).

    Returns:
        Dict with delivered_to list and agent_name.
    """
    if summary is None:
        summary = text[:50]

    message = {
        "from": sender,
        "text": text,
        "summary": summary,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "read": False,
    }

    agent_dir = AGENTS_DIR / agent_name
    delivered_to = []

    # Always write to inbox
    inbox = agent_dir / "inbox"
    _append_message(inbox, message)
    delivered_to.append("inbox")

    # Write to live-inbox if symlink exists and resolves
    live_inbox = agent_dir / "live-inbox"
    if live_inbox.is_symlink() and live_inbox.resolve().parent.exists():
        _append_message(live_inbox, message)
        delivered_to.append("live-inbox")

    return {"delivered_to": delivered_to, "agent_name": agent_name}


def setup_live_inbox(agent_name: str, team_name: str, recipient: str = "team-lead") -> Path:
    """Create a live-inbox symlink pointing to a Claude Code team inbox.

    Args:
        agent_name: Agent whose live-inbox to configure.
        team_name: Claude Code team name.
        recipient: Team member inbox to target.

    Returns:
        The symlink path.
    """
    target = Path.home() / ".claude" / "teams" / team_name / "inboxes" / f"{recipient}.json"
    target.parent.mkdir(parents=True, exist_ok=True)

    symlink = AGENTS_DIR / agent_name / "live-inbox"
    symlink.parent.mkdir(parents=True, exist_ok=True)

    if symlink.is_symlink() or symlink.exists():
        symlink.unlink()
    symlink.symlink_to(target)

    logger.info(f"Messaging: live-inbox for '{agent_name}' -> {target}")
    return symlink


def _append_message(path: Path, message: dict):
    """Append a message to a JSON array file, creating it if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    messages = []
    if path.exists():
        try:
            messages = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            messages = []
    messages.append(message)
    path.write_text(json.dumps(messages, indent=2) + "\n")
