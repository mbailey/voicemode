"""
Music For Programming service for the DJ module.

Provides access to the Music For Programming (MFP) podcast episodes,
including RSS parsing, episode streaming URLs, and chapter file management.
"""

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Protocol
from urllib.error import URLError
from urllib.request import urlopen

from .chapters import convert_cue_to_ffmetadata


# Default locations
MFP_RSS_URL = "https://musicforprogramming.net/rss.xml"
DEFAULT_CACHE_DIR = Path.home() / ".voicemode" / "music-for-programming"


class RssFetcher(Protocol):
    """Protocol for RSS fetching (mockable for tests)."""

    def fetch(self, url: str) -> str:
        """Fetch RSS content from URL.

        Args:
            url: The URL to fetch.

        Returns:
            The RSS content as a string.

        Raises:
            RuntimeError: If the fetch fails.
        """
        ...


class HttpFetcher:
    """HTTP-based RSS fetcher using urllib."""

    def __init__(self, timeout: int = 10):
        """Initialize the fetcher.

        Args:
            timeout: Request timeout in seconds.
        """
        self.timeout = timeout

    def fetch(self, url: str) -> str:
        """Fetch content from URL.

        Args:
            url: The URL to fetch.

        Returns:
            The content as a string.

        Raises:
            RuntimeError: If the fetch fails.
        """
        try:
            with urlopen(url, timeout=self.timeout) as response:
                return response.read().decode("utf-8")
        except (URLError, TimeoutError) as e:
            raise RuntimeError(f"Failed to fetch {url}: {e}")


@dataclass
class MfpEpisode:
    """Music For Programming episode info.

    Attributes:
        number: Episode number.
        title: Full episode title from RSS.
        url: Streaming/download URL.
        curator: DJ/curator name.
        has_chapters: Whether chapter files exist locally.
        has_local_file: Whether a local MP3 file exists.
        length_bytes: File size in bytes (from RSS).
    """

    number: int
    title: str
    url: str
    curator: str
    has_chapters: bool = False
    has_local_file: bool = False
    length_bytes: int | None = None


