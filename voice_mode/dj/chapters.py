"""
Chapter file handling for the DJ module.

Provides CUE to FFmetadata conversion for use with mpv's --chapters-file option.
This enables chapter navigation for audio streams where CUE files don't work directly.
"""

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Chapter:
    """A single chapter in an audio file.

    Attributes:
        title: Chapter title/name.
        performer: Artist/performer for this chapter.
        start_ms: Start time in milliseconds.
        end_ms: End time in milliseconds (may be None for last chapter).
    """

    title: str
    performer: str | None
    start_ms: int
    end_ms: int | None = None


def parse_cue_time(time_str: str) -> int:
    """Convert CUE time format (MM:SS:FF) to milliseconds.

    CUE format: MM:SS:FF where FF is frames (75 frames per second).

    Args:
        time_str: Time string in CUE format (e.g., "01:23:45").

    Returns:
        Time in milliseconds.
    """
    parts = time_str.split(":")
    if len(parts) == 3:
        minutes, seconds, frames = int(parts[0]), int(parts[1]), int(parts[2])
        total_ms = (minutes * 60 + seconds) * 1000 + int(frames * 1000 / 75)
        return total_ms
    return 0


def parse_cue_content(cue_content: str) -> list[Chapter]:
    """Parse CUE file content into a list of chapters.

    Args:
        cue_content: Raw CUE file content.

    Returns:
        List of Chapter objects sorted by start time.
    """
    chapters = []
    current_track: dict = {}
    in_track = False

    for line in cue_content.split("\n"):
        line = line.strip()

        # Track start - create new track and mark we're in a track context
        if line.startswith("TRACK"):
            # Save previous track if it has a timestamp
            if current_track and "start_ms" in current_track:
                chapters.append(
                    Chapter(
                        title=current_track.get("title", ""),
                        performer=current_track.get("performer"),
                        start_ms=current_track["start_ms"],
                    )
                )
            in_track = True
            current_track = {}

        # Title - only capture if we're inside a TRACK block
        elif line.startswith("TITLE") and in_track:
            match = re.match(r'TITLE\s+"(.+)"', line)
            if match:
                current_track["title"] = match.group(1)

        # Performer - only capture if we're inside a TRACK block
        elif line.startswith("PERFORMER") and in_track:
            match = re.match(r'PERFORMER\s+"(.+)"', line)
            if match:
                current_track["performer"] = match.group(1)

        # Index (timestamp)
        elif line.startswith("INDEX 01") and in_track:
            match = re.match(r"INDEX 01\s+(\d+:\d+:\d+)", line)
            if match:
                current_track["start_ms"] = parse_cue_time(match.group(1))

    # Don't forget the last track (if it has a timestamp)
    if current_track and "start_ms" in current_track:
        chapters.append(
            Chapter(
                title=current_track.get("title", ""),
                performer=current_track.get("performer"),
                start_ms=current_track["start_ms"],
            )
        )

    # Sort chapters by start time
    chapters.sort(key=lambda x: x.start_ms)

    return chapters


def convert_cue_to_ffmetadata(
    cue_content: str, duration_ms: int | None = None
) -> str:
    """Convert CUE content to FFmpeg metadata chapter format.

    Args:
        cue_content: Raw CUE file content.
        duration_ms: Optional duration in milliseconds for the last chapter's end time.

    Returns:
        FFmpeg metadata format string suitable for mpv --chapters-file.
    """
    chapters = parse_cue_content(cue_content)

    # Calculate end times
    for i, chapter in enumerate(chapters):
        if i + 1 < len(chapters):
            chapter.end_ms = chapters[i + 1].start_ms
        else:
            # Use provided duration or add 1 hour for last chapter
            chapter.end_ms = duration_ms if duration_ms else chapter.start_ms + 3600000

    # Generate FFmpeg chapters format
    output = [";FFMETADATA1"]

    for i, chapter in enumerate(chapters):
        title = chapter.title or f"Track {i + 1}"
        if chapter.performer:
            title = f"{title} - {chapter.performer}"

        output.append("")
        output.append("[CHAPTER]")
        output.append("TIMEBASE=1/1000")
        output.append(f"START={chapter.start_ms}")
        output.append(f"END={chapter.end_ms}")
        output.append(f"title={title}")

    return "\n".join(output)


def convert_cue_file(cue_path: Path, duration_ms: int | None = None) -> str:
    """Convert a CUE file to FFmpeg metadata chapter format.

    Args:
        cue_path: Path to the CUE file.
        duration_ms: Optional duration in milliseconds for the last chapter's end time.

    Returns:
        FFmpeg metadata format string.

    Raises:
        FileNotFoundError: If the CUE file doesn't exist.
        IOError: If the file can't be read.
    """
    cue_content = cue_path.read_text()
    return convert_cue_to_ffmetadata(cue_content, duration_ms)


def get_chapter_count(cue_content: str) -> int:
    """Get the number of chapters in a CUE file.

    Args:
        cue_content: Raw CUE file content.

    Returns:
        Number of chapters.
    """
    return len(parse_cue_content(cue_content))
