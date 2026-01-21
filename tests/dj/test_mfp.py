"""Tests for the Music For Programming service module."""

import pytest
from pathlib import Path

from voice_mode.dj.mfp import (
    HttpFetcher,
    MfpEpisode,
    MfpService,
    RssFetcher,
)


# Sample RSS content for testing
SAMPLE_RSS_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Music For Programming</title>
    <description>Datassette presents a series of mixes intended for listening while programming.</description>
    <item>
      <title>Episode 76: Material Object</title>
      <enclosure url="https://datashat.net/music_for_programming_76-material_object.mp3" length="145678901" type="audio/mpeg"/>
    </item>
    <item>
      <title>Episode 49: Julien Mier</title>
      <enclosure url="https://datashat.net/music_for_programming_49-julien_mier.mp3" length="134567890" type="audio/mpeg"/>
    </item>
    <item>
      <title>Episode 01: Datassette</title>
      <enclosure url="https://datashat.net/music_for_programming_01-datassette.mp3" length="98765432" type="audio/mpeg"/>
    </item>
  </channel>
</rss>
'''


class MockFetcher:
    """Mock RSS fetcher for testing."""

    def __init__(self, content: str = SAMPLE_RSS_XML, should_fail: bool = False):
        """Initialize mock fetcher.

        Args:
            content: RSS content to return.
            should_fail: If True, raise RuntimeError on fetch.
        """
        self.content = content
        self.should_fail = should_fail
        self.fetch_count = 0

    def fetch(self, url: str) -> str:
        """Mock fetch implementation."""
        self.fetch_count += 1
        if self.should_fail:
            raise RuntimeError("Network error")
        return self.content


class TestMfpEpisode:
    """Tests for MfpEpisode dataclass."""

    def test_basic_episode(self):
        """Test basic episode creation."""
        episode = MfpEpisode(
            number=49,
            title="Episode 49: Julien Mier",
            url="https://example.com/music_for_programming_49-julien_mier.mp3",
            curator="julien mier",
        )

        assert episode.number == 49
        assert episode.title == "Episode 49: Julien Mier"
        assert episode.curator == "julien mier"
        assert episode.has_chapters is False
        assert episode.has_local_file is False

    def test_episode_with_flags(self):
        """Test episode with chapter and local flags."""
        episode = MfpEpisode(
            number=49,
            title="Episode 49",
            url="https://example.com/ep49.mp3",
            curator="artist",
            has_chapters=True,
            has_local_file=True,
            length_bytes=123456789,
        )

        assert episode.has_chapters is True
        assert episode.has_local_file is True
        assert episode.length_bytes == 123456789


class TestMfpService:
    """Tests for MfpService class."""

    @pytest.fixture
    def mock_fetcher(self):
        """Create a mock fetcher."""
        return MockFetcher()

    @pytest.fixture
    def service(self, tmp_path, mock_fetcher):
        """Create an MFP service with mock fetcher and temp cache."""
        return MfpService(cache_dir=tmp_path, fetcher=mock_fetcher)

    def test_list_episodes(self, service):
        """Test listing episodes from RSS."""
        episodes = service.list_episodes(with_chapters_only=False)

        assert len(episodes) == 3
        # Should be sorted by number descending
        assert episodes[0].number == 76
        assert episodes[1].number == 49
        assert episodes[2].number == 1

    def test_list_episodes_with_chapters_only(self, service, tmp_path):
        """Test filtering to episodes with chapters."""
        # Create a chapter file for episode 49
        cue_file = tmp_path / "music_for_programming_49-julien_mier.cue"
        cue_file.write_text("TRACK 01 AUDIO\n  INDEX 01 00:00:00\n")

        # Clear cache to reload with chapter detection
        service._episodes_cache = None
        episodes = service.list_episodes(with_chapters_only=True)

        assert len(episodes) == 1
        assert episodes[0].number == 49

    def test_get_episode(self, service):
        """Test getting a single episode by number."""
        episode = service.get_episode(49)

        assert episode is not None
        assert episode.number == 49
        assert episode.curator == "julien mier"

    def test_get_episode_not_found(self, service):
        """Test getting a non-existent episode."""
        episode = service.get_episode(999)

        assert episode is None

    def test_get_stream_url(self, service):
        """Test getting streaming URL."""
        url = service.get_stream_url(49)

        assert url is not None
        assert "music_for_programming_49" in url
        assert url.endswith(".mp3")

    def test_get_stream_url_not_found(self, service):
        """Test streaming URL for non-existent episode."""
        url = service.get_stream_url(999)

        assert url is None

    def test_get_local_path_not_downloaded(self, service):
        """Test local path when file doesn't exist."""
        path = service.get_local_path(49)

        assert path is None

    def test_get_local_path_exists(self, service, tmp_path):
        """Test local path when file exists."""
        # Create a local MP3 file
        mp3_file = tmp_path / "music_for_programming_49-julien_mier.mp3"
        mp3_file.write_bytes(b"fake mp3 data")

        # Clear cache to reload
        service._episodes_cache = None
        path = service.get_local_path(49)

        assert path is not None
        assert path.exists()

    def test_get_chapters_file_none(self, service):
        """Test chapters file when none exists locally or in package."""
        # Use episode 76 which doesn't have bundled chapters
        path = service.get_chapters_file(76)

        assert path is None

    def test_get_chapters_file_copies_from_package(self, service, tmp_path):
        """Test that chapters are copied from package on-demand for bundled episodes."""
        # Episode 49 has bundled chapters in the package
        # Ensure no local files exist initially
        local_ffmeta = tmp_path / "music_for_programming_49-julien_mier.ffmeta"
        local_cue = tmp_path / "music_for_programming_49-julien_mier.cue"
        assert not local_ffmeta.exists()
        assert not local_cue.exists()

        # Get chapters file - should copy from package
        path = service.get_chapters_file(49)

        # Should return a valid path
        assert path is not None
        assert path.suffix == ".ffmeta"
        assert path.exists()

        # Local files should now exist (copied from package)
        assert local_ffmeta.exists() or local_cue.exists()

    def test_get_chapters_file_ffmeta(self, service, tmp_path):
        """Test getting existing FFmeta chapters file."""
        # Create an FFmeta file
        ffmeta_file = tmp_path / "music_for_programming_49-julien_mier.ffmeta"
        ffmeta_file.write_text(";FFMETADATA1\n")

        path = service.get_chapters_file(49)

        assert path is not None
        assert path.suffix == ".ffmeta"

    def test_get_chapters_file_converts_cue(self, service, tmp_path):
        """Test that CUE file is converted to FFmeta."""
        # Create a CUE file
        cue_file = tmp_path / "music_for_programming_49-julien_mier.cue"
        cue_file.write_text('''TRACK 01 AUDIO
    TITLE "Test Track"
    INDEX 01 00:00:00
