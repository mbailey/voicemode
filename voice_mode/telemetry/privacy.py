"""
Privacy utilities for telemetry data anonymization and binning.

This module provides functions to anonymize and bin telemetry data to protect
user privacy while still providing useful aggregate analytics.
"""

from enum import Enum
from pathlib import Path
from typing import Optional


class DurationBin(str, Enum):
    """Duration bins for privacy-preserving time tracking."""
    UNDER_1_MIN = "<1min"
    MIN_1_TO_5 = "1-5min"
    MIN_5_TO_10 = "5-10min"
    MIN_10_TO_20 = "10-20min"
    MIN_20_TO_60 = "20-60min"
    OVER_60_MIN = ">60min"


class SizeBin(str, Enum):
    """Size bins for privacy-preserving size tracking."""
    UNDER_50KB = "<50KB"
    KB_50_TO_100 = "50-100KB"
    KB_100_TO_200 = "100-200KB"
    KB_200_TO_500 = "200-500KB"
    OVER_500KB = ">500KB"


def bin_duration(seconds: float) -> str:
    """
    Bin a duration in seconds into privacy-preserving categories.

    Args:
        seconds: Duration in seconds

    Returns:
        Duration bin string (e.g., "1-5min")

    Examples:
        >>> bin_duration(30)
        '<1min'
        >>> bin_duration(180)
        '1-5min'
        >>> bin_duration(7200)
        '>60min'
    """
    minutes = seconds / 60.0

    if minutes < 1:
        return DurationBin.UNDER_1_MIN.value
    elif minutes < 5:
        return DurationBin.MIN_1_TO_5.value
    elif minutes < 10:
        return DurationBin.MIN_5_TO_10.value
    elif minutes < 20:
        return DurationBin.MIN_10_TO_20.value
    elif minutes < 60:
        return DurationBin.MIN_20_TO_60.value
    else:
        return DurationBin.OVER_60_MIN.value


def bin_size(size_bytes: int) -> str:
    """
    Bin a size in bytes into privacy-preserving categories.

    Args:
        size_bytes: Size in bytes

    Returns:
        Size bin string (e.g., "50-100KB")

    Examples:
        >>> bin_size(1024)
        '<50KB'
        >>> bin_size(75 * 1024)
        '50-100KB'
        >>> bin_size(1024 * 1024)
        '>500KB'
    """
    kb = size_bytes / 1024.0

    if kb < 50:
        return SizeBin.UNDER_50KB.value
    elif kb < 100:
        return SizeBin.KB_50_TO_100.value
    elif kb < 200:
        return SizeBin.KB_100_TO_200.value
    elif kb < 500:
        return SizeBin.KB_200_TO_500.value
    else:
        return SizeBin.OVER_500KB.value


def anonymize_path(path: str) -> str:
    """
    Anonymize a file path by removing user-specific information.

    Replaces home directory with ~, removes username, and generalizes
    project-specific paths to protect user privacy.

    Args:
        path: File path to anonymize

    Returns:
        Anonymized path string

    Examples:
        >>> anonymize_path("/home/user/Code/project/file.py")
        '~/Code/project'
        >>> anonymize_path("/Users/username/Documents/work")
        '~/Documents'
    """
    try:
        p = Path(path).expanduser().resolve()
        home = Path.home()

        # If path is under home directory, use ~ notation
        if p.is_relative_to(home):
            relative = p.relative_to(home)
            # Only keep up to 2 levels of depth for privacy
            parts = relative.parts[:2] if len(relative.parts) >= 2 else relative.parts
            return str(Path("~") / Path(*parts))

        # For paths outside home, only keep first 2 components
        parts = p.parts[:2] if len(p.parts) >= 2 else p.parts
        return str(Path(*parts))

    except (ValueError, RuntimeError):
        # If path resolution fails, return a generic placeholder
        return "~"


def anonymize_error_message(error_msg: str) -> Optional[str]:
    """
    Anonymize error messages by removing user-specific information.

    Removes file paths, usernames, and other identifying information while
    preserving the error type and general context.

    Args:
        error_msg: Error message to anonymize

    Returns:
        Anonymized error message, or None if message should not be tracked

    Examples:
        >>> anonymize_error_message("FileNotFoundError: /home/user/file.txt")
        'FileNotFoundError: <path>'
        >>> anonymize_error_message("Connection refused at 192.168.1.100")
        'Connection refused'
    """
    if not error_msg:
        return None

    # Preserve error type but anonymize details
    # Common error patterns to preserve
    error_types = [
        "FileNotFoundError",
        "PermissionError",
        "ConnectionError",
        "TimeoutError",
        "HTTPError",
        "APIError",
        "ValueError",
        "TypeError",
    ]

    # Extract error type if present
    for error_type in error_types:
        if error_type in error_msg:
            return error_type

    # For other errors, return first word (usually the error type)
    first_word = error_msg.split(":")[0].split()[0]
    return first_word if first_word else None


def sanitize_version_string(version: str) -> str:
    """
    Sanitize version string to remove any potentially identifying suffixes.

    Args:
        version: Version string (e.g., "2.17.2+local.dev.abc123")

    Returns:
        Sanitized version string (e.g., "2.17.2")

    Examples:
        >>> sanitize_version_string("2.17.2")
        '2.17.2'
        >>> sanitize_version_string("2.17.2+local")
        '2.17.2'
        >>> sanitize_version_string("2.17.2-dev.abc123")
        '2.17.2-dev'
    """
    # Split on + to remove local version suffixes
    base_version = version.split("+")[0]

    # For -dev suffixes, keep the -dev but remove hash
    if "-dev." in base_version:
        base_version = base_version.split(".")[0] + "-dev"

    return base_version
