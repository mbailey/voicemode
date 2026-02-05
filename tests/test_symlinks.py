"""Unit tests for symlink utilities in voice_mode.utils.symlinks."""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


class TestUpdateLatestSymlinks:
    """Tests for update_latest_symlinks function."""

    def test_creates_stt_and_latest_symlinks_for_wav(self, isolate_home_directory):
        """Test that symlinks are created correctly for .wav STT files."""
        from voice_mode.utils.symlinks import update_latest_symlinks
        from voice_mode.config import AUDIO_DIR

        # Create test audio file
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        year_month = AUDIO_DIR / "2026" / "02"
        year_month.mkdir(parents=True, exist_ok=True)
        test_file = year_month / "123456_conv1_stt.wav"
        test_file.write_bytes(b"fake audio data")

        # Call the function
        type_symlink, latest_symlink = update_latest_symlinks(test_file, "stt")

        # Verify symlinks were created
        assert type_symlink is not None
        assert latest_symlink is not None
        assert type_symlink.name == "latest-STT.wav"
        assert latest_symlink.name == "latest.wav"

        # Verify symlinks point to correct file
        assert type_symlink.is_symlink()
        assert latest_symlink.is_symlink()
        assert type_symlink.resolve() == test_file.resolve()
        assert latest_symlink.resolve() == test_file.resolve()

    def test_creates_tts_and_latest_symlinks_for_mp3(self, isolate_home_directory):
        """Test that symlinks are created correctly for .mp3 TTS files."""
        from voice_mode.utils.symlinks import update_latest_symlinks
        from voice_mode.config import AUDIO_DIR

        # Create test audio file
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        year_month = AUDIO_DIR / "2026" / "02"
        year_month.mkdir(parents=True, exist_ok=True)
        test_file = year_month / "123456_conv1_tts.mp3"
        test_file.write_bytes(b"fake mp3 data")

        # Call the function
        type_symlink, latest_symlink = update_latest_symlinks(test_file, "tts")

        # Verify symlinks were created
        assert type_symlink is not None
        assert latest_symlink is not None
        assert type_symlink.name == "latest-TTS.mp3"
        assert latest_symlink.name == "latest.mp3"

        # Verify symlinks point to correct file
        assert type_symlink.resolve() == test_file.resolve()
        assert latest_symlink.resolve() == test_file.resolve()

    def test_creates_symlinks_for_various_extensions(self, isolate_home_directory):
        """Test symlink creation works for multiple audio formats."""
        from voice_mode.utils.symlinks import update_latest_symlinks
        from voice_mode.config import AUDIO_DIR

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

        extensions = [".wav", ".mp3", ".flac", ".aac", ".opus", ".ogg"]

        for ext in extensions:
            test_file = AUDIO_DIR / f"test_audio{ext}"
            test_file.write_bytes(b"fake audio data")

            type_symlink, latest_symlink = update_latest_symlinks(test_file, "stt")

            assert type_symlink is not None, f"Failed for extension {ext}"
            assert latest_symlink is not None, f"Failed for extension {ext}"
            assert type_symlink.name == f"latest-STT{ext}"
            assert latest_symlink.name == f"latest{ext}"

            # Clean up for next iteration
            test_file.unlink()
            type_symlink.unlink()
            latest_symlink.unlink()

    def test_uses_relative_paths_for_symlinks(self, isolate_home_directory):
        """Test that symlinks use relative paths when file is under AUDIO_DIR."""
        from voice_mode.utils.symlinks import update_latest_symlinks
        from voice_mode.config import AUDIO_DIR

        # Create test audio file in subdirectory
        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        year_month = AUDIO_DIR / "2026" / "02"
        year_month.mkdir(parents=True, exist_ok=True)
        test_file = year_month / "test_relative.wav"
        test_file.write_bytes(b"fake audio data")

        type_symlink, latest_symlink = update_latest_symlinks(test_file, "stt")

        # Read the symlink target (without resolving)
        stt_target = os.readlink(type_symlink)
        latest_target = os.readlink(latest_symlink)

        # Should be relative path like "2026/02/test_relative.wav"
        assert not os.path.isabs(stt_target), "STT symlink should use relative path"
        assert not os.path.isabs(latest_target), "latest symlink should use relative path"
        assert stt_target == "2026/02/test_relative.wav"
        assert latest_target == "2026/02/test_relative.wav"


