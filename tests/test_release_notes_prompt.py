"""Tests for the release notes prompt."""

import pytest
from unittest.mock import patch, MagicMock

from voice_mode.prompts.release_notes import release_notes_prompt


def test_release_notes_prompt_parses_changelog():
    """Test that the prompt correctly parses changelog entries."""
    mock_changelog = """# Changelog

## [2.0.0] - 2025-01-01
### Added
- Feature A
- Feature B

### Fixed
- Bug fix 1

## [1.1.0] - 2024-12-15
### Changed
- Updated something

## [1.0.0] - 2024-12-01
### Initial Release
- First version
"""
    
    with patch("voice_mode.resources.changelog.changelog_resource") as mock_resource:
        mock_resource.fn.return_value = mock_changelog
        
        result = release_notes_prompt.fn(versions="2")
        
        # Should show oldest first
        assert "[1.1.0]" in result
        assert "[2.0.0]" in result
        assert "[1.0.0]" not in result  # Only 2 versions requested
        
        # Check order (oldest first)
        assert result.index("[1.1.0]") < result.index("[2.0.0]")
        
        # Check content is included
        assert "Feature A" in result
        assert "Updated something" in result
        
        # Check clean output (no header/footer)
        assert "Voice Mode Release Notes" not in result
        assert "https://github.com/mbailey/voicemode" not in result


def test_release_notes_prompt_handles_missing_changelog():
    """Test that the prompt handles missing CHANGELOG gracefully."""
    with patch("voice_mode.resources.changelog.changelog_resource") as mock_resource:
        mock_resource.fn.return_value = "CHANGELOG.md not found in package."
        
        result = release_notes_prompt.fn()
        
        assert "CHANGELOG.md not found" in result


def test_release_notes_prompt_handles_error():
    """Test that the prompt handles errors from the resource."""
    with patch("voice_mode.resources.changelog.changelog_resource") as mock_resource:
        mock_resource.fn.return_value = "Error reading CHANGELOG.md: Permission denied"
        
        result = release_notes_prompt.fn()
        
        assert "Error reading CHANGELOG.md" in result


def test_release_notes_prompt_default_versions():
    """Test that the prompt defaults to 5 versions."""
    mock_changelog = """# Changelog

## [6.0.0] - 2025-06-01
### Added
- Version 6

## [5.0.0] - 2025-05-01
### Added
- Version 5

## [4.0.0] - 2025-04-01
### Added
- Version 4

## [3.0.0] - 2025-03-01
### Added
- Version 3

## [2.0.0] - 2025-02-01
### Added
- Version 2

## [1.0.0] - 2025-01-01
### Added
- Version 1
"""
    
    with patch("voice_mode.resources.changelog.changelog_resource") as mock_resource:
        mock_resource.fn.return_value = mock_changelog
        
        result = release_notes_prompt.fn()  # No versions specified
        
        # Should show 5 versions (default)
        assert "[2.0.0]" in result
        assert "[3.0.0]" in result
        assert "[4.0.0]" in result
        assert "[5.0.0]" in result
        assert "[6.0.0]" in result
        assert "[1.0.0]" not in result  # Only 5 versions


def test_release_notes_prompt_handles_empty_string():
    """Test that the prompt handles empty string parameter from Claude Code."""
    mock_changelog = """# Changelog

## [6.0.0] - 2025-06-01
### Added
- Version 6

## [5.0.0] - 2025-05-01
### Added
- Version 5

## [4.0.0] - 2025-04-01
### Added
- Version 4

## [3.0.0] - 2025-03-01
### Added
- Version 3

## [2.0.0] - 2025-02-01
### Added
- Version 2

## [1.0.0] - 2025-01-01
### Added
- Version 1
"""
    
    with patch("voice_mode.resources.changelog.changelog_resource") as mock_resource:
        mock_resource.fn.return_value = mock_changelog
        
        # Test with empty string (what Claude Code sends)
        result = release_notes_prompt.fn(versions="")
        
        # Should use default of 5 versions
        assert "[2.0.0]" in result
        assert "[3.0.0]" in result
        assert "[4.0.0]" in result
        assert "[5.0.0]" in result
        assert "[6.0.0]" in result
        assert "[1.0.0]" not in result  # Only 5 versions


def test_release_notes_prompt_respects_version_limit():
    """Test that the prompt respects the version limit parameter."""
    mock_changelog = """# Changelog

## [3.0.0] - 2025-03-01
### Added
- Version 3

## [2.0.0] - 2025-02-01
### Added
- Version 2

## [1.0.0] - 2025-01-01
### Added
- Version 1
"""
    
    with patch("voice_mode.resources.changelog.changelog_resource") as mock_resource:
        mock_resource.fn.return_value = mock_changelog
        
        # Test with 1 version
        result = release_notes_prompt.fn(versions="1")
        assert "[3.0.0]" in result
        assert "[2.0.0]" not in result
        assert "[1.0.0]" not in result
        
        # Test with all versions
        result = release_notes_prompt.fn(versions="10")
        assert "[3.0.0]" in result
        assert "[2.0.0]" in result
        assert "[1.0.0]" in result