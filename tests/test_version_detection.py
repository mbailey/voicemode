"""Tests for version detection functionality."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from voice_mode.version import (
    get_git_commit_hash,
    is_git_repository,
    get_version,
    __version__,
    base_version
)


def test_get_git_commit_hash():
    """Test getting git commit hash."""
    # Should return a hash in a real git repo
    commit = get_git_commit_hash(short=True)
    commit_full = get_git_commit_hash(short=False)

    if commit:
        # Git auto-grows the short hash as the repo grows so the abbreviation
        # stays unambiguous. Assert a sane range and that the short form is a
        # prefix of the full hash, rather than a fixed length.
        assert 7 <= len(commit) <= 40
        assert all(c in "0123456789abcdef" for c in commit)
        if commit_full:
            assert commit_full.startswith(commit)

    # Test full hash
    if commit_full:
        assert len(commit_full) == 40  # Full hash is always 40 characters
        assert all(c in "0123456789abcdef" for c in commit_full)


def test_is_git_repository():
    """Test git repository detection."""
    # Current directory should be in a git repo during development
    result = is_git_repository()
    # This will be True in development, False in packaged version
    assert isinstance(result, bool)


def test_version_format():
    """Test version string format."""
    # Version should always be a string
    assert isinstance(__version__, str)
    
    # Check format based on environment
    if "-dev." in __version__:
        # Development version format: X.Y.Z-dev.commit[-dirty]
        parts = __version__.split("-")
        assert len(parts) >= 2
        assert parts[1].startswith("dev.")
        
        # Check if dirty flag is present when there are changes
        # (can't reliably test this without modifying files)
    else:
        # Release version format: X.Y.Z
        parts = __version__.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)


def test_get_version_non_git():
    """Test version when not in a git repository."""
    with patch('voice_mode.version.is_git_repository', return_value=False):
        version = get_version()
        # Should return base version without dev suffix
        assert "-dev." not in version
        assert version == base_version  # Use actual base version


def test_get_version_git_with_commit():
    """Test version in git repository with commit."""
    with patch('voice_mode.version.is_git_repository', return_value=True):
        with patch('voice_mode.version.get_git_commit_hash', return_value='abc1234'):
            with patch('subprocess.run') as mock_run:
                # Mock clean git status
                mock_run.return_value = MagicMock(stdout='')
                version = get_version()
                assert version == f"{base_version}-dev.abc1234"


def test_get_version_git_with_changes():
    """Test version in git repository with uncommitted changes."""
    with patch('voice_mode.version.is_git_repository', return_value=True):
        with patch('voice_mode.version.get_git_commit_hash', return_value='abc1234'):
            with patch('subprocess.run') as mock_run:
                # Mock dirty git status
                mock_run.return_value = MagicMock(stdout='M some_file.py')
                version = get_version()
                assert version == f"{base_version}-dev.abc1234-dirty"