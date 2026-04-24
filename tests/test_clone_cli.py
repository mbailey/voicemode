"""Unit tests for the voicemode clone CLI subcommand group."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from voice_mode.cli import voice_mode_main_cli


@pytest.fixture
def runner():
    """Create a Click CliRunner."""
    return CliRunner()


# ============================================================================
# Group Registration
# ============================================================================


class TestCloneGroupRegistered:
    """Verify the clone group is registered and accessible."""

    def test_clone_group_in_main_cli(self, runner):
        """The 'clone' subcommand should appear in voicemode --help."""
        result = runner.invoke(voice_mode_main_cli, ["clone", "--help"])
        assert result.exit_code == 0
        assert "Voice cloning service management" in result.output

    def test_clone_help_lists_all_subcommands(self, runner):
        """clone --help should list install, status, uninstall, add, list, remove."""
        result = runner.invoke(voice_mode_main_cli, ["clone", "--help"])
        assert result.exit_code == 0
        for cmd in ("install", "status", "uninstall", "add", "list", "remove"):
            assert cmd in result.output, f"Missing subcommand '{cmd}' in clone --help"


# ============================================================================
# clone install
# ============================================================================


class TestCloneInstall:
    """Test clone install subcommand."""

    def test_install_help(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["clone", "install", "--help"])
        assert result.exit_code == 0
        assert "--port" in result.output
        assert "--force" in result.output
        assert "--model" in result.output

    @patch("voice_mode.tools.clone.install.clone_install", new_callable=AsyncMock)
    def test_install_success(self, mock_install, runner):
        mock_install.return_value = {
            "success": True,
            "install_path": "/home/user/.voicemode/services/clone",
            "model": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
            "service_url": "http://127.0.0.1:8890",
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "install"])
        assert result.exit_code == 0
        assert "Clone TTS installed successfully" in result.output
        mock_install.assert_called_once()

    @patch("voice_mode.tools.clone.install.clone_install", new_callable=AsyncMock)
    def test_install_already_installed(self, mock_install, runner):
        mock_install.return_value = {
            "success": True,
            "already_installed": True,
            "install_path": "/home/user/.voicemode/services/clone",
            "model": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "install"])
        assert result.exit_code == 0
        assert "Already installed" in result.output

    @patch("voice_mode.tools.clone.install.clone_install", new_callable=AsyncMock)
    def test_install_failure(self, mock_install, runner):
        mock_install.return_value = {
            "success": False,
            "error": "Clone TTS requires Apple Silicon (M1/M2/M3/M4).",
            "platform": "x86_64",
            "system": "Linux",
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "install"])
        assert result.exit_code == 1
        assert "Installation failed" in result.output
        assert "Apple Silicon" in result.output

    @patch("voice_mode.tools.clone.install.clone_install", new_callable=AsyncMock)
    def test_install_custom_port(self, mock_install, runner):
        mock_install.return_value = {
            "success": True,
            "install_path": "/tmp/clone",
            "model": "test-model",
            "service_url": "http://127.0.0.1:9999",
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "install", "--port", "9999"])
        assert result.exit_code == 0
        call_kwargs = mock_install.call_args
        assert call_kwargs.kwargs.get("port") == 9999

    @patch("voice_mode.tools.clone.install.clone_install", new_callable=AsyncMock)
    def test_install_with_force(self, mock_install, runner):
        mock_install.return_value = {
            "success": True,
            "install_path": "/tmp/clone",
            "model": "test-model",
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "install", "--force"])
        assert result.exit_code == 0
        call_kwargs = mock_install.call_args
        assert call_kwargs.kwargs.get("force_reinstall") is True or call_kwargs[1].get("force_reinstall") is True


# ============================================================================
# clone status
# ============================================================================


class TestCloneStatus:
    """Test clone status subcommand."""

    def test_status_help(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["clone", "status", "--help"])
        assert result.exit_code == 0
        assert "Check clone TTS service status" in result.output

    @patch("voice_mode.tools.clone.status.clone_status", new_callable=AsyncMock)
    def test_status_running(self, mock_status, runner):
        mock_status.return_value = {
            "healthy": True,
            "status": "running",
            "port": 8890,
            "url": "http://127.0.0.1:8890",
            "models": {"data": [{"id": "test-model"}]},
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "status"])
        assert result.exit_code == 0
        assert "Clone TTS is running" in result.output
        assert "8890" in result.output

    @patch("voice_mode.tools.clone.status.clone_status", new_callable=AsyncMock)
    def test_status_not_running(self, mock_status, runner):
        mock_status.return_value = {
            "healthy": False,
            "status": "not_running",
            "port": 8890,
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "status"])
        assert result.exit_code == 0
        assert "not running" in result.output

    @patch("voice_mode.tools.clone.status.clone_status", new_callable=AsyncMock)
    def test_status_unhealthy(self, mock_status, runner):
        mock_status.return_value = {
            "healthy": False,
            "status": "unhealthy",
            "http_status": 500,
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "status"])
        assert result.exit_code == 0
        assert "unhealthy" in result.output


# ============================================================================
# clone uninstall
# ============================================================================


class TestCloneUninstall:
    """Test clone uninstall subcommand."""

    def test_uninstall_help(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["clone", "uninstall", "--help"])
        assert result.exit_code == 0
        assert "--remove-model" in result.output

    @patch("voice_mode.tools.clone.uninstall.clone_uninstall", new_callable=AsyncMock)
    def test_uninstall_success(self, mock_uninstall, runner):
        mock_uninstall.return_value = {
            "success": True,
            "message": "Clone TTS service uninstalled",
            "removed_items": ["Stopped running clone TTS service", "Removed launchd configuration"],
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "uninstall", "--yes"])
        assert result.exit_code == 0
        assert "uninstalled successfully" in result.output

    @patch("voice_mode.tools.clone.uninstall.clone_uninstall", new_callable=AsyncMock)
    def test_uninstall_failure(self, mock_uninstall, runner):
        mock_uninstall.return_value = {
            "success": False,
            "message": "Failed to uninstall",
            "errors": ["Permission denied"],
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "uninstall", "--yes"])
        assert result.exit_code == 1
        assert "Uninstall failed" in result.output

    def test_uninstall_confirmation_prompt(self, runner):
        """Without --yes, uninstall should prompt for confirmation."""
        result = runner.invoke(voice_mode_main_cli, ["clone", "uninstall"], input="n\n")
        assert result.exit_code != 0  # Aborted


# ============================================================================
# clone add
# ============================================================================


class TestCloneAdd:
    """Test clone add subcommand."""

    def test_add_help(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["clone", "add", "--help"])
        assert result.exit_code == 0
        assert "NAME" in result.output
        assert "AUDIO_FILE" in result.output
        assert "--description" in result.output
        assert "--ref-text" in result.output

    @patch("voice_mode.tools.clone.profiles.clone_add", new_callable=AsyncMock)
    def test_add_success(self, mock_add, runner, tmp_path):
        # Create a temp audio file so click.Path(exists=True) passes
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

        mock_add.return_value = {
            "success": True,
            "name": "testvoice",
            "ref_audio": str(tmp_path / "voices" / "testvoice.wav"),
            "ref_text": "Hello world",
            "description": "Test voice",
        }
        result = runner.invoke(voice_mode_main_cli, [
            "clone", "add", "testvoice", str(audio_file),
            "-d", "Test voice", "--ref-text", "Hello world",
        ])
        assert result.exit_code == 0
        assert "added successfully" in result.output

    @patch("voice_mode.tools.clone.profiles.clone_add", new_callable=AsyncMock)
    def test_add_duplicate(self, mock_add, runner, tmp_path):
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

        mock_add.return_value = {
            "success": False,
            "error": "Voice profile 'testvoice' already exists.",
        }
        result = runner.invoke(voice_mode_main_cli, [
            "clone", "add", "testvoice", str(audio_file),
        ])
        assert result.exit_code == 1
        assert "already exists" in result.output

    def test_add_missing_audio_file(self, runner):
        """Should fail if audio file doesn't exist (click.Path(exists=True))."""
        result = runner.invoke(voice_mode_main_cli, [
            "clone", "add", "testvoice", "/nonexistent/audio.wav",
        ])
        assert result.exit_code != 0

    @patch("voice_mode.tools.clone.profiles.clone_add", new_callable=AsyncMock)
    def test_add_whisper_failure_shows_hint(self, mock_add, runner, tmp_path):
        audio_file = tmp_path / "test.wav"
        audio_file.write_bytes(b"RIFF" + b"\x00" * 100)

        mock_add.return_value = {
            "success": False,
            "error": "Cannot reach Whisper STT",
            "hint": "Start Whisper with: voicemode whisper service install",
        }
        result = runner.invoke(voice_mode_main_cli, [
            "clone", "add", "testvoice", str(audio_file),
        ])
        assert result.exit_code == 1
        assert "Hint:" in result.output


