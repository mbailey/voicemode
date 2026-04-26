"""Tests for the mlx_audio install/uninstall tools (VM-1078)."""

from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice_mode.tools.mlx_audio.install import (  # noqa: E402
    MLX_AUDIO_DEFAULT_PORT,
    MLX_AUDIO_PIP_PACKAGE,
    mlx_audio_install as install_tool,
)
from voice_mode.tools.mlx_audio.uninstall import (  # noqa: E402
    mlx_audio_uninstall as uninstall_tool,
)

# Strip FastMCP wrappers (mirrors test_unified_service.py pattern).
mlx_audio_install = getattr(install_tool, "fn", install_tool)
mlx_audio_uninstall = getattr(uninstall_tool, "fn", uninstall_tool)


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


class TestMlxAudioInstall:
    """Verifies platform gating, the uv tool install pipeline, and the
    rendered service file path.
    """

    @pytest.mark.asyncio
    async def test_refuses_intel_mac(self):
        with patch("voice_mode.tools.mlx_audio.install.platform.system", return_value="Darwin"), \
             patch("voice_mode.tools.mlx_audio.install.platform.machine", return_value="x86_64"):
            result = await mlx_audio_install()

        assert result["success"] is False
        assert "Apple Silicon" in result["error"]
        assert "x86_64" in result["platform"]

    @pytest.mark.asyncio
    async def test_refuses_linux(self):
        with patch("voice_mode.tools.mlx_audio.install.platform.system", return_value="Linux"), \
             patch("voice_mode.tools.mlx_audio.install.platform.machine", return_value="x86_64"):
            result = await mlx_audio_install()

        assert result["success"] is False
        assert "Apple Silicon" in result["error"]

    @pytest.mark.asyncio
    async def test_uses_uv_tool_install(self, tmp_path):
        """Happy path: ``uv tool install mlx-audio`` is invoked and the
        rendered plist path is returned."""
        env_dir = tmp_path / "voicemode"

        def _entry_point_exists(self):
            return self.name == "mlx_audio.server"

        run_mock = MagicMock(returncode=0, stderr=b"", stdout=b"")
        service_path = tmp_path / "rendered.plist"
        service_result = {
            "success": True,
            "updated": True,
            "service_path": str(service_path),
            "enabled": False,
        }

        with patch.dict(os.environ, {"VOICEMODE_BASE_DIR": str(env_dir)}, clear=False), \
             patch("voice_mode.tools.mlx_audio.install.platform.system", return_value="Darwin"), \
             patch("voice_mode.tools.mlx_audio.install.platform.machine", return_value="arm64"), \
             patch("voice_mode.tools.mlx_audio.install.shutil.which", return_value="/opt/homebrew/bin/uv"), \
             patch("voice_mode.tools.mlx_audio.install.subprocess.run", return_value=run_mock) as run_patch, \
             patch("voice_mode.tools.mlx_audio.install.Path.exists", new=_entry_point_exists), \
             patch("voice_mode.tools.mlx_audio.install._update_mlx_audio_service_files",
                   new=AsyncMock(return_value=service_result)):
            result = await mlx_audio_install(port=8890, auto_enable=False)

        assert result["success"] is True, result
        assert result["port"] == 8890
        assert result["host"] == "127.0.0.1"
        assert result["service_url"] == "http://127.0.0.1:8890"
        assert result["service_path"] == str(service_path)
        assert "uv tool install" in result["message"]

        # uv tool install was called with the expected target.
        cmd_args = run_patch.call_args_list[-1].args[0]
        assert cmd_args[:4] == ["uv", "tool", "install", MLX_AUDIO_PIP_PACKAGE]

    @pytest.mark.asyncio
    async def test_force_reinstall_passes_force_flag(self, tmp_path):
        env_dir = tmp_path / "voicemode"

        def _entry_point_exists(self):
            return self.name == "mlx_audio.server"

        run_mock = MagicMock(returncode=0, stderr=b"", stdout=b"")
        service_result = {"success": True, "updated": True, "service_path": str(tmp_path / "p.plist")}

        with patch.dict(os.environ, {"VOICEMODE_BASE_DIR": str(env_dir)}, clear=False), \
             patch("voice_mode.tools.mlx_audio.install.platform.system", return_value="Darwin"), \
             patch("voice_mode.tools.mlx_audio.install.platform.machine", return_value="arm64"), \
             patch("voice_mode.tools.mlx_audio.install.shutil.which", return_value="/opt/homebrew/bin/uv"), \
             patch("voice_mode.tools.mlx_audio.install.subprocess.run", return_value=run_mock) as run_patch, \
             patch("voice_mode.tools.mlx_audio.install.Path.exists", new=_entry_point_exists), \
             patch("voice_mode.tools.mlx_audio.install._update_mlx_audio_service_files",
                   new=AsyncMock(return_value=service_result)):
            await mlx_audio_install(force_reinstall=True, auto_enable=False)

        cmd_args = run_patch.call_args_list[-1].args[0]
        assert "--force" in cmd_args

    @pytest.mark.asyncio
    async def test_version_pin_passed_to_uv(self, tmp_path):
        env_dir = tmp_path / "voicemode"

        def _entry_point_exists(self):
            return self.name == "mlx_audio.server"

        run_mock = MagicMock(returncode=0, stderr=b"", stdout=b"")
        service_result = {"success": True, "updated": True, "service_path": str(tmp_path / "p.plist")}

        with patch.dict(os.environ, {"VOICEMODE_BASE_DIR": str(env_dir)}, clear=False), \
             patch("voice_mode.tools.mlx_audio.install.platform.system", return_value="Darwin"), \
             patch("voice_mode.tools.mlx_audio.install.platform.machine", return_value="arm64"), \
             patch("voice_mode.tools.mlx_audio.install.shutil.which", return_value="/opt/homebrew/bin/uv"), \
             patch("voice_mode.tools.mlx_audio.install.subprocess.run", return_value=run_mock) as run_patch, \
             patch("voice_mode.tools.mlx_audio.install.Path.exists", new=_entry_point_exists), \
             patch("voice_mode.tools.mlx_audio.install._update_mlx_audio_service_files",
                   new=AsyncMock(return_value=service_result)):
            await mlx_audio_install(version="0.2.5", auto_enable=False)

        cmd_args = run_patch.call_args_list[-1].args[0]
        assert f"{MLX_AUDIO_PIP_PACKAGE}==0.2.5" in cmd_args

    @pytest.mark.asyncio
    async def test_missing_entry_point_after_install_fails(self, tmp_path):
        """If ``uv tool install`` succeeds but the entry point is missing,
        the install must fail loudly rather than claiming success."""
        env_dir = tmp_path / "voicemode"
        run_mock = MagicMock(returncode=0, stderr=b"", stdout=b"")

        with patch.dict(os.environ, {"VOICEMODE_BASE_DIR": str(env_dir)}, clear=False), \
             patch("voice_mode.tools.mlx_audio.install.platform.system", return_value="Darwin"), \
             patch("voice_mode.tools.mlx_audio.install.platform.machine", return_value="arm64"), \
             patch("voice_mode.tools.mlx_audio.install.shutil.which", return_value="/opt/homebrew/bin/uv"), \
             patch("voice_mode.tools.mlx_audio.install.subprocess.run", return_value=run_mock), \
             patch("voice_mode.tools.mlx_audio.install.Path.exists", return_value=False):
            result = await mlx_audio_install(auto_enable=False)

        assert result["success"] is False
        assert "missing" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_default_port_matches_upstream_convention(self):
        """8890 is the upstream mlx-audio default we deliberately match."""
        assert MLX_AUDIO_DEFAULT_PORT == 8890


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------


