"""Tests for VoiceMode Connect WebSocket client."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_mode.connect.client import ConnectClient, DeviceInfo, get_client
from voice_mode.connect.types import ConnectState
from voice_mode.connect.users import UserManager


@pytest.fixture
def user_manager(tmp_path):
    """Create a UserManager with a temporary directory."""
    users_dir = tmp_path / "users"
    users_dir.mkdir()
    return UserManager(host="test-host", users_dir=users_dir)


@pytest.fixture
def client(user_manager):
    """Create a ConnectClient for testing."""
    return ConnectClient(user_manager)


class TestDeviceInfo:
    def test_from_connection_info(self):
        data = {
            "sessionId": "abc123def456",
            "deviceId": "dev-1",
            "platform": "ios",
            "name": "iPhone",
            "capabilities": {"tts": True, "stt": True},
            "ready": True,
            "connectedAt": 1700000000000,
            "lastActivity": 1700000060000,
        }
        device = DeviceInfo.from_connection_info(data)

        assert device.session_id == "abc123def456"
        assert device.device_id == "dev-1"
        assert device.platform == "ios"
        assert device.name == "iPhone"
        assert device.capabilities == {"tts": True, "stt": True}
        assert device.ready is True
        assert device.connected_at == 1700000000000

    def test_from_connection_info_minimal(self):
        device = DeviceInfo.from_connection_info({})
        assert device.session_id == ""
        assert device.device_id is None
        assert device.platform is None
        assert device.ready is False
        assert device.capabilities == {}

    def test_display_name_with_name(self):
        device = DeviceInfo(session_id="abc", name="My Phone")
        assert device.display_name() == "My Phone"

    def test_display_name_with_platform(self):
        device = DeviceInfo(session_id="abc", platform="ios")
        assert device.display_name() == "Ios"

    def test_display_name_fallback(self):
        device = DeviceInfo(session_id="abc12345")
        assert device.display_name() == "Device abc12345"

    def test_capabilities_str(self):
        device = DeviceInfo(
            session_id="abc",
            capabilities={"tts": True, "stt": True, "mic": True, "speaker": True},
        )
        assert device.capabilities_str() == "TTS+STT+Mic+Speaker"

    def test_capabilities_str_partial(self):
        device = DeviceInfo(
            session_id="abc",
            capabilities={"tts": True, "stt": False},
        )
        assert device.capabilities_str() == "TTS"

    def test_capabilities_str_none(self):
        device = DeviceInfo(session_id="abc", capabilities={})
        assert device.capabilities_str() == "none"

    def test_activity_ago_unknown(self):
        device = DeviceInfo(session_id="abc", last_activity=0)
        assert device.activity_ago() == "unknown"


class TestConnectClientInit:
    def test_initial_state(self, client):
        assert client.state == ConnectState.DISCONNECTED
        assert client.is_connected is False
        assert client.is_connecting is False
        assert client.devices == []
        assert client.status_message == "Not initialized"
        assert client._session_id is None
        assert client._reconnect_count == 0

    def test_devices_returns_copy(self, client):
        client._devices = [DeviceInfo(session_id="a")]
        devices = client.devices
        assert len(devices) == 1
        devices.append(DeviceInfo(session_id="b"))
        assert len(client._devices) == 1  # Original unchanged

    def test_status_message_custom(self, client):
        client._status_message = "Custom status"
        assert client.status_message == "Custom status"

    def test_status_message_connected(self, client):
        client.state = ConnectState.CONNECTED
        assert client.status_message == "Connected"


class TestConnectClientConnect:
    @pytest.mark.asyncio
    async def test_connect_disabled(self, client):
        with patch("voice_mode.connect.client.connect_config") as mock_config:
            mock_config.is_enabled.return_value = False
            await client.connect()

        assert "Disabled" in client.status_message
        assert client._task is None

    @pytest.mark.asyncio
    async def test_connect_no_credentials(self, client):
        with (
            patch("voice_mode.connect.client.connect_config") as mock_config,
            patch("voice_mode.connect.client.asyncio") as mock_asyncio,
        ):
            mock_config.is_enabled.return_value = True
            mock_asyncio.to_thread = AsyncMock(return_value=None)
            await client.connect()

        assert "no credentials" in client.status_message

    @pytest.mark.asyncio
    async def test_connect_auth_error(self, client):
        with (
            patch("voice_mode.connect.client.connect_config") as mock_config,
            patch("voice_mode.connect.client.asyncio") as mock_asyncio,
        ):
            mock_config.is_enabled.return_value = True
            mock_asyncio.to_thread = AsyncMock(side_effect=Exception("auth failed"))
            await client.connect()

        assert "Auth error" in client.status_message

    @pytest.mark.asyncio
    async def test_connect_idempotent(self, client):
        """Calling connect when task is running should be a no-op."""
        mock_task = MagicMock()
        mock_task.done.return_value = False
        client._task = mock_task

        await client.connect()
        # Should not have replaced the task
        assert client._task is mock_task


class TestConnectClientDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_no_task(self, client):
        await client.disconnect()
        assert client.state == ConnectState.DISCONNECTED
        assert client._devices == []
        assert client._ws is None

    @pytest.mark.asyncio
    async def test_disconnect_cancels_task(self, client):
        cancelled = False

        async def fake_coro():
            nonlocal cancelled
            try:
                await asyncio.sleep(100)
            except asyncio.CancelledError:
                cancelled = True
                raise

        task = asyncio.create_task(fake_coro())
        # Let the task start
        await asyncio.sleep(0)
        client._task = task

        await client.disconnect()

        assert cancelled
        assert client.state == ConnectState.DISCONNECTED


class TestHandleMessage:
    @pytest.mark.asyncio
    async def test_devices_message(self, client):
        msg = {
            "type": "devices",
            "devices": [
                {"sessionId": "s1", "platform": "ios", "ready": True},
                {"sessionId": "s2", "platform": "web", "ready": False},
            ],
        }
        await client._handle_message(msg)

        assert len(client._devices) == 2
        assert client._devices[0].session_id == "s1"
        assert client._devices[0].platform == "ios"
        assert client._devices[1].session_id == "s2"

    @pytest.mark.asyncio
    async def test_heartbeat_ack_ignored(self, client):
        await client._handle_message({"type": "heartbeat_ack"})
        await client._handle_message({"type": "heartbeat"})
        # No error, no state change

    @pytest.mark.asyncio
    async def test_ack_ignored(self, client):
        await client._handle_message({"type": "ack"})

    @pytest.mark.asyncio
    async def test_error_message(self, client):
        msg = {"type": "error", "message": "rate limited", "code": "429"}
        await client._handle_message(msg)
        # Should log warning but not crash

    @pytest.mark.asyncio
    async def test_user_message_delivery(self, client, user_manager):
        user_manager.add("cora", display_name="Cora 7")

        msg = {
            "type": "user_message_delivery",
            "text": "Hey, are you there?",
            "from": "user-123",
            "userId": "user-abc123",
            "target_user": "cora",
        }
        await client._handle_message(msg)

        from voice_mode.connect.messaging import read_inbox

        messages = read_inbox(user_manager._user_dir("cora"))
        assert len(messages) == 1
        assert messages[0]["text"] == "Hey, are you there?"

    @pytest.mark.asyncio
    async def test_unhandled_message(self, client):
        await client._handle_message({"type": "unknown_type"})
        # Should log debug but not crash


class TestHandleUserMessageDelivery:
    @pytest.mark.asyncio
    async def test_routes_to_target_user(self, client, user_manager):
        user_manager.add("cora", display_name="Cora")
        user_manager.add("echo", display_name="Echo")

        data = {
            "text": "Hello Cora!",
            "from": "dashboard-user",
            "target_user": "cora",
        }
        await client._handle_user_message_delivery(data)

        from voice_mode.connect.messaging import read_inbox

        cora_msgs = read_inbox(user_manager._user_dir("cora"))
        echo_msgs = read_inbox(user_manager._user_dir("echo"))
        assert len(cora_msgs) == 1
        assert cora_msgs[0]["text"] == "Hello Cora!"
        assert cora_msgs[0]["from"] == "dashboard-user"
        assert len(echo_msgs) == 0

    @pytest.mark.asyncio
    async def test_falls_back_to_first_user(self, client, user_manager):
        user_manager.add("cora", display_name="Cora")

        data = {"text": "Hello!", "from": "user"}
        await client._handle_user_message_delivery(data)

        from voice_mode.connect.messaging import read_inbox

        messages = read_inbox(user_manager._user_dir("cora"))
        assert len(messages) == 1

    @pytest.mark.asyncio
    async def test_ignores_empty_text(self, client, user_manager):
        user_manager.add("cora")
        data = {"text": "   ", "from": "user"}
        await client._handle_user_message_delivery(data)

        from voice_mode.connect.messaging import read_inbox

        messages = read_inbox(user_manager._user_dir("cora"))
        assert len(messages) == 0

    @pytest.mark.asyncio
    async def test_no_user_found(self, client):
        data = {"text": "Hello!", "from": "user", "target_user": "nobody"}
        # Should not raise, just log warning
        await client._handle_user_message_delivery(data)

    @pytest.mark.asyncio
    async def test_message_source_is_gateway(self, client, user_manager):
        user_manager.add("cora")
        data = {"text": "test", "from": "user"}
        await client._handle_user_message_delivery(data)

        from voice_mode.connect.messaging import read_inbox

        messages = read_inbox(user_manager._user_dir("cora"))
        assert messages[0]["source"] == "gateway"


class TestCapabilitiesUpdate:
    @pytest.mark.asyncio
    async def test_sends_registered_user(self, client, user_manager):
        """capabilities_update only announces the registered primary user."""
        user = user_manager.add("cora", display_name="Cora 7")

        mock_ws = AsyncMock()
        client._ws = mock_ws
        client.state = ConnectState.CONNECTED
        client._primary_user = user  # Register as primary user

        await client.send_capabilities_update()

        mock_ws.send.assert_called_once()
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["type"] == "capabilities_update"
        assert len(sent["users"]) == 1
        assert sent["users"][0]["name"] == "cora"
        assert sent["users"][0]["display_name"] == "Cora 7"
        assert sent["users"][0]["host"] == "test-host"

    @pytest.mark.asyncio
    async def test_no_primary_user_sends_empty(self, client, user_manager):
        """Without a registered primary user, no users are announced."""
        user_manager.add("cora", display_name="Cora 7")

        mock_ws = AsyncMock()
        client._ws = mock_ws
        client.state = ConnectState.CONNECTED
        # No _primary_user set

        await client.send_capabilities_update()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["users"] == []

    @pytest.mark.asyncio
    async def test_platform_field(self, client, user_manager):
        """capabilities_update includes platform field."""
        user = user_manager.add("cora", display_name="Cora 7")

        mock_ws = AsyncMock()
        client._ws = mock_ws
        client.state = ConnectState.CONNECTED
        client._primary_user = user

        await client.send_capabilities_update()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["platform"] == "claude-code"
        assert "wakeable" not in sent
        assert "agentName" not in sent
        assert "agentPlatform" not in sent

    @pytest.mark.asyncio
    async def test_no_users_sends_empty_list(self, client):
        mock_ws = AsyncMock()
        client._ws = mock_ws
        client.state = ConnectState.CONNECTED

        await client.send_capabilities_update()

        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["users"] == []
        assert "wakeable" not in sent

    @pytest.mark.asyncio
    async def test_not_connected_noop(self, client):
        client.state = ConnectState.DISCONNECTED
        # Should not raise
        await client.send_capabilities_update()


class TestGetStatusText:
    def test_not_initialized(self, client):
        text = client.get_status_text()
        assert "VoiceMode Connect" in text
        assert "Not initialized" in text

    def test_connected_no_devices(self, client):
        client.state = ConnectState.CONNECTED
        client._status_message = "Connected"
        text = client.get_status_text()
        assert "Connected" in text
        assert "Remote Devices: none" in text

    def test_connected_with_devices(self, client):
        client.state = ConnectState.CONNECTED
        client._status_message = "Connected"
        client._devices = [
            DeviceInfo(session_id="s1", platform="ios", name="iPhone", ready=True),
        ]
        text = client.get_status_text()
        assert "iPhone" in text
        assert "ready" in text

    def test_filters_mcp_server_devices(self, client):
        client.state = ConnectState.CONNECTED
        client._status_message = "Connected"
        client._devices = [
            DeviceInfo(session_id="s1", platform="mcp-server"),
            DeviceInfo(session_id="s2", platform="ios", name="iPhone"),
        ]
        text = client.get_status_text()
        assert "iPhone" in text
        # mcp-server device should be filtered
        lines = text.split("\n")
        device_lines = [l for l in lines if l.strip().startswith("Device") or "mcp-server" in l.lower()]
        assert len(device_lines) == 0

    def test_shows_registered_users(self, client, user_manager):
        user_manager.add("cora", display_name="Cora 7")
        client.state = ConnectState.CONNECTED
        client._status_message = "Connected"
        text = client.get_status_text()
        assert "Cora 7" in text


class TestGetClient:
    def test_returns_singleton(self):
        import voice_mode.connect.client as client_module

        # Reset singleton
        client_module._client = None

        with patch.object(client_module.connect_config, "get_host", return_value="test"):
            c1 = get_client()
            c2 = get_client()

        assert c1 is c2

        # Cleanup
        client_module._client = None

    def test_creates_with_host(self):
        import voice_mode.connect.client as client_module

        client_module._client = None

        with patch.object(client_module.connect_config, "get_host", return_value="my-host"):
            c = get_client()

        assert c.user_manager.host == "my-host"

        # Cleanup
        client_module._client = None
