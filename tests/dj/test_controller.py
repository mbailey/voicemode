"""Tests for the DJController class."""

import pytest

from voice_mode.dj import DJController, TrackStatus


class TestDJControllerStatus:
    """Tests for status reporting."""

    def test_status_returns_track_status_when_playing(
        self, mock_controller, mock_backend
    ):
        """Status returns TrackStatus when mpv is running."""
        status = mock_controller.status()
        assert status is not None
        assert isinstance(status, TrackStatus)

    def test_status_returns_none_when_not_playing(self, disconnected_controller):
        """Status returns None when mpv is not running."""
        assert disconnected_controller.status() is None

    def test_status_includes_position(self, mock_controller, mock_backend):
        """Status includes current position."""
        mock_backend.set_property("time-pos", 45.0)
        status = mock_controller.status()
        assert status.position == 45.0

    def test_status_includes_duration(self, mock_controller, mock_backend):
        """Status includes track duration."""
        mock_backend.set_property("duration", 300.0)
        status = mock_controller.status()
        assert status.duration == 300.0

    def test_status_includes_volume(self, mock_controller, mock_backend):
        """Status includes volume level."""
        mock_backend.set_property("volume", 75.0)
        status = mock_controller.status()
        assert status.volume == 75

    def test_status_includes_title(self, mock_controller, mock_backend):
        """Status includes track title."""
        mock_backend.set_property("media-title", "Test Song")
        status = mock_controller.status()
        assert status.title == "Test Song"

    def test_status_includes_pause_state(self, mock_controller, mock_backend):
        """Status includes pause state."""
        mock_backend.set_property("pause", True)
        status = mock_controller.status()
        assert status.is_paused is True

    def test_status_includes_chapter_info(self, mock_controller, mock_backend):
        """Status includes chapter information."""
        mock_backend.set_property("chapter-metadata", {"title": "Chapter 2"})
        mock_backend.set_property("chapter", 1)
        mock_backend.set_property("chapter-list/count", 5)
        status = mock_controller.status()
        assert status.chapter == "Chapter 2"
        assert status.chapter_index == 1
        assert status.chapter_count == 5


class TestDJControllerPlaybackState:
    """Tests for is_playing method."""

    def test_is_playing_when_running(self, mock_controller, mock_backend):
        """is_playing returns True when mpv is running."""
        assert mock_controller.is_playing() is True

    def test_is_playing_when_not_running(self, disconnected_controller):
        """is_playing returns False when mpv is not running."""
        assert disconnected_controller.is_playing() is False


class TestDJControllerPause:
    """Tests for pause/resume functionality."""

    def test_pause_sends_pause_command(self, mock_controller, mock_backend):
        """Pause sends pause command to player."""
        mock_controller.pause()
        commands = mock_backend.get_commands()
        assert ["set_property", "pause", True] in commands

    def test_pause_returns_true_on_success(self, mock_controller, mock_backend):
        """Pause returns True when successful."""
        assert mock_controller.pause() is True

    def test_pause_returns_false_when_not_playing(self, disconnected_controller):
        """Pause returns False when mpv is not running."""
        assert disconnected_controller.pause() is False

    def test_resume_sends_resume_command(self, mock_controller, mock_backend):
        """Resume sends resume command to player."""
        mock_controller.resume()
        commands = mock_backend.get_commands()
        assert ["set_property", "pause", False] in commands

    def test_resume_returns_true_on_success(self, mock_controller, mock_backend):
        """Resume returns True when successful."""
        assert mock_controller.resume() is True

    def test_resume_returns_false_when_not_playing(self, disconnected_controller):
        """Resume returns False when mpv is not running."""
        assert disconnected_controller.resume() is False


class TestDJControllerTogglePause:
    """Tests for toggle_pause functionality."""

    def test_toggle_pause_pauses_when_playing(self, mock_controller, mock_backend):
        """Toggle pause pauses when playing."""
        mock_backend.set_property("pause", False)
        mock_controller.toggle_pause()
        commands = mock_backend.get_commands()
        # Should have checked pause state then set pause to True
        assert ["set_property", "pause", True] in commands

    def test_toggle_pause_resumes_when_paused(self, mock_controller, mock_backend):
        """Toggle pause resumes when paused."""
        mock_backend.set_property("pause", True)
        mock_controller.toggle_pause()
        commands = mock_backend.get_commands()
        # Should have checked pause state then set pause to False
        assert ["set_property", "pause", False] in commands

    def test_toggle_pause_returns_false_when_not_playing(self, disconnected_controller):
        """Toggle pause returns False when mpv is not running."""
        assert disconnected_controller.toggle_pause() is False


