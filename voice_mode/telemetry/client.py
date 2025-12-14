"""
Telemetry HTTP client.

Handles transmission of telemetry events to the backend endpoint with
retry logic, rate limiting, and offline queueing support.
"""

import json
import logging
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from urllib.parse import urljoin

import httpx

from voice_mode import config

logger = logging.getLogger(__name__)


class TelemetryClient:
    """
    HTTP client for sending telemetry events to backend.

    Features:
    - Configurable endpoint URL
    - Event deduplication via event IDs
    - Retry logic with exponential backoff
    - Offline queueing for later transmission
    - Request timeout and error handling
    """

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        timeout: float = 10.0,
        max_retries: int = 3,
    ):
        """
        Initialize the telemetry client.

        Args:
            endpoint_url: Backend endpoint URL (will be configurable via env var)
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        # Endpoint URL will come from config in tel-006
        # For now, accept as parameter but don't hardcode
        self.endpoint_url = endpoint_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.queue_dir = config.BASE_DIR / "telemetry_queue"

        # Ensure queue directory exists
        self.queue_dir.mkdir(parents=True, exist_ok=True)

    def _generate_event_id(self, event_data: Dict[str, Any]) -> str:
        """
        Generate a unique, deterministic event ID.

        Uses a hash of telemetry_id + timestamp to create an idempotent
        event identifier that prevents duplicate submissions.

        Args:
            event_data: Event data dictionary

        Returns:
            Hexadecimal event ID string
        """
        # Create stable hash from telemetry_id and timestamp
        id_string = f"{event_data.get('telemetry_id', '')}:{event_data.get('timestamp', '')}"
        event_hash = hashlib.sha256(id_string.encode()).hexdigest()
        return event_hash[:16]  # Use first 16 chars for brevity

    def send_event(self, event_data: Dict[str, Any]) -> bool:
        """
        Send a telemetry event to the backend.

        Args:
            event_data: Event data dictionary from TelemetryCollector

        Returns:
            True if event was sent successfully, False otherwise
        """
        if not self.endpoint_url:
            logger.debug("No telemetry endpoint configured, skipping send")
            return False

        # Generate event ID for idempotency
        event_id = self._generate_event_id(event_data)

        # Add event ID to payload
        payload = {
            "event_id": event_id,
            **event_data
        }

        # Attempt to send with retries
        for attempt in range(self.max_retries):
            try:
                response = httpx.post(
                    self.endpoint_url,
                    json=payload,
                    timeout=self.timeout,
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": f"VoiceMode/{event_data.get('environment', {}).get('version', 'unknown')}",
                    }
                )

                if response.status_code == 200:
                    logger.debug(f"Telemetry event sent successfully: {event_id}")
                    return True
                elif response.status_code == 429:
                    logger.warning("Telemetry rate limit exceeded, will retry later")
                    self._queue_event(payload)
                    return False
                else:
                    logger.warning(
                        f"Telemetry send failed with status {response.status_code}: {response.text}"
                    )

            except httpx.TimeoutException:
                logger.warning(f"Telemetry send timeout (attempt {attempt + 1}/{self.max_retries})")
            except httpx.ConnectError:
                logger.debug("Telemetry endpoint not reachable (offline?)")
                break  # Don't retry connection errors
            except Exception as e:
                logger.error(f"Unexpected error sending telemetry: {e}")
                break

        # If all retries failed, queue for later
        self._queue_event(payload)
        return False

    def _queue_event(self, event_data: Dict[str, Any]) -> None:
        """
        Queue an event for later transmission.

        Stores event in local queue directory for retry when connection
        is restored.

        Args:
            event_data: Event data to queue
        """
        try:
            event_id = event_data.get("event_id", "unknown")
            queue_file = self.queue_dir / f"event_{event_id}.json"

            with open(queue_file, 'w') as f:
                json.dump(event_data, f, indent=2)

            logger.debug(f"Event queued for later transmission: {event_id}")

        except Exception as e:
            logger.error(f"Failed to queue telemetry event: {e}")

    def send_queued_events(self) -> int:
        """
        Send all queued events.

        Attempts to transmit all events that were previously queued due
        to connection failures or rate limiting.

        Returns:
            Number of events successfully sent
        """
        if not self.endpoint_url:
            logger.debug("No telemetry endpoint configured, skipping queued events")
            return 0

        sent_count = 0
        queued_files = list(self.queue_dir.glob("event_*.json"))

        for queue_file in queued_files:
            try:
                with open(queue_file, 'r') as f:
                    event_data = json.load(f)

                if self._send_queued_event(event_data):
                    # Remove from queue on success
                    queue_file.unlink()
                    sent_count += 1
                else:
                    # Keep in queue for later retry
                    logger.debug(f"Keeping {queue_file.name} in queue")

            except Exception as e:
                logger.error(f"Error processing queued event {queue_file}: {e}")
                continue

        if sent_count > 0:
            logger.info(f"Sent {sent_count} queued telemetry events")

        return sent_count

    def _send_queued_event(self, event_data: Dict[str, Any]) -> bool:
        """
        Send a single queued event.

        Args:
            event_data: Event data from queue

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            response = httpx.post(
                self.endpoint_url,
                json=event_data,
                timeout=self.timeout,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": f"VoiceMode/{event_data.get('environment', {}).get('version', 'unknown')}",
                }
            )

            if response.status_code == 200:
                return True
            elif response.status_code == 429:
                logger.debug("Rate limit still in effect, keeping event queued")
                return False
            else:
                logger.warning(
                    f"Queued event send failed with status {response.status_code}"
                )
                return False

        except Exception as e:
            logger.debug(f"Failed to send queued event: {e}")
            return False

    def clear_old_queued_events(self, max_age_days: int = 7) -> int:
        """
        Clear old queued events to prevent unbounded queue growth.

        Args:
            max_age_days: Maximum age in days before events are discarded

        Returns:
            Number of events cleared
        """
        cleared_count = 0
        cutoff_time = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)

        for queue_file in self.queue_dir.glob("event_*.json"):
            try:
                # Check file modification time
                if queue_file.stat().st_mtime < cutoff_time:
                    queue_file.unlink()
                    cleared_count += 1

            except Exception as e:
                logger.error(f"Error clearing old event {queue_file}: {e}")
                continue

        if cleared_count > 0:
            logger.info(f"Cleared {cleared_count} old queued telemetry events")

        return cleared_count

    def get_queue_size(self) -> int:
        """
        Get the number of events in the queue.

        Returns:
            Number of queued events
        """
        return len(list(self.queue_dir.glob("event_*.json")))
