"""
DJ module for background music playback in voice sessions.

This module provides programmatic control of audio playback via mpv,
with support for chapters, volume control, and playback status.

Example usage:
    >>> from voice_mode.dj import DJController
    >>> dj = DJController()
    >>> dj.play("/path/to/ambient.mp3", volume=30)
    >>> status = dj.status()
    >>> print(f"Playing: {status.title}")
    >>> dj.pause()
    >>> dj.stop()
"""

from .controller import DJController
from .models import CommandResult, TrackStatus
from .player import MpvBackend, MpvPlayer, SocketBackend

__all__ = [
    "DJController",
    "TrackStatus",
    "CommandResult",
    "MpvPlayer",
    "MpvBackend",
    "SocketBackend",
]
