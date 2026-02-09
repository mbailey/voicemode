"""Tests for the VoiceMode Connect registry."""

import time

import pytest

from voice_mode.connect_registry import ConnectRegistry, DeviceInfo


class TestDeviceInfo:
    """Tests for DeviceInfo dataclass."""

    def test_from_connection_info_full(self):
        """Parse a full ConnectionInfo JSON payload."""
        data = {
            "sessionId": "abc123def456",
            "deviceId": "dev-iphone-xyz",
            "platform": "ios",
            "name": "Mike's iPhone",
            "capabilities": {"tts": True, "stt": True, "canStartOperator": False},
            "ready": True,
            "connectedAt": 1700000000000,
            "lastActivity": 1700000060000,
            "hasAgent": False,
            "agentStatus": None,
        }
        device = DeviceInfo.from_connection_info(data)

        assert device.session_id == "abc123def456"
        assert device.device_id == "dev-iphone-xyz"
        assert device.platform == "ios"
        assert device.name == "Mike's iPhone"
        assert device.capabilities == {"tts": True, "stt": True, "canStartOperator": False}
        assert device.ready is True
        assert device.connected_at == 1700000000000
        assert device.last_activity == 1700000060000
        assert device.has_agent is False
        assert device.agent_status is None

    def test_from_connection_info_minimal(self):
        """Parse a minimal ConnectionInfo with only sessionId."""
        data = {"sessionId": "sess-minimal"}
        device = DeviceInfo.from_connection_info(data)

        assert device.session_id == "sess-minimal"
        assert device.device_id is None
        assert device.platform is None
        assert device.name is None
        assert device.capabilities == {}
        assert device.ready is False

    def test_display_name_with_name(self):
        device = DeviceInfo(session_id="abc", name="My Phone")
        assert device.display_name() == "My Phone"

    def test_display_name_with_platform(self):
        device = DeviceInfo(session_id="abc", platform="ios")
        assert device.display_name() == "Ios"

    def test_display_name_fallback(self):
        device = DeviceInfo(session_id="abcdefgh1234")
        assert device.display_name() == "Device abcdefgh"

    def test_capabilities_str_all(self):
        device = DeviceInfo(
            session_id="abc",
            capabilities={"tts": True, "stt": True, "canStartOperator": True},
        )
        assert device.capabilities_str() == "TTS+STT+Wake"

    def test_capabilities_str_partial(self):
        device = DeviceInfo(session_id="abc", capabilities={"tts": True, "stt": False})
        assert device.capabilities_str() == "TTS"

    def test_capabilities_str_none(self):
        device = DeviceInfo(session_id="abc", capabilities={})
        assert device.capabilities_str() == "none"

    def test_activity_ago_just_now(self):
        device = DeviceInfo(session_id="abc", last_activity=time.time() * 1000)
        assert device.activity_ago() == "just now"

    def test_activity_ago_minutes(self):
        device = DeviceInfo(
            session_id="abc",
            last_activity=(time.time() - 300) * 1000,  # 5 minutes ago
        )
        assert device.activity_ago() == "5m ago"

    def test_activity_ago_unknown(self):
        device = DeviceInfo(session_id="abc", last_activity=0)
        assert device.activity_ago() == "unknown"


