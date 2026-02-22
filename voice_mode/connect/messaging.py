"""Message delivery for VoiceMode Connect."""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("voicemode")


def deliver_message(
    user_dir: Path,
    text: str,
    sender: str = "user",
    source: str = "dashboard",
    message_id: Optional[str] = None,
) -> dict:
    """Deliver a message to a user's inbox.

    Always writes to the persistent inbox (JSONL append).
    If inbox-live symlink exists and is valid, also writes to Claude inbox.

    Returns:
        dict with message fields and delivery status
    """
    msg_id = message_id or f"msg_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    message = {
        "id": msg_id,
        "from": sender,
        "text": text,
        "timestamp": now.isoformat(),
        "source": source,
    }

    # Always write to persistent inbox (JSONL — append-only)
    _write_persistent_inbox(user_dir / "inbox", message)

    # Try to write to live inbox (Claude team inbox via symlink)
    delivered = False
    symlink = user_dir / "inbox-live"
    if symlink.is_symlink():
        try:
            delivered = _write_live_inbox(symlink, text, sender, source, now)
        except Exception as e:
            logger.warning(f"Live inbox delivery failed: {e}")

    # Return delivery status for caller (e.g., to send confirmation back via gateway)
    message["delivered"] = delivered
    return message


def read_inbox(
    user_dir: Path,
    since: Optional[datetime] = None,
    limit: int = 100,
) -> list[dict]:
    """Read messages from a user's persistent inbox.

    Args:
        user_dir: Path to user directory
        since: Only return messages after this timestamp
        limit: Maximum messages to return (most recent)

    Returns:
        List of message dicts
    """
    inbox_path = user_dir / "inbox"
    if not inbox_path.exists():
        return []

    messages = []
    for line in inbox_path.read_text().strip().splitlines():
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
            # Skip delivery confirmations when reading messages
            if msg.get("type") == "delivery_confirmation":
                continue
            if since:
                msg_time = datetime.fromisoformat(msg["timestamp"])
                if msg_time <= since:
                    continue
            messages.append(msg)
        except (json.JSONDecodeError, KeyError):
            logger.warning(f"Skipping malformed inbox line: {line[:80]}")
            continue

    # Return most recent messages up to limit
    return messages[-limit:]


def _write_persistent_inbox(inbox_path: Path, message: dict) -> None:
    """Append a message to the JSONL inbox file."""
    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    with open(inbox_path, "a") as f:
        f.write(json.dumps(message) + "\n")


def _write_live_inbox(symlink_path: Path, text: str, sender: str, source: str, timestamp: datetime) -> bool:
    """Write a message to the Claude inbox via the inbox-live symlink.

    Claude Code expects a JSON array of message objects.
    Reads existing array, appends new message, writes back.
    Returns True if delivery succeeded.
    """
    try:
        target = symlink_path.resolve()
        if not target.parent.exists():
            logger.debug("Live inbox target directory doesn't exist")
            return False

        # Read existing messages
        existing = []
        if target.exists():
            try:
                content = target.read_text().strip()
                if content:
                    existing = json.loads(content)
            except (json.JSONDecodeError, OSError):
                existing = []

        # Append new message in Claude Code team inbox format
        claude_message = {
            "from": sender,
            "text": text,
            "summary": text[:50] if len(text) > 50 else text,
            "timestamp": timestamp.isoformat(),
            "read": False,
        }
        existing.append(claude_message)

        # Write back
        target.write_text(json.dumps(existing, indent=2) + "\n")
        return True

    except OSError as e:
        logger.warning(f"Failed to write live inbox: {e}")
        return False
