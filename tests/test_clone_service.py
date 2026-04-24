"""Tests for clone TTS service management (install, status, uninstall)."""

from pathlib import Path
from unittest.mock import patch

import pytest

from voice_mode.tools.clone.install import is_apple_silicon, CLONE_SERVICE_DIR
from voice_mode.tools.service import get_service_config_vars


def unwrap(func):
    """Unwrap a function from MCP tool decorator if present."""
    if hasattr(func, '__wrapped__'):
        return func.__wrapped__
    if hasattr(func, 'fn'):
        return func.fn
    return func


class TestAppleSiliconCheck:
    """Test the Apple Silicon hardware detection."""

    def test_apple_silicon_on_arm64_mac(self):
        with patch("voice_mode.tools.clone.install.platform") as mock_platform:
            mock_platform.system.return_value = "Darwin"
            mock_platform.machine.return_value = "arm64"
            assert is_apple_silicon() is True

    def test_not_apple_silicon_on_intel_mac(self):
        with patch("voice_mode.tools.clone.install.platform") as mock_platform:
            mock_platform.system.return_value = "Darwin"
            mock_platform.machine.return_value = "x86_64"
            assert is_apple_silicon() is False

    def test_not_apple_silicon_on_linux(self):
        with patch("voice_mode.tools.clone.install.platform") as mock_platform:
            mock_platform.system.return_value = "Linux"
            mock_platform.machine.return_value = "x86_64"
            assert is_apple_silicon() is False

    def test_not_apple_silicon_on_linux_arm(self):
        with patch("voice_mode.tools.clone.install.platform") as mock_platform:
            mock_platform.system.return_value = "Linux"
            mock_platform.machine.return_value = "arm64"
            assert is_apple_silicon() is False


class TestCloneInstallRejectsNonAppleSilicon:
    """Test that clone_install returns error on non-Apple-Silicon."""

    @pytest.mark.asyncio
    async def test_rejects_intel_mac(self):
        from voice_mode.tools.clone.install import clone_install

        with patch("voice_mode.tools.clone.install.is_apple_silicon", return_value=False), \
             patch("voice_mode.tools.clone.install.platform") as mock_platform:
            mock_platform.machine.return_value = "x86_64"
            mock_platform.system.return_value = "Darwin"
            result = await unwrap(clone_install)()
            assert result["success"] is False
            assert "Apple Silicon" in result["error"]

    @pytest.mark.asyncio
    async def test_rejects_linux(self):
        from voice_mode.tools.clone.install import clone_install

        with patch("voice_mode.tools.clone.install.is_apple_silicon", return_value=False), \
             patch("voice_mode.tools.clone.install.platform") as mock_platform:
            mock_platform.machine.return_value = "x86_64"
            mock_platform.system.return_value = "Linux"
            result = await unwrap(clone_install)()
            assert result["success"] is False
            assert "Apple Silicon" in result["error"]


class TestCloneServiceConfigVars:
    """Test that clone service config vars are correctly generated."""

    def test_clone_config_vars_have_required_keys(self):
        config_vars = get_service_config_vars("clone")
        assert "HOME" in config_vars
        assert "START_SCRIPT" in config_vars
        assert "CLONE_DIR" in config_vars

    def test_clone_dir_under_services(self):
        config_vars = get_service_config_vars("clone")
        assert "services/clone" in config_vars["CLONE_DIR"]

    def test_start_script_in_bin_dir(self):
        config_vars = get_service_config_vars("clone")
        assert config_vars["START_SCRIPT"].endswith("bin/start-clone-server.sh")


class TestCloneServiceTemplates:
    """Test that service templates exist for clone."""

    def test_launchd_template_exists(self):
        template = Path(__file__).parent.parent / "voice_mode" / "templates" / "launchd" / "com.voicemode.clone.plist"
        assert template.exists(), f"Launchd template not found: {template}"

    def test_systemd_template_exists(self):
        template = Path(__file__).parent.parent / "voice_mode" / "templates" / "systemd" / "voicemode-clone.service"
        assert template.exists(), f"Systemd template not found: {template}"

    def test_start_script_template_exists(self):
        template = Path(__file__).parent.parent / "voice_mode" / "templates" / "scripts" / "start-clone-server.sh"
        assert template.exists(), f"Start script template not found: {template}"

    def test_launchd_template_has_clone_label(self):
        template = Path(__file__).parent.parent / "voice_mode" / "templates" / "launchd" / "com.voicemode.clone.plist"
        content = template.read_text()
        assert "com.voicemode.clone" in content
        assert "{START_SCRIPT}" in content
        assert "{CLONE_DIR}" in content

    def test_systemd_template_has_clone_identifier(self):
        template = Path(__file__).parent.parent / "voice_mode" / "templates" / "systemd" / "voicemode-clone.service"
        content = template.read_text()
        assert "voicemode-clone" in content
        assert "{START_SCRIPT}" in content


class TestCloneConfig:
    """Test that clone config values are properly defined."""

    def test_clone_port_default(self):
        from voice_mode.config import CLONE_PORT
        assert CLONE_PORT == 8890

    def test_clone_model_default(self):
        from voice_mode.config import CLONE_MODEL
        assert "Qwen3-TTS" in CLONE_MODEL

    def test_clone_service_dir_under_voicemode(self):
        assert "services" in str(CLONE_SERVICE_DIR)
        assert "clone" in str(CLONE_SERVICE_DIR)


class TestCloneStatus:
    """Test clone status check."""

    @pytest.mark.asyncio
    async def test_status_when_not_running(self):
        from voice_mode.tools.clone.status import clone_status

        result = await unwrap(clone_status)()
        # When nothing is running on port 8890, should report not running
        assert result["service"] == "clone"
        assert result["port"] == 8890
        assert "status" in result


class TestCloneUninstall:
    """Test clone uninstall on a clean system (nothing to remove)."""

    @pytest.mark.asyncio
    async def test_uninstall_clean_system(self):
        from voice_mode.tools.clone.uninstall import clone_uninstall

        with patch("voice_mode.tools.clone.uninstall.find_process_by_port", return_value=None):
            result = await unwrap(clone_uninstall)()
            assert result["success"] is True
            assert isinstance(result["removed_items"], list)
