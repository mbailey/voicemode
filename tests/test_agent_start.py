"""Tests for agent start command and tmux helper functions."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from voice_mode.cli_commands.agent import (
    agent,
    build_claude_command,
    is_agent_running_in_pane,
    tmux_session_exists,
    tmux_window_exists,
)


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
# Tmux Helper Function Tests
# =============================================================================


class TestTmuxSessionExists:
    """Tests for tmux_session_exists function."""

    def test_returns_true_when_session_exists(self):
        """Should return True when tmux session exists."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)

            result = tmux_session_exists('voicemode')

            assert result is True
            mock_run.assert_called_once_with(
                ['tmux', 'has-session', '-t', 'voicemode'],
                capture_output=True
            )

    def test_returns_false_when_session_not_exists(self):
        """Should return False when tmux session doesn't exist."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = tmux_session_exists('nonexistent')

            assert result is False


class TestTmuxWindowExists:
    """Tests for tmux_window_exists function."""

    def test_returns_true_when_window_exists(self):
        """Should return True when window is in the list."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='operator\nmain\n'
            )

            result = tmux_window_exists('voicemode:operator')

            assert result is True
            mock_run.assert_called_once_with(
                ['tmux', 'list-windows', '-t', 'voicemode', '-F', '#{window_name}'],
                capture_output=True,
                text=True
            )

    def test_returns_false_when_window_not_exists(self):
        """Should return False when window is not in the list."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='main\nother\n'
            )

            result = tmux_window_exists('voicemode:operator')

            assert result is False

    def test_returns_false_when_session_not_exists(self):
        """Should return False when session doesn't exist."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = tmux_window_exists('nonexistent:operator')

            assert result is False

    def test_returns_false_for_invalid_window_format(self):
        """Should return False when window format is invalid."""
        result = tmux_window_exists('no-colon-here')

        assert result is False


class TestIsAgentRunningInPane:
    """Tests for is_agent_running_in_pane function."""

    def test_returns_true_when_agent_running(self):
        """Should return True when pane_current_command is not a shell."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            # Claude Code shows version number as pane_current_command
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='2.1.25\n'
            )

            result = is_agent_running_in_pane('voicemode:operator')

            assert result is True

    def test_returns_false_when_bash_running(self):
        """Should return False when pane_current_command is bash."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='bash\n'
            )

            result = is_agent_running_in_pane('voicemode:operator')

            assert result is False

    def test_returns_false_when_zsh_running(self):
        """Should return False when pane_current_command is zsh."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='zsh\n'
            )

            result = is_agent_running_in_pane('voicemode:operator')

            assert result is False

    def test_returns_false_when_login_shell(self):
        """Should return False when pane_current_command is -bash (login shell)."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout='-bash\n'
            )

            result = is_agent_running_in_pane('voicemode:operator')

            assert result is False

    def test_returns_false_on_error(self):
        """Should return False when tmux command fails."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1)

            result = is_agent_running_in_pane('voicemode:operator')

            assert result is False


class TestBuildClaudeCommand:
    """Tests for build_claude_command function."""

    def test_builds_basic_command(self, tmp_path):
        """Should build command with cd and claude."""
        agent_dir = tmp_path / '.voicemode' / 'agents' / 'operator'

        result = build_claude_command(agent_dir)

        assert f"cd {agent_dir}" in result
        assert "claude" in result
        assert "--dangerously-skip-permissions" not in result

    def test_builds_command_with_extra_args(self, tmp_path):
        """Should include extra arguments when provided."""
        agent_dir = tmp_path / '.voicemode' / 'agents' / 'operator'

        result = build_claude_command(agent_dir, extra_args='--verbose')

        assert "--verbose" in result


# =============================================================================
# Start Command Tests
# =============================================================================


class TestStartCommand:
    """Tests for the 'voicemode agent start' command."""

    def test_start_creates_session_and_window(self, temp_home, runner):
        """Should create tmux session and window when they don't exist."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            # All tmux commands succeed
            mock_run.return_value = MagicMock(returncode=0, stdout='')

            # Mock session and window checks to return False (don't exist)
            with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=False):
                with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
                    with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=False):
                        result = runner.invoke(agent, ['start'])

            assert result.exit_code == 0
            assert "Created tmux session" in result.output
            assert "Created tmux window" in result.output
            assert "Operator started" in result.output

    def test_start_is_idempotent_when_running(self, temp_home, runner):
        """Should report already running without restarting."""
        with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=True):
            with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
                with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=True):
                    result = runner.invoke(agent, ['start'])

        assert result.exit_code == 0
        assert "already running" in result.output

    def test_start_creates_agent_directory(self, temp_home, runner):
        """Should create agent directory if it doesn't exist."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='')

            with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=True):
                with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
                    with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=True):
                        result = runner.invoke(agent, ['start'])

        # Check directory was created
        agent_dir = temp_home / '.voicemode' / 'agents' / 'operator'
        assert agent_dir.exists()
        assert (agent_dir / 'CLAUDE.md').exists()

    def test_start_uses_custom_session_name(self, temp_home, runner):
        """Should use custom session name when provided."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='')

            with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=False):
                with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
                    with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=False):
                        result = runner.invoke(agent, ['start', '--session', 'custom'])

            assert result.exit_code == 0
            assert "custom" in result.output

    def test_start_only_creates_window_when_session_exists(self, temp_home, runner):
        """Should not create session if it already exists."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='')

            with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=True):
                with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
                    with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=False):
                        result = runner.invoke(agent, ['start'])

            assert result.exit_code == 0
            assert "Created tmux session" not in result.output
            assert "Created tmux window" in result.output

    def test_start_only_starts_claude_when_window_exists(self, temp_home, runner):
        """Should not create session/window if they exist."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='')

            with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=True):
                with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
                    with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=False):
                        result = runner.invoke(agent, ['start'])

            assert result.exit_code == 0
            assert "Created tmux session" not in result.output
            assert "Created tmux window" not in result.output
            assert "Operator started" in result.output

    def test_start_fails_when_session_creation_fails(self, temp_home, runner):
        """Should fail with error when session creation fails."""
        with patch('voice_mode.cli_commands.agent.subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr=b'error')

            with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=False):
                result = runner.invoke(agent, ['start'])

        assert result.exit_code == 1
        assert "Failed to create tmux session" in result.output
