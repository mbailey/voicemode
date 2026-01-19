"""
voice-mode - Voice interaction capabilities for Model Context Protocol (MCP) servers

This package provides MCP servers for voice interactions through multiple transports:
- Local microphone recording and playback
- LiveKit room-based voice communication
- Configurable OpenAI-compatible STT/TTS services
"""

from .version import __version__

# DJ module - background music playback for voice sessions
from .dj import (
    # Core playback
    DJController,
    TrackStatus,
    CommandResult,
    MpvPlayer,
    MpvBackend,
    SocketBackend,
    # MFP integration
    MfpService,
    MfpEpisode,
    RssFetcher,
    HttpFetcher,
    # Chapter handling
    Chapter,
    convert_cue_to_ffmetadata,
    convert_cue_file,
    parse_cue_content,
    get_chapter_count,
    # Music library
    MusicLibrary,
    Track,
    LibraryStats,
    FileScanner,
)

__all__ = [
    "__version__",
    # DJ Core
    "DJController",
    "TrackStatus",
    "CommandResult",
    "MpvPlayer",
    "MpvBackend",
    "SocketBackend",
    # DJ MFP
    "MfpService",
    "MfpEpisode",
    "RssFetcher",
    "HttpFetcher",
    # DJ Chapters
    "Chapter",
    "convert_cue_to_ffmetadata",
    "convert_cue_file",
    "parse_cue_content",
    "get_chapter_count",
    # DJ Library
    "MusicLibrary",
    "Track",
    "LibraryStats",
    "FileScanner",
]