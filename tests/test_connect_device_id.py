"""Tests for deterministic device ID generation."""

import re
from unittest.mock import patch

import pytest

from voice_mode.connect.client import get_device_id, get_device_name, _get_project_name


DEVICE_ID_PATTERN = re.compile(r"^dev-[0-9a-f]{24}$")


class TestGetProjectName:
    def test_from_git_remote(self):
        """Extracts repo name from git remote origin URL."""
        with patch("voice_mode.connect.client.subprocess") as mock_sub:
            # First call: git remote get-url origin
            mock_sub.run.return_value.returncode = 0
            mock_sub.run.return_value.stdout = "git@github.com:mbailey/voicemode.git\n"
            assert _get_project_name() == "voicemode"

    def test_from_https_remote(self):
        """Extracts repo name from HTTPS git remote URL."""
        with patch("voice_mode.connect.client.subprocess") as mock_sub:
            mock_sub.run.return_value.returncode = 0
            mock_sub.run.return_value.stdout = "https://github.com/mbailey/voicemode.git\n"
            assert _get_project_name() == "voicemode"

    def test_from_remote_no_dot_git(self):
        """Handles remote URLs without .git suffix."""
        with patch("voice_mode.connect.client.subprocess") as mock_sub:
            mock_sub.run.return_value.returncode = 0
            mock_sub.run.return_value.stdout = "https://github.com/mbailey/voicemode\n"
            assert _get_project_name() == "voicemode"

    def test_fallback_to_git_toplevel(self):
        """Falls back to git toplevel directory name when no remote."""
        with patch("voice_mode.connect.client.subprocess") as mock_sub:
            # First call fails (no remote), second succeeds (toplevel)
            call_count = [0]
            def side_effect(*args, **kwargs):
                call_count[0] += 1
                result = type("Result", (), {"returncode": 1, "stdout": ""})()
                if call_count[0] == 2:
                    result.returncode = 0
                    result.stdout = "/Users/admin/Code/taskmaster\n"
                return result
            mock_sub.run.side_effect = side_effect
            assert _get_project_name() == "taskmaster"

    def test_fallback_to_cwd(self):
        """Falls back to current directory basename when git unavailable."""
        with patch("voice_mode.connect.client.subprocess") as mock_sub:
            mock_sub.run.side_effect = FileNotFoundError("git not found")
            with patch("voice_mode.connect.client.os.getcwd", return_value="/Users/admin/projects/myapp"):
                assert _get_project_name() == "myapp"

    def test_last_resort_fallback(self):
        """Returns 'claude-code' as last resort."""
        with patch("voice_mode.connect.client.subprocess") as mock_sub:
            mock_sub.run.side_effect = FileNotFoundError("git not found")
            with patch("voice_mode.connect.client.os.getcwd", return_value="/"):
                # basename of "/" is empty string
                assert _get_project_name() == "claude-code"


class TestGetDeviceId:
    def test_format_matches_gateway_validation(self):
        """Device ID format matches gateway regex: /^dev-[0-9a-f]{24}$/."""
        with patch("voice_mode.connect.client._get_project_name", return_value="voicemode"):
            with patch("voice_mode.connect.client.socket") as mock_socket:
                mock_socket.gethostname.return_value = "mba"
                device_id = get_device_id()
        assert DEVICE_ID_PATTERN.match(device_id), (
            f"Device ID '{device_id}' doesn't match pattern dev-[0-9a-f]{{24}}"
        )

    def test_deterministic(self):
        """Same project + hostname always gives the same device ID."""
        with patch("voice_mode.connect.client._get_project_name", return_value="voicemode"):
            with patch("voice_mode.connect.client.socket") as mock_socket:
                mock_socket.gethostname.return_value = "mba"
                id1 = get_device_id()
                id2 = get_device_id()
        assert id1 == id2

    def test_different_projects_different_ids(self):
        """Different project names produce different device IDs."""
        with patch("voice_mode.connect.client.socket") as mock_socket:
            mock_socket.gethostname.return_value = "mba"
            with patch("voice_mode.connect.client._get_project_name", return_value="voicemode"):
                id_vm = get_device_id()
            with patch("voice_mode.connect.client._get_project_name", return_value="taskmaster"):
                id_tm = get_device_id()
        assert id_vm != id_tm

    def test_different_hosts_different_ids(self):
        """Same project on different hosts produces different device IDs."""
        with patch("voice_mode.connect.client._get_project_name", return_value="voicemode"):
            with patch("voice_mode.connect.client.socket") as mock_socket:
                mock_socket.gethostname.return_value = "mba"
                id_mba = get_device_id()
                mock_socket.gethostname.return_value = "ms2"
                id_ms2 = get_device_id()
        assert id_mba != id_ms2

    def test_strips_domain_from_hostname(self):
        """Uses short hostname (strips .local, .lan, etc)."""
        with patch("voice_mode.connect.client._get_project_name", return_value="voicemode"):
            with patch("voice_mode.connect.client.socket") as mock_socket:
                mock_socket.gethostname.return_value = "mba.local"
                id_fqdn = get_device_id()
                mock_socket.gethostname.return_value = "mba"
                id_short = get_device_id()
        assert id_fqdn == id_short


class TestGetDeviceName:
    def test_format(self):
        """Device name is '{project} on {hostname}'."""
        with patch("voice_mode.connect.client._get_project_name", return_value="voicemode"):
            with patch("voice_mode.connect.client.socket") as mock_socket:
                mock_socket.gethostname.return_value = "mba"
                assert get_device_name() == "voicemode on mba"

    def test_strips_domain(self):
        """Uses short hostname in device name."""
        with patch("voice_mode.connect.client._get_project_name", return_value="taskmaster"):
            with patch("voice_mode.connect.client.socket") as mock_socket:
                mock_socket.gethostname.return_value = "ms2.local"
                assert get_device_name() == "taskmaster on ms2"
