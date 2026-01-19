"""
Music library with SQLite backend.

This module provides indexing and search functionality for local music files,
with support for favorites, play history, and sidecar file tracking.

Example usage:
    >>> from voice_mode.dj.library import MusicLibrary
    >>> library = MusicLibrary()
    >>> library.scan(Path.home() / "Audio" / "music")
    42
    >>> tracks = library.search("ambient")
    >>> print(tracks[0].title)
"""

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


# Supported audio extensions
SUPPORTED_EXTENSIONS = frozenset({".mp3", ".flac", ".m4a", ".wav", ".ogg", ".opus"})


@dataclass
class Track:
    """Music library track.

    Represents a track in the music library with metadata parsed from
    directory structure (Artist/Year-Album/Track.ext) and user data.

    Attributes:
        id: Database primary key.
        path: Relative path from music root.
        filename: Base filename.
        artist: Artist name from directory structure.
        album: Album name from directory structure.
        title: Track title from filename.
        year: Album year if present.
        track_number: Track number if parsed from filename.
        format: File extension (mp3, flac, etc.).
        is_favorite: Whether track is marked as favorite.
        play_count: Number of times track has been played.
        is_sidecar: True if in a .d folder (stems, loops, samples).
        sidecar_type: Type of sidecar (stem, loop, sample) or None.
        parent_track_id: ID of parent track for sidecars.
    """

    id: int
    path: str
    filename: str
    artist: str | None
    album: str | None
    title: str
    year: int | None
    track_number: int | None
    format: str
    is_favorite: bool
    play_count: int
    is_sidecar: bool = False
    sidecar_type: str | None = None
    parent_track_id: int | None = None


@dataclass
class LibraryStats:
    """Music library statistics.

    Attributes:
        total_tracks: Total number of main tracks (excluding sidecars).
        total_sidecars: Number of sidecar files (stems, loops, samples).
        total_favorites: Number of favorited tracks.
        total_artists: Number of distinct artists.
        total_albums: Number of distinct albums.
    """

    total_tracks: int
    total_sidecars: int
    total_favorites: int
    total_artists: int
    total_albums: int


class FileScanner(Protocol):
    """Protocol for file scanning (mockable for tests)."""

    def scan(self, root: Path) -> list[Path]:
        """Scan directory and return list of audio files."""
        ...


class DefaultFileScanner:
    """Default implementation that scans the filesystem."""

    def scan(self, root: Path) -> list[Path]:
        """Recursively scan directory for audio files.

        Args:
            root: Root directory to scan.

        Returns:
            List of Path objects for discovered audio files.
        """
        files = []
        for ext in SUPPORTED_EXTENSIONS:
            files.extend(root.rglob(f"*{ext}"))
        return files


