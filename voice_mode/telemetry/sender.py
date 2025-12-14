"""
Telemetry auto-send module.

Handles automatic telemetry sending on MCP server startup with:
- 24-hour cooldown between sends
- Non-blocking background execution
- Local logging for transparency
"""

import asyncio
import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from voice_mode import config
from voice_mode.telemetry.collector import TelemetryCollector
from voice_mode.telemetry.client import TelemetryClient

logger = logging.getLogger(__name__)

# Constants
COOLDOWN_HOURS = 24
TELEMETRY_DIR = config.BASE_DIR / "telemetry"
LOGS_DIR = config.BASE_DIR / "logs" / "telemetry"
LAST_SEND_FILE = TELEMETRY_DIR / "last_send"
MAX_LOG_AGE_DAYS = 30


def get_last_send_time() -> Optional[datetime]:
    """Get the timestamp of the last telemetry send.

    Returns:
        datetime if last_send file exists and is valid, None otherwise
    """
    if not LAST_SEND_FILE.exists():
        return None

    try:
        timestamp_str = LAST_SEND_FILE.read_text().strip()
        return datetime.fromisoformat(timestamp_str)
    except (ValueError, OSError) as e:
        logger.debug(f"Failed to read last send time: {e}")
        return None


def update_last_send_time() -> None:
    """Update the last send timestamp to now."""
    TELEMETRY_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    LAST_SEND_FILE.write_text(timestamp)


def should_send_telemetry() -> bool:
    """Determine if telemetry should be sent.

    Returns True if:
    - Telemetry is enabled
    - Endpoint is configured
    - At least COOLDOWN_HOURS have passed since last send (or never sent)
    """
    # Check if telemetry is enabled
    if not config.is_telemetry_enabled():
        logger.debug("Telemetry not enabled, skipping send")
        return False

    # Check if endpoint is configured
    if not config.VOICEMODE_TELEMETRY_ENDPOINT:
        logger.debug("No telemetry endpoint configured, skipping send")
        return False

    # Check cooldown
    last_send = get_last_send_time()
    if last_send is not None:
        now = datetime.now(timezone.utc)
        hours_since_last = (now - last_send).total_seconds() / 3600
        if hours_since_last < COOLDOWN_HOURS:
            logger.debug(
                f"Telemetry sent {hours_since_last:.1f} hours ago, "
                f"waiting until {COOLDOWN_HOURS} hours have passed"
            )
            return False

    return True


def log_telemetry_payload(payload: dict) -> None:
    """Save telemetry payload to local log file for transparency.

    Creates a date-stamped JSON file in ~/.voicemode/logs/telemetry/
    so users can audit exactly what data was sent.

    Args:
        payload: The telemetry event payload that was sent
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    log_file = LOGS_DIR / f"telemetry_{today}.json"

    try:
        # Append to existing file or create new one
        if log_file.exists():
            # Read existing content
            with open(log_file, 'r') as f:
                try:
                    existing = json.load(f)
                    if not isinstance(existing, list):
                        existing = [existing]
                except json.JSONDecodeError:
                    existing = []
            existing.append(payload)
        else:
            existing = [payload]

        # Write with pretty formatting for readability
        with open(log_file, 'w') as f:
            json.dump(existing, f, indent=2, default=str)

        logger.info(f"Telemetry payload logged to: {log_file}")

    except Exception as e:
        logger.warning(f"Failed to log telemetry payload: {e}")


def cleanup_old_logs() -> int:
    """Remove telemetry log files older than MAX_LOG_AGE_DAYS.

    Returns:
        Number of files removed
    """
    if not LOGS_DIR.exists():
        return 0

    removed = 0
    cutoff = datetime.now(timezone.utc).timestamp() - (MAX_LOG_AGE_DAYS * 86400)

    for log_file in LOGS_DIR.glob("telemetry_*.json"):
        try:
            if log_file.stat().st_mtime < cutoff:
                log_file.unlink()
                removed += 1
                logger.debug(f"Removed old telemetry log: {log_file.name}")
        except Exception as e:
            logger.warning(f"Failed to remove old log {log_file}: {e}")

    if removed:
        logger.info(f"Cleaned up {removed} old telemetry log files")

    return removed


def send_telemetry_sync() -> bool:
    """Synchronous telemetry send function.

    Collects telemetry data and sends to configured endpoint.
    Logs the payload locally for transparency.

    Returns:
        True if send was successful, False otherwise
    """
    try:
        # Collect telemetry event
        collector = TelemetryCollector()
        event = collector.collect_telemetry_event()

        if not event:
            logger.warning("No telemetry data collected")
            return False

        # Log the payload locally before sending (transparency)
        log_telemetry_payload(event)

        # Send to endpoint
        client = TelemetryClient(endpoint_url=config.VOICEMODE_TELEMETRY_ENDPOINT)
        success = client.send_event(event)

        if success:
            update_last_send_time()
            logger.info("Telemetry sent successfully")
            # Clean up old logs while we're at it
            cleanup_old_logs()
            # Also try to send any queued events
            queued = client.send_queued_events()
            if queued:
                logger.info(f"Also sent {queued} queued telemetry events")
        else:
            logger.warning("Telemetry send failed (will retry later)")

        return success

    except Exception as e:
        logger.error(f"Error sending telemetry: {e}")
        return False


def maybe_send_telemetry_background() -> None:
    """Send telemetry in a background thread if appropriate.

    This is the main entry point called from server startup.
    Runs telemetry send in a separate thread to avoid blocking.
    """
    if not should_send_telemetry():
        return

    def _send_in_background():
        try:
            logger.info("Starting background telemetry send...")
            send_telemetry_sync()
        except Exception as e:
            logger.error(f"Background telemetry send failed: {e}")

    # Run in background thread to avoid blocking server startup
    thread = threading.Thread(target=_send_in_background, daemon=True)
    thread.start()
    logger.debug("Telemetry send initiated in background thread")


async def maybe_send_telemetry_async() -> bool:
    """Async version of telemetry send for use in async contexts.

    Returns:
        True if telemetry was sent successfully, False otherwise
    """
    if not should_send_telemetry():
        return False

    # Run the sync function in a thread pool to not block the event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, send_telemetry_sync)
