"""Tests for the music library module."""

from pathlib import Path

import pytest

from voice_mode.dj.library import (
    MusicLibrary,
    Track,
    LibraryStats,
    FileScanner,
    SUPPORTED_EXTENSIONS,
)


class MockFileScanner:
    """Mock file scanner for testing."""

    def __init__(self, files: list[Path] | None = None):
        """Initialize with a list of file paths to return."""
        self._files = files or []

    def scan(self, root: Path) -> list[Path]:
        """Return the mock file list."""
        return self._files


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database path."""
    return tmp_path / "test-music.db"


@pytest.fixture
def temp_music_dir(tmp_path):
    """Create a temporary music directory with test files."""
    music_dir = tmp_path / "music"
    music_dir.mkdir()

    # Create a sample directory structure
    # Artist/Year-Album/Track.ext
    artist_dir = music_dir / "Daft_Punk" / "2001-Discovery"
    artist_dir.mkdir(parents=True)

    # Create test files
    (artist_dir / "01-One_More_Time.mp3").touch()
    (artist_dir / "02-Aerodynamic.mp3").touch()
    (artist_dir / "03-Digital_Love.mp3").touch()

    # Create another artist
    artist2_dir = music_dir / "Boards_Of_Canada" / "2002-Geogaddi"
    artist2_dir.mkdir(parents=True)
    (artist2_dir / "01-Music_Is_Math.flac").touch()
    (artist2_dir / "02-Beware_The_Friendly_Stranger.flac").touch()

    # Create a sidecar directory (stems)
    sidecar_dir = artist_dir / "01-One_More_Time.mp3.d" / "stems"
    sidecar_dir.mkdir(parents=True)
    (sidecar_dir / "vocals.mp3").touch()
    (sidecar_dir / "drums.mp3").touch()

    return music_dir


@pytest.fixture
def library(temp_db, temp_music_dir):
    """Create a library with test database and music directory."""
    return MusicLibrary(db_path=temp_db, music_root=temp_music_dir)


class TestTrackDataclass:
    """Tests for the Track dataclass."""

    def test_track_creation(self):
        """Test creating a Track with all fields."""
        track = Track(
            id=1,
            path="Artist/2001-Album/01-Track.mp3",
            filename="01-Track.mp3",
            artist="Artist",
            album="Album",
            title="Track",
            year=2001,
            track_number=1,
            format="mp3",
            is_favorite=False,
            play_count=0,
        )
        assert track.id == 1
        assert track.artist == "Artist"
        assert track.title == "Track"
        assert track.year == 2001
        assert track.is_favorite is False

    def test_track_with_sidecar(self):
        """Test creating a sidecar track."""
        track = Track(
            id=2,
            path="Artist/Album/track.mp3.d/stems/vocals.mp3",
            filename="vocals.mp3",
            artist="Artist",
            album="Album",
            title="vocals",
            year=None,
            track_number=None,
            format="mp3",
            is_favorite=False,
            play_count=0,
            is_sidecar=True,
            sidecar_type="stem",
            parent_track_id=1,
        )
        assert track.is_sidecar is True
        assert track.sidecar_type == "stem"
        assert track.parent_track_id == 1


class TestLibraryStats:
    """Tests for LibraryStats dataclass."""

    def test_stats_creation(self):
        """Test creating LibraryStats."""
        stats = LibraryStats(
            total_tracks=100,
            total_sidecars=20,
            total_favorites=5,
            total_artists=10,
            total_albums=15,
        )
        assert stats.total_tracks == 100
        assert stats.total_sidecars == 20
        assert stats.total_favorites == 5
        assert stats.total_artists == 10
        assert stats.total_albums == 15


class TestMusicLibraryInit:
    """Tests for MusicLibrary initialization."""

    def test_creates_db_directory(self, tmp_path):
        """Test that database directory is created."""
        db_path = tmp_path / "subdir" / "music.db"
        MusicLibrary(db_path=db_path)
        assert db_path.parent.exists()

    def test_creates_schema(self, temp_db):
        """Test that database schema is created."""
        import sqlite3

        library = MusicLibrary(db_path=temp_db)

        with sqlite3.connect(temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
            tables = {row[0] for row in cursor.fetchall()}

        assert "tracks" in tables
        assert "play_history" in tables
        assert "music_roots" in tables

    def test_accepts_custom_scanner(self, temp_db, tmp_path):
        """Test that custom scanner can be injected."""
        scanner = MockFileScanner([])
        library = MusicLibrary(
            db_path=temp_db,
            music_root=tmp_path,
            scanner=scanner,
        )
        count = library.scan()
        assert count == 0


class TestPathMetadataParsing:
    """Tests for metadata parsing from path structure."""

    def test_parses_artist_year_album_track(self, temp_db):
        """Test parsing Artist/Year-Album/Track.ext format."""
        library = MusicLibrary(db_path=temp_db)
        metadata = library._parse_path_metadata(
            "Daft_Punk/2001-Discovery/01-One_More_Time.mp3"
        )

        assert metadata["artist"] == "Daft Punk"
        assert metadata["album"] == "Discovery"
        assert metadata["year"] == 2001
        assert metadata["track_number"] == 1
        assert metadata["title"] == "One More Time"
        assert metadata["format"] == "mp3"
        assert metadata["is_sidecar"] is False

    def test_parses_album_without_year(self, temp_db):
        """Test parsing when album has no year prefix."""
        library = MusicLibrary(db_path=temp_db)
        metadata = library._parse_path_metadata(
            "Artist/Some_Album/02-Track_Name.flac"
        )

        assert metadata["artist"] == "Artist"
        assert metadata["album"] == "Some Album"
        assert metadata["year"] is None
        assert metadata["track_number"] == 2
        assert metadata["title"] == "Track Name"

    def test_parses_track_without_number(self, temp_db):
        """Test parsing when track has no number prefix."""
        library = MusicLibrary(db_path=temp_db)
        metadata = library._parse_path_metadata(
            "Artist/2020-Album/Untitled.wav"
        )

        assert metadata["track_number"] is None
        assert metadata["title"] == "Untitled"

    def test_identifies_sidecar_stem(self, temp_db):
        """Test identifying stem sidecar files."""
        library = MusicLibrary(db_path=temp_db)
        metadata = library._parse_path_metadata(
            "Artist/Album/track.mp3.d/stems/vocals.mp3"
        )

        assert metadata["is_sidecar"] is True
        assert metadata["sidecar_type"] == "stem"

    def test_identifies_sidecar_loop(self, temp_db):
        """Test identifying loop sidecar files."""
        library = MusicLibrary(db_path=temp_db)
        metadata = library._parse_path_metadata(
            "Artist/Album/track.mp3.d/loops/beat.mp3"
        )

        assert metadata["is_sidecar"] is True
        assert metadata["sidecar_type"] == "loop"

    def test_identifies_sidecar_sample(self, temp_db):
        """Test identifying sample sidecar files."""
        library = MusicLibrary(db_path=temp_db)
        metadata = library._parse_path_metadata(
            "Artist/Album/track.mp3.d/samples/sample1.wav"
        )

        assert metadata["is_sidecar"] is True
        assert metadata["sidecar_type"] == "sample"

    def test_cleans_underscores_to_spaces(self, temp_db):
        """Test that underscores are converted to spaces."""
        library = MusicLibrary(db_path=temp_db)
        metadata = library._parse_path_metadata(
            "The_Chemical_Brothers/2015-Born_In_The_Echoes/01-Sometimes_I_Feel_So_Deserted.mp3"
        )

        assert metadata["artist"] == "The Chemical Brothers"
        assert metadata["album"] == "Born In The Echoes"
        assert metadata["title"] == "Sometimes I Feel So Deserted"


class TestMusicLibraryScan:
    """Tests for MusicLibrary.scan()."""

    def test_scans_music_directory(self, library, temp_music_dir):
        """Test scanning indexes all tracks."""
        count = library.scan()

        # 5 main tracks + 2 sidecars = 7 total
        assert count == 7

    def test_scan_nonexistent_directory(self, temp_db, tmp_path):
        """Test scanning nonexistent directory returns 0."""
        library = MusicLibrary(
            db_path=temp_db,
            music_root=tmp_path / "nonexistent",
        )
        count = library.scan()
        assert count == 0

    def test_scan_with_mock_scanner(self, temp_db, tmp_path):
        """Test scanning with mock scanner."""
        music_dir = tmp_path / "music"
        music_dir.mkdir()

        # Create test files
        test_files = [
            music_dir / "Artist" / "Album" / "track1.mp3",
            music_dir / "Artist" / "Album" / "track2.mp3",
        ]
        for f in test_files:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.touch()

        scanner = MockFileScanner(test_files)
        library = MusicLibrary(
            db_path=temp_db,
            music_root=music_dir,
            scanner=scanner,
        )

        count = library.scan()
        assert count == 2


class TestMusicLibrarySearch:
    """Tests for MusicLibrary.search()."""

    def test_search_by_artist(self, library):
        """Test searching by artist name."""
        library.scan()
        results = library.search("Daft Punk")

        assert len(results) == 3
        assert all(t.artist == "Daft Punk" for t in results)

    def test_search_by_title(self, library):
        """Test searching by track title."""
        library.scan()
        results = library.search("Digital Love")

        assert len(results) == 1
        assert results[0].title == "Digital Love"

    def test_search_by_album(self, library):
        """Test searching by album name."""
        library.scan()
        results = library.search("Geogaddi")

        assert len(results) == 2
        assert all(t.album == "Geogaddi" for t in results)

    def test_search_case_insensitive(self, library):
        """Test that search is case-insensitive."""
        library.scan()
        results = library.search("daft punk")

        assert len(results) == 3

    def test_search_excludes_sidecars_by_default(self, library):
        """Test that sidecars are excluded by default."""
        library.scan()
        results = library.search("vocals")

        assert len(results) == 0

    def test_search_includes_sidecars_when_requested(self, library):
        """Test that sidecars can be included."""
        library.scan()
        results = library.search("vocals", include_sidecars=True)

        assert len(results) == 1
        assert results[0].is_sidecar is True

    def test_search_respects_limit(self, library):
        """Test that search respects limit parameter."""
        library.scan()
        results = library.search("", limit=2)  # Match all

        assert len(results) <= 2

    def test_search_no_results(self, library):
        """Test search with no matches."""
        library.scan()
        results = library.search("nonexistent artist xyz")

        assert len(results) == 0


class TestMusicLibraryGetTrack:
    """Tests for MusicLibrary.get_track()."""

    def test_get_track_by_id(self, library):
        """Test getting track by ID."""
        library.scan()
        results = library.search("One More Time")
        track_id = results[0].id

        track = library.get_track(track_id)

        assert track is not None
        assert track.title == "One More Time"
        assert track.artist == "Daft Punk"

    def test_get_track_not_found(self, library):
        """Test getting nonexistent track returns None."""
        library.scan()
        track = library.get_track(99999)

        assert track is None


class TestMusicLibraryGetTrackByPath:
    """Tests for MusicLibrary.get_track_by_path()."""

    def test_get_track_by_path(self, library):
        """Test getting track by relative path."""
        library.scan()
        path = "Daft_Punk/2001-Discovery/01-One_More_Time.mp3"

        track = library.get_track_by_path(path)

        assert track is not None
        assert track.title == "One More Time"

    def test_get_track_by_path_not_found(self, library):
        """Test getting nonexistent path returns None."""
        library.scan()
        track = library.get_track_by_path("nonexistent/path.mp3")

        assert track is None


class TestMusicLibraryFavorites:
    """Tests for favorite functionality."""

    def test_toggle_favorite_on(self, library):
        """Test toggling favorite to true."""
        library.scan()
        results = library.search("One More Time")
        track_id = results[0].id

        is_favorite = library.toggle_favorite(track_id)

        assert is_favorite is True
        track = library.get_track(track_id)
        assert track.is_favorite is True

    def test_toggle_favorite_off(self, library):
        """Test toggling favorite to false."""
        library.scan()
        results = library.search("One More Time")
        track_id = results[0].id

        # Toggle on then off
        library.toggle_favorite(track_id)
        is_favorite = library.toggle_favorite(track_id)

        assert is_favorite is False
        track = library.get_track(track_id)
        assert track.is_favorite is False

    def test_get_favorites(self, library):
        """Test getting favorite tracks."""
        library.scan()
        results = library.search("Daft Punk")

        # Mark first two as favorites
        library.toggle_favorite(results[0].id)
        library.toggle_favorite(results[1].id)

        favorites = library.get_favorites()

        assert len(favorites) == 2
        assert all(t.is_favorite for t in favorites)


class TestMusicLibraryPlayHistory:
    """Tests for play history functionality."""

    def test_record_play(self, library):
        """Test recording a play."""
        library.scan()
        results = library.search("One More Time")
        track_id = results[0].id

        # Record multiple plays
        library.record_play(track_id)
        library.record_play(track_id)

        track = library.get_track(track_id)
        assert track.play_count == 2


class TestMusicLibraryStats:
    """Tests for MusicLibrary.stats()."""

    def test_stats_counts(self, library):
        """Test stats returns correct counts."""
        library.scan()
        stats = library.stats()

        assert stats.total_tracks == 5  # 3 Daft Punk + 2 Boards of Canada
        assert stats.total_sidecars == 2  # 2 stem files
        assert stats.total_favorites == 0
        assert stats.total_artists == 2
        assert stats.total_albums == 2

    def test_stats_with_favorites(self, library):
        """Test stats includes favorites count."""
        library.scan()
        results = library.search("Daft Punk")
        library.toggle_favorite(results[0].id)

        stats = library.stats()

        assert stats.total_favorites == 1


class TestMusicLibraryGetFullPath:
    """Tests for MusicLibrary.get_full_path()."""

    def test_get_full_path(self, library, temp_music_dir):
        """Test getting full filesystem path."""
        library.scan()
        results = library.search("One More Time")
        track = results[0]

        full_path = library.get_full_path(track)

        assert full_path.exists()
        assert full_path.name == "01-One_More_Time.mp3"
        assert str(full_path).startswith(str(temp_music_dir))


class TestSupportedExtensions:
    """Tests for supported extensions constant."""

    def test_supported_extensions(self):
        """Test that common audio formats are supported."""
        assert ".mp3" in SUPPORTED_EXTENSIONS
        assert ".flac" in SUPPORTED_EXTENSIONS
        assert ".m4a" in SUPPORTED_EXTENSIONS
        assert ".wav" in SUPPORTED_EXTENSIONS
        assert ".ogg" in SUPPORTED_EXTENSIONS
        assert ".opus" in SUPPORTED_EXTENSIONS

    def test_unsupported_extensions_excluded(self):
        """Test that non-audio formats are not included."""
        assert ".txt" not in SUPPORTED_EXTENSIONS
        assert ".jpg" not in SUPPORTED_EXTENSIONS
        assert ".mp4" not in SUPPORTED_EXTENSIONS