class MusicLibrary:
    """Music library with SQLite backend.

    Provides indexing and search functionality for local music files.
    Tracks metadata is parsed from directory structure:
        Artist/Year-Album/Track.ext

    Example:
        Daft_Punk/2001-Discovery/01-One_More_Time.mp3
        -> artist="Daft Punk", year=2001, album="Discovery",
           track_number=1, title="One More Time"
    """

    def __init__(
        self,
        db_path: Path | None = None,
        music_root: Path | None = None,
        scanner: FileScanner | None = None,
    ):
        """Initialize the music library.

        Args:
            db_path: Path to SQLite database. Defaults to ~/.voicemode/music-library.db
            music_root: Default music directory. Defaults to ~/Audio/music
            scanner: File scanner implementation (for testing).
        """
        self.db_path = db_path or Path.home() / ".voicemode" / "music-library.db"
        self.music_root = music_root or Path.home() / "Audio" / "music"
        self._scanner = scanner or DefaultFileScanner()
        self._ensure_db()

    def _ensure_db(self) -> None:
        """Create database and schema if not exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                -- Tracks table - main index of all audio files
                CREATE TABLE IF NOT EXISTS tracks (
                    id INTEGER PRIMARY KEY,
                    path TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    artist TEXT,
                    album TEXT,
                    title TEXT,
                    year INTEGER,
                    track_number INTEGER,
                    duration INTEGER,
                    format TEXT,

                    -- Sidecar tracking
                    is_sidecar BOOLEAN DEFAULT 0,
                    sidecar_type TEXT,
                    parent_track_id INTEGER,

                    -- User data
                    favorite BOOLEAN DEFAULT 0,
                    tags TEXT,
                    play_count INTEGER DEFAULT 0,
                    last_played TIMESTAMP,

                    -- Metadata
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_mtime INTEGER,

                    FOREIGN KEY (parent_track_id) REFERENCES tracks(id)
                );

                -- Indexes for fast searching
                CREATE INDEX IF NOT EXISTS idx_artist ON tracks(artist);
                CREATE INDEX IF NOT EXISTS idx_album ON tracks(album);
                CREATE INDEX IF NOT EXISTS idx_title ON tracks(title);
                CREATE INDEX IF NOT EXISTS idx_favorite ON tracks(favorite);
                CREATE INDEX IF NOT EXISTS idx_is_sidecar ON tracks(is_sidecar);
                CREATE INDEX IF NOT EXISTS idx_parent_track ON tracks(parent_track_id);

                -- Play history
                CREATE TABLE IF NOT EXISTS play_history (
                    id INTEGER PRIMARY KEY,
                    track_id INTEGER NOT NULL,
                    played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    source TEXT DEFAULT 'local',
                    FOREIGN KEY (track_id) REFERENCES tracks(id)
                );

                -- Music roots for multi-location support
                CREATE TABLE IF NOT EXISTS music_roots (
                    id INTEGER PRIMARY KEY,
                    path TEXT UNIQUE NOT NULL,
                    name TEXT,
                    last_scan TIMESTAMP,
                    active BOOLEAN DEFAULT 1
                );
            """)

    def _parse_path_metadata(self, rel_path: str) -> dict:
        """Parse metadata from path structure.

        Expected formats:
            Artist/Year-Album/Track.ext
            Artist/Year-Album/track.d/stems/stem.ext

        Args:
            rel_path: Relative path from music root.

        Returns:
            Dict with artist, album, title, year, track_number, format,
            is_sidecar, sidecar_type.
        """
        path = Path(rel_path)
        filename = path.name
        base_name = path.stem
        ext = path.suffix.lstrip(".").lower()

        # Check if this is a sidecar file (in a .d folder)
        is_sidecar = False
        sidecar_type = None
        parts = rel_path.split("/")
        for i, part in enumerate(parts):
            if part.endswith(".d"):
                is_sidecar = True
                # Check what type of sidecar
                if i + 1 < len(parts):
                    subdir = parts[i + 1].lower()
                    if "stem" in subdir:
                        sidecar_type = "stem"
                    elif "loop" in subdir:
                        sidecar_type = "loop"
                    elif "sample" in subdir:
                        sidecar_type = "sample"
                    else:
                        sidecar_type = "other"
                break

        # Get the main track directory (before any .d folder)
        main_parts = []
        for part in parts[:-1]:  # Exclude filename
            if part.endswith(".d"):
                break
            main_parts.append(part)

        # Parse Artist/Album from path
        artist = None
        album = None
        year = None

        if len(main_parts) >= 2:
            artist = main_parts[-2]
            album_dir = main_parts[-1]

            # Handle year-album format (2005-Human_After_All)
            year_match = re.match(r"^(\d{4})-(.+)$", album_dir)
            if year_match:
                year = int(year_match.group(1))
                album = year_match.group(2)
            else:
                album = album_dir
        elif len(main_parts) == 1:
            artist = main_parts[0]

        # Parse track number from filename (01-Track_Name or 01 Track Name)
        title = base_name
        track_number = None
        track_match = re.match(r"^(\d+)[-_\s](.+)$", base_name)
        if track_match:
            track_number = int(track_match.group(1))
            title = track_match.group(2)

        # Clean up underscores and dashes to spaces
        def clean_name(name: str | None) -> str | None:
            if name is None:
                return None
            return name.replace("_", " ").replace("-", " ").strip()

        return {
            "artist": clean_name(artist),
            "album": clean_name(album),
            "title": clean_name(title),
            "year": year,
            "track_number": track_number,
            "format": ext,
            "is_sidecar": is_sidecar,
            "sidecar_type": sidecar_type,
        }

    def scan(self, music_path: Path | None = None) -> int:
        """Scan directory and index tracks.

        Args:
            music_path: Directory to scan. Defaults to music_root.

        Returns:
            Number of tracks indexed.
        """
        music_path = music_path or self.music_root

        if not music_path.exists():
            return 0

        # Get all audio files
        files = self._scanner.scan(music_path)

        count = 0
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            for file_path in files:
                # Get relative path
                try:
                    rel_path = str(file_path.relative_to(music_path))
                except ValueError:
                    continue

                # Get file modification time
                try:
                    mtime = int(file_path.stat().st_mtime)
                except OSError:
                    mtime = 0

                # Parse metadata from path
                metadata = self._parse_path_metadata(rel_path)

                # Insert or update track
                cursor.execute(
                    """
                    INSERT INTO tracks (
                        path, filename, artist, album, title, year,
                        track_number, format, is_sidecar, sidecar_type, file_mtime
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(path) DO UPDATE SET
                        artist = excluded.artist,
                        album = excluded.album,
                        title = excluded.title,
                        year = excluded.year,
                        track_number = excluded.track_number,
                        format = excluded.format,
                        is_sidecar = excluded.is_sidecar,
                        sidecar_type = excluded.sidecar_type,
                        file_mtime = excluded.file_mtime
                    """,
                    (
                        rel_path,
                        file_path.name,
                        metadata["artist"],
                        metadata["album"],
                        metadata["title"],
                        metadata["year"],
                        metadata["track_number"],
                        metadata["format"],
                        metadata["is_sidecar"],
                        metadata["sidecar_type"],
                        mtime,
                    ),
                )
                count += 1

            conn.commit()

            # Link sidecars to parent tracks (second pass)
            cursor.execute(
                """
                UPDATE tracks SET parent_track_id = (
                    SELECT t2.id FROM tracks t2
                    WHERE t2.is_sidecar = 0
                    AND tracks.path LIKE t2.path || '.d/%'
                    LIMIT 1
                )
                WHERE is_sidecar = 1 AND parent_track_id IS NULL
                """
            )
            conn.commit()

        return count

    def search(
        self,
        query: str,
        limit: int = 50,
        include_sidecars: bool = False,
    ) -> list[Track]:
        """Search tracks by artist, album, or title.

        Args:
            query: Search term (case-insensitive).
            limit: Maximum results to return.
            include_sidecars: Whether to include sidecar files.

        Returns:
            List of matching Track objects.
        """
        sidecar_filter = "" if include_sidecars else "AND is_sidecar = 0"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                f"""
                SELECT
                    id, path, filename, artist, album, title, year,
                    track_number, format, favorite, play_count,
                    is_sidecar, sidecar_type, parent_track_id
                FROM tracks
                WHERE (
                    artist LIKE ?
                    OR title LIKE ?
                    OR album LIKE ?
                )
                {sidecar_filter}
                ORDER BY artist, album, track_number
                LIMIT ?
                """,
                (f"%{query}%", f"%{query}%", f"%{query}%", limit),
            )

            return [self._row_to_track(row) for row in cursor.fetchall()]

    def get_track(self, track_id: int) -> Track | None:
        """Get track by ID.

        Args:
            track_id: Database primary key.

        Returns:
            Track object or None if not found.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    id, path, filename, artist, album, title, year,
                    track_number, format, favorite, play_count,
                    is_sidecar, sidecar_type, parent_track_id
                FROM tracks
                WHERE id = ?
                """,
                (track_id,),
            )

            row = cursor.fetchone()
            return self._row_to_track(row) if row else None

    def get_track_by_path(self, path: str) -> Track | None:
        """Get track by relative path.

        Args:
            path: Relative path from music root.

        Returns:
            Track object or None if not found.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    id, path, filename, artist, album, title, year,
                    track_number, format, favorite, play_count,
                    is_sidecar, sidecar_type, parent_track_id
                FROM tracks
                WHERE path = ?
                """,
                (path,),
            )

            row = cursor.fetchone()
            return self._row_to_track(row) if row else None

    def toggle_favorite(self, track_id: int) -> bool:
        """Toggle favorite status.

        Args:
            track_id: Track database ID.

        Returns:
            New favorite status (True if now favorite).
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "UPDATE tracks SET favorite = NOT favorite WHERE id = ?",
                (track_id,),
            )
            conn.commit()

            cursor.execute("SELECT favorite FROM tracks WHERE id = ?", (track_id,))
            row = cursor.fetchone()
            return bool(row[0]) if row else False

    def record_play(self, track_id: int) -> None:
        """Record a track play in history.

        Args:
            track_id: Track database ID.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "INSERT INTO play_history (track_id) VALUES (?)",
                (track_id,),
            )

            cursor.execute(
                """
                UPDATE tracks
                SET play_count = play_count + 1, last_played = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (track_id,),
            )
            conn.commit()

    def get_favorites(self, limit: int = 50) -> list[Track]:
        """Get favorite tracks.

        Args:
            limit: Maximum results to return.

        Returns:
            List of favorite Track objects.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT
                    id, path, filename, artist, album, title, year,
                    track_number, format, favorite, play_count,
                    is_sidecar, sidecar_type, parent_track_id
                FROM tracks
                WHERE favorite = 1 AND is_sidecar = 0
                ORDER BY artist, album, track_number
                LIMIT ?
                """,
                (limit,),
            )

            return [self._row_to_track(row) for row in cursor.fetchall()]

    def stats(self) -> LibraryStats:
        """Get library statistics.

        Returns:
            LibraryStats with counts.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "SELECT COUNT(*) FROM tracks WHERE is_sidecar = 0"
            )
            total_tracks = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM tracks WHERE is_sidecar = 1"
            )
            total_sidecars = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(*) FROM tracks WHERE favorite = 1"
            )
            total_favorites = cursor.fetchone()[0]

            cursor.execute(
                "SELECT COUNT(DISTINCT artist) FROM tracks WHERE is_sidecar = 0"
            )
            total_artists = cursor.fetchone()[0]

            cursor.execute(
                """
                SELECT COUNT(DISTINCT album) FROM tracks
                WHERE is_sidecar = 0 AND album IS NOT NULL AND album != ''
                """
            )
            total_albums = cursor.fetchone()[0]

            return LibraryStats(
                total_tracks=total_tracks,
                total_sidecars=total_sidecars,
                total_favorites=total_favorites,
                total_artists=total_artists,
                total_albums=total_albums,
            )

    def get_full_path(self, track: Track) -> Path:
        """Get full filesystem path for a track.

        Args:
            track: Track object.

        Returns:
            Full Path to the audio file.
        """
        return self.music_root / track.path

    def _row_to_track(self, row: sqlite3.Row) -> Track:
        """Convert database row to Track object."""
        return Track(
            id=row["id"],
            path=row["path"],
            filename=row["filename"],
            artist=row["artist"],
            album=row["album"],
            title=row["title"] or row["filename"],
            year=row["year"],
            track_number=row["track_number"],
            format=row["format"],
            is_favorite=bool(row["favorite"]),
            play_count=row["play_count"],
            is_sidecar=bool(row["is_sidecar"]),
            sidecar_type=row["sidecar_type"],
            parent_track_id=row["parent_track_id"],
        )