class TestMlxAudioUninstall:

    @pytest.mark.asyncio
    async def test_runs_uv_tool_uninstall(self, tmp_path):
        plist_dir = tmp_path / "LaunchAgents"
        plist_dir.mkdir()
        plist_path = plist_dir / "com.voicemode.mlx-audio.plist"
        plist_path.write_text("<plist/>")

        install_dir = tmp_path / "services" / "mlx-audio"
        install_dir.mkdir(parents=True)

        run_mock = MagicMock()
        run_mock.return_value = MagicMock(returncode=0, stderr="", stdout="")

        with patch("voice_mode.tools.mlx_audio.uninstall.platform.system", return_value="Darwin"), \
             patch("voice_mode.tools.mlx_audio.uninstall.find_process_by_port", return_value=None), \
             patch("voice_mode.tools.mlx_audio.uninstall.shutil.which", return_value="/opt/homebrew/bin/uv"), \
             patch("voice_mode.tools.mlx_audio.uninstall.Path.home", return_value=tmp_path), \
             patch("voice_mode.tools.mlx_audio.uninstall.BASE_DIR", tmp_path), \
             patch("voice_mode.tools.mlx_audio.uninstall.subprocess.run", side_effect=run_mock):
            result = await mlx_audio_uninstall()

        assert result["success"] is True, result
        # `uv tool uninstall mlx-audio` was called.
        all_calls = [call.args[0] for call in run_mock.call_args_list]
        assert any(
            cmd[:3] == ["uv", "tool", "uninstall"] and "mlx-audio" in cmd
            for cmd in all_calls
        ), all_calls

    @pytest.mark.asyncio
    async def test_uv_tool_not_installed_is_not_an_error(self, tmp_path):
        """``uv tool uninstall`` returns nonzero when the tool isn't
        installed; that's a no-op, not a failure."""
        not_installed = MagicMock(returncode=1, stderr="`mlx-audio` is not installed", stdout="")

        with patch("voice_mode.tools.mlx_audio.uninstall.platform.system", return_value="Darwin"), \
             patch("voice_mode.tools.mlx_audio.uninstall.find_process_by_port", return_value=None), \
             patch("voice_mode.tools.mlx_audio.uninstall.shutil.which", return_value="/opt/homebrew/bin/uv"), \
             patch("voice_mode.tools.mlx_audio.uninstall.Path.home", return_value=tmp_path), \
             patch("voice_mode.tools.mlx_audio.uninstall.BASE_DIR", tmp_path), \
             patch("voice_mode.tools.mlx_audio.uninstall.subprocess.run", return_value=not_installed):
            result = await mlx_audio_uninstall()

        assert result["success"] is True
        assert result["errors"] == []

    @pytest.mark.asyncio
    async def test_skips_uv_tool_when_uv_missing(self, tmp_path):
        with patch("voice_mode.tools.mlx_audio.uninstall.platform.system", return_value="Darwin"), \
             patch("voice_mode.tools.mlx_audio.uninstall.find_process_by_port", return_value=None), \
             patch("voice_mode.tools.mlx_audio.uninstall.shutil.which", return_value=None), \
             patch("voice_mode.tools.mlx_audio.uninstall.Path.home", return_value=tmp_path), \
             patch("voice_mode.tools.mlx_audio.uninstall.BASE_DIR", tmp_path), \
             patch("voice_mode.tools.mlx_audio.uninstall.subprocess.run") as run_patch:
            result = await mlx_audio_uninstall()

        assert result["success"] is True
        # uv was never invoked.
        for call in run_patch.call_args_list:
            assert call.args[0][0] != "uv", call.args


# ---------------------------------------------------------------------------
# rendered service file
# ---------------------------------------------------------------------------


class TestMlxAudioServiceFile:
    """End-to-end render check for the launchd plist."""

    def test_plist_renders_with_shell_c_form(self):
        from voice_mode.tools.service import create_service_file

        with patch("voice_mode.tools.service.platform.system", return_value="Darwin"):
            path, content = create_service_file("mlx_audio")

        assert "com.voicemode.mlx-audio.plist" in str(path)
        # The plist no longer relies on a start script -- it exec's the
        # uv-tool entry point directly.
        assert "start-mlx-audio.sh" not in content
        assert "/bin/sh" in content
        assert "$HOME/.local/bin/mlx_audio.server" in content
        # Shell-side variable expansion survives Python str.format escaping.
        assert "${VOICEMODE_MLX_AUDIO_HOST:-127.0.0.1}" in content
        assert "${VOICEMODE_MLX_AUDIO_PORT:-8890}" in content
