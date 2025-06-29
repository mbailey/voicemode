"""Tests for FFmpeg detection and error handling."""

import pytest
from unittest.mock import patch, MagicMock
import sys
import platform

from voice_mode.utils.ffmpeg_check import (
    check_ffmpeg,
    check_ffprobe,
    get_ffmpeg_version,
    get_install_instructions,
    check_and_report_ffmpeg,
    ensure_ffmpeg_or_exit
)


class TestFFmpegDetection:
    """Test FFmpeg detection functions."""
    
    def test_check_ffmpeg_installed(self):
        """Test when FFmpeg is installed."""
        with patch('shutil.which', return_value='/usr/bin/ffmpeg'):
            installed, path = check_ffmpeg()
            assert installed is True
            assert path == '/usr/bin/ffmpeg'
    
    def test_check_ffmpeg_not_installed(self):
        """Test when FFmpeg is not installed."""
        with patch('shutil.which', return_value=None):
            installed, path = check_ffmpeg()
            assert installed is False
            assert path is None
    
    def test_check_ffprobe_installed(self):
        """Test when ffprobe is installed."""
        with patch('shutil.which', return_value='/usr/bin/ffprobe'):
            installed, path = check_ffprobe()
            assert installed is True
            assert path == '/usr/bin/ffprobe'
    
    def test_check_ffprobe_not_installed(self):
        """Test when ffprobe is not installed."""
        with patch('shutil.which', return_value=None):
            installed, path = check_ffprobe()
            assert installed is False
            assert path is None
    
    def test_get_ffmpeg_version_success(self):
        """Test getting FFmpeg version when installed."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ffmpeg version 4.4.2-0ubuntu0.22.04.1 Copyright (c) 2000-2021 the FFmpeg developers\n"
        
        with patch('subprocess.run', return_value=mock_result):
            version = get_ffmpeg_version()
            assert version == "4.4.2-0ubuntu0.22.04.1"
    
    def test_get_ffmpeg_version_not_installed(self):
        """Test getting FFmpeg version when not installed."""
        with patch('subprocess.run', side_effect=FileNotFoundError):
            version = get_ffmpeg_version()
            assert version is None
    
    @pytest.mark.parametrize("system,expected_content", [
        ("darwin", "brew install ffmpeg"),
        ("linux", ["sudo apt install ffmpeg", "sudo dnf install ffmpeg", "sudo pacman -S ffmpeg"]),  # Any Linux distro
        ("windows", "WSL2")
    ])
    def test_get_install_instructions(self, system, expected_content):
        """Test platform-specific installation instructions."""
        with patch('platform.system', return_value=system):
            instructions = get_install_instructions()
            
            # For Linux, at least one of the package manager commands should be present
            if isinstance(expected_content, list):
                assert any(cmd in instructions for cmd in expected_content), \
                    f"None of {expected_content} found in instructions"
            else:
                assert expected_content in instructions
            
            assert "FFmpeg is required" in instructions
    
    def test_check_and_report_ffmpeg_all_installed(self, capsys):
        """Test reporting when everything is installed."""
        with patch('shutil.which', return_value='/usr/bin/ffmpeg'):
            with patch('voice_mode.utils.ffmpeg_check.get_ffmpeg_version', return_value="4.4.2"):
                result = check_and_report_ffmpeg()
                assert result is True
                captured = capsys.readouterr()
                assert "FFmpeg Installation Required" not in captured.out
    
    def test_check_and_report_ffmpeg_missing(self, capsys):
        """Test reporting when FFmpeg is missing."""
        with patch('shutil.which', return_value=None):
            result = check_and_report_ffmpeg()
            assert result is False
            captured = capsys.readouterr()
            assert "FFmpeg Installation Required" in captured.out
            assert "FFmpeg is required" in captured.out
    
    def test_ensure_ffmpeg_or_exit_installed(self):
        """Test ensure_ffmpeg_or_exit when FFmpeg is installed."""
        with patch('voice_mode.utils.ffmpeg_check.check_and_report_ffmpeg', return_value=True):
            # Should not raise or exit
            ensure_ffmpeg_or_exit()
    
    def test_ensure_ffmpeg_or_exit_missing(self):
        """Test ensure_ffmpeg_or_exit when FFmpeg is missing."""
        with patch('voice_mode.utils.ffmpeg_check.check_and_report_ffmpeg', return_value=False):
            with patch('sys.exit') as mock_exit:
                ensure_ffmpeg_or_exit()
                mock_exit.assert_called_once_with(1)


class TestFFmpegLinuxDistros:
    """Test Linux distribution detection for install instructions."""
    
    @pytest.mark.parametrize("distro_id,expected_command", [
        ("ubuntu", "sudo apt install ffmpeg"),
        ("debian", "sudo apt install ffmpeg"),
        ("fedora", "sudo dnf install ffmpeg"),
        ("rhel", "sudo dnf install ffmpeg"),
        ("arch", "sudo pacman -S ffmpeg"),
        ("manjaro", "sudo pacman -S ffmpeg"),
        ("opensuse", "sudo zypper install ffmpeg"),  # Falls back to generic
    ])
    def test_linux_distro_instructions(self, distro_id, expected_command):
        """Test instructions for different Linux distributions."""
        with patch('platform.system', return_value='Linux'):
            # Mock the os-release file
            os_release_content = f'ID={distro_id}\nNAME="Test Linux"\n'
            with patch('builtins.open', create=True) as mock_open:
                mock_open.return_value.__enter__.return_value = os_release_content.splitlines()
                instructions = get_install_instructions()
                assert expected_command in instructions


class TestManualTesting:
    """Instructions for manual testing."""
    
    def test_manual_ffmpeg_missing(self):
        """
        Manual test instructions:
        
        1. Temporarily rename ffmpeg:
           sudo mv /usr/bin/ffmpeg /usr/bin/ffmpeg.bak
           sudo mv /usr/bin/ffprobe /usr/bin/ffprobe.bak
        
        2. Run voice-mode:
           uvx voice-mode
        
        3. Verify you see the error message with installation instructions
        
        4. Restore ffmpeg:
           sudo mv /usr/bin/ffmpeg.bak /usr/bin/ffmpeg
           sudo mv /usr/bin/ffprobe.bak /usr/bin/ffprobe
        
        Alternative using PATH:
        1. Create empty directory: mkdir /tmp/empty-bin
        2. Run with modified PATH: PATH=/tmp/empty-bin:$PATH uvx voice-mode
        3. Verify error message appears
        """
        pass  # This is just documentation