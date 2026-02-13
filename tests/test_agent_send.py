"""Tests for agent send command."""

from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest
from click.testing import CliRunner

from voice_mode.cli_commands.agent import agent, escape_for_tmux, is_operator_running


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
# Helper Function Tests
# =============================================================================


class TestEscapeForTmux:
    """Tests for the escape_for_tmux helper function."""

    def test_returns_simple_message_unchanged(self):
        """Should return simple messages unchanged."""
        assert escape_for_tmux("hello world") == "hello world"

    def test_handles_quotes(self):
        """Should handle quoted strings."""
        assert escape_for_tmux('say "hello"') == 'say "hello"'

    def test_handles_special_characters(self):
        """Should handle special characters."""
        assert escape_for_tmux("test $HOME & other") == "test $HOME & other"

    def test_handles_empty_string(self):
        """Should handle empty strings."""
        assert escape_for_tmux("") == ""


class TestIsOperatorRunning:
    """Tests for the is_operator_running helper function."""

    def test_returns_true_when_window_and_claude_exist(self):
        """Should return True when both window exists and Claude is running."""
        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
            with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=True):
                assert is_operator_running() is True

    def test_returns_false_when_window_not_exists(self):
        """Should return False when window doesn't exist."""
        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
            with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=True):
                assert is_operator_running() is False

    def test_returns_false_when_claude_not_running(self):
        """Should return False when Claude is not running."""
        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
            with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=False):
                assert is_operator_running() is False

    def test_uses_custom_session_name(self):
        """Should use custom session name when provided."""
        with patch('voice_mode.cli_commands.agent.tmux_window_exists') as mock_window:
            mock_window.return_value = False
            is_operator_running('custom')
            mock_window.assert_called_once_with('custom:operator')


# =============================================================================
# Send Command Tests
# =============================================================================


