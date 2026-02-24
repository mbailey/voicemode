"""Tests for VoiceMode Connect CLI commands."""

import json
from unittest.mock import AsyncMock, patch

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


@pytest.fixture
def mock_gateway_connected():
    """Mock _query_gateway_status returning a successful connection."""
    async def _mock_query(ws_url, access_token):
        return {
            "connected": True,
            "session_id": "abc123def456",
            "devices": [],
            "error": None,
        }
    with patch("voice_mode.cli._query_gateway_status", side_effect=_mock_query):
        yield


@pytest.fixture
def mock_gateway_unreachable():
    """Mock _query_gateway_status returning a connection failure."""
    async def _mock_query(ws_url, access_token):
        return {
            "connected": False,
            "session_id": "",
            "devices": [],
            "error": "Connection refused",
        }
    with patch("voice_mode.cli._query_gateway_status", side_effect=_mock_query):
        yield


@pytest.fixture
def mock_credentials(monkeypatch):
    """Mock get_valid_credentials to return a valid token."""
    from voice_mode.auth import Credentials
    creds = Credentials(
        access_token="test-token",
        refresh_token="test-refresh",
        expires_at=9999999999.0,
        token_type="Bearer",
    )
    with patch("voice_mode.auth.get_valid_credentials", return_value=creds):
        yield creds


class TestStatus:
    def test_shows_disabled_when_not_enabled(self, runner, monkeypatch):
        import voice_mode.config as config_mod
        monkeypatch.setattr(config_mod, "CONNECT_ENABLED", False)

        result = runner.invoke(voice_mode_main_cli, ["connect", "status"])
        assert result.exit_code == 0
        assert "disabled" in result.output

    def test_shows_gateway_connected(self, runner, connect_env, mock_credentials, mock_gateway_connected):
        result = runner.invoke(voice_mode_main_cli, ["connect", "status"])
        assert result.exit_code == 0
        assert "connected" in result.output
        assert "abc123def456" in result.output
        assert "Gateway: wss://voicemode.dev/ws" in result.output
        assert "Host: testhost" in result.output

    def test_shows_no_users_hint(self, runner, connect_env, mock_credentials, mock_gateway_connected):
        result = runner.invoke(voice_mode_main_cli, ["connect", "status"])
        assert result.exit_code == 0
        assert "Users: (none)" in result.output
        assert "voicemode connect user add" in result.output

    def test_shows_users_when_present(self, runner, connect_env, mock_credentials, mock_gateway_connected):
        # Add a user
        runner.invoke(
            voice_mode_main_cli,
            ["connect", "user", "add", "cora", "--name", "Cora 7"],
        )

        result = runner.invoke(voice_mode_main_cli, ["connect", "status"])
        assert result.exit_code == 0
        assert "Users:" in result.output
        assert "cora@testhost" in result.output

    def test_shows_devices_from_gateway(self, runner, connect_env, mock_credentials):
        """Displays remote devices returned by the gateway."""
        async def _mock_query(ws_url, access_token):
            return {
                "connected": True,
                "session_id": "sess123",
                "devices": [
                    {
                        "sessionId": "dev-001",
                        "platform": "ios",
                        "name": "iPhone",
                        "capabilities": {"tts": True, "stt": True, "mic": True},
                        "ready": True,
                        "connectedAt": 1700000000000,
                        "lastActivity": 1700000000000,
                    },
                ],
                "error": None,
            }
        with patch("voice_mode.cli._query_gateway_status", side_effect=_mock_query):
            result = runner.invoke(voice_mode_main_cli, ["connect", "status"])

        assert result.exit_code == 0
        assert "Devices:" in result.output
        assert "iPhone" in result.output
        assert "ios" in result.output
        assert "ready" in result.output

    def test_falls_back_to_local_state(self, runner, connect_env, tmp_path, monkeypatch, mock_credentials, mock_gateway_unreachable):
        """Falls back to local filesystem when gateway is unreachable."""
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
        assert "gateway unreachable" in result.output
        assert "Falling back to local" in result.output
        assert "up" in result.output
        assert "2026-02-17T10:00:00Z" in result.output

    def test_falls_back_without_credentials(self, runner, connect_env, tmp_path, monkeypatch):
        """Falls back to local state when no credentials are available."""
        with patch("voice_mode.auth.get_valid_credentials", return_value=None):
            result = runner.invoke(voice_mode_main_cli, ["connect", "status"])

        assert result.exit_code == 0
        assert "gateway unreachable" in result.output
        assert "no credentials" in result.output


