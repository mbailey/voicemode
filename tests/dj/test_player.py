"""Tests for the MpvPlayer class."""

import pytest

from voice_mode.dj import CommandResult, MpvPlayer


class TestMpvPlayerConnection:
    """Tests for connection status."""

    def test_is_running_returns_true_when_connected(self, mock_player, mock_backend):
        """Player reports running when backend is connected."""
        assert mock_player.is_running() is True

    def test_is_running_returns_false_when_disconnected(
        self, disconnected_player, disconnected_backend
    ):
        """Player reports not running when backend is disconnected."""
        assert disconnected_player.is_running() is False


class TestMpvPlayerPropertyAccess:
    """Tests for property get/set operations."""

    def test_get_property_returns_value(self, mock_player, mock_backend):
        """Getting a property returns its value."""
        mock_backend.set_property("volume", 75.0)
        assert mock_player.get_property("volume") == 75.0

    def test_get_property_returns_none_for_unknown(self, mock_player, mock_backend):
        """Getting an unknown property returns None."""
        mock_backend.set_command_result(
            ["get_property", "unknown"],
            CommandResult(success=False, error="property not found"),
        )
        assert mock_player.get_property("unknown") is None

    def test_set_property_sends_command(self, mock_player, mock_backend):
        """Setting a property sends the correct command."""
        mock_player.set_property("volume", 80)
        commands = mock_backend.get_commands()
        assert ["set_property", "volume", 80] in commands

    def test_set_property_returns_success(self, mock_player, mock_backend):
        """Setting a property returns success status."""
        assert mock_player.set_property("volume", 80) is True


class TestMpvPlayerPlaybackControl:
    """Tests for playback control methods."""

    def test_pause_sets_pause_property(self, mock_player, mock_backend):
        """Pause sets the pause property to True."""
        mock_player.pause()
        commands = mock_backend.get_commands()
        assert ["set_property", "pause", True] in commands

    def test_resume_clears_pause_property(self, mock_player, mock_backend):
        """Resume sets the pause property to False."""
        mock_player.resume()
        commands = mock_backend.get_commands()
        assert ["set_property", "pause", False] in commands

    def test_stop_sends_quit_command(self, mock_player, mock_backend):
        """Stop sends the quit command."""
        mock_player.stop()
        commands = mock_backend.get_commands()
        assert ["quit"] in commands


class TestMpvPlayerNavigation:
    """Tests for navigation methods."""

    def test_seek_absolute(self, mock_player, mock_backend):
        """Seek sends correct command for absolute seek."""
        mock_player.seek(60.0, "absolute")
        commands = mock_backend.get_commands()
        assert ["seek", 60.0, "absolute"] in commands

    def test_seek_relative(self, mock_player, mock_backend):
        """Seek sends correct command for relative seek."""
        mock_player.seek(10.0, "relative")
        commands = mock_backend.get_commands()
        assert ["seek", 10.0, "relative"] in commands

    def test_next_chapter(self, mock_player, mock_backend):
        """Next chapter sends correct command."""
        mock_player.next_chapter()
        commands = mock_backend.get_commands()
        assert ["add", "chapter", 1] in commands

    def test_prev_chapter(self, mock_player, mock_backend):
        """Previous chapter sends correct command."""
        mock_player.prev_chapter()
        commands = mock_backend.get_commands()
        assert ["add", "chapter", -1] in commands


class TestMpvPlayerVolume:
    """Tests for volume control methods."""

    def test_get_volume_returns_level(self, mock_player, mock_backend):
        """Get volume returns the current level."""
        mock_backend.set_property("volume", 65.0)
        assert mock_player.get_volume() == 65.0

    def test_set_volume_sends_command(self, mock_player, mock_backend):
        """Set volume sends the correct command."""
        mock_player.set_volume(70)
        commands = mock_backend.get_commands()
        assert ["set_property", "volume", 70] in commands

    def test_set_volume_clamps_high(self, mock_player, mock_backend):
        """Set volume clamps values above 100."""
        mock_player.set_volume(150)
        commands = mock_backend.get_commands()
        assert ["set_property", "volume", 100] in commands

    def test_set_volume_clamps_low(self, mock_player, mock_backend):
        """Set volume clamps values below 0."""
        mock_player.set_volume(-10)
        commands = mock_backend.get_commands()
        assert ["set_property", "volume", 0] in commands


class TestMpvPlayerStatus:
    """Tests for status information methods."""

    def test_get_position(self, mock_player, mock_backend):
        """Get position returns current time."""
        mock_backend.set_property("time-pos", 45.5)
        assert mock_player.get_position() == 45.5

    def test_get_duration(self, mock_player, mock_backend):
        """Get duration returns total time."""
        mock_backend.set_property("duration", 200.0)
        assert mock_player.get_duration() == 200.0

    def test_get_path(self, mock_player, mock_backend):
        """Get path returns the track path."""
        mock_backend.set_property("path", "/music/track.mp3")
        assert mock_player.get_path() == "/music/track.mp3"

    def test_get_title(self, mock_player, mock_backend):
        """Get title returns the media title."""
        mock_backend.set_property("media-title", "My Song")
        assert mock_player.get_title() == "My Song"

    def test_is_paused_when_paused(self, mock_player, mock_backend):
        """Is paused returns True when paused."""
        mock_backend.set_property("pause", True)
        assert mock_player.is_paused() is True

    def test_is_paused_when_playing(self, mock_player, mock_backend):
        """Is paused returns False when playing."""
        mock_backend.set_property("pause", False)
        assert mock_player.is_paused() is False

    def test_get_chapter_metadata(self, mock_player, mock_backend):
        """Get chapter metadata returns chapter info."""
        meta = {"title": "Introduction"}
        mock_backend.set_property("chapter-metadata", meta)
        assert mock_player.get_chapter_metadata() == meta

    def test_get_chapter_index(self, mock_player, mock_backend):
        """Get chapter index returns current chapter."""
        mock_backend.set_property("chapter", 3)
        assert mock_player.get_chapter_index() == 3

    def test_get_chapter_count(self, mock_player, mock_backend):
        """Get chapter count returns total chapters."""
        mock_backend.set_property("chapter-list/count", 10)
        assert mock_player.get_chapter_count() == 10
