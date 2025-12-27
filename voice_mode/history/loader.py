"""Load conversation history from JSONL into SQLite database."""

import hashlib
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from voice_mode.exchanges.reader import ExchangeReader
from voice_mode.exchanges.models import Exchange
from voice_mode.history.database import HistoryDatabase

logger = logging.getLogger(__name__)


class HistoryLoader:
    """Loads conversation history from JSONL files into SQLite."""

    def __init__(self, db: HistoryDatabase, base_dir: Optional[Path] = None):
        """Initialize loader.

        Args:
            db: HistoryDatabase instance
            base_dir: Base directory for logs. Defaults to ~/.voicemode
        """
        self.db = db
        self.reader = ExchangeReader(base_dir=base_dir)

    def _generate_exchange_id(self, exchange: Exchange) -> str:
        """Generate a unique ID for an exchange.

        Uses a hash of timestamp + conversation_id + text to create a
        deterministic ID that won't change across reloads.

        Args:
            exchange: Exchange to generate ID for

        Returns:
            Unique exchange ID
        """
        # Create deterministic ID from key fields
        id_string = f"{exchange.timestamp.isoformat()}|{exchange.conversation_id}|{exchange.text}"
        hash_digest = hashlib.sha256(id_string.encode()).hexdigest()
        return f"ex_{hash_digest[:16]}"

    def load_exchange(self, exchange: Exchange) -> bool:
        """Load a single exchange into the database.

        Args:
            exchange: Exchange to load

        Returns:
            True if inserted, False if already exists
        """
        exchange_id = self._generate_exchange_id(exchange)

        # Convert metadata to dict for JSON storage
        metadata_dict = exchange.metadata.to_dict() if exchange.metadata else None

        return self.db.insert_exchange(
            id=exchange_id,
            timestamp=exchange.timestamp.isoformat(),
            conversation_id=exchange.conversation_id,
            type=exchange.type,
            text=exchange.text,
            audio_file=exchange.audio_file,
            project_path=exchange.project_path,
            metadata=metadata_dict,
        )

    def load_all(self, since: Optional[datetime] = None) -> dict:
        """Load all exchanges from JSONL files into database.

        Args:
            since: Only load exchanges after this datetime

        Returns:
            Dictionary with stats: {total, inserted, skipped, errors}
        """
        stats = {"total": 0, "inserted": 0, "skipped": 0, "errors": 0}

        # If since not specified, check for last sync timestamp
        if since is None:
            last_sync = self.db.get_sync_metadata("last_sync_timestamp")
            if last_sync:
                since = datetime.fromisoformat(last_sync)
                logger.info(f"Resuming from last sync: {since}")

        # Read all exchanges
        exchanges = self.reader._read_all()

        for exchange in exchanges:
            stats["total"] += 1

            # Skip if before cutoff time
            if since and exchange.timestamp < since:
                stats["skipped"] += 1
                continue

            try:
                if self.load_exchange(exchange):
                    stats["inserted"] += 1
                else:
                    stats["skipped"] += 1

            except Exception as e:
                logger.error(f"Error loading exchange: {e}")
                stats["errors"] += 1

        # Update last sync timestamp to now
        self.db.set_sync_metadata("last_sync_timestamp", datetime.now().isoformat())

        logger.info(
            f"Load complete: {stats['inserted']} inserted, "
            f"{stats['skipped']} skipped, {stats['errors']} errors"
        )

        return stats

    def load_date(self, target_date: date) -> dict:
        """Load exchanges for a specific date.

        Args:
            target_date: Date to load

        Returns:
            Dictionary with stats: {total, inserted, skipped, errors}
        """
        stats = {"total": 0, "inserted": 0, "skipped": 0, "errors": 0}

        exchanges = self.reader.read_date(target_date)

        for exchange in exchanges:
            stats["total"] += 1

            try:
                if self.load_exchange(exchange):
                    stats["inserted"] += 1
                else:
                    stats["skipped"] += 1

            except Exception as e:
                logger.error(f"Error loading exchange: {e}")
                stats["errors"] += 1

        return stats

    def load_recent(self, days: int = 7) -> dict:
        """Load exchanges from recent days.

        Args:
            days: Number of days to look back

        Returns:
            Dictionary with stats: {total, inserted, skipped, errors}
        """
        stats = {"total": 0, "inserted": 0, "skipped": 0, "errors": 0}

        exchanges = self.reader.read_recent(days=days)

        for exchange in exchanges:
            stats["total"] += 1

            try:
                if self.load_exchange(exchange):
                    stats["inserted"] += 1
                else:
                    stats["skipped"] += 1

            except Exception as e:
                logger.error(f"Error loading exchange: {e}")
                stats["errors"] += 1

        # Update last sync timestamp
        self.db.set_sync_metadata("last_sync_timestamp", datetime.now().isoformat())

        return stats