class MfpService:
    """Music For Programming service.

    Provides access to MFP episodes with smart caching:
    - Tries to fetch fresh RSS from network
    - Falls back to cached RSS if network fails
    - Tracks local chapter files and downloads
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        fetcher: RssFetcher | None = None,
    ):
        """Initialize the MFP service.

        Args:
            cache_dir: Directory for cached files. Defaults to ~/.voicemode/music-for-programming.
            fetcher: RSS fetcher implementation. Defaults to HttpFetcher.
        """
        self.cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self._fetcher = fetcher or HttpFetcher()
        self._rss_cache_file = self.cache_dir / "rss.xml"
        self._episodes_cache: dict[int, MfpEpisode] | None = None

    def get_package_mfp_dir(self) -> Path | None:
        """Get the path to bundled MFP chapter files in the package.

        Uses importlib.resources to locate the package data directory.
        This works both when running from source and when installed as a package.

        Returns:
            Path to the package mfp data directory, or None if not found.
        """
        try:
            package_mfp = files("voice_mode.data.mfp")
            # Check if it's a valid directory with content
            if not package_mfp.is_dir():
                return None

            # MultiplexedPath has _paths attribute with actual Path objects
            if hasattr(package_mfp, "_paths") and package_mfp._paths:
                return Path(package_mfp._paths[0])

            # Fallback: iterate to find a file and get its parent
            try:
                for item in package_mfp.iterdir():
                    if hasattr(item, "_paths") and item._paths:
                        return Path(item._paths[0]).parent
                    # For PosixPath items (when running from source)
                    if isinstance(item, Path):
                        return item.parent
            except (StopIteration, AttributeError):
                pass

            return None
        except (ModuleNotFoundError, TypeError):
            # Package data not found
            return None

    def _ensure_cache_dir(self) -> None:
        """Ensure the cache directory exists."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _fetch_rss(self, force_refresh: bool = False) -> str:
        """Fetch RSS feed with smart caching.

        Strategy:
        1. Try to fetch fresh RSS from the network
        2. If successful, update the cache
        3. If network fails and cache exists, use cache
        4. If network fails and no cache, raise error

        Args:
            force_refresh: If True, don't use cache on network failure.

        Returns:
            RSS content as a string.

        Raises:
            RuntimeError: If RSS cannot be fetched and no cache exists.
        """
        self._ensure_cache_dir()

        try:
            content = self._fetcher.fetch(MFP_RSS_URL)
            # Update cache on successful fetch
            self._rss_cache_file.write_text(content)
            return content
        except RuntimeError:
            if force_refresh:
                raise

            # Network failed, try cache
            if self._rss_cache_file.exists():
                return self._rss_cache_file.read_text()

            raise RuntimeError(
                f"Cannot fetch RSS feed and no cache exists at {self._rss_cache_file}"
            )

    def _parse_episodes(self, rss_content: str) -> dict[int, MfpEpisode]:
        """Parse RSS content into episode dictionary.

        Args:
            rss_content: Raw RSS XML content.

        Returns:
            Dictionary mapping episode numbers to MfpEpisode objects.
        """
        episodes = {}
        root = ET.fromstring(rss_content)

        for item in root.findall(".//item"):
            enclosure = item.find("enclosure")
            if enclosure is None:
                continue

            url = enclosure.get("url", "")
            title = item.findtext("title", "")
            length = enclosure.get("length", "")

            # Extract episode number from URL
            # Pattern: music_for_programming_76-material_object.mp3
            match = re.search(r"music_for_programming_(\d+)-", url)
            if match:
                episode_num = int(match.group(1))

                # Extract curator name from URL
                curator_match = re.search(
                    r"music_for_programming_\d+-(.+)\.mp3", url
                )
                curator = (
                    curator_match.group(1).replace("_", " ")
                    if curator_match
                    else "unknown"
                )

                # Check for local files
                filename_base = self._get_filename_base_from_url(url)
                has_chapters = self._check_chapters_exist(filename_base)
                has_local = self._check_local_file_exists(filename_base)

                episodes[episode_num] = MfpEpisode(
                    number=episode_num,
                    title=title,
                    url=url,
                    curator=curator,
                    has_chapters=has_chapters,
                    has_local_file=has_local,
                    length_bytes=int(length) if length else None,
                )

        return episodes

    def _get_filename_base_from_url(self, url: str) -> str:
        """Extract filename base (without extension) from RSS URL.

        Args:
            url: The RSS enclosure URL.

        Returns:
            Filename base like "music_for_programming_49-julien_mier".

        Raises:
            ValueError: If filename cannot be extracted.
        """
        match = re.search(r"(music_for_programming_\d+-.+)\.mp3", url)
        if match:
            return match.group(1)
        raise ValueError(f"Cannot extract filename from URL: {url}")

    def _check_chapters_exist(self, filename_base: str) -> bool:
        """Check if chapter files exist for an episode.

        Args:
            filename_base: Episode filename base.

        Returns:
            True if CUE or FFmeta chapter file exists.
        """
        cue_file = self.cache_dir / f"{filename_base}.cue"
        ffmeta_file = self.cache_dir / f"{filename_base}.ffmeta"
        return cue_file.exists() or ffmeta_file.exists()

    def _check_local_file_exists(self, filename_base: str) -> bool:
        """Check if local MP3 file exists.

        Args:
            filename_base: Episode filename base.

        Returns:
            True if local MP3 file exists.
        """
        mp3_file = self.cache_dir / f"{filename_base}.mp3"
        return mp3_file.exists()

    def _load_episodes(self, force_refresh: bool = False) -> dict[int, MfpEpisode]:
        """Load and cache episodes from RSS.

        Args:
            force_refresh: Force a fresh RSS fetch.

        Returns:
            Dictionary of episodes.
        """
        if self._episodes_cache is None or force_refresh:
            rss_content = self._fetch_rss(force_refresh)
            self._episodes_cache = self._parse_episodes(rss_content)
        return self._episodes_cache

    def get_episode(self, number: int) -> MfpEpisode | None:
        """Get episode info by number.

        Args:
            number: Episode number.

        Returns:
            MfpEpisode if found, None otherwise.
        """
        episodes = self._load_episodes()
        return episodes.get(number)

    def list_episodes(
        self,
        with_chapters_only: bool = True,
        refresh: bool = False,
    ) -> list[MfpEpisode]:
        """List available episodes.

        Args:
            with_chapters_only: Only return episodes with chapter files.
            refresh: Force refresh from RSS.

        Returns:
            List of MfpEpisode objects sorted by episode number (descending).
        """
        episodes = self._load_episodes(force_refresh=refresh)
        episode_list = list(episodes.values())

        if with_chapters_only:
            episode_list = [ep for ep in episode_list if ep.has_chapters]

        return sorted(episode_list, key=lambda ep: ep.number, reverse=True)

    def get_stream_url(self, number: int) -> str | None:
        """Get streaming URL for an episode.

        Args:
            number: Episode number.

        Returns:
            Streaming URL or None if episode not found.
        """
        episode = self.get_episode(number)
        return episode.url if episode else None

    def get_local_path(self, number: int) -> Path | None:
        """Get path to local MP3 file if it exists.

        Args:
            number: Episode number.

        Returns:
            Path to local file or None if not downloaded.
        """
        episode = self.get_episode(number)
        if not episode:
            return None

        try:
            filename_base = self._get_filename_base_from_url(episode.url)
            mp3_path = self.cache_dir / f"{filename_base}.mp3"
            return mp3_path if mp3_path.exists() else None
        except ValueError:
            return None

    def get_chapters_file(self, number: int) -> Path | None:
        """Get path to chapters file for an episode.

        Prefers FFmeta format if available, otherwise returns CUE.
        If only CUE exists, converts it to FFmeta first.

        Args:
            number: Episode number.

        Returns:
            Path to FFmeta chapters file or None if no chapters available.
        """
        episode = self.get_episode(number)
        if not episode:
            return None

        try:
            filename_base = self._get_filename_base_from_url(episode.url)
        except ValueError:
            return None

        ffmeta_path = self.cache_dir / f"{filename_base}.ffmeta"
        cue_path = self.cache_dir / f"{filename_base}.cue"

        # Prefer existing FFmeta
        if ffmeta_path.exists():
            return ffmeta_path

        # Convert CUE to FFmeta if needed
        if cue_path.exists():
            try:
                ffmeta_content = convert_cue_to_ffmetadata(cue_path.read_text())
                ffmeta_path.write_text(ffmeta_content)
                return ffmeta_path
            except Exception:
                # If conversion fails, return the CUE file
                return cue_path

        return None

    def sync_chapters(self, force: bool = False) -> int:
        """Convert all CUE files to FFmeta format.

        Scans the cache directory for CUE files and converts them
        to FFmeta format for mpv compatibility.

        Args:
            force: Re-convert even if FFmeta already exists.

        Returns:
            Number of files converted.
        """
        self._ensure_cache_dir()
        converted = 0

        for cue_file in self.cache_dir.glob("music_for_programming_*.cue"):
            ffmeta_file = cue_file.with_suffix(".ffmeta")

            if ffmeta_file.exists() and not force:
                continue

            try:
                ffmeta_content = convert_cue_to_ffmetadata(cue_file.read_text())
                ffmeta_file.write_text(ffmeta_content)
                converted += 1
            except Exception:
                # Skip files that can't be converted
                continue

        return converted

    def refresh(self) -> int:
        """Force refresh the RSS feed and return episode count.

        Returns:
            Number of episodes found in RSS.
        """
        episodes = self._load_episodes(force_refresh=True)
        return len(episodes)