# ============================================================================
# clone list
# ============================================================================


class TestCloneList:
    """Test clone list subcommand."""

    def test_list_help(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["clone", "list", "--help"])
        assert result.exit_code == 0
        assert "List available clone voice profiles" in result.output

    @patch("voice_mode.tools.clone.profiles.clone_list", new_callable=AsyncMock)
    def test_list_voices(self, mock_list, runner):
        mock_list.return_value = {
            "success": True,
            "count": 2,
            "voices": [
                {"name": "alice", "description": "Alice voice", "ref_audio": "/tmp/alice.wav"},
                {"name": "bob", "description": "Bob voice", "ref_audio": "/tmp/bob.wav"},
            ],
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "list"])
        assert result.exit_code == 0
        assert "alice" in result.output
        assert "bob" in result.output
        assert "Alice voice" in result.output

    @patch("voice_mode.tools.clone.profiles.clone_list", new_callable=AsyncMock)
    def test_list_empty(self, mock_list, runner):
        mock_list.return_value = {
            "success": True,
            "count": 0,
            "voices": [],
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "list"])
        assert result.exit_code == 0
        assert "No voice profiles found" in result.output

    @patch("voice_mode.tools.clone.profiles.clone_list", new_callable=AsyncMock)
    def test_list_no_description(self, mock_list, runner):
        """Voices without descriptions should still display."""
        mock_list.return_value = {
            "success": True,
            "count": 1,
            "voices": [
                {"name": "charlie", "description": "", "ref_audio": "/tmp/charlie.wav"},
            ],
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "list"])
        assert result.exit_code == 0
        assert "charlie" in result.output
        assert "--" not in result.output  # No description separator


