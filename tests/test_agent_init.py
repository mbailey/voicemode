"""Tests for agent directory initialization."""

import pytest
from pathlib import Path

from voice_mode.cli_commands.agent import (
    init_agent_directory,
    get_agents_base_dir,
    parse_env_file,
    load_agent_env,
    BASE_AGENT_MD,
    BASE_CLAUDE_MD,
    BASE_SKILL_MD,
    BASE_ENV,
    OPERATOR_AGENT_MD,
    OPERATOR_CLAUDE_MD,
    OPERATOR_SKILL_MD,
    OPERATOR_ENV,
)


@pytest.fixture
def temp_home(tmp_path, monkeypatch):
    """Set up a temporary home directory."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Also patch Path.home() for platforms where HOME might not be used
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


class TestInitAgentDirectory:
    """Tests for init_agent_directory function."""

    def test_creates_base_directory(self, temp_home):
        """Should create ~/.voicemode/agents/ base directory."""
        init_agent_directory('operator')

        base_dir = temp_home / '.voicemode' / 'agents'
        assert base_dir.exists()
        assert base_dir.is_dir()

    def test_creates_operator_directory(self, temp_home):
        """Should create operator subdirectory."""
        agent_dir = init_agent_directory('operator')

        assert agent_dir.exists()
        assert agent_dir.is_dir()
        assert agent_dir == temp_home / '.voicemode' / 'agents' / 'operator'

    def test_creates_base_files(self, temp_home):
        """Should create shared template files in base directory."""
        init_agent_directory('operator')

        base_dir = temp_home / '.voicemode' / 'agents'

        # Check all base files exist
        assert (base_dir / 'AGENT.md').exists()
        assert (base_dir / 'CLAUDE.md').exists()
        assert (base_dir / 'SKILL.md').exists()
        assert (base_dir / 'voicemode.env').exists()

        # Check content matches templates
        assert (base_dir / 'AGENT.md').read_text() == BASE_AGENT_MD
        assert (base_dir / 'CLAUDE.md').read_text() == BASE_CLAUDE_MD
        assert (base_dir / 'SKILL.md').read_text() == BASE_SKILL_MD
        assert (base_dir / 'voicemode.env').read_text() == BASE_ENV

    def test_creates_operator_files(self, temp_home):
        """Should create operator-specific files."""
        agent_dir = init_agent_directory('operator')

        # Check all operator files exist
        assert (agent_dir / 'AGENT.md').exists()
        assert (agent_dir / 'CLAUDE.md').exists()
        assert (agent_dir / 'SKILL.md').exists()
        assert (agent_dir / 'voicemode.env').exists()

        # Check content matches operator templates
        assert (agent_dir / 'AGENT.md').read_text() == OPERATOR_AGENT_MD
        assert (agent_dir / 'CLAUDE.md').read_text() == OPERATOR_CLAUDE_MD
        assert (agent_dir / 'SKILL.md').read_text() == OPERATOR_SKILL_MD
        assert (agent_dir / 'voicemode.env').read_text() == OPERATOR_ENV

    def test_is_idempotent(self, temp_home):
        """Should not overwrite existing files on second call."""
        agent_dir = init_agent_directory('operator')

        # Modify a file
        custom_content = "# Custom content\n"
        (agent_dir / 'SKILL.md').write_text(custom_content)

        # Call init again
        init_agent_directory('operator')

        # File should not be overwritten
        assert (agent_dir / 'SKILL.md').read_text() == custom_content

    def test_creates_custom_agent(self, temp_home):
        """Should create a custom agent with generic templates."""
        agent_dir = init_agent_directory('assistant')

        # Check directory exists
        assert agent_dir.exists()
        assert agent_dir == temp_home / '.voicemode' / 'agents' / 'assistant'

        # Check files exist
        assert (agent_dir / 'AGENT.md').exists()
        assert (agent_dir / 'CLAUDE.md').exists()
        assert (agent_dir / 'SKILL.md').exists()
        assert (agent_dir / 'voicemode.env').exists()

        # Custom agent should have name in CLAUDE.md
        claude_content = (agent_dir / 'CLAUDE.md').read_text()
        assert 'assistant' in claude_content

    def test_returns_agent_directory_path(self, temp_home):
        """Should return the path to the agent's directory."""
        result = init_agent_directory('operator')

        expected = temp_home / '.voicemode' / 'agents' / 'operator'
        assert result == expected


class TestParseEnvFile:
    """Tests for parse_env_file function."""

    def test_parses_simple_values(self, tmp_path):
        """Should parse simple KEY=value pairs."""
        env_file = tmp_path / 'test.env'
        env_file.write_text("FOO=bar\nBAZ=qux\n")

        result = parse_env_file(env_file)

        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_handles_comments(self, tmp_path):
        """Should ignore comment lines."""
        env_file = tmp_path / 'test.env'
        env_file.write_text("# Comment\nFOO=bar\n# Another comment\n")

        result = parse_env_file(env_file)

        assert result == {"FOO": "bar"}

    def test_handles_empty_lines(self, tmp_path):
        """Should ignore empty lines."""
        env_file = tmp_path / 'test.env'
        env_file.write_text("FOO=bar\n\n\nBAZ=qux\n")

        result = parse_env_file(env_file)

        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_handles_quoted_values(self, tmp_path):
        """Should strip quotes from values."""
        env_file = tmp_path / 'test.env'
        env_file.write_text('FOO="bar"\nBAZ=\'qux\'\n')

        result = parse_env_file(env_file)

        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_handles_missing_file(self, tmp_path):
        """Should return empty dict for missing file."""
        result = parse_env_file(tmp_path / 'nonexistent.env')

        assert result == {}


class TestLoadAgentEnv:
    """Tests for load_agent_env function."""

    def test_loads_base_and_agent_config(self, temp_home):
        """Should load and merge base and agent-specific config."""
        # Set up directories
        init_agent_directory('operator')

        base_dir = temp_home / '.voicemode' / 'agents'
        agent_dir = base_dir / 'operator'

        # Write base config
        (base_dir / 'voicemode.env').write_text("BASE_VAR=base_value\nSHARED=base\n")

        # Write agent config
        (agent_dir / 'voicemode.env').write_text("AGENT_VAR=agent_value\nSHARED=agent\n")

        result = load_agent_env('operator')

        # Should have both base and agent values
        assert result["BASE_VAR"] == "base_value"
        assert result["AGENT_VAR"] == "agent_value"
        # Agent should override base
        assert result["SHARED"] == "agent"

    def test_works_with_missing_files(self, temp_home):
        """Should work even if config files don't exist."""
        # Don't initialize - no files exist
        result = load_agent_env('operator')

        assert result == {}
