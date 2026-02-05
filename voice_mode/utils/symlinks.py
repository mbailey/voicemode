"""Symlink utilities for VoiceMode audio files.

Provides functions to maintain 'latest' symlinks that always point to the most recent
audio files, making it easy to quickly access the last recording or TTS output.
"""

import logging
from pathlib import Path
from typing import Optional, Literal

from ..config import AUDIO_DIR

logger = logging.getLogger("voicemode")

AudioType = Literal["stt", "tts"]


def update_latest_symlinks(
    file_path: Path | str,
    audio_type: AudioType,
) -> tuple[Optional[Path], Optional[Path]]:
    """Update 'latest' symlinks to point to the most recently saved audio file.

    Creates/updates two symlinks in AUDIO_DIR:
    - latest-{TYPE}.<ext> - Most recent file of this type (STT or TTS)
    - latest.<ext> - Most recent file of any type

    The symlinks include the target file's extension for OS file browser compatibility.
    Relative paths are used for portability.

    Args:
        file_path: Path to the audio file that was just saved
        audio_type: Type of audio - "stt" for speech-to-text recordings,
                   "tts" for text-to-speech output

    Returns:
        Tuple of (type_symlink_path, latest_symlink_path) or (None, None) on error

    Example:
        >>> update_latest_symlinks("/home/user/.voicemode/audio/2026/02/123_conv_stt.wav", "stt")
        (Path('~/.voicemode/audio/latest-stt.wav'), Path('~/.voicemode/audio/latest.wav'))
    """
    file_path = Path(file_path)

    if not file_path.exists():
        logger.warning(f"Cannot create symlink: file does not exist: {file_path}")
        return None, None

    # Get file extension (including the dot)
    extension = file_path.suffix
    if not extension:
        logger.warning(f"Cannot create symlink: file has no extension: {file_path}")
        return None, None

    # Normalize audio type to uppercase for symlink name (STT, TTS)
    type_upper = audio_type.upper()

    # Define symlink names
    type_symlink_name = f"latest-{type_upper}{extension}"
    latest_symlink_name = f"latest{extension}"

    type_symlink_path = AUDIO_DIR / type_symlink_name
    latest_symlink_path = AUDIO_DIR / latest_symlink_name

    # Calculate relative path from AUDIO_DIR to the target file
    try:
        relative_target = file_path.relative_to(AUDIO_DIR)
    except ValueError:
        # File is not under AUDIO_DIR, use absolute path
        logger.debug(f"File not under AUDIO_DIR, using absolute path: {file_path}")
        relative_target = file_path

    try:
        # Remove old symlinks with any extension for this type
        _remove_old_symlinks(AUDIO_DIR, f"latest-{type_upper}")

        # Remove old 'latest' symlinks with any extension
        _remove_old_symlinks(AUDIO_DIR, "latest")

        # Create new symlinks
        type_symlink_path.symlink_to(relative_target)
        logger.debug(f"Created symlink: {type_symlink_path} -> {relative_target}")

        latest_symlink_path.symlink_to(relative_target)
        logger.debug(f"Created symlink: {latest_symlink_path} -> {relative_target}")

        return type_symlink_path, latest_symlink_path

    except OSError as e:
        logger.error(f"Failed to create symlink: {e}")
        return None, None


def _remove_old_symlinks(directory: Path, prefix: str) -> None:
    """Remove old symlinks matching a prefix pattern.

    Removes symlinks like 'latest-STT.*', 'latest-TTS.*', or 'latest.*'
    to handle extension changes between files.

    Args:
        directory: Directory containing the symlinks
        prefix: Symlink name prefix to match (e.g., 'latest-STT', 'latest')
    """
    # Glob for files matching the prefix pattern
    # Use case-insensitive matching for the prefix
    for pattern in [f"{prefix}.*", f"{prefix.lower()}.*", f"{prefix.upper()}.*"]:
        for old_symlink in directory.glob(pattern):
            # Only remove if it's a symlink (not a regular file)
            if old_symlink.is_symlink():
                try:
                    old_symlink.unlink()
                    logger.debug(f"Removed old symlink: {old_symlink}")
                except OSError as e:
                    logger.warning(f"Failed to remove old symlink {old_symlink}: {e}")
