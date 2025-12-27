"""SQLite database schema and operations for conversation history."""

import json
import sqlite3
from pathlib import Path
from typing import Optional


class HistoryDatabase:
    """Manages SQLite database for conversation history."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database. Defaults to ~/.voicemode/cache/conversations.db
        """
        if db_path is None:
            db_path = Path.home() / ".voicemode" / "cache" / "conversations.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema with exchanges table and FTS5 index."""
        cursor = self.conn.cursor()

        # Create main exchanges table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS exchanges (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                conversation_id TEXT,
                type TEXT NOT NULL,
                text TEXT NOT NULL,
                audio_file TEXT,
                project_path TEXT,
                metadata TEXT
            )
        """)

        # Create FTS5 virtual table for full-text search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS exchanges_fts
            USING fts5(text, content=exchanges, content_rowid=rowid)
        """)

        # Create triggers to keep FTS5 in sync with exchanges table
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS exchanges_ai
            AFTER INSERT ON exchanges
            BEGIN
                INSERT INTO exchanges_fts(rowid, text)
                VALUES (new.rowid, new.text);
            END
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS exchanges_ad
            AFTER DELETE ON exchanges
            BEGIN
                DELETE FROM exchanges_fts WHERE rowid = old.rowid;
            END
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS exchanges_au
            AFTER UPDATE ON exchanges
            BEGIN
                DELETE FROM exchanges_fts WHERE rowid = old.rowid;
                INSERT INTO exchanges_fts(rowid, text)
                VALUES (new.rowid, new.text);
            END
        """)

        # Create metadata table for tracking sync state
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sync_metadata (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Create index on timestamp for efficient date filtering
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_exchanges_timestamp
            ON exchanges(timestamp)
        """)

        # Create index on type for filtering by STT/TTS
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_exchanges_type
            ON exchanges(type)
        """)

        # Create index on conversation_id for grouping
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_exchanges_conversation
            ON exchanges(conversation_id)
        """)

        self.conn.commit()

    def insert_exchange(
        self,
        id: str,
        timestamp: str,
        conversation_id: Optional[str],
        type: str,
        text: str,
        audio_file: Optional[str],
        project_path: Optional[str],
        metadata: Optional[dict],
    ) -> bool:
        """Insert a single exchange into the database.

        Args:
            id: Unique exchange identifier
            timestamp: ISO timestamp
            conversation_id: Conversation group identifier
            type: Exchange type ('stt' or 'tts')
            text: Transcribed or spoken text
            audio_file: Path to audio file
            project_path: Working directory context
            metadata: Full metadata dictionary

        Returns:
            True if inserted, False if already exists (duplicate ID)
        """
        cursor = self.conn.cursor()

        metadata_json = json.dumps(metadata) if metadata else None

        try:
            cursor.execute(
                """
                INSERT INTO exchanges (
                    id, timestamp, conversation_id, type, text,
                    audio_file, project_path, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    id,
                    timestamp,
                    conversation_id,
                    type,
                    text,
                    audio_file,
                    project_path,
                    metadata_json,
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_sync_metadata(self, key: str) -> Optional[str]:
        """Get sync metadata value by key.

        Args:
            key: Metadata key

        Returns:
            Value or None if key doesn't exist
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM sync_metadata WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None

    def set_sync_metadata(self, key: str, value: str):
        """Set sync metadata value.

        Args:
            key: Metadata key
            value: Metadata value
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO sync_metadata (key, value)
            VALUES (?, ?)
            """,
            (key, value),
        )
        self.conn.commit()

    def get_exchange_count(self) -> int:
        """Get total number of exchanges in database.

        Returns:
            Total exchange count
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) as count FROM exchanges")
        return cursor.fetchone()["count"]

    def close(self):
        """Close database connection."""
        self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
