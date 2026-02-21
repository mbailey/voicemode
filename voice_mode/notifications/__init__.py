"""Pluggable notification system for VoiceMode converse tool.

Notifications piggyback on converse responses — like badge counts on phone apps.
Sources are executable commands configured in ~/.voicemode/notifications.json.

Read-only: notifications NEVER modify source data. Commands must be side-effect-free.
"""

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("voicemode")

VOICEMODE_DIR = Path.home() / ".voicemode"
NOTIFICATIONS_CONFIG_PATH = VOICEMODE_DIR / "notifications.json"


def _format_for_level(name: str, data: dict, level: str) -> str:
    """Format notification data according to the requested level."""
    count = data["count"]

    if level == "detail" and "detail" in data:
        items = data["detail"][:3]
        parts = [f"{item.get('from', '?')}: {item.get('text', '')}" for item in items]
        remaining = count - len(items)
        if remaining > 0:
            parts.append(f"+{remaining} more")
        return "; ".join(parts)

    if level in ("summary", "detail") and "summary" in data:
        return data["summary"]

    return f"{count} from {name}"


def parse_source_output(name: str, stdout: str, level: str = "count") -> Optional[dict]:
    """Parse notification source output with increasing leniency.

    Returns: {"count": int, "display": str} or None if unparseable/zero.
    """
    text = stdout.strip()
    if not text:
        return None

    # 1. Try JSON object — richest format, supports all levels
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "count" in data:
            count = int(data["count"])
            if count == 0:
                return None
            display = _format_for_level(name, data, level)
            return {"count": count, "display": display}
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # 2. Try plain integer (only supports count level)
    try:
        count = int(text)
        if count == 0:
            return None
        return {"count": count, "display": f"{count} from {name}"}
    except ValueError:
        pass

    # 3. Try extracting leading number from text ("3 messages", "17 notifications")
    match = re.match(r'^(\d+)\s+(.+)', text)
    if match:
        count = int(match.group(1))
        if count == 0:
            return None
        description = match.group(2).strip()
        return {"count": count, "display": f"{count} {description}"}

    # 4. Give up — log warning, skip this source
    logger.warning(f"Notification source '{name}' returned unparseable output: {text[:80]}")
    return None


class NotificationManager:
    """Runs notification source commands and aggregates results.

    Read-only: never modifies source data. Commands must be side-effect-free.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or NOTIFICATIONS_CONFIG_PATH
        self.config = self._load_config()
        self.global_level = self.config.get("level", "count")
        self.sources = self.config.get("sources", [])

    def _load_config(self) -> dict:
        """Load notifications.json config file."""
        if not self.config_path.exists():
            return {"sources": []}
        try:
            with open(self.config_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load notifications config: {e}")
            return {"sources": []}

    def check_all(self) -> str:
        """Run all source commands, return formatted notification string or empty."""
        if not self.sources:
            return ""
        notifications = []
        for source in self.sources:
            level = source.get("level", self.global_level)
            result = self._run_source(source, level)
            if result and result["count"] > 0:
                notifications.append(result["display"])
        if not notifications:
            return ""
        return " | Notifications: " + ", ".join(notifications)

    def _run_source(self, source: dict, level: str) -> Optional[dict]:
        """Run a single source command with timeout. Read-only."""
        try:
            proc = subprocess.run(
                source["command"],
                shell=True,
                capture_output=True,
                text=True,
                timeout=source.get("timeout", 5),
            )
            if proc.returncode != 0:
                logger.warning(f"Notification source '{source['name']}' exited {proc.returncode}")
                return None
            return parse_source_output(source["name"], proc.stdout, level)
        except subprocess.TimeoutExpired:
            logger.warning(f"Notification source '{source['name']}' timed out")
            return None
        except Exception as e:
            logger.warning(f"Notification source '{source['name']}' failed: {e}")
            return None


def ensure_default_config():
    """Auto-generate default notifications.json when Connect + notifications are both enabled.

    Only creates the file if it doesn't already exist.
    """
    if NOTIFICATIONS_CONFIG_PATH.exists():
        return

    NOTIFICATIONS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    default_config = {
        "level": "count",
        "sources": [
            {
                "name": "connect-inbox",
                "command": "voicemode notifications check-inbox",
                "timeout": 5
            }
        ]
    }
    try:
        with open(NOTIFICATIONS_CONFIG_PATH, 'w') as f:
            json.dump(default_config, f, indent=2)
            f.write("\n")
        logger.info(f"Created default notifications config at {NOTIFICATIONS_CONFIG_PATH}")
    except OSError as e:
        logger.warning(f"Failed to create default notifications config: {e}")


# Module-level notification manager instance (lazy-initialized)
_notification_manager: Optional[NotificationManager] = None


def get_notification_manager() -> Optional[NotificationManager]:
    """Get or create the notification manager singleton.

    Returns None if notifications are disabled.
    """
    global _notification_manager
    if _notification_manager is not None:
        return _notification_manager

    from voice_mode.config import NOTIFICATIONS_ENABLED, CONNECT_ENABLED

    if not NOTIFICATIONS_ENABLED:
        return None

    # Auto-generate default config if Connect is enabled
    if CONNECT_ENABLED:
        ensure_default_config()

    _notification_manager = NotificationManager()
    if _notification_manager.sources:
        logger.info(f"Notifications enabled with {len(_notification_manager.sources)} source(s)")
    else:
        logger.info("Notifications enabled but no sources configured")
    return _notification_manager
