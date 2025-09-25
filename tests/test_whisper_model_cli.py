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
        
        # Just test that the command runs without mocking
        # The actual implementation will use real functions
        result = runner.invoke(voice_mode_main_cli, ['whisper', 'models'])
        
        assert result.exit_code == 0
        assert 'Whisper Models:' in result.output


class TestWhisperModelActiveCLI:
    """Test whisper model active command."""
    
    def test_show_active_model(self):
        """Test showing the currently active model."""
        runner = CliRunner()
        
        # Let's just test that the command runs without mocking
        # since the actual model can vary
        result = runner.invoke(voice_mode_main_cli, ['whisper', 'model', 'active'])
        
        assert result.exit_code == 0
        assert 'Active Whisper model:' in result.output
    
    def test_set_active_model(self):
        """Test setting a new active model."""
        runner = CliRunner()
        
        # Patch at the correct module level where imported
        with patch('voice_mode.tools.whisper.models.is_whisper_model_installed') as mock_installed, \
             patch('voice_mode.tools.whisper.models.set_active_model') as mock_set:
            
            mock_installed.return_value = True
            
            result = runner.invoke(voice_mode_main_cli, ['whisper', 'model', 'active', 'small'])
            
            assert result.exit_code == 0
            assert "Active model set to: small" in result.output
            assert "restart the whisper service" in result.output.lower()
            mock_set.assert_called_once_with('small')
    
    def test_set_active_model_not_installed(self):
        """Test setting an active model that's not installed."""
        runner = CliRunner()
        
        # Patch at the correct module level
        with patch('voice_mode.tools.whisper.models.is_whisper_model_installed') as mock_installed:
            mock_installed.return_value = False
            
            result = runner.invoke(voice_mode_main_cli, ['whisper', 'model', 'active', 'small'])
            
            # The CLI exits with code 1 when model is not installed (click.Abort())
            assert result.exit_code == 1
            assert "not installed" in result.output


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
    
    def test_remove_model_with_confirmation(self):
        """Test removing a model with confirmation."""
        runner = CliRunner()
        
        with patch('voice_mode.tools.whisper.models.is_model_installed') as mock_installed, \
             patch('click.confirm') as mock_confirm, \
             patch('os.unlink') as mock_unlink, \
             patch('voice_mode.tools.whisper.models.get_model_directory') as mock_dir:
            
            mock_installed.return_value = True
            mock_confirm.return_value = True
            mock_dir.return_value = MagicMock()
            
            result = runner.invoke(voice_mode_main_cli, ['whisper', 'model', 'remove', 'tiny'])
            
            # Note: The actual implementation exits in the command, not at CLI level
            # so we check the mocks were called
            mock_confirm.assert_called_once()
    
    def test_remove_model_not_installed(self):
        """Test removing a model that's not installed."""
        runner = CliRunner()
        
        # Patch at the correct module level
        with patch('voice_mode.tools.whisper.models.is_whisper_model_installed') as mock_installed:
            mock_installed.return_value = False
            
            result = runner.invoke(voice_mode_main_cli, ['whisper', 'model', 'remove', 'base'])
            
            assert result.exit_code == 0
            assert "Model 'base' is not installed" in result.output
    
    def test_remove_invalid_model(self):
        """Test removing an invalid model name."""
        runner = CliRunner()
        
        result = runner.invoke(voice_mode_main_cli, ['whisper', 'model', 'remove', 'invalid-model'])
        
        assert result.exit_code == 1
        assert "not a valid model" in result.output