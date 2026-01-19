"""Tests for DJ module data models."""

import pytest

from voice_mode.dj import CommandResult, TrackStatus


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_success_result(self):
        """Create a successful result."""
        result = CommandResult(success=True, data={"key": "value"})
        assert result.success is True
        assert result.data == {"key": "value"}
        assert result.error is None

    def test_error_result(self):
        """Create an error result."""
        result = CommandResult(success=False, error="Connection failed")
        assert result.success is False
        assert result.data is None
        assert result.error == "Connection failed"

    def test_default_values(self):
        """Default values are set correctly."""
        result = CommandResult(success=True)
        assert result.data is None
        assert result.error is None


class TestTrackStatus:
    """Tests for TrackStatus dataclass."""

    def test_basic_creation(self):
        """Create a basic TrackStatus."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test Track",
            artist="Test Artist",
            position=30.0,
            duration=180.0,
            volume=50,
        )
        assert status.is_playing is True
        assert status.is_paused is False
        assert status.title == "Test Track"
        assert status.artist == "Test Artist"
        assert status.position == 30.0
        assert status.duration == 180.0
        assert status.volume == 50

    def test_optional_fields(self):
        """Optional fields default to None."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=0.0,
            duration=100.0,
            volume=50,
        )
        assert status.chapter is None
        assert status.chapter_index is None
        assert status.chapter_count is None
        assert status.path is None

    def test_with_chapter_info(self):
        """Create status with chapter information."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=60.0,
            duration=300.0,
            volume=50,
            chapter="Introduction",
            chapter_index=0,
            chapter_count=5,
        )
        assert status.chapter == "Introduction"
        assert status.chapter_index == 0
        assert status.chapter_count == 5


class TestTrackStatusProgressPercent:
    """Tests for progress_percent property."""

    def test_at_start(self):
        """Progress is 0% at start."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=0.0,
            duration=100.0,
            volume=50,
        )
        assert status.progress_percent == 0.0

    def test_at_middle(self):
        """Progress is 50% at middle."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=50.0,
            duration=100.0,
            volume=50,
        )
        assert status.progress_percent == 50.0

    def test_at_end(self):
        """Progress is 100% at end."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=100.0,
            duration=100.0,
            volume=50,
        )
        assert status.progress_percent == 100.0

    def test_clamps_at_100(self):
        """Progress clamps at 100%."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=150.0,
            duration=100.0,
            volume=50,
        )
        assert status.progress_percent == 100.0

    def test_zero_duration(self):
        """Progress is 0% with zero duration."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=50.0,
            duration=0.0,
            volume=50,
        )
        assert status.progress_percent == 0.0


class TestTrackStatusRemaining:
    """Tests for remaining property."""

    def test_at_start(self):
        """Full duration remaining at start."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=0.0,
            duration=100.0,
            volume=50,
        )
        assert status.remaining == 100.0

    def test_at_middle(self):
        """Half duration remaining at middle."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=50.0,
            duration=100.0,
            volume=50,
        )
        assert status.remaining == 50.0

    def test_at_end(self):
        """Zero remaining at end."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=100.0,
            duration=100.0,
            volume=50,
        )
        assert status.remaining == 0.0

    def test_clamps_at_zero(self):
        """Remaining clamps at 0."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=150.0,
            duration=100.0,
            volume=50,
        )
        assert status.remaining == 0.0


class TestTrackStatusTimeFormatting:
    """Tests for time formatting methods."""

    def test_format_seconds(self):
        """Format under one minute."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=45.0,
            duration=100.0,
            volume=50,
        )
        assert status.format_position() == "0:45"

    def test_format_minutes(self):
        """Format minutes and seconds."""
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

    def test_format_hours(self):
        """Format hours, minutes, and seconds."""
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
        """Format duration."""
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

    def test_format_remaining(self):
        """Format remaining time."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=55.0,
            duration=300.0,  # Remaining: 245 = 4:05
            volume=50,
        )
        assert status.format_remaining() == "4:05"

    def test_format_zero_padding(self):
        """Seconds are zero-padded."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=62.0,  # 1:02
            duration=100.0,
            volume=50,
        )
        assert status.format_position() == "1:02"

    def test_format_zero(self):
        """Format zero time."""
        status = TrackStatus(
            is_playing=True,
            is_paused=False,
            title="Test",
            artist=None,
            position=0.0,
            duration=100.0,
            volume=50,
        )
        assert status.format_position() == "0:00"
