"""
Telemetry data collector.

Gathers telemetry data from existing VoiceMode logs including events and
conversations, applying privacy protections and aggregating into useful metrics.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import defaultdict

from voice_mode.telemetry.privacy import (
    bin_duration,
    bin_size,
    anonymize_path,
    anonymize_error_message,
    sanitize_version_string,
)
from voice_mode import config

logger = logging.getLogger(__name__)


class TelemetryCollector:
    """
    Collects telemetry data from VoiceMode logs.

    Analyzes event logs and conversation logs to extract privacy-preserving
    usage metrics including session statistics, provider usage, and error rates.
    """

    def __init__(self, logs_dir: Optional[Path] = None):
        """
        Initialize the telemetry collector.

        Args:
            logs_dir: Base directory for logs (defaults to config.LOGS_DIR)
        """
        self.logs_dir = logs_dir or config.LOGS_DIR
        self.events_dir = Path(self.logs_dir) / "events"
        self.conversations_dir = Path(self.logs_dir) / "conversations"

    def collect_session_data(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Collect aggregated session data from conversation logs.

        Uses conversation logs (exchanges_*.jsonl) which have conversation_id
        to accurately track multi-exchange conversations rather than individual
        tool calls.

        Args:
            start_date: Start date for data collection (inclusive)
            end_date: End date for data collection (inclusive)

        Returns:
            Dictionary with session statistics including:
            - total_conversations: Number of conversations (multi-exchange sessions)
            - total_exchanges: Total TTS/STT exchanges across all conversations
            - duration_distribution: Binned conversation durations
            - exchanges_per_conversation: Distribution of exchanges per conversation
            - transport_usage: Counts by transport type (local/livekit)
            - provider_usage: TTS and STT provider usage counts
        """
        if not self.conversations_dir.exists():
            logger.warning(f"Conversations directory does not exist: {self.conversations_dir}")
            return {}

        conversations: Dict[str, Dict] = {}

        # Process conversation log files
        for log_file in sorted(self.conversations_dir.glob("exchanges_*.jsonl")):
            # Check date filter if provided
            if start_date or end_date:
                file_date = self._extract_exchange_date_from_filename(log_file.name)
                if file_date:
                    if start_date and file_date < start_date.date():
                        continue
                    if end_date and file_date > end_date.date():
                        continue

            try:
                with open(log_file, 'r') as f:
                    for line in f:
                        if not line.strip():
                            continue

                        try:
                            exchange = json.loads(line)
                            self._process_exchange(exchange, conversations)
                        except json.JSONDecodeError:
                            logger.debug(f"Skipping invalid JSON line in {log_file}")
                            continue
            except Exception as e:
                logger.error(f"Error processing {log_file}: {e}")
                continue

        # Aggregate statistics from conversations
        return self._aggregate_conversation_stats(conversations)

    def _process_exchange(self, exchange: Dict, conversations: Dict[str, Dict]) -> None:
        """
        Process a single exchange and update conversation tracking.

        Args:
            exchange: Exchange dictionary from JSONL conversation log
            conversations: Conversations dictionary to update
        """
        conv_id = exchange.get("conversation_id")
        timestamp_str = exchange.get("timestamp")
        exchange_type = exchange.get("type")  # "tts" or "stt"
        metadata = exchange.get("metadata", {})

        if not conv_id or not timestamp_str:
            return

        # Initialize conversation if new
        if conv_id not in conversations:
            conversations[conv_id] = {
                "start_time": None,
                "end_time": None,
                "tts_count": 0,
                "stt_count": 0,
                "tts_providers": set(),
                "stt_providers": set(),
                "transport": None,
            }

        conv = conversations[conv_id]

        # Parse timestamp
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        except ValueError:
            return

        # Update conversation timing
        if not conv["start_time"]:
            conv["start_time"] = timestamp
        conv["end_time"] = timestamp

        # Count exchanges by type
        if exchange_type == "tts":
            conv["tts_count"] += 1
            # Track TTS provider
            provider = metadata.get("provider")
            if provider:
                normalized = self._normalize_provider_name(provider)
                conv["tts_providers"].add(normalized)
        elif exchange_type == "stt":
            conv["stt_count"] += 1
            # Track STT provider - check provider_url first for local providers
            provider_url = metadata.get("provider_url", "")
            provider = metadata.get("provider", "")
            # Use the more specific provider name if available
            if provider_url:
                normalized = self._normalize_provider_name(provider_url)
            elif provider:
                normalized = self._normalize_provider_name(provider)
            else:
                normalized = "unknown"
            conv["stt_providers"].add(normalized)

        # Track transport
        transport = metadata.get("transport")
        if transport:
            conv["transport"] = transport

    def _normalize_provider_name(self, provider: str) -> str:
        """
        Normalize provider name to a consistent format.

        Args:
            provider: Provider name or URL string

        Returns:
            Normalized provider name (e.g., "openai", "kokoro", "whisper-local")
        """
        if not provider:
            return "unknown"

        provider_lower = provider.lower()

        # OpenAI
        if "openai.com" in provider_lower or provider_lower == "openai":
            return "openai"

        # Kokoro TTS
        if "8880" in provider_lower or provider_lower == "kokoro":
            return "kokoro"

        # Local Whisper STT
        if "2022" in provider_lower or provider_lower in ("whisper-local", "whisper"):
            return "whisper-local"

        # OpenAI Whisper (cloud)
        if "openai-whisper" in provider_lower:
            return "openai-whisper"

        # No-op (for testing)
        if provider_lower == "no-op":
            return "no-op"

        # Other known names - return as-is if simple
        if provider_lower.replace("-", "").replace("_", "").isalnum():
            return provider_lower

        # For URLs or complex strings, anonymize
        return "other"

    def _extract_provider_name(self, provider_url: str) -> Optional[str]:
        """
        Extract provider name from URL (legacy method, use _normalize_provider_name).

        Args:
            provider_url: Provider URL string

        Returns:
            Provider name (e.g., "openai", "kokoro", "whisper-local")
        """
        return self._normalize_provider_name(provider_url) if provider_url else None

    def _extract_date_from_filename(self, filename: str) -> Optional[Any]:
        """
        Extract date from log filename.

        Args:
            filename: Log filename (e.g., "voicemode_events_2025-07-29.jsonl")

        Returns:
            Date object or None if parsing fails
        """
        try:
            # Extract YYYY-MM-DD from filename
            parts = filename.replace("voicemode_events_", "").replace(".jsonl", "")
            return datetime.strptime(parts, "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            return None

    def _extract_exchange_date_from_filename(self, filename: str) -> Optional[Any]:
        """
        Extract date from exchange log filename.

        Args:
            filename: Log filename (e.g., "exchanges_2025-07-29.jsonl")

        Returns:
            Date object or None if parsing fails
        """
        try:
            # Extract YYYY-MM-DD from filename
            parts = filename.replace("exchanges_", "").replace(".jsonl", "")
            return datetime.strptime(parts, "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            return None

    def _aggregate_conversation_stats(self, conversations: Dict[str, Dict]) -> Dict[str, Any]:
        """
        Aggregate statistics from all conversations.

        Args:
            conversations: Dictionary of conversation data

        Returns:
            Aggregated statistics dictionary
        """
        duration_bins = defaultdict(int)
        exchange_bins = defaultdict(int)
        transport_counts = defaultdict(int)
        tts_provider_counts = defaultdict(int)
        stt_provider_counts = defaultdict(int)

        total_conversations = len(conversations)
        total_exchanges = 0

        for conv in conversations.values():
            # Calculate conversation duration
            if conv["start_time"] and conv["end_time"]:
                duration_seconds = (conv["end_time"] - conv["start_time"]).total_seconds()
                duration_bin = bin_duration(duration_seconds)
                duration_bins[duration_bin] += 1

            # Count total exchanges (TTS + STT)
            exchanges = conv["tts_count"] + conv["stt_count"]
            total_exchanges += exchanges

            # Bin exchange counts (privacy-preserving)
            if exchanges == 0:
                exchange_bin = "0"
            elif exchanges <= 5:
                exchange_bin = "1-5"
            elif exchanges <= 10:
                exchange_bin = "6-10"
            elif exchanges <= 20:
                exchange_bin = "11-20"
            else:
                exchange_bin = ">20"
            exchange_bins[exchange_bin] += 1

            # Transport usage
            if conv["transport"]:
                transport_counts[conv["transport"]] += 1

            # Provider usage (from conversation metadata)
            for provider in conv["tts_providers"]:
                tts_provider_counts[provider] += 1
            for provider in conv["stt_providers"]:
                stt_provider_counts[provider] += 1

        return {
            "total_sessions": total_conversations,
            "total_exchanges": total_exchanges,
            "duration_distribution": dict(duration_bins),
            "exchanges_per_session": dict(exchange_bins),
            "transport_usage": dict(transport_counts),
            "provider_usage": {
                "tts": dict(tts_provider_counts),
                "stt": dict(stt_provider_counts),
            },
        }

    def collect_environment_data(self) -> Dict[str, Any]:
        """
        Collect environment and configuration data.

        Returns:
            Dictionary with environment information:
            - os: Operating system (matches worker schema)
            - install_method: Installation method (dev/uv/pip)
            - mcp_host: MCP host application (if applicable)
            - exec_source: Execution source (mcp/cli)
            - version: VoiceMode version (sanitized)
        """
        from voice_mode import __version__

        env_info = config.get_environment_info()

        return {
            "os": env_info.get("os_type"),  # Worker expects "os" not "os_type"
            "install_method": env_info.get("install_method"),
            "mcp_host": env_info.get("mcp_host"),
            "exec_source": env_info.get("exec_source"),
            "version": sanitize_version_string(__version__),
        }

    def collect_telemetry_event(self) -> Dict[str, Any]:
        """
        Collect a complete telemetry event payload.

        Combines session data and environment data into a single event
        suitable for transmission to telemetry backend.

        Returns:
            Complete telemetry event dictionary
        """
        # Get environment data
        env_data = self.collect_environment_data()

        # Get session data (last 24 hours by default)
        end_date = datetime.now(timezone.utc)
        start_date = end_date.replace(hour=0, minute=0, second=0, microsecond=0)
        session_data = self.collect_session_data(start_date, end_date)

        # Get telemetry ID from config
        telemetry_id = config.TELEMETRY_ID

        return {
            "telemetry_id": telemetry_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": env_data,
            "usage": session_data,
        }