class TestDJControllerStop:
    """Tests for stop functionality."""

    def test_stop_sends_quit_command(self, mock_controller, mock_backend):
        """Stop sends quit command to player."""
        mock_controller.stop()
        commands = mock_backend.get_commands()
        assert ["quit"] in commands

    def test_stop_returns_true_when_not_running(self, disconnected_controller):
        """Stop returns True when mpv is not running (nothing to stop)."""
        assert disconnected_controller.stop() is True


class TestDJControllerNavigation:
    """Tests for chapter navigation."""

    def test_next_chapter_sends_command(self, mock_controller, mock_backend):
        """Next sends next chapter command."""
        mock_controller.next()
        commands = mock_backend.get_commands()
        assert ["add", "chapter", 1] in commands

    def test_next_returns_status(self, mock_controller, mock_backend):
        """Next returns updated status."""
        status = mock_controller.next()
        assert status is not None
        assert isinstance(status, TrackStatus)

    def test_next_returns_none_when_not_playing(self, disconnected_controller):
        """Next returns None when mpv is not running."""
        assert disconnected_controller.next() is None

    def test_prev_chapter_sends_command(self, mock_controller, mock_backend):
        """Prev sends previous chapter command."""
        mock_controller.prev()
        commands = mock_backend.get_commands()
        assert ["add", "chapter", -1] in commands

    def test_prev_returns_status(self, mock_controller, mock_backend):
        """Prev returns updated status."""
        status = mock_controller.prev()
        assert status is not None
        assert isinstance(status, TrackStatus)

    def test_prev_returns_none_when_not_playing(self, disconnected_controller):
        """Prev returns None when mpv is not running."""
        assert disconnected_controller.prev() is None


class TestDJControllerVolume:
    """Tests for volume control."""

    def test_volume_get_returns_level(self, mock_controller, mock_backend):
        """Getting volume returns current level."""
        mock_backend.set_property("volume", 65.0)
        assert mock_controller.volume() == 65

    def test_volume_set_updates_level(self, mock_controller, mock_backend):
        """Setting volume updates the level."""
        mock_controller.volume(80)
        commands = mock_backend.get_commands()
        assert ["set_property", "volume", 80] in commands

    def test_volume_set_returns_new_level(self, mock_controller, mock_backend):
        """Setting volume returns the new level."""
        # After setting, the mock backend will have updated the value
        result = mock_controller.volume(80)
        # The backend updates the property when set, so get_volume returns 80
        assert result == 80

    def test_volume_returns_none_when_not_playing(self, disconnected_controller):
        """Volume returns None when mpv is not running."""
        assert disconnected_controller.volume() is None


class TestTrackStatusFormatting:
    """Tests for TrackStatus formatting methods."""

    def test_progress_percent(self):
        """Progress percent calculates correctly."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=60.0,
            duration=120.0,
            volume=50,
        )
        assert status.progress_percent == 50.0

    def test_progress_percent_zero_duration(self):
        """Progress percent handles zero duration."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=60.0,
            duration=0.0,
            volume=50,
        )
        assert status.progress_percent == 0.0

    def test_remaining(self):
        """Remaining time calculates correctly."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=60.0,
            duration=120.0,
            volume=50,
        )
        assert status.remaining == 60.0

    def test_format_position_minutes(self):
        """Format position as MM:SS."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=125.0,  # 2:05
            duration=300.0,
            volume=50,
        )
        assert status.format_position() == "2:05"

    def test_format_position_hours(self):
        """Format position as HH:MM:SS for long tracks."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=3725.0,  # 1:02:05
            duration=7200.0,
            volume=50,
        )
        assert status.format_position() == "1:02:05"

    def test_format_duration(self):
        """Format duration as MM:SS."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=0.0,
            duration=245.0,  # 4:05
            volume=50,
        )
        assert status.format_duration() == "4:05"
