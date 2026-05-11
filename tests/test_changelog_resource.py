"""Tests for the changelog resource."""

import pytest
from unittest.mock import patch, mock_open
from pathlib import Path

from voice_mode.resources.changelog import changelog_resource


def test_changelog_resource_finds_file_from_source():
    """Test that the resource finds CHANGELOG.md when running from source."""
    mock_content = """# Changelog

## [2.0.0] - 2025-01-01
### Added
- New feature

## [1.0.0] - 2024-12-01
### Initial Release
- First version
"""
    
    with patch("pathlib.Path.exists") as mock_exists:
        with patch("pathlib.Path.read_text") as mock_read:
            # First path (from source) exists
            mock_exists.side_effect = [True, False, False]
            mock_read.return_value = mock_content
            
            result = getattr(changelog_resource, 'fn', changelog_resource)()
            
            assert result == mock_content
            assert mock_exists.call_count == 1


def test_changelog_resource_fallback_paths():
    """Test that the resource tries multiple paths."""
    mock_content = "# Changelog content"
    
    with patch("pathlib.Path.exists") as mock_exists:
        with patch("pathlib.Path.read_text") as mock_read:
            # First two paths don't exist, third one does
            mock_exists.side_effect = [False, False, True]
            mock_read.return_value = mock_content
            
            result = getattr(changelog_resource, 'fn', changelog_resource)()
            
            assert result == mock_content
            assert mock_exists.call_count == 3


def test_changelog_resource_file_not_found():
    """Test that the resource returns helpful message when file not found."""
    with patch("pathlib.Path.exists") as mock_exists:
        # No paths exist
        mock_exists.return_value = False
        
        result = getattr(changelog_resource, 'fn', changelog_resource)()
        
        assert "CHANGELOG.md not found in package" in result
        assert "https://github.com/mbailey/voicemode" in result


def test_changelog_resource_read_error():
    """Test that the resource handles read errors gracefully."""
    with patch("pathlib.Path.exists") as mock_exists:
        with patch("pathlib.Path.read_text") as mock_read:
            # First path exists but read fails
            mock_exists.side_effect = [True, False, False]
            mock_read.side_effect = PermissionError("Access denied")
            
            result = getattr(changelog_resource, 'fn', changelog_resource)()
            
            assert "Error reading CHANGELOG.md" in result
            assert "Access denied" in result