class TestSendCommand:
    """Tests for the 'voicemode agent send' command."""

    def test_send_delivers_message_when_running(self, runner):
        """Should send message to tmux pane when agent is running."""
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch('voice_mode.cli_commands.agent.is_agent_running', return_value=True):
            with patch('voice_mode.cli_commands.agent.subprocess.run', mock_run):
                result = runner.invoke(agent, ['send', 'Hello, world!'])

        assert result.exit_code == 0
        assert "Sent to" in result.output
        # Verify send-keys was called with -l for literal
        # First calls may be tmux list-windows etc., find the send-keys calls
        send_calls = [c for c in mock_run.call_args_list if 'send-keys' in c[0][0]]
        assert len(send_calls) == 2  # Message + Enter
        assert '-l' in send_calls[0][0][0]
        assert 'Hello, world!' in send_calls[0][0][0]
        assert 'Enter' in send_calls[1][0][0]

    def test_send_auto_starts_when_not_running(self, runner, temp_home):
        """Should auto-start agent if not running (default behavior)."""
        mock_run = MagicMock(return_value=MagicMock(returncode=0))

        with patch('voice_mode.cli_commands.agent.is_agent_running', return_value=False):
            with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=True):
                with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
                    with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=False):
                        with patch('voice_mode.cli_commands.agent.subprocess.run', mock_run):
                            result = runner.invoke(agent, ['send', 'Hello!'])

        assert result.exit_code == 0
        assert "Starting agent" in result.output

    def test_send_no_start_fails_when_not_running(self, runner):
        """Should fail with --no-start when agent is not running."""
        with patch('voice_mode.cli_commands.agent.is_agent_running', return_value=False):
            result = runner.invoke(agent, ['send', '--no-start', 'Hello!'])

        assert result.exit_code == 1
        assert "not running" in result.output

    def test_send_prompts_for_message_when_not_provided(self, runner):
        """Should prompt for message when not provided."""
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch('voice_mode.cli_commands.agent.is_agent_running', return_value=True):
            with patch('voice_mode.cli_commands.agent.subprocess.run', mock_run):
                result = runner.invoke(agent, ['send'], input='My message\n')

        assert result.exit_code == 0
        assert "Sent to" in result.output

    def test_send_uses_custom_session_name(self, runner):
        """Should use custom session name."""
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch('voice_mode.cli_commands.agent.is_agent_running', return_value=True) as mock_running:
            with patch('voice_mode.cli_commands.agent.subprocess.run', mock_run):
                result = runner.invoke(agent, ['send', '--session', 'custom', 'Hello!'])

        mock_running.assert_called_once_with('operator', 'custom')
        # Find the send-keys call and verify it targets custom:operator
        send_calls = [c for c in mock_run.call_args_list if 'send-keys' in c[0][0]]
        assert 'custom:operator' in ' '.join(send_calls[0][0][0])

    def test_send_truncates_long_messages_in_output(self, runner):
        """Should truncate long messages in output for readability."""
        long_message = "A" * 100
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch('voice_mode.cli_commands.agent.is_agent_running', return_value=True):
            with patch('voice_mode.cli_commands.agent.subprocess.run', mock_run):
                result = runner.invoke(agent, ['send', long_message])

        assert result.exit_code == 0
        assert "..." in result.output
        # But the full message should be sent via tmux
        send_calls = [c for c in mock_run.call_args_list if 'send-keys' in c[0][0] and '-l' in c[0][0]]
        assert len(send_calls) >= 1
        assert long_message in send_calls[0][0][0]

    def test_send_handles_send_keys_error(self, runner):
        """Should handle errors from tmux send-keys."""
        mock_run = MagicMock(return_value=MagicMock(returncode=1))
        with patch('voice_mode.cli_commands.agent.is_agent_running', return_value=True):
            with patch('voice_mode.cli_commands.agent.subprocess.run', mock_run):
                result = runner.invoke(agent, ['send', 'Hello!'])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_send_handles_enter_key_error(self, runner):
        """Should handle errors when sending Enter key."""
        def run_side_effect(*args, **kwargs):
            cmd = args[0]
            if 'Enter' in cmd:
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)

        with patch('voice_mode.cli_commands.agent.is_agent_running', return_value=True):
            with patch('voice_mode.cli_commands.agent.subprocess.run', side_effect=run_side_effect):
                result = runner.invoke(agent, ['send', 'Hello!'])

        assert result.exit_code == 1
        assert "Error" in result.output

    def test_send_help_option(self, runner):
        """Should display help when -h is passed."""
        result = runner.invoke(agent, ['send', '-h'])

        assert result.exit_code == 0
        assert "Send a message to an agent" in result.output
        assert "--no-start" in result.output
        assert "--session" in result.output

    def test_send_handles_special_characters(self, runner):
        """Should handle messages with special characters."""
        special_msg = 'Hello "world" & $HOME!'
        mock_run = MagicMock(return_value=MagicMock(returncode=0))
        with patch('voice_mode.cli_commands.agent.is_agent_running', return_value=True):
            with patch('voice_mode.cli_commands.agent.subprocess.run', mock_run):
                result = runner.invoke(agent, ['send', special_msg])

        assert result.exit_code == 0
        # Message should be sent with -l flag for literal interpretation
        send_calls = [c for c in mock_run.call_args_list if 'send-keys' in c[0][0] and '-l' in c[0][0]]
        assert len(send_calls) >= 1
        assert special_msg in send_calls[0][0][0]

    def test_send_auto_starts_with_message_as_prompt(self, runner, temp_home):
        """Should auto-start agent with message passed as initial prompt."""
        mock_run = MagicMock(return_value=MagicMock(returncode=0))

        with patch('voice_mode.cli_commands.agent.is_agent_running', return_value=False):
            with patch('voice_mode.cli_commands.agent.tmux_session_exists', return_value=True):
                with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
                    with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=False):
                        with patch('voice_mode.cli_commands.agent.subprocess.run', mock_run):
                            result = runner.invoke(agent, ['send', 'Hello!'])

        assert result.exit_code == 0
        # Auto-start passes message as initial prompt to claude command
        assert "Started with: Hello!" in result.output
