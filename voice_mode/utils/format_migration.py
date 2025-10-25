"""
Audio format migration utilities.

This module provides utilities for detecting existing audio format usage
and helping with migration to the new default pcm format for streaming TTS.
"""

import os
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger("voicemode")


def detect_existing_format_preference() -> Optional[str]:
    """
    Detect if user has existing audio files that suggest a format preference.
    
    Returns:
        Format string if a clear preference is detected, None otherwise
    """
    audio_dir = Path.home() / "voice-mode_audio"
    
    if not audio_dir.exists():
        return None
    
    # Count files by extension
    format_counts = {}
    for file in audio_dir.iterdir():
        if file.is_file():
            ext = file.suffix.lower().lstrip('.')
            if ext in ['mp3', 'opus', 'wav', 'flac', 'aac', 'm4a']:
                format_counts[ext] = format_counts.get(ext, 0) + 1
    
    if not format_counts:
        return None
    
    # If user has many MP3 files but no Opus files, suggest keeping MP3
    mp3_count = format_counts.get('mp3', 0)
    opus_count = format_counts.get('opus', 0)
    
    if mp3_count > 10 and opus_count == 0:
        logger.info(f"Detected {mp3_count} existing MP3 files. Consider setting VOICE_AUDIO_FORMAT=mp3 for consistency.")
        return 'mp3'
    
    return None


def should_show_migration_hint() -> bool:
    """
    Determine if we should show a migration hint to the user.
    
    Returns:
        True if migration hint should be shown
    """
    # Check if user has explicitly set format
    if os.getenv('VOICE_AUDIO_FORMAT'):
        return False
    
    # Check if migration hint was already shown
    hint_file = Path.home() / '.voice-mode-format-migration-shown'
    if hint_file.exists():
        return False
    
    # Check if user has existing MP3 files
    existing_format = detect_existing_format_preference()
    if existing_format == 'mp3':
        return True
    
    return False


def mark_migration_hint_shown():
    """Mark that the migration hint has been shown to the user."""
    hint_file = Path.home() / '.voice-mode-format-migration-shown'
    hint_file.touch()


def get_migration_message() -> str:
    """Get the migration hint message."""
    return """
🎵 Voice Mode Audio Format Update

Voice Mode now uses Opus format by default for better performance.
We detected you have existing MP3 recordings.

To continue using MP3 format, set:
  export VOICE_AUDIO_FORMAT=mp3

Or to use the new Opus format (recommended):
  export VOICE_AUDIO_FORMAT=opus

Your existing MP3 files will continue to work regardless of this setting.
For more info, see: docs/audio-format-migration.md
"""