class TestConnectRegistry:
    """Tests for ConnectRegistry class."""

    def test_initial_state(self):
        """Registry starts uninitialized with no devices."""
        registry = ConnectRegistry()
        assert registry._initialized is False
        assert registry.devices == []
        assert registry.is_connected is False

    @pytest.mark.asyncio
    async def test_initialize_disabled(self, monkeypatch):
        """Initialize does nothing when CONNECT_AUTO_ENABLED is False."""
        monkeypatch.setattr("voice_mode.connect_registry.CONNECT_AUTO_ENABLED", False)
        registry = ConnectRegistry()
        await registry.initialize()

        assert registry._initialized is True
        assert registry.is_connected is False
        assert "Disabled" in registry.get_status_text()

    @pytest.mark.asyncio
    async def test_initialize_no_credentials(self, monkeypatch):
        """Initialize without credentials shows appropriate message."""
        monkeypatch.setattr("voice_mode.connect_registry.CONNECT_AUTO_ENABLED", True)

        async def fake_get_creds(*args, **kwargs):
            return None

        monkeypatch.setattr("asyncio.to_thread", lambda fn, *a, **kw: fake_get_creds())
        registry = ConnectRegistry()
        await registry.initialize()

        assert registry._initialized is True
        assert registry.is_connected is False
        assert "no credentials" in registry.get_status_text()

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self, monkeypatch):
        """Calling initialize() twice does not re-initialize."""
        monkeypatch.setattr("voice_mode.connect_registry.CONNECT_AUTO_ENABLED", False)
        registry = ConnectRegistry()
        await registry.initialize()
        await registry.initialize()  # Should be a no-op
        assert registry._initialized is True

    @pytest.mark.asyncio
    async def test_handle_connections_message(self):
        """Connections message replaces device list."""
        registry = ConnectRegistry()
        msg = {
            "type": "connections",
            "connections": [
                {
                    "sessionId": "sess-iphone",
                    "platform": "ios",
                    "name": "iPhone",
                    "capabilities": {"tts": True, "stt": True},
                    "ready": True,
                    "connectedAt": 1700000000000,
                    "lastActivity": int(time.time() * 1000),
                },
                {
                    "sessionId": "sess-web",
                    "platform": "web",
                    "name": "MacBook Pro",
                    "capabilities": {"tts": True, "stt": True},
                    "ready": True,
                    "connectedAt": 1700000000000,
                    "lastActivity": int(time.time() * 1000),
                },
            ],
            "timestamp": int(time.time() * 1000),
        }
        await registry._handle_message(msg)

        assert len(registry.devices) == 2
        assert registry.devices[0].name == "iPhone"
        assert registry.devices[1].name == "MacBook Pro"

    @pytest.mark.asyncio
    async def test_handle_connections_replaces_previous(self):
        """New connections message replaces previous device list."""
        registry = ConnectRegistry()

        # First message with 2 devices
        await registry._handle_message({
            "type": "connections",
            "connections": [
                {"sessionId": "a", "ready": True},
                {"sessionId": "b", "ready": True},
            ],
        })
        assert len(registry.devices) == 2

        # Second message with 1 device
        await registry._handle_message({
            "type": "connections",
            "connections": [{"sessionId": "c", "ready": True}],
        })
        assert len(registry.devices) == 1
        assert registry.devices[0].session_id == "c"

    @pytest.mark.asyncio
    async def test_handle_heartbeat_ack(self):
        """Heartbeat ack is handled without error."""
        registry = ConnectRegistry()
        await registry._handle_message({"type": "heartbeat_ack"})
        # No assertion needed - just should not raise

    @pytest.mark.asyncio
    async def test_handle_error_message(self):
        """Error messages are handled gracefully."""
        registry = ConnectRegistry()
        await registry._handle_message({
            "type": "error",
            "message": "Rate limited",
            "code": "rate_limit",
        })
        # Should not raise

    @pytest.mark.asyncio
    async def test_handle_unknown_message(self):
        """Unknown message types are handled gracefully."""
        registry = ConnectRegistry()
        await registry._handle_message({"type": "some_future_type", "data": "test"})
        # Should not raise

    def test_get_status_text_not_initialized(self):
        """Status text before initialization."""
        registry = ConnectRegistry()
        text = registry.get_status_text()
        assert "VoiceMode Connect" in text
        assert "Not initialized" in text

    def test_get_status_text_connected_with_devices(self):
        """Status text when connected with remote devices."""
        registry = ConnectRegistry()
        registry._connected = True
        registry._status_message = "Connected"
        registry._devices = [
            DeviceInfo(
                session_id="sess-1",
                platform="ios",
                name="iPhone",
                capabilities={"tts": True, "stt": True},
                ready=True,
                last_activity=time.time() * 1000,
            ),
            DeviceInfo(
                session_id="sess-2",
                platform="web",
                name="MacBook Pro",
                capabilities={"tts": True, "stt": True},
                ready=True,
                last_activity=time.time() * 1000,
            ),
        ]

        text = registry.get_status_text()
        assert "Connected" in text
        assert "iPhone (ios)" in text
        assert "MacBook Pro (web)" in text
        assert "TTS+STT" in text

    def test_get_status_text_connected_no_devices(self):
        """Status text when connected but no remote devices."""
        registry = ConnectRegistry()
        registry._connected = True
        registry._status_message = "Connected"
        registry._devices = []

        text = registry.get_status_text()
        assert "Connected" in text
        assert "none" in text

    def test_get_status_text_filters_own_connection(self):
        """Status text filters out our own mcp-server connection."""
        registry = ConnectRegistry()
        registry._connected = True
        registry._status_message = "Connected"
        registry._devices = [
            DeviceInfo(session_id="self", platform="mcp-server", ready=True),
            DeviceInfo(
                session_id="phone",
                platform="ios",
                name="iPhone",
                capabilities={"tts": True},
                ready=True,
                last_activity=time.time() * 1000,
            ),
        ]

        text = registry.get_status_text()
        assert "mcp-server" not in text
        assert "iPhone" in text

    @pytest.mark.asyncio
    async def test_shutdown(self):
        """Shutdown cleans up state."""
        registry = ConnectRegistry()
        registry._initialized = True
        registry._connected = True
        registry._devices = [DeviceInfo(session_id="test")]

        await registry.shutdown()

        assert registry._connected is False
        assert registry.devices == []
        assert registry._initialized is False
