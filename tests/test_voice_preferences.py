"""Tests for voice preferences system."""

import os
import tempfile
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

from voice_mode.voice_preferences import (
    find_voices_file,
    load_voice_preferences,
    get_preferred_voices,
    clear_cache
)


class TestVoicePreferences:
    """Test voice preferences loading and discovery."""
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_cache()
    
    def test_find_voices_file_in_current_dir(self, tmp_path):
        """Test finding voices.txt in current directory."""
        # Create .voicemode/voices.txt in temp dir
        voicemode_dir = tmp_path / ".voicemode"
        voicemode_dir.mkdir()
        voices_file = voicemode_dir / "voices.txt"
        voices_file.write_text("nova\nshimmer\n")
        
        # Change to temp directory
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            
            # Should find the file
            found = find_voices_file()
            assert found is not None
            assert found == voices_file
        finally:
            os.chdir(original_cwd)
    
    def test_find_voices_file_in_parent_dir(self, tmp_path):
        """Test finding voices.txt in parent directory."""
        # Create parent/.voicemode/voices.txt
        parent_dir = tmp_path / "parent"
        parent_dir.mkdir()
        voicemode_dir = parent_dir / ".voicemode"
        voicemode_dir.mkdir()
        voices_file = voicemode_dir / "voices.txt"
        voices_file.write_text("alloy\n")
        
        # Create subdirectory
        sub_dir = parent_dir / "subdir"
        sub_dir.mkdir()
        
        # Change to subdirectory
        original_cwd = os.getcwd()
        try:
            os.chdir(sub_dir)
            
            # Should find the file in parent
            found = find_voices_file()
            assert found is not None
            assert found == voices_file
        finally:
            os.chdir(original_cwd)
    
    def test_find_voices_file_in_home(self, tmp_path):
        """Test finding voices.txt in home directory."""
        # Create a fake home directory
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        voicemode_dir = fake_home / ".voicemode"
        voicemode_dir.mkdir()
        voices_file = voicemode_dir / "voices.txt"
        voices_file.write_text("echo\nfable\n")
        
        # Create a working directory
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        
        original_cwd = os.getcwd()
        try:
            os.chdir(work_dir)
            
            # Mock Path.home() to return our fake home
            with patch('pathlib.Path.home', return_value=fake_home):
                found = find_voices_file()
                assert found is not None
                assert found == voices_file
        finally:
            os.chdir(original_cwd)
    
    def test_no_voices_file(self, tmp_path):
        """Test when no voices.txt file exists."""
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            
            # Mock Path.home() to return temp dir (no .voicemode there)
            with patch('pathlib.Path.home', return_value=tmp_path):
                found = find_voices_file()
                assert found is None
        finally:
            os.chdir(original_cwd)
    
    def test_load_voice_preferences(self, tmp_path):
        """Test loading voice preferences from file."""
        # Create voices file
        voicemode_dir = tmp_path / ".voicemode"
        voicemode_dir.mkdir()
        voices_file = voicemode_dir / "voices.txt"
        voices_file.write_text("nova\nshimmer\nalloy\n# This is a comment\n\necho\n")
        
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            
            # Load preferences
            voices = load_voice_preferences()
            assert voices == ["nova", "shimmer", "alloy", "echo"]
        finally:
            os.chdir(original_cwd)
    
    def test_load_voice_preferences_with_whitespace(self, tmp_path):
        """Test loading preferences handles whitespace correctly."""
        # Create voices file with whitespace
        voicemode_dir = tmp_path / ".voicemode"
        voicemode_dir.mkdir()
        voices_file = voicemode_dir / "voices.txt"
        voices_file.write_text("  nova  \n\tshimmer\t\n  \n\nalloy")
        
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            
            # Load preferences
            voices = load_voice_preferences()
            assert voices == ["nova", "shimmer", "alloy"]
        finally:
            os.chdir(original_cwd)
    
    def test_preferences_cached(self, tmp_path):
        """Test that preferences are cached after first load."""
        # Create voices file
        voicemode_dir = tmp_path / ".voicemode"
        voicemode_dir.mkdir()
        voices_file = voicemode_dir / "voices.txt"
        voices_file.write_text("nova\n")
        
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            
            # First load
            voices1 = get_preferred_voices()
            assert voices1 == ["nova"]
            
            # Modify file
            voices_file.write_text("shimmer\necho\n")
            
            # Should still get cached value
            voices2 = get_preferred_voices()
            assert voices2 == ["nova"]
            
            # Clear cache and reload
            clear_cache()
            voices3 = get_preferred_voices()
            assert voices3 == ["shimmer", "echo"]
        finally:
            os.chdir(original_cwd)
    
    def test_error_handling(self, tmp_path):
        """Test error handling when file can't be read."""
        # Create a directory instead of file
        voicemode_dir = tmp_path / ".voicemode"
        voicemode_dir.mkdir()
        voices_file = voicemode_dir / "voices.txt"
        voices_file.mkdir()  # This will cause an error when trying to read
        
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            
            # Should handle error gracefully
            voices = load_voice_preferences()
            assert voices == []
        finally:
            os.chdir(original_cwd)
    
    def test_only_first_file_used(self, tmp_path):
        """Test that only the first found file is used."""
        # Create parent/.voicemode/voices.txt
        parent_dir = tmp_path / "parent"
        parent_dir.mkdir()
        parent_voicemode = parent_dir / ".voicemode"
        parent_voicemode.mkdir()
        parent_voices = parent_voicemode / "voices.txt"
        parent_voices.write_text("parent_voice\n")
        
        # Create parent/child/.voicemode/voices.txt
        child_dir = parent_dir / "child"
        child_dir.mkdir()
        child_voicemode = child_dir / ".voicemode"
        child_voicemode.mkdir()
        child_voices = child_voicemode / "voices.txt"
        child_voices.write_text("child_voice\n")
        
        original_cwd = os.getcwd()
        try:
            os.chdir(child_dir)
            
            # Should only use child file, not parent
            voices = load_voice_preferences()
            assert voices == ["child_voice"]
            assert "parent_voice" not in voices
        finally:
            os.chdir(original_cwd)
    
    def test_standalone_voices_file_precedence(self, tmp_path):
        """Test that standalone .voices.txt takes precedence over .voicemode/voices.txt."""
        # Create both files in same directory
        standalone_file = tmp_path / ".voices.txt"
        standalone_file.write_text("echo\nfable")
        
        voicemode_dir = tmp_path / ".voicemode"
        voicemode_dir.mkdir()
        voicemode_file = voicemode_dir / "voices.txt"
        voicemode_file.write_text("nova\nalloy")
        
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)
            
            # Reset cache
            import voice_mode.voice_preferences
            voice_mode.voice_preferences._cached_preferences = None
            voice_mode.voice_preferences._preferences_loaded = False
            
            # Should find standalone file first
            found = find_voices_file()
            assert found == standalone_file
            
            # Should load from standalone file
            voices = load_voice_preferences()
            assert voices == ["echo", "fable"]
        finally:
            os.chdir(original_cwd)
    
    def test_home_standalone_voices_file(self, tmp_path):
        """Test finding standalone .voices.txt in home directory."""
        # Create a fake home directory
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        
        # Create standalone file (hidden with dot prefix)
        standalone_file = fake_home / ".voices.txt"
        standalone_file.write_text("shimmer\nonyx")
        
        # Also create .voicemode version (should not be used)
        voicemode_dir = fake_home / ".voicemode"
        voicemode_dir.mkdir()
        voicemode_file = voicemode_dir / "voices.txt"
        voicemode_file.write_text("nova\nalloy")
        
        # Create a working directory
        work_dir = tmp_path / "work"
        work_dir.mkdir()
        
        original_cwd = os.getcwd()
        try:
            os.chdir(work_dir)
            
            # Mock Path.home() to return our fake home
            with patch('pathlib.Path.home', return_value=fake_home):
                # Reset cache
                import voice_mode.voice_preferences
                voice_mode.voice_preferences._cached_preferences = None
                voice_mode.voice_preferences._preferences_loaded = False
                
                # Should find standalone file first
                found = find_voices_file()
                assert found == standalone_file
                
                # Should load from standalone file
                voices = load_voice_preferences()
                assert voices == ["shimmer", "onyx"]
        finally:
            os.chdir(original_cwd)