''')

        path = service.get_chapters_file(49)

        assert path is not None
        assert path.suffix == ".ffmeta"
        assert path.exists()
        # Check content
        content = path.read_text()
        assert ";FFMETADATA1" in content

    def test_sync_chapters(self, service, tmp_path):
        """Test syncing chapter files from package to local."""
        # sync_chapters should copy files from package to local
        results = service.sync_chapters()

        # Should have added files from package (episode 49 CUE and FFmeta)
        added_files = [f for f, status in results.items() if status == "Added"]
        assert len(added_files) == 2
        assert "music_for_programming_49-julien_mier.cue" in added_files
        assert "music_for_programming_49-julien_mier.ffmeta" in added_files

        # Files should exist in local cache
        assert (tmp_path / "music_for_programming_49-julien_mier.cue").exists()
        assert (tmp_path / "music_for_programming_49-julien_mier.ffmeta").exists()

        # Local checksum file should be created
        assert (tmp_path / ".chapters.sha256").exists()

    def test_sync_chapters_skips_unchanged(self, service, tmp_path):
        """Test that sync detects unchanged files."""
        # First sync - should add files
        results1 = service.sync_chapters()
        added_count = len([f for f, s in results1.items() if s == "Added"])
        assert added_count == 2

        # Second sync - should detect unchanged
        results2 = service.sync_chapters()
        unchanged_count = len([f for f, s in results2.items() if s == "Unchanged"])
        assert unchanged_count == 2

    def test_sync_chapters_force(self, service, tmp_path):
        """Test force sync backs up user modifications."""
        # First sync to get files
        service.sync_chapters()

        # Modify a local file (simulate user edit)
        cue_file = tmp_path / "music_for_programming_49-julien_mier.cue"
        cue_file.write_text("USER MODIFIED CONTENT")

        # Sync with force - should backup user file and restore package version
        results = service.sync_chapters(force=True)

        # Should show updated (because local was modified)
        assert results.get("music_for_programming_49-julien_mier.cue") == "Updated"

        # User backup should exist
        backup_file = tmp_path / "music_for_programming_49-julien_mier.cue.user"
        assert backup_file.exists()
        assert backup_file.read_text() == "USER MODIFIED CONTENT"

        # Original should be restored from package
        assert cue_file.read_text() != "USER MODIFIED CONTENT"

    def test_refresh(self, service, mock_fetcher):
        """Test refresh forces new RSS fetch."""
        # First load
        service.list_episodes(with_chapters_only=False)
        initial_count = mock_fetcher.fetch_count

        # Refresh
        count = service.refresh()

        assert mock_fetcher.fetch_count == initial_count + 1
        assert count == 3

    def test_rss_caching(self, tmp_path):
        """Test RSS caching on network failure."""
        # First request with working fetcher
        fetcher1 = MockFetcher()
        service1 = MfpService(cache_dir=tmp_path, fetcher=fetcher1)
        service1.list_episodes(with_chapters_only=False)

        # Second request with failing fetcher - should use cache
        fetcher2 = MockFetcher(should_fail=True)
        service2 = MfpService(cache_dir=tmp_path, fetcher=fetcher2)
        episodes = service2.list_episodes(with_chapters_only=False)

        assert len(episodes) == 3

    def test_no_cache_network_fail(self, tmp_path):
        """Test error when no cache and network fails."""
        fetcher = MockFetcher(should_fail=True)
        service = MfpService(cache_dir=tmp_path, fetcher=fetcher)

        with pytest.raises(RuntimeError, match="Cannot fetch RSS"):
            service.list_episodes(with_chapters_only=False)


class TestCuratorExtraction:
    """Tests for curator name extraction from URLs."""

    @pytest.fixture
    def service(self, tmp_path):
        """Create a service with various curator names in RSS."""
        rss = '''<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Episode 1</title>
      <enclosure url="https://example.com/music_for_programming_01-simple_name.mp3" type="audio/mpeg"/>
    </item>
    <item>
      <title>Episode 2</title>
      <enclosure url="https://example.com/music_for_programming_02-name_with_multiple_parts.mp3" type="audio/mpeg"/>
    </item>
  </channel>
