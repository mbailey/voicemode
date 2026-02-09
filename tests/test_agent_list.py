"""Tests for agent list command (Easter egg)."""

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from voice_mode.cli_commands.agent import agent, list_agents, get_agents_base_dir


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
# List Command Tests
# =============================================================================


class TestListCommand:
    """Tests for the 'voicemode agent list' command."""

    def test_list_command_visible_in_help(self, runner):
        """The list command should be visible in --help output."""
        result = runner.invoke(agent, ['--help'])

        assert result.exit_code == 0
        # list should appear in the help output
        assert 'list' in result.output.lower()

    def test_list_command_works_when_called_directly(self, runner, temp_home):
        """The list command should work when called directly despite being hidden."""
        # Create agent directories
        base = temp_home / '.voicemode' / 'agents'
        (base / 'operator').mkdir(parents=True)
        (base / 'custom').mkdir(parents=True)

        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
            with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=False):
                result = runner.invoke(agent, ['list'])

        assert result.exit_code == 0
        assert 'operator' in result.output
        assert 'custom' in result.output

    def test_list_shows_no_agents_when_none_configured(self, runner, temp_home):
        """Should show message when no agents are configured."""
        result = runner.invoke(agent, ['list'])

        assert result.exit_code == 0
        assert "No agents configured" in result.output

    def test_list_shows_no_agents_when_base_dir_empty(self, runner, temp_home):
        """Should show message when agents directory exists but is empty."""
        base = temp_home / '.voicemode' / 'agents'
        base.mkdir(parents=True)

        result = runner.invoke(agent, ['list'])

        assert result.exit_code == 0
        assert "No agents configured" in result.output

    def test_list_shows_running_status(self, runner, temp_home):
        """Should show 'running' status for agents that are running."""
        base = temp_home / '.voicemode' / 'agents'
        (base / 'operator').mkdir(parents=True)

        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
            with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=True):
                result = runner.invoke(agent, ['list'])

        assert result.exit_code == 0
        assert 'running' in result.output

    def test_list_shows_stopped_status(self, runner, temp_home):
        """Should show 'stopped' status for agents that are not running."""
        base = temp_home / '.voicemode' / 'agents'
        (base / 'operator').mkdir(parents=True)

        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
            result = runner.invoke(agent, ['list'])

        assert result.exit_code == 0
        assert 'stopped' in result.output

    def test_list_ignores_hidden_directories(self, runner, temp_home):
        """Should not list hidden directories (starting with .)."""
        base = temp_home / '.voicemode' / 'agents'
        (base / 'operator').mkdir(parents=True)
        (base / '.hidden').mkdir(parents=True)

        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
            result = runner.invoke(agent, ['list'])

        assert result.exit_code == 0
        assert 'operator' in result.output
        assert '.hidden' not in result.output

    def test_list_checks_default_session(self, runner, temp_home):
        """Should check status in the default 'voicemode' session."""
        base = temp_home / '.voicemode' / 'agents'
        (base / 'operator').mkdir(parents=True)

        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False) as mock_window:
            result = runner.invoke(agent, ['list'])

        assert result.exit_code == 0
        mock_window.assert_called_with('voicemode:operator')

    def test_list_sorts_agents_alphabetically(self, runner, temp_home):
        """Should sort agents alphabetically."""
        base = temp_home / '.voicemode' / 'agents'
        (base / 'zebra').mkdir(parents=True)
        (base / 'alpha').mkdir(parents=True)
        (base / 'operator').mkdir(parents=True)

        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
            result = runner.invoke(agent, ['list'])

        assert result.exit_code == 0
        lines = result.output.strip().split('\n')
        # Skip header rows
        agent_lines = [l for l in lines if 'Agent' not in l and '---' not in l]
        agent_names = [l.split()[0] for l in agent_lines]
        assert agent_names == ['alpha', 'operator', 'zebra']

    def test_list_shows_machine_readable_output(self, runner, temp_home):
        """Should display tab-separated output in non-TTY mode (CliRunner)."""
        base = temp_home / '.voicemode' / 'agents'
        (base / 'operator').mkdir(parents=True)

        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
            result = runner.invoke(agent, ['list'])

        assert result.exit_code == 0
        # CliRunner is not a TTY, so output is tab-separated
        assert 'operator\tstopped' in result.output

    def test_list_help_option(self, runner, temp_home):
        """Should display help when -h is passed."""
        result = runner.invoke(agent, ['list', '-h'])

        assert result.exit_code == 0
        assert "List all agents and their status" in result.output


# =============================================================================
# list_agents Helper Function Tests
# =============================================================================


class TestListAgentsHelper:
    """Tests for the list_agents helper function."""

    def test_list_agents_returns_empty_when_no_base_dir(self, temp_home):
        """Should return empty list when base directory doesn't exist."""
        result = list_agents()
        assert result == []

    def test_list_agents_returns_agents_with_status(self, temp_home):
        """Should return list of agents with their status."""
        base = temp_home / '.voicemode' / 'agents'
        (base / 'operator').mkdir(parents=True)
        (base / 'custom').mkdir(parents=True)

        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
            result = list_agents()

        assert len(result) == 2
        assert {'name': 'operator', 'status': 'stopped'} in result
        assert {'name': 'custom', 'status': 'stopped'} in result

    def test_list_agents_detects_running_status(self, temp_home):
        """Should detect running agents."""
        base = temp_home / '.voicemode' / 'agents'
        (base / 'operator').mkdir(parents=True)

        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=True):
            with patch('voice_mode.cli_commands.agent.is_agent_running_in_pane', return_value=True):
                result = list_agents()

        assert len(result) == 1
        assert result[0] == {'name': 'operator', 'status': 'running'}

    def test_list_agents_ignores_hidden_dirs(self, temp_home):
        """Should not include hidden directories."""
        base = temp_home / '.voicemode' / 'agents'
        (base / 'operator').mkdir(parents=True)
        (base / '.hidden').mkdir(parents=True)

        with patch('voice_mode.cli_commands.agent.tmux_window_exists', return_value=False):
            result = list_agents()

        assert len(result) == 1
        names = [a['name'] for a in result]
        assert 'operator' in names
        assert '.hidden' not in names
