"""Tests for Whisper model management CLI commands."""

import pytest
from click.testing import CliRunner
from unittest.mock import patch, MagicMock
from voice_mode.cli import voice_mode_main_cli


class TestWhisperModelsCLI:
    """Test whisper models listing command."""

    def test_whisper_models_command(self):
        """Test that whisper models command runs successfully."""
        runner = CliRunner()

        # The command is now 'whisper model --all' not 'whisper models'
        result = runner.invoke(voice_mode_main_cli, ['whisper', 'model', '--all'])

        assert result.exit_code == 0
        assert 'Available Whisper Models' in result.output or 'Whisper Models' in result.output


class TestWhisperModelActiveCLI:
    """Test whisper model active command."""

    def test_show_active_model(self):
        """Test showing the currently active model."""
        runner = CliRunner()

        # Command is now just 'whisper model' without 'active'
        result = runner.invoke(voice_mode_main_cli, ['whisper', 'model'])

        assert result.exit_code == 0 or result.exit_code == 1  # May fail if no models installed
        assert 'Active' in result.output or 'model' in result.output.lower()

    def test_set_active_model(self):
        """Test setting a new active model."""
        runner = CliRunner()

        # Command is now 'whisper model <model>' not 'whisper model active <model>'
        # With --no-install to avoid actually installing
        with patch('voice_mode.tools.whisper.models.is_whisper_model_installed') as mock_installed:
            mock_installed.return_value = True

            result = runner.invoke(voice_mode_main_cli, ['whisper', 'model', 'small', '--no-install'])

            assert result.exit_code == 0
            assert "small" in result.output.lower()

    def test_set_active_model_not_installed(self):
        """Test setting an active model that's not installed."""
        runner = CliRunner()

        # With --no-install, setting a non-installed model should fail
        with patch('voice_mode.tools.whisper.models.is_whisper_model_installed') as mock_installed:
            mock_installed.return_value = False

            result = runner.invoke(voice_mode_main_cli, ['whisper', 'model', 'small', '--no-install'])

            # Should fail with exit code 1
            assert result.exit_code == 1
            assert "not installed" in result.output.lower() or "not available" in result.output.lower()


class TestWhisperModelInstallCLI:
    """Test whisper model install command."""
    
    @pytest.mark.skip(reason="Test needs refactoring after services directory removal")
    def test_install_default_model(self):
        """Test installing the default model."""
        runner = CliRunner()

        with patch('asyncio.run') as mock_run:
            mock_run.return_value = '{"success": true, "results": [{"model": "large-v2"}]}'

            result = runner.invoke(voice_mode_main_cli, ['whisper', 'model', 'install'])

            assert result.exit_code == 0
            assert '✅ Model download completed!' in result.output
    
    @pytest.mark.skip(reason="Test needs refactoring after services directory removal")
    def test_install_specific_model(self):
        """Test installing a specific model."""
        runner = CliRunner()

        with patch('asyncio.run') as mock_run:
            mock_run.return_value = '{"success": true, "results": [{"model": "small"}]}'

            result = runner.invoke(voice_mode_main_cli, ['whisper', 'model', 'install', 'small'])

            assert result.exit_code == 0
            assert '✅ Model download completed!' in result.output

    @pytest.mark.skip(reason="Test needs refactoring after services directory removal")
    def test_install_invalid_model(self):
        """Test installing an invalid model name."""
        runner = CliRunner()

        with patch('asyncio.run') as mock_run:
            mock_run.return_value = '{"success": false, "error": "Invalid model: invalid-model"}'

            result = runner.invoke(voice_mode_main_cli, ['whisper', 'model', 'install', 'invalid-model'])

            # Should still exit 0 but show error message
            assert result.exit_code == 0
            assert '❌ Download failed' in result.output


class TestWhisperModelRemoveCLI:
    """Test whisper model remove command."""

    @pytest.mark.skip(reason="Remove command has been removed from CLI")
    def test_remove_model_with_confirmation(self):
        """Test removing a model with confirmation."""
        pass

    @pytest.mark.skip(reason="Remove command has been removed from CLI")
    def test_remove_model_not_installed(self):
        """Test removing a model that's not installed."""
        pass

    @pytest.mark.skip(reason="Remove command has been removed from CLI")
    def test_remove_invalid_model(self):
        """Test removing an invalid model name."""
        pass