class TestQueryGatewayStatus:
    """Tests for the _query_gateway_status async function."""

    @pytest.mark.asyncio
    async def test_returns_connected_with_session_id(self):
        """Successful connection returns session_id from gateway."""
        from voice_mode.cli import _query_gateway_status

        mock_ws = AsyncMock()
        # First recv: connected message
        # Second recv: devices message
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"type": "connected", "sessionId": "sess-abcdef123456"}),
            json.dumps({"type": "devices", "devices": []}),
        ])
        mock_ws.send = AsyncMock()

        mock_connect = AsyncMock()
        mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect.__aexit__ = AsyncMock(return_value=False)

        with patch("websockets.connect", return_value=mock_connect):
            result = await _query_gateway_status("wss://test.dev/ws", "test-token")

        assert result["connected"] is True
        assert result["session_id"] == "sess-abcdef1"  # truncated to 12 chars
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_returns_devices_from_gateway(self):
        """Devices from gateway are included in the result."""
        from voice_mode.cli import _query_gateway_status

        device_data = [
            {"sessionId": "dev-1", "platform": "ios", "name": "iPhone", "ready": True},
        ]

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"type": "connected", "sessionId": "sess-123"}),
            json.dumps({"type": "devices", "devices": device_data}),
        ])
        mock_ws.send = AsyncMock()

        mock_connect = AsyncMock()
        mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect.__aexit__ = AsyncMock(return_value=False)

        with patch("websockets.connect", return_value=mock_connect):
            result = await _query_gateway_status("wss://test.dev/ws", "test-token")

        assert result["connected"] is True
        assert len(result["devices"]) == 1
        assert result["devices"][0]["name"] == "iPhone"

    @pytest.mark.asyncio
    async def test_handles_connection_error(self):
        """Returns error dict when WebSocket connection fails."""
        from voice_mode.cli import _query_gateway_status

        with patch("websockets.connect", side_effect=ConnectionRefusedError("refused")):
            result = await _query_gateway_status("wss://test.dev/ws", "test-token")

        assert result["connected"] is False
        assert "refused" in result["error"]

    @pytest.mark.asyncio
    async def test_handles_unexpected_first_message(self):
        """Returns error when gateway sends unexpected first message."""
        from voice_mode.cli import _query_gateway_status

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(return_value=json.dumps({"type": "error", "message": "bad auth"}))

        mock_connect = AsyncMock()
        mock_connect.__aenter__ = AsyncMock(return_value=mock_ws)
        mock_connect.__aexit__ = AsyncMock(return_value=False)

        with patch("websockets.connect", return_value=mock_connect):
            result = await _query_gateway_status("wss://test.dev/ws", "bad-token")

        assert result["connected"] is False
        assert "Unexpected first message" in result["error"]

    @pytest.mark.asyncio
    async def test_handles_missing_websockets_package(self):
        """Returns error when websockets is not installed."""
        import sys
        from voice_mode.cli import _query_gateway_status

        # Temporarily remove websockets from sys.modules to simulate missing package
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        def mock_import(name, *args, **kwargs):
            if name == "websockets":
                raise ImportError("No module named 'websockets'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = await _query_gateway_status("wss://test.dev/ws", "token")

        assert result["connected"] is False
        assert "websockets" in result["error"].lower()


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