class TestSymlinkExtensionChanges:
    """Tests for symlink updates when file extension changes."""

    def test_removes_old_stt_symlink_when_extension_changes(self, isolate_home_directory):
        """Test that old STT symlink is removed when a new file has different extension."""
        from voice_mode.utils.symlinks import update_latest_symlinks
        from voice_mode.config import AUDIO_DIR

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

        # Create first file with .wav extension
        wav_file = AUDIO_DIR / "first_stt.wav"
        wav_file.write_bytes(b"wav data")
        update_latest_symlinks(wav_file, "stt")

        # Verify initial symlinks exist
        old_stt_symlink = AUDIO_DIR / "latest-STT.wav"
        old_latest_symlink = AUDIO_DIR / "latest.wav"
        assert old_stt_symlink.is_symlink()
        assert old_latest_symlink.is_symlink()

        # Create second file with .mp3 extension
        mp3_file = AUDIO_DIR / "second_stt.mp3"
        mp3_file.write_bytes(b"mp3 data")
        update_latest_symlinks(mp3_file, "stt")

        # Old symlinks should be removed
        assert not old_stt_symlink.exists(), "Old .wav STT symlink should be removed"
        assert not old_latest_symlink.exists(), "Old .wav latest symlink should be removed"

        # New symlinks should exist
        new_stt_symlink = AUDIO_DIR / "latest-STT.mp3"
        new_latest_symlink = AUDIO_DIR / "latest.mp3"
        assert new_stt_symlink.is_symlink()
        assert new_latest_symlink.is_symlink()
        assert new_stt_symlink.resolve() == mp3_file.resolve()
        assert new_latest_symlink.resolve() == mp3_file.resolve()

    def test_removes_old_tts_symlink_when_extension_changes(self, isolate_home_directory):
        """Test that old TTS symlink is removed when a new file has different extension."""
        from voice_mode.utils.symlinks import update_latest_symlinks
        from voice_mode.config import AUDIO_DIR

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

        # Create first file with .mp3 extension
        mp3_file = AUDIO_DIR / "first_tts.mp3"
        mp3_file.write_bytes(b"mp3 data")
        update_latest_symlinks(mp3_file, "tts")

        # Create second file with .flac extension
        flac_file = AUDIO_DIR / "second_tts.flac"
        flac_file.write_bytes(b"flac data")
        update_latest_symlinks(flac_file, "tts")

        # Old symlinks should be removed
        assert not (AUDIO_DIR / "latest-TTS.mp3").exists()
        assert not (AUDIO_DIR / "latest.mp3").exists()

        # New symlinks should exist
        assert (AUDIO_DIR / "latest-TTS.flac").is_symlink()
        assert (AUDIO_DIR / "latest.flac").is_symlink()

    def test_latest_symlink_updated_by_both_stt_and_tts(self, isolate_home_directory):
        """Test that 'latest' symlink is updated by both STT and TTS."""
        from voice_mode.utils.symlinks import update_latest_symlinks
        from voice_mode.config import AUDIO_DIR

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

        # Create STT file
        stt_file = AUDIO_DIR / "recording.wav"
        stt_file.write_bytes(b"stt data")
        update_latest_symlinks(stt_file, "stt")

        assert (AUDIO_DIR / "latest.wav").resolve() == stt_file.resolve()

        # Create TTS file (should update latest)
        tts_file = AUDIO_DIR / "speech.mp3"
        tts_file.write_bytes(b"tts data")
        update_latest_symlinks(tts_file, "tts")

        # latest should now point to TTS file
        assert (AUDIO_DIR / "latest.mp3").resolve() == tts_file.resolve()
        assert not (AUDIO_DIR / "latest.wav").exists()

        # STT-specific symlink should still point to STT file
        assert (AUDIO_DIR / "latest-STT.wav").resolve() == stt_file.resolve()
        # TTS-specific symlink should point to TTS file
        assert (AUDIO_DIR / "latest-TTS.mp3").resolve() == tts_file.resolve()


class TestSymlinkCleanup:
    """Tests for cleanup of old symlinks."""

    def test_removes_only_symlinks_not_regular_files(self, isolate_home_directory, tmp_path):
        """Test that cleanup only removes symlinks, not regular files."""
        from voice_mode.utils.symlinks import _remove_old_symlinks

        # Use a fresh directory to avoid conflicts with other tests
        test_dir = tmp_path / "symlink_cleanup_test"
        test_dir.mkdir(parents=True, exist_ok=True)

        # Create a regular file that matches the pattern
        regular_file = test_dir / "latest-STT.txt"
        regular_file.write_text("not a symlink")

        # Create a symlink that matches the pattern
        symlink_target = test_dir / "target.wav"
        symlink_target.write_bytes(b"target")
        symlink = test_dir / "latest-STT.wav"
        symlink.symlink_to(symlink_target)

        # Run cleanup
        _remove_old_symlinks(test_dir, "latest-STT")

        # Regular file should still exist
        assert regular_file.exists(), "Regular file should not be removed"
        # Symlink should be removed
        assert not symlink.exists(), "Symlink should be removed"

    def test_cleanup_removes_symlink_with_different_extension(self, isolate_home_directory, tmp_path):
        """Test that cleanup removes symlinks with various extensions."""
        from voice_mode.utils.symlinks import _remove_old_symlinks

        # Use a fresh directory
        test_dir = tmp_path / "symlink_ext_test"
        test_dir.mkdir(parents=True, exist_ok=True)

        # Create target file
        target = test_dir / "target.wav"
        target.write_bytes(b"target")

        # Create symlinks with different extensions
        symlink_wav = test_dir / "latest-STT.wav"
        symlink_mp3 = test_dir / "latest-STT.mp3"
        symlink_wav.symlink_to(target)
        symlink_mp3.symlink_to(target)

        # Run cleanup
        _remove_old_symlinks(test_dir, "latest-STT")

        # Both symlinks should be removed
        assert not symlink_wav.exists()
        assert not symlink_mp3.exists()


