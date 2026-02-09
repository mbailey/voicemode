"""Tests for agent status command."""

from pathlib import Path
from unittest.mock import patch

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
# Status Command Tests
# =============================================================================


class TestStatusCommand:
    """Tests for the 'voicemode agent status' command."""

    def test_status_shows_running_when_all_exists(self, runner):
        """Should show 'running' when session, window, and Claude exist."""
        with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=True):
            with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
                with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=True):
                    result = runner.invoke(agent, ['status'])

        assert result.exit_code == 0
        assert result.output.strip() == "running"

    def test_status_shows_stopped_no_session(self, runner):
        """Should show 'stopped' when tmux session doesn't exist."""
        with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=False):
            result = runner.invoke(agent, ['status'])

        assert result.exit_code == 0
        assert "stopped" in result.output
        assert "no tmux session" in result.output

    def test_status_shows_stopped_no_window(self, runner):
        """Should show 'stopped' when window doesn't exist."""
        with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=True):
            with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
                result = runner.invoke(agent, ['status'])

        assert result.exit_code == 0
        assert "stopped" in result.output
        assert "no 'operator' window" in result.output

    def test_status_shows_stopped_claude_not_running(self, runner):
        """Should show 'stopped' when Claude is not running in pane."""
        with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=True):
            with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
                with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=False):
                    result = runner.invoke(agent, ['status'])

        assert result.exit_code == 0
        assert "stopped" in result.output
        assert "Claude not running" in result.output

    def test_status_uses_custom_session_name(self, runner):
        """Should check the specified session name."""
        with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=False) as mock_exists:
            result = runner.invoke(agent, ['status', '--session', 'custom'])

        assert result.exit_code == 0
        mock_exists.assert_called_once_with('custom')
        assert "custom" in result.output

    def test_status_checks_correct_window_name(self, runner):
        """Should check for 'operator' window in the session."""
        with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=True):
            with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False) as mock_window:
                result = runner.invoke(agent, ['status', '--session', 'test'])

        mock_window.assert_called_once_with('test:operator')

    def test_status_help_option(self, runner):
        """Should display help when -h is passed."""
        result = runner.invoke(agent, ['status', '-h'])

        assert result.exit_code == 0
        assert "Show agent status" in result.output
        assert "--session" in result.output
