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

Music For Programming integration:
    >>> from voice_mode.dj import MfpService
    >>> mfp = MfpService()
    >>> episodes = mfp.list_episodes()
    >>> ep = episodes[0]
    >>> dj = DJController()
    >>> dj.play(ep.url, chapters_file=str(mfp.get_chapters_file(ep.number)))
"""

from .controller import DJController
from .models import CommandResult, TrackStatus
from .player import MpvBackend, MpvPlayer, SocketBackend
from .mfp import MfpService, MfpEpisode, RssFetcher, HttpFetcher
from .chapters import (
    Chapter,
    convert_cue_to_ffmetadata,
    convert_cue_file,
    parse_cue_content,
    get_chapter_count,
)

__all__ = [
    # Core playback
    "DJController",
    "TrackStatus",
    "CommandResult",
    "MpvPlayer",
    "MpvBackend",
    "SocketBackend",
    # MFP integration
    "MfpService",
    "MfpEpisode",
    "RssFetcher",
    "HttpFetcher",
    # Chapter handling
    "Chapter",
    "convert_cue_to_ffmetadata",
    "convert_cue_file",
    "parse_cue_content",
    "get_chapter_count",
]
