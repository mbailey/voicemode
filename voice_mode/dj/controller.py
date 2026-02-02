"""
High-level DJ controller for managing audio playback.

This module provides the DJController class which handles the business
logic of starting, controlling, and monitoring audio playback. It uses
the MpvPlayer for low-level mpv communication and adds higher-level
operations like starting new playback and gathering status information.
"""

import os
import subprocess
import time
from pathlib import Path

from .models import TrackStatus
from .player import MpvPlayer


class DJController:
    """High-level DJ operations controller.

    This class provides a clean, high-level interface for controlling
    audio playback. It manages starting mpv instances, controlling
    playback, and gathering comprehensive status information.

    The player can be injected for testing purposes.
    """

    # Default volume for new playback sessions (configurable via VOICEMODE_DJ_VOLUME)
    DEFAULT_VOLUME = int(os.environ.get("VOICEMODE_DJ_VOLUME", "50"))

    # Timeout for waiting for mpv to start (seconds)
    STARTUP_TIMEOUT = 5.0

    # Poll interval when waiting for mpv to start
    STARTUP_POLL_INTERVAL = 0.1

    def __init__(self, player: MpvPlayer | None = None):
        """Initialize the controller.

        Args:
            player: Optional player instance. If None, creates a new MpvPlayer.
        """
        self._player = player or MpvPlayer()

    @property
    def socket_path(self) -> str:
        """Get the socket path used by the player."""
        return self._player.socket_path

    # Playback control

    def play(
        self,
        source: str,
        chapters_file: str | None = None,
        volume: int | None = None,
    ) -> bool:
        """Start playback of a file or URL.

        This method stops any existing playback and starts a new mpv
        instance with the specified source. It waits for mpv to become
        responsive before returning.

        Args:
            source: Path to audio file or URL to play.
            chapters_file: Optional path to chapters file (FFmetadata or CUE).
            volume: Initial volume (0-100). Defaults to DEFAULT_VOLUME.

        Returns:
            True if playback started successfully.
        """
        # Stop any existing playback
        if self.is_playing():
            self.stop()
            # Give mpv time to shut down
            time.sleep(0.2)

        # Remove any stale socket file
        socket_path = Path(self._player.socket_path)
        if socket_path.exists():
            try:
                socket_path.unlink()
            except OSError:
                pass

        # Build mpv command
        vol = volume if volume is not None else self.DEFAULT_VOLUME
        args = [
            "mpv",
            "--no-video",
            f"--input-ipc-server={self._player.socket_path}",
            f"--volume={vol}",
        ]

        if chapters_file:
            chapters_path = Path(chapters_file)
            if chapters_path.exists():
                args.append(f"--chapters-file={chapters_file}")

        args.append(source)

        # Start mpv in the background
        try:
            subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError:
            # mpv not installed
            return False
        except OSError:
            return False

        # Wait for mpv to become responsive
        return self._wait_for_socket()

    def _wait_for_socket(self) -> bool:
        """Wait for mpv's IPC socket to become available.

        Returns:
            True if mpv became responsive within the timeout.
        """
        start_time = time.time()
        while time.time() - start_time < self.STARTUP_TIMEOUT:
            if self._player.is_running():
                return True
            time.sleep(self.STARTUP_POLL_INTERVAL)
        return False

    def stop(self) -> bool:
        """Stop playback and quit mpv.

        Returns:
            True if the stop command was sent (or mpv wasn't running).
        """
        if not self._player.is_running():
            return True
        return self._player.stop()

    def pause(self) -> bool:
        """Pause playback.

        Returns:
            True if playback was paused successfully.
        """
        if not self._player.is_running():
            return False
        return self._player.pause()

    def resume(self) -> bool:
        """Resume playback.

        Returns:
            True if playback was resumed successfully.
        """
        if not self._player.is_running():
            return False
        return self._player.resume()

    def toggle_pause(self) -> bool:
        """Toggle between paused and playing states.

        Returns:
            True if the toggle succeeded.
        """
        if not self._player.is_running():
            return False

        if self._player.is_paused():
            return self._player.resume()
        else:
            return self._player.pause()

    # Status

    def status(self) -> TrackStatus | None:
        """Get current playback status.

        Returns:
            TrackStatus with current state, or None if not playing.
        """
        if not self._player.is_running():
            return None

        # Gather all status information
        position = self._player.get_position()
        duration = self._player.get_duration()
        volume = self._player.get_volume()

        # Handle missing values (could happen during startup/shutdown)
        if position is None or duration is None or volume is None:
            return None

        # Get chapter information
        chapter_meta = self._player.get_chapter_metadata()
        chapter_title = None
        if chapter_meta and isinstance(chapter_meta, dict):
            # mpv returns metadata keys in UPPERCASE
            chapter_title = chapter_meta.get("TITLE") or chapter_meta.get("title")

        return TrackStatus(
            is_playing=True,
            is_paused=self._player.is_paused(),
            title=self._player.get_title(),
            artist=None,  # mpv doesn't provide artist separately
            position=position,
            duration=duration,
            volume=int(volume),
            chapter=chapter_title,
            chapter_index=self._player.get_chapter_index(),
            chapter_count=self._player.get_chapter_count(),
            path=self._player.get_path(),
        )

    def is_playing(self) -> bool:
        """Check if mpv is running.

        Note: This returns True even if playback is paused.
        Use status().is_paused to check pause state.

        Returns:
            True if mpv is running.
        """
        return self._player.is_running()

    # Navigation (Phase 2 will expand these)

    def next(self) -> TrackStatus | None:
        """Skip to next chapter and return new status.

        Returns:
            Updated TrackStatus, or None if not playing.
        """
        if not self._player.is_running():
            return None
        self._player.next_chapter()
        # Give mpv a moment to update
        time.sleep(0.1)
        return self.status()

    def prev(self) -> TrackStatus | None:
        """Go to previous chapter and return new status.

        Returns:
            Updated TrackStatus, or None if not playing.
        """
        if not self._player.is_running():
            return None
        self._player.prev_chapter()
        # Give mpv a moment to update
        time.sleep(0.1)
        return self.status()

    # Volume (Phase 2 will expand these)

    def volume(self, level: int | None = None) -> int | None:
        """Get or set volume.

        Args:
            level: If provided, sets the volume to this level (0-100).
                   If None, returns the current volume.

        Returns:
            Current volume level, or None if not playing.
        """
        if not self._player.is_running():
            return None

        if level is not None:
            self._player.set_volume(level)

        return int(self._player.get_volume() or 0)