class TestSymlinkErrorHandling:
    """Tests for error handling in symlink operations."""

    def test_returns_none_for_nonexistent_file(self, isolate_home_directory):
        """Test that function returns (None, None) for nonexistent source file."""
        from voice_mode.utils.symlinks import update_latest_symlinks
        from voice_mode.config import AUDIO_DIR

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        nonexistent = AUDIO_DIR / "does_not_exist.wav"

        type_symlink, latest_symlink = update_latest_symlinks(nonexistent, "stt")

        assert type_symlink is None
        assert latest_symlink is None

    def test_returns_none_for_file_without_extension(self, isolate_home_directory):
        """Test that function returns (None, None) for file without extension."""
        from voice_mode.utils.symlinks import update_latest_symlinks
        from voice_mode.config import AUDIO_DIR

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        no_ext_file = AUDIO_DIR / "no_extension"
        no_ext_file.write_bytes(b"data")

        type_symlink, latest_symlink = update_latest_symlinks(no_ext_file, "stt")

        assert type_symlink is None
        assert latest_symlink is None

    def test_handles_permission_error_gracefully(self, isolate_home_directory):
        """Test that permission errors are handled and return (None, None)."""
        from voice_mode.utils.symlinks import update_latest_symlinks
        from voice_mode.config import AUDIO_DIR

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        test_file = AUDIO_DIR / "test.wav"
        test_file.write_bytes(b"data")

        # Mock symlink_to to raise permission error
        with patch.object(Path, "symlink_to", side_effect=OSError("Permission denied")):
            type_symlink, latest_symlink = update_latest_symlinks(test_file, "stt")

        assert type_symlink is None
        assert latest_symlink is None

    def test_handles_string_path_input(self, isolate_home_directory):
        """Test that function accepts string paths in addition to Path objects."""
        from voice_mode.utils.symlinks import update_latest_symlinks
        from voice_mode.config import AUDIO_DIR

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        test_file = AUDIO_DIR / "test_string_path.wav"
        test_file.write_bytes(b"data")

        # Pass string path instead of Path object
        type_symlink, latest_symlink = update_latest_symlinks(str(test_file), "stt")

        assert type_symlink is not None
        assert latest_symlink is not None
        assert type_symlink.resolve() == test_file.resolve()

    def test_handles_file_outside_audio_dir(self, isolate_home_directory, tmp_path):
        """Test handling of files outside AUDIO_DIR (uses absolute path)."""
        from voice_mode.utils.symlinks import update_latest_symlinks
        from voice_mode.config import AUDIO_DIR

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

        # Create file outside AUDIO_DIR
        external_file = tmp_path / "external_audio.wav"
        external_file.write_bytes(b"external data")

        type_symlink, latest_symlink = update_latest_symlinks(external_file, "stt")

        # Should still create symlinks
        assert type_symlink is not None
        assert latest_symlink is not None

        # Symlink should use absolute path since file is outside AUDIO_DIR
        stt_target = os.readlink(type_symlink)
        assert os.path.isabs(stt_target) or str(external_file) in stt_target


class TestRemoveOldSymlinksFunction:
    """Tests specifically for _remove_old_symlinks helper."""

    def test_handles_empty_directory(self, isolate_home_directory):
        """Test that cleanup handles empty directory without errors."""
        from voice_mode.utils.symlinks import _remove_old_symlinks
        from voice_mode.config import AUDIO_DIR

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

        # Should not raise any errors
        _remove_old_symlinks(AUDIO_DIR, "latest")
        _remove_old_symlinks(AUDIO_DIR, "latest-STT")
        _remove_old_symlinks(AUDIO_DIR, "latest-TTS")

    def test_handles_nonexistent_directory(self, isolate_home_directory, tmp_path):
        """Test that cleanup handles nonexistent directory without errors."""
        from voice_mode.utils.symlinks import _remove_old_symlinks

        nonexistent_dir = tmp_path / "nonexistent"

        # Should not raise any errors (glob returns empty for nonexistent paths)
        _remove_old_symlinks(nonexistent_dir, "latest")

    def test_removes_multiple_matching_symlinks(self, isolate_home_directory):
        """Test that all matching symlinks are removed."""
        from voice_mode.utils.symlinks import _remove_old_symlinks
        from voice_mode.config import AUDIO_DIR

        AUDIO_DIR.mkdir(parents=True, exist_ok=True)

        # Create target
        target = AUDIO_DIR / "target.wav"
        target.write_bytes(b"target")

        # Create multiple symlinks matching pattern
        symlinks = [
            AUDIO_DIR / "latest.wav",
            AUDIO_DIR / "latest.mp3",
            AUDIO_DIR / "latest.flac",
        ]
        for s in symlinks:
            s.symlink_to(target)

        # Run cleanup
        _remove_old_symlinks(AUDIO_DIR, "latest")

        # All should be removed
        for s in symlinks:
            assert not s.exists(), f"{s.name} should be removed"
