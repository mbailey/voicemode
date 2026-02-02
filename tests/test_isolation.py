"""Tests to verify test isolation is working correctly.

These tests verify that Path.home() and os.path.expanduser() are properly
isolated to prevent tests from writing plist files to the real
~/Library/LaunchAgents/ directory.
"""

import os
from pathlib import Path


class TestHomeIsolation:
    """Verify that Path.home() and os.path.expanduser() are properly isolated."""

    def test_path_home_is_isolated(self, isolate_home_directory):
        """Path.home() should return a temp directory, not real home."""
        home = Path.home()
        assert home == isolate_home_directory
        # Verify it's not the real home directory
        real_home = os.environ.get("HOME", "")
        assert str(home) != real_home
        # The fake home should be in a pytest temp directory
        assert "pytest" in str(home) or "tmp" in str(home).lower()

    def test_expanduser_is_isolated(self, isolate_home_directory):
        """os.path.expanduser() should use the fake home."""
        expanded = os.path.expanduser("~")
        assert expanded == str(isolate_home_directory)

        # Also verify subpath expansion works correctly
        expanded_path = os.path.expanduser("~/.voicemode")
        assert expanded_path == str(isolate_home_directory / ".voicemode")

        expanded_path = os.path.expanduser("~/Library/LaunchAgents")
        assert expanded_path == str(isolate_home_directory / "Library" / "LaunchAgents")

    def test_expanduser_non_tilde_unchanged(self, isolate_home_directory):
        """os.path.expanduser() should not modify paths without ~."""
        # Absolute paths should be unchanged
        assert os.path.expanduser("/usr/local/bin") == "/usr/local/bin"
        # Relative paths should be unchanged
        assert os.path.expanduser("relative/path") == "relative/path"

    def test_launchagents_directory_exists(self, isolate_home_directory):
        """The fake LaunchAgents directory should exist."""
        launchagents = isolate_home_directory / "Library" / "LaunchAgents"
        assert launchagents.exists()
        assert launchagents.is_dir()

    def test_systemd_directory_exists(self, isolate_home_directory):
        """The fake systemd user directory should exist."""
        systemd_dir = isolate_home_directory / ".config" / "systemd" / "user"
        assert systemd_dir.exists()
        assert systemd_dir.is_dir()

    def test_voicemode_directories_exist(self, isolate_home_directory):
        """Standard .voicemode directories should exist."""
        for subdir in ["logs", "services", "config"]:
            path = isolate_home_directory / ".voicemode" / subdir
            assert path.exists(), f".voicemode/{subdir} should exist"
            assert path.is_dir(), f".voicemode/{subdir} should be a directory"

    def test_can_write_to_fake_launchagents(self, isolate_home_directory):
        """Verify we can write files to the fake LaunchAgents directory."""
        launchagents = Path.home() / "Library" / "LaunchAgents"
        test_plist = launchagents / "test.plist"

        # Write a test file
        test_plist.write_text("test content")

        # Verify it was written to the fake directory, not the real one
        assert test_plist.exists()
        assert test_plist.read_text() == "test content"
        assert str(test_plist).startswith(str(isolate_home_directory))

        # Verify the real LaunchAgents was not affected
        real_plist = Path(os.environ.get("HOME", "")) / "Library" / "LaunchAgents" / "test.plist"
        assert not real_plist.exists(), "File should not exist in real LaunchAgents!"

    def test_isolation_per_test(self, isolate_home_directory):
        """Each test gets its own isolated home directory."""
        marker_file = isolate_home_directory / "test_marker.txt"
        marker_file.write_text("test")
        assert marker_file.exists()
        # The marker file only exists in this test's tmp directory
        # Other tests won't see it because they get different tmp_path


class TestIsolationWithPathHome:
    """Test that code using Path.home() is properly isolated."""

    def test_plist_path_construction(self, isolate_home_directory):
        """Verify that plist path construction uses fake home."""
        # This mimics how service.py constructs paths
        plist_path = Path.home() / "Library" / "LaunchAgents" / "com.voicemode.test.plist"

        # The path should be in the fake home
        assert str(plist_path).startswith(str(isolate_home_directory))
        assert "Library/LaunchAgents" in str(plist_path)

    def test_voicemode_config_path(self, isolate_home_directory):
        """Verify that .voicemode config paths use fake home."""
        config_path = Path.home() / ".voicemode" / "config" / "settings.yaml"

        # The path should be in the fake home
        assert str(config_path).startswith(str(isolate_home_directory))
        assert ".voicemode/config" in str(config_path)
