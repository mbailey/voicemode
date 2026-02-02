"""
Data models for the DJ module.

These dataclasses provide clean, typed interfaces for playback status
and command results, enabling type-safe operations throughout the module.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class CommandResult:
    """Result from an mpv command.

    Encapsulates the outcome of any mpv IPC command, providing
    a consistent interface for success/failure handling.

    Attributes:
        success: Whether the command executed successfully.
        data: Any data returned by the command (varies by command type).
        error: Error message if the command failed, None otherwise.
    """

    success: bool
    data: Any = None
    error: str | None = None


@dataclass
class TrackStatus:
    """Current playback status.

    Provides a snapshot of the current playback state, including
    track information, position, volume, and chapter data.

    Attributes:
        is_playing: True if playback is active (not stopped).
        is_paused: True if playback is paused.
        title: Track title from metadata, or None if unavailable.
        artist: Artist name from metadata, or None if unavailable.
        position: Current playback position in seconds.
        duration: Total track duration in seconds.
        volume: Current volume level (0-100).
        chapter: Current chapter name, or None if no chapters.
        chapter_index: Current chapter index (0-based), or None.
        chapter_count: Total number of chapters, or None if no chapters.
        path: Path or URL of the current track.
    """

    is_playing: bool
    is_paused: bool
    title: str | None
    artist: str | None
    position: float
    duration: float
    volume: int
    chapter: str | None = None
    chapter_index: int | None = None
    chapter_count: int | None = None
    path: str | None = None

    @property
    def progress_percent(self) -> float:
        """Get playback progress as a percentage (0-100)."""
        if self.duration <= 0:
            return 0.0
        return min(100.0, (self.position / self.duration) * 100)

    @property
    def remaining(self) -> float:
        """Get remaining time in seconds."""
        return max(0.0, self.duration - self.position)

    def format_position(self) -> str:
        """Format position as MM:SS or HH:MM:SS."""
        return self._format_time(self.position)

    def format_duration(self) -> str:
        """Format duration as MM:SS or HH:MM:SS."""
        return self._format_time(self.duration)

    def format_remaining(self) -> str:
        """Format remaining time as MM:SS or HH:MM:SS."""
        return self._format_time(self.remaining)

    @staticmethod
    def _format_time(seconds: float) -> str:
        """Format seconds as MM:SS or HH:MM:SS."""
        total_seconds = int(seconds)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        secs = total_seconds % 60

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        return f"{minutes}:{secs:02d}"
