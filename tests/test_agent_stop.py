"""Tests for agent stop command."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from voice_mode.cli_commands.agent import agent


@pytest.fixture
def temp_home(tmp_path, monkeypatch):
    """Set up a temporary home directory."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


# =============================================================================
# Stop Command Tests
# =============================================================================


class TestStopCommand:
    """Tests for the 'voicemode agent stop' command."""

    def test_stop_sends_ctrl_c_when_window_exists(self, runner):
        """Should send Ctrl-C 3 times when window exists."""
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
            with patch('voice_mode.cli_commands.agent.subprocess.run', mock_run):
                with patch('voice_mode.cli_commands.agent.time.sleep'):
                    result = runner.invoke(agent, ['stop'])

        assert result.exit_code == 0
        assert "Sent stop signal" in result.output
        # Verify Ctrl-C was sent 3 times (Claude Code needs multiple signals)
        assert mock_run.call_count == 3
        for c in mock_run.call_args_list:
            assert c[0][0] == ['tmux', 'send-keys', '-t', 'voicemode:operator', 'C-c']

    def test_stop_reports_not_running_when_no_window(self, runner):
        """Should report not running when window doesn't exist."""
        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
            result = runner.invoke(agent, ['stop'])

        assert result.exit_code == 0
        assert "not running" in result.output

    def test_stop_kill_flag_kills_window(self, runner):
        """Should kill window when --kill flag is used."""
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
            with patch('voice_mode.cli_commands.agent.subprocess.run', mock_run):
                result = runner.invoke(agent, ['stop', '--kill'])

        assert result.exit_code == 0
        assert "window killed" in result.output
        # Verify kill-window was called
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert call_args == ['tmux', 'kill-window', '-t', 'voicemode:operator']

    def test_stop_uses_custom_session_name(self, runner):
        """Should use custom session name."""
        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False) as mock_window:
            result = runner.invoke(agent, ['stop', '--session', 'custom'])

        mock_window.assert_called_once_with('custom:operator')
        assert "custom" in result.output

    def test_stop_handles_subprocess_error(self, runner):
        """Should handle subprocess errors gracefully."""
        mock_run = MagicMock(return_value=MagicMock(returncode=1))
        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
            with patch('voice_mode.cli_commands.agent.subprocess.run', mock_run):
                result = runner.invoke(agent, ['stop'])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_stop_kill_handles_subprocess_error(self, runner):
        """Should handle subprocess errors when killing window."""
        mock_run = MagicMock(return_value=MagicMock(returncode=1))
        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
            with patch('voice_mode.cli_commands.agent.subprocess.run', mock_run):
                result = runner.invoke(agent, ['stop', '--kill'])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_stop_help_option(self, runner):
        """Should display help when -h is passed."""
        result = runner.invoke(agent, ['stop', '-h'])

        assert result.exit_code == 0
        assert "Stop an agent" in result.output
        assert "--session" in result.output
        assert "--kill" in result.output

    def test_stop_exit_code_zero_when_not_running(self, runner):
        """Should exit with code 0 when agent not running (idempotent)."""
        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
            result = runner.invoke(agent, ['stop'])

        # Stop is idempotent - not an error if already stopped
        assert result.exit_code == 0
