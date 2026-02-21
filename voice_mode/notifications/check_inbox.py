"""Built-in notification source: Check Connect inboxes for new messages.

Read-only: uses watermark file to track position. Never modifies inbox files.
Watermarks are the notification system's own state, not the inbox's.
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("voicemode")

VOICEMODE_DIR = Path.home() / ".voicemode"
USERS_DIR = VOICEMODE_DIR / "connect" / "users"
WATERMARK_DIR = VOICEMODE_DIR / "notifications"
WATERMARK_FILE = WATERMARK_DIR / "inbox-watermarks.json"


def load_watermarks(watermark_file: Optional[Path] = None) -> dict:
    """Load byte-offset watermarks from file."""
    path = watermark_file or WATERMARK_FILE
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load watermarks: {e}")
        return {}


def save_watermarks(watermarks: dict, watermark_file: Optional[Path] = None):
    """Save byte-offset watermarks to file."""
    path = watermark_file or WATERMARK_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, 'w') as f:
            json.dump(watermarks, f, indent=2)
            f.write("\n")
    except OSError as e:
        logger.warning(f"Failed to save watermarks: {e}")


def read_new_messages(inbox: Path, offset: int) -> list:
    """Read new JSONL messages from inbox starting at byte offset.

    Skips delivery_confirmation entries and non-JSON lines.
    """
    messages = []
    try:
        with open(inbox, 'r') as f:
            f.seek(offset)
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    # Skip delivery confirmations and system messages
                    msg_type = msg.get("type", "")
                    if msg_type == "delivery_confirmation":
                        continue
                    messages.append(msg)
                except json.JSONDecodeError:
                    continue
    except OSError as e:
        logger.warning(f"Failed to read inbox {inbox}: {e}")
    return messages


def check_inbox_messages(
    users_dir: Optional[Path] = None,
    watermark_file: Optional[Path] = None,
) -> dict:
    """Check Connect inboxes for new messages since last check.

    Returns dict with count, summary, and detail fields (all notification levels).
    First check sets baseline — no flood of old messages on startup.

    Args:
        users_dir: Override users directory (for testing)
        watermark_file: Override watermark file (for testing)
    """
    udir = users_dir or USERS_DIR
    wfile = watermark_file or WATERMARK_FILE
    watermarks = load_watermarks(wfile)

    total_new = 0
    by_sender: dict[str, list] = {}

    if not udir.exists():
        save_watermarks(watermarks, wfile)
        return {"count": 0}

    for user_dir in sorted(udir.iterdir()):
        if not user_dir.is_dir():
            continue
        inbox = user_dir / "inbox"
        if not inbox.exists():
            continue

        name = user_dir.name
        try:
            current_size = inbox.stat().st_size
        except OSError:
            continue

        last_size = watermarks.get(name)

        if last_size is None:
            # First check: set baseline, no notifications
            watermarks[name] = current_size
            continue

        if current_size > last_size:
            new_messages = read_new_messages(inbox, last_size)
            for msg in new_messages:
                sender = msg.get("from", name)
                preview = str(msg.get("text", ""))[:50]
                by_sender.setdefault(sender, []).append({"text": preview})
                total_new += 1

        watermarks[name] = current_size

    save_watermarks(watermarks, wfile)

    output: dict = {"count": total_new}
    if total_new > 0:
        sender_parts = [f"{len(msgs)} from {sender}" for sender, msgs in by_sender.items()]
        output["summary"] = f"{total_new} messages ({', '.join(sender_parts)})"
        output["detail"] = [
            {"from": sender, "count": len(msgs), "text": msgs[0]["text"]}
            for sender, msgs in by_sender.items()
        ]

    return output
