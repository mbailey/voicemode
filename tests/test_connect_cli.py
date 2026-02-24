"""Tests for VoiceMode Connect CLI commands."""

import json

import pytest
from click.testing import CliRunner

from voice_mode.cli import voice_mode_main_cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def connect_env(tmp_path, monkeypatch):
    """Set up environment for Connect-enabled tests."""
    users_dir = tmp_path / "connect" / "users"
    users_dir.mkdir(parents=True)

    # Enable Connect
    monkeypatch.setenv("VOICEMODE_CONNECT_ENABLED", "true")
    monkeypatch.setenv("VOICEMODE_CONNECT_HOST", "testhost")

    # Patch USERS_DIR so we use tmp directory
    import voice_mode.connect.users as users_mod
    monkeypatch.setattr(users_mod, "USERS_DIR", users_dir)

    # Reload config to pick up env vars
    import voice_mode.config as config_mod
    monkeypatch.setattr(config_mod, "CONNECT_ENABLED", True)
    monkeypatch.setattr(config_mod, "CONNECT_HOST", "testhost")
    monkeypatch.setattr(config_mod, "CONNECT_WS_URL", "wss://voicemode.dev/ws")

    return {"users_dir": users_dir, "tmp_path": tmp_path}


class TestUserAdd:
    def test_adds_user_with_valid_name(self, runner, connect_env):
        result = runner.invoke(voice_mode_main_cli, ["connect", "user", "add", "cora"])
        assert result.exit_code == 0
        assert "Added user: cora@testhost" in result.output

    def test_adds_user_with_display_name(self, runner, connect_env):
        result = runner.invoke(
            voice_mode_main_cli,
            ["connect", "user", "add", "cora", "--name", "Cora 7"],
        )
        assert result.exit_code == 0
        assert "Added user: cora@testhost" in result.output
        assert "Display name: Cora 7" in result.output

    def test_rejects_uppercase_name(self, runner, connect_env):
        result = runner.invoke(voice_mode_main_cli, ["connect", "user", "add", "Cora"])
        assert result.exit_code != 0
        assert "Error: Name must be lowercase" in result.output

    def test_rejects_name_starting_with_number(self, runner, connect_env):
        result = runner.invoke(voice_mode_main_cli, ["connect", "user", "add", "1bad"])
        assert result.exit_code != 0
        assert "Error: Name must be lowercase" in result.output

    def test_errors_when_not_enabled(self, runner, monkeypatch):
        import voice_mode.config as config_mod
        monkeypatch.setattr(config_mod, "CONNECT_ENABLED", False)

        result = runner.invoke(voice_mode_main_cli, ["connect", "user", "add", "cora"])
        assert result.exit_code != 0
        assert "not enabled" in result.output


class TestUserList:
    def test_shows_no_users_message(self, runner, connect_env):
        result = runner.invoke(voice_mode_main_cli, ["connect", "user", "list"])
        assert result.exit_code == 0
        assert "No users registered" in result.output

    def test_shows_users_table(self, runner, connect_env):
        # Add a user first
        runner.invoke(
            voice_mode_main_cli,
            ["connect", "user", "add", "cora", "--name", "Cora 7"],
        )

        result = runner.invoke(voice_mode_main_cli, ["connect", "user", "list"])
        assert result.exit_code == 0
        assert "NAME" in result.output
        assert "ADDRESS" in result.output
        assert "cora" in result.output
        assert "cora@testhost" in result.output

    def test_errors_when_not_enabled(self, runner, monkeypatch):
        import voice_mode.config as config_mod
        monkeypatch.setattr(config_mod, "CONNECT_ENABLED", False)

        result = runner.invoke(voice_mode_main_cli, ["connect", "user", "list"])
        assert result.exit_code != 0
        assert "not enabled" in result.output


class TestUserRemove:
    def test_removes_existing_user(self, runner, connect_env):
        # Add then remove
        runner.invoke(voice_mode_main_cli, ["connect", "user", "add", "cora"])
        result = runner.invoke(voice_mode_main_cli, ["connect", "user", "remove", "cora"])
        assert result.exit_code == 0
        assert "Removed user: cora" in result.output

    def test_errors_for_nonexistent_user(self, runner, connect_env):
        result = runner.invoke(voice_mode_main_cli, ["connect", "user", "remove", "nobody"])
        assert result.exit_code != 0
        assert "User not found: nobody" in result.output

    def test_errors_when_not_enabled(self, runner, monkeypatch):
        import voice_mode.config as config_mod
        monkeypatch.setattr(config_mod, "CONNECT_ENABLED", False)

        result = runner.invoke(voice_mode_main_cli, ["connect", "user", "remove", "cora"])
        assert result.exit_code != 0
        assert "not enabled" in result.output


class TestStatus:
    def test_shows_disabled_when_not_enabled(self, runner, monkeypatch):
        import voice_mode.config as config_mod
        monkeypatch.setattr(config_mod, "CONNECT_ENABLED", False)

        result = runner.invoke(voice_mode_main_cli, ["connect", "status"])
        assert result.exit_code == 0
        assert "disabled" in result.output

    def test_shows_enabled_status(self, runner, connect_env):
        result = runner.invoke(voice_mode_main_cli, ["connect", "status"])
        assert result.exit_code == 0
        assert "VoiceMode Connect: enabled (not connected)" in result.output
        assert "Gateway: wss://voicemode.dev/ws" in result.output
        assert "Host: testhost" in result.output

    def test_shows_no_users_hint(self, runner, connect_env):
        result = runner.invoke(voice_mode_main_cli, ["connect", "status"])
        assert result.exit_code == 0
        assert "Users: (none)" in result.output
        assert "voicemode connect user add" in result.output

    def test_shows_users_when_present(self, runner, connect_env):
        # Add a user
        runner.invoke(
            voice_mode_main_cli,
            ["connect", "user", "add", "cora", "--name", "Cora 7"],
        )

        result = runner.invoke(voice_mode_main_cli, ["connect", "status"])
        assert result.exit_code == 0
        assert "Users:" in result.output
        assert "cora@testhost" in result.output

    def test_shows_connected_state(self, runner, connect_env, tmp_path, monkeypatch):
        # Create state file
        import voice_mode.connect.users as users_mod
        connect_dir = tmp_path / "connect"
        connect_dir.mkdir(exist_ok=True)
        monkeypatch.setattr(users_mod, "CONNECT_DIR", connect_dir)

        state_file = connect_dir / "state.json"
        state_file.write_text(json.dumps({
            "status": "up",
            "connected_since": "2026-02-17T10:00:00Z",
        }))

        result = runner.invoke(voice_mode_main_cli, ["connect", "status"])
        assert result.exit_code == 0
        assert "up" in result.output
        assert "2026-02-17T10:00:00Z" in result.output


class TestUpRemoved:
    """Verify connect up command has been removed (VM-824)."""

    def test_up_command_not_registered(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["connect", "up", "--help"])
        assert result.exit_code != 0


class TestDownRemoved:
    """Verify connect down command has been removed (VM-824)."""

    def test_down_command_not_registered(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["connect", "down", "--help"])
        assert result.exit_code != 0


class TestStandbyRemoved:
    def test_standby_command_removed(self, runner):
        """standby command should no longer exist (replaced by 'up')."""
        result = runner.invoke(voice_mode_main_cli, ["connect", "standby", "--help"])
        assert result.exit_code != 0
