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


class TestUp:
    def test_up_help(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["connect", "up", "--help"])
        assert result.exit_code == 0
        assert "Bring up connection" in result.output
        assert "voicemode connect up" in result.output

    def test_up_requires_connect_enabled(self, runner, monkeypatch):
        import voice_mode.config as config_mod
        monkeypatch.setattr(config_mod, "CONNECT_ENABLED", False)

        result = runner.invoke(voice_mode_main_cli, ["connect", "up"])
        assert result.exit_code != 0
        assert "not enabled" in result.output

    def test_up_requires_credentials(self, runner, connect_env, monkeypatch):
        """up should fail gracefully when not logged in."""
        monkeypatch.setattr(
            "voice_mode.auth.get_valid_credentials",
            lambda auto_refresh=False: None,
        )
        result = runner.invoke(voice_mode_main_cli, ["connect", "up"])
        assert result.exit_code != 0
        assert "Not logged in" in result.output


class TestDown:
    def test_down_help(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["connect", "down", "--help"])
        assert result.exit_code == 0
        assert "Disconnect" in result.output

    def test_down_no_process_running(self, runner, connect_env, tmp_path, monkeypatch):
        """down should report when no process is running."""
        import voice_mode.connect.users as users_mod
        connect_dir = tmp_path / "connect"
        connect_dir.mkdir(exist_ok=True)
        monkeypatch.setattr(users_mod, "CONNECT_DIR", connect_dir)

        result = runner.invoke(voice_mode_main_cli, ["connect", "down"])
        assert result.exit_code == 0
        assert "No connect process running" in result.output

    def test_down_stale_pid(self, runner, connect_env, tmp_path, monkeypatch):
        """down should clean up stale PID file for dead process."""
        import voice_mode.connect.users as users_mod
        connect_dir = tmp_path / "connect"
        connect_dir.mkdir(exist_ok=True)
        monkeypatch.setattr(users_mod, "CONNECT_DIR", connect_dir)

        # Write a PID that doesn't exist (use a very high PID)
        pid_file = connect_dir / "pid"
        pid_file.write_text("999999999")

        result = runner.invoke(voice_mode_main_cli, ["connect", "down"])
        assert result.exit_code == 0
        assert "not running" in result.output
        # PID file should be cleaned up
        assert not pid_file.exists()


class TestStandbyAlias:
    def test_standby_still_works(self, runner):
        """standby command should still exist (hidden, deprecated)."""
        result = runner.invoke(voice_mode_main_cli, ["connect", "standby", "--help"])
        assert result.exit_code == 0
        assert "Deprecated" in result.output or "deprecated" in result.output
