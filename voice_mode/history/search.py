"""Search conversation history using FTS5 full-text search."""

import json
import sqlite3
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List, Literal

from voice_mode.history.database import HistoryDatabase


class SearchResult:
    """Search result with exchange data and audio file path."""

    def __init__(self, row: sqlite3.Row):
        """Initialize from database row.

        Args:
            row: SQLite row from search query
        """
        self.id = row["id"]
        self.timestamp = datetime.fromisoformat(row["timestamp"])
        self.conversation_id = row["conversation_id"]
        self.type = row["type"]
        self.text = row["text"]
        self.audio_file = row["audio_file"]
        self.project_path = row["project_path"]

        # Parse metadata JSON
        self.metadata = json.loads(row["metadata"]) if row["metadata"] else None

    def get_audio_path(self, base_dir: Optional[Path] = None) -> Optional[Path]:
        """Resolve audio file to full path.

        Args:
            base_dir: Base directory for audio files. Defaults to ~/.voicemode

        Returns:
            Full path to audio file, or None if not available
        """
        if not self.audio_file:
            return None

        if base_dir is None:
            base_dir = Path.home() / ".voicemode"

        # Audio files are stored in audio/YYYY/MM/ directory structure
        # Extract date from timestamp
        year = self.timestamp.strftime("%Y")
        month = self.timestamp.strftime("%m")

        # Try year/month directory structure first
        audio_path = base_dir / "audio" / year / month / self.audio_file
        if audio_path.exists():
            return audio_path

        # Fallback to flat structure
        audio_path = base_dir / "audio" / self.audio_file
        if audio_path.exists():
            return audio_path

        # File doesn't exist
        return None

    def __repr__(self):
        """String representation."""
        return (
            f"SearchResult(id={self.id}, timestamp={self.timestamp}, "
            f"type={self.type}, text={self.text[:50]}...)"
        )


class HistorySearcher:
    """Search conversation history using SQLite FTS5."""

    def __init__(self, db: HistoryDatabase):
        """Initialize searcher.

        Args:
            db: HistoryDatabase instance
        """
        self.db = db

    def search(
        self,
        query: str,
        exchange_type: Optional[Literal["stt", "tts"]] = None,
        target_date: Optional[date] = None,
        limit: int = 20,
    ) -> List[SearchResult]:
        """Search exchanges using FTS5 full-text search.

        Args:
            query: Search query (supports FTS5 syntax)
            exchange_type: Filter by 'stt' or 'tts'
            target_date: Filter by specific date
            limit: Maximum number of results

        Returns:
            List of SearchResult objects
        """
        cursor = self.db.conn.cursor()

        # Build query with filters
        conditions = ["exchanges_fts MATCH ?"]
        params = [query]

        if exchange_type:
            conditions.append("type = ?")
            params.append(exchange_type)

        if target_date:
            # Filter by date range (whole day)
            start = f"{target_date.isoformat()} 00:00:00"
            end = f"{target_date.isoformat()} 23:59:59"
            conditions.append("timestamp >= ? AND timestamp <= ?")
            params.extend([start, end])

        where_clause = " AND ".join(conditions)
        params.append(limit)

        sql = f"""
            SELECT
                e.id, e.timestamp, e.conversation_id, e.type,
                e.text, e.audio_file, e.project_path, e.metadata
            FROM exchanges e
            JOIN exchanges_fts fts ON e.rowid = fts.rowid
            WHERE {where_clause}
            ORDER BY e.timestamp DESC
            LIMIT ?
        """

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        return [SearchResult(row) for row in rows]

    def get_by_id(self, exchange_id: str) -> Optional[SearchResult]:
        """Get exchange by ID.

        Args:
            exchange_id: Exchange ID to retrieve

        Returns:
            SearchResult or None if not found
        """
        cursor = self.db.conn.cursor()

        cursor.execute(
            """
            SELECT id, timestamp, conversation_id, type, text,
                   audio_file, project_path, metadata
            FROM exchanges
            WHERE id = ?
            """,
            (exchange_id,),
        )

        row = cursor.fetchone()
        return SearchResult(row) if row else None

    def get_recent(
        self,
        limit: int = 20,
        exchange_type: Optional[Literal["stt", "tts"]] = None,
    ) -> List[SearchResult]:
        """Get recent exchanges without search.

        Args:
            limit: Maximum number of results
            exchange_type: Filter by 'stt' or 'tts'

        Returns:
            List of SearchResult objects
        """
        cursor = self.db.conn.cursor()

        conditions = []
        params = []

        if exchange_type:
            conditions.append("type = ?")
            params.append(exchange_type)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(limit)

        sql = f"""
            SELECT id, timestamp, conversation_id, type, text,
                   audio_file, project_path, metadata
            FROM exchanges
            {where_clause}
            ORDER BY timestamp DESC
            LIMIT ?
        """

        cursor.execute(sql, params)
        rows = cursor.fetchall()

        return [SearchResult(row) for row in rows]
