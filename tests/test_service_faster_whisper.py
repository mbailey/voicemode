"""Tests for faster-whisper service registration."""

from voice_mode.tools.service import _SERVICE_FILE_NAMES


def test_faster_whisper_registered():
    """Test that faster_whisper is registered in the service manager."""
    assert "faster_whisper" in _SERVICE_FILE_NAMES
    assert _SERVICE_FILE_NAMES["faster_whisper"] == "faster-whisper"