</rss>
'''
        return MfpService(cache_dir=tmp_path, fetcher=MockFetcher(rss))

    def test_simple_name(self, service):
        """Test simple curator name extraction."""
        episode = service.get_episode(1)
        assert episode.curator == "simple name"

    def test_multi_part_name(self, service):
        """Test multi-part curator name."""
        episode = service.get_episode(2)
        assert episode.curator == "name with multiple parts"


class TestChapterDistribution:
    """Tests for chapter file distribution from package."""

    @pytest.fixture
    def mock_fetcher(self):
        """Create a mock fetcher."""
        return MockFetcher()

    @pytest.fixture
    def service(self, tmp_path, mock_fetcher):
        """Create an MFP service with mock fetcher and temp cache."""
        return MfpService(cache_dir=tmp_path, fetcher=mock_fetcher)

    def test_get_package_mfp_dir_returns_valid_path(self, service):
        """Test get_package_mfp_dir() returns a valid path with expected content."""
        package_dir = service.get_package_mfp_dir()

        # Should return a valid Path
        assert package_dir is not None
        assert isinstance(package_dir, Path)
        assert package_dir.is_dir()

        # Should contain the bundled chapter files
        expected_files = [
            "music_for_programming_49-julien_mier.cue",
            "music_for_programming_49-julien_mier.ffmeta",
            "chapters.sha256",
        ]
        for filename in expected_files:
            file_path = package_dir / filename
            assert file_path.exists(), f"Expected file {filename} not found in package dir"

    def test_get_package_mfp_dir_checksum_file_valid(self, service):
        """Test that package checksum file has valid format."""
        package_dir = service.get_package_mfp_dir()
        assert package_dir is not None

        checksum_file = package_dir / "chapters.sha256"
        assert checksum_file.exists()

        # Load and validate checksums
        checksums = service._load_checksums(checksum_file)
        assert len(checksums) >= 2  # At least CUE and FFmeta for episode 49
        assert "music_for_programming_49-julien_mier.cue" in checksums
        assert "music_for_programming_49-julien_mier.ffmeta" in checksums

        # Each checksum should be a valid hex SHA256 (64 chars)
        for filename, checksum in checksums.items():
            assert len(checksum) == 64, f"Invalid checksum length for {filename}"
            assert all(c in "0123456789abcdef" for c in checksum), f"Invalid hex for {filename}"

    def test_sync_chapters_detects_package_update(self, service, tmp_path):
        """Test sync detects when package has updated files (different checksum)."""
        # First sync - adds files
        results1 = service.sync_chapters()
        assert "music_for_programming_49-julien_mier.cue" in results1
        assert results1["music_for_programming_49-julien_mier.cue"] == "Added"

        # Verify local checksum file was created
        local_checksum_file = tmp_path / ".chapters.sha256"
        assert local_checksum_file.exists()

        # Simulate scenario where package was updated with new content
        # by modifying the local checksum file to have an old (different) checksum
        # This simulates: local file matches OLD package version, package has NEW version
        local_checksums = service._load_checksums(local_checksum_file)
        # Change the stored checksum to simulate "old version"
        local_checksums["music_for_programming_49-julien_mier.cue"] = "0" * 64
        service._save_checksums(local_checksums, local_checksum_file)

        # Also update local file to match the "old" checksum we just saved
        # (The file content doesn't matter, what matters is that its hash matches
        # the stored local checksum but differs from package checksum)
        local_cue = tmp_path / "music_for_programming_49-julien_mier.cue"
        # Write content that produces a different hash than the package file
        old_content = "OLD VERSION - will be updated"
        local_cue.write_text(old_content)
        # Update the local checksum to match this file
        actual_hash = service._compute_file_sha256(local_cue)
        local_checksums["music_for_programming_49-julien_mier.cue"] = actual_hash
        service._save_checksums(local_checksums, local_checksum_file)

        # Now sync again - should detect the package has a newer version
        results2 = service.sync_chapters()

        # The CUE file should be marked as Updated (package version is newer)
        assert results2.get("music_for_programming_49-julien_mier.cue") == "Updated"

        # Local file should now have package content (not old content)
        assert local_cue.read_text() != old_content

    def test_on_demand_copy_creates_both_files(self, service, tmp_path):
        """Test that on-demand copy creates both CUE and FFmeta files when available."""
        # Ensure no local files exist
        local_cue = tmp_path / "music_for_programming_49-julien_mier.cue"
        local_ffmeta = tmp_path / "music_for_programming_49-julien_mier.ffmeta"
        assert not local_cue.exists()
        assert not local_ffmeta.exists()

        # Call get_chapters_file which triggers on-demand copy
        result = service.get_chapters_file(49)

        # Should return FFmeta file
        assert result is not None
        assert result.suffix == ".ffmeta"

        # Both files should now exist locally
        assert local_ffmeta.exists(), "FFmeta file should exist after on-demand copy"
        assert local_cue.exists(), "CUE file should exist after on-demand copy"


class TestHttpFetcher:
    """Tests for HttpFetcher class."""

    def test_timeout_setting(self):
        """Test timeout is configurable."""
        fetcher = HttpFetcher(timeout=5)
        assert fetcher.timeout == 5

    def test_default_timeout(self):
        """Test default timeout."""
        fetcher = HttpFetcher()
        assert fetcher.timeout == 10