# ============================================================================
# clone remove
# ============================================================================


class TestCloneRemove:
    """Test clone remove subcommand."""

    def test_remove_help(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["clone", "remove", "--help"])
        assert result.exit_code == 0
        assert "NAME" in result.output
        assert "--keep-audio" in result.output

    @patch("voice_mode.tools.clone.profiles.clone_remove", new_callable=AsyncMock)
    def test_remove_success(self, mock_remove, runner):
        mock_remove.return_value = {
            "success": True,
            "name": "testvoice",
            "audio_removed": True,
            "removed_items": ["Profile 'testvoice' from voices.json", "Audio file: /tmp/testvoice.wav"],
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "remove", "testvoice"])
        assert result.exit_code == 0
        assert "removed" in result.output

    @patch("voice_mode.tools.clone.profiles.clone_remove", new_callable=AsyncMock)
    def test_remove_not_found(self, mock_remove, runner):
        mock_remove.return_value = {
            "success": False,
            "error": "Voice profile 'nonexistent' not found.",
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "remove", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    @patch("voice_mode.tools.clone.profiles.clone_remove", new_callable=AsyncMock)
    def test_remove_keep_audio(self, mock_remove, runner):
        mock_remove.return_value = {
            "success": True,
            "name": "testvoice",
            "audio_removed": False,
            "removed_items": ["Profile 'testvoice' from voices.json"],
        }
        result = runner.invoke(voice_mode_main_cli, ["clone", "remove", "testvoice", "--keep-audio"])
        assert result.exit_code == 0
        call_kwargs = mock_remove.call_args
        assert call_kwargs.kwargs.get("remove_audio") is False or call_kwargs[1].get("remove_audio") is False

    def test_remove_missing_name(self, runner):
        """Remove without a name should fail."""
        result = runner.invoke(voice_mode_main_cli, ["clone", "remove"])
        assert result.exit_code != 0
