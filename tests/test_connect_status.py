"""Tests for voice_mode.tools.connect_status."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from voice_mode.connect.types import UserInfo
from voice_mode.tools.connect_status import connect_status as connect_status_tool

# FastMCP 2.x wraps tools as FunctionTool (with .fn attribute),
# FastMCP 3.x returns the raw function.
_connect_status_fn = getattr(connect_status_tool, "fn", connect_status_tool)


def _make_user(name="cora", display_name="Cora 7", host="test-host"):
    return UserInfo(name=name, display_name=display_name, host=host)


@pytest.fixture
def mock_client():
    """Create a mock ConnectClient."""
    client = MagicMock()
    client.is_connected = True
    client.is_connecting = False
    client.connect = AsyncMock()
    client._primary_user = None
    client._ws = AsyncMock()
    client.user_manager = MagicMock()
    client.get_status_text.return_value = "VoiceMode Connect: Connected"
    client.register_user = AsyncMock()
    return client


class TestConnectStatusDisabled:
    @pytest.mark.asyncio
    async def test_returns_disabled_message(self):
        """connect_status returns helpful message when Connect is disabled."""
        with patch(
            "voice_mode.connect.config.is_enabled", return_value=False
        ):
            result = await _connect_status_fn()

        assert "VoiceMode Connect is disabled" in result
        assert "VOICEMODE_CONNECT_ENABLED=true" in result


class TestConnectStatusNotConnected:
    @pytest.mark.asyncio
    async def test_triggers_connect_when_disconnected(self, mock_client):
        """connect_status calls client.connect() when not connected."""
        mock_client.is_connected = False
        mock_client.is_connecting = False

        with (
            patch(
                "voice_mode.connect.config.is_enabled", return_value=True
            ),
            patch(
                "voice_mode.connect.client.get_client",
                return_value=mock_client,
            ),
        ):
            await _connect_status_fn()

        mock_client.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_status_text_when_no_presence(self, mock_client):
        """connect_status returns status text when set_presence is not given."""
        with (
            patch(
                "voice_mode.connect.config.is_enabled", return_value=True
            ),
            patch(
                "voice_mode.connect.client.get_client",
                return_value=mock_client,
            ),
        ):
            result = await _connect_status_fn()

        assert result == "VoiceMode Connect: Connected"
        mock_client.get_status_text.assert_called_once()


class TestSetPresenceValidation:
    @pytest.mark.asyncio
    async def test_invalid_presence_rejected(self, mock_client):
        """Invalid presence values return an error message."""
        from voice_mode.tools.connect_status import _set_presence

        result = await _set_presence(mock_client, "invisible")
        assert "Invalid presence" in result
        assert "'invisible'" in result
        assert "available" in result
        assert "away" in result

    @pytest.mark.asyncio
    async def test_random_string_rejected(self, mock_client):
        from voice_mode.tools.connect_status import _set_presence

        result = await _set_presence(mock_client, "online")
        assert "Invalid presence" in result

    @pytest.mark.asyncio
    async def test_not_connected_returns_error(self, mock_client):
        """Cannot set presence when disconnected."""
        from voice_mode.tools.connect_status import _set_presence

        mock_client.is_connected = False
        result = await _set_presence(mock_client, "available")
        assert "Not connected" in result
        assert "Cannot set presence" in result


class TestAliasMapping:
    @pytest.mark.asyncio
    async def test_busy_maps_to_away(self, mock_client):
        """'busy' alias maps to 'away'."""
        from voice_mode.tools.connect_status import _set_presence

        user = _make_user()
        with patch(
            "voice_mode.tools.connect_status._ensure_user_registered",
            new_callable=AsyncMock,
            return_value=[user],
        ):
            mock_client.user_manager.is_subscribed.return_value = True
            result = await _set_presence(mock_client, "busy")

        assert "Away" in result

    @pytest.mark.asyncio
    async def test_dnd_maps_to_away(self, mock_client):
        """'dnd' alias maps to 'away'."""
        from voice_mode.tools.connect_status import _set_presence

        user = _make_user()
        with patch(
            "voice_mode.tools.connect_status._ensure_user_registered",
            new_callable=AsyncMock,
            return_value=[user],
        ):
            mock_client.user_manager.is_subscribed.return_value = True
            result = await _set_presence(mock_client, "dnd")

        assert "Away" in result

    @pytest.mark.asyncio
    async def test_unavailable_maps_to_away(self, mock_client):
        """'unavailable' alias maps to 'away'."""
        from voice_mode.tools.connect_status import _set_presence

        user = _make_user()
        with patch(
            "voice_mode.tools.connect_status._ensure_user_registered",
            new_callable=AsyncMock,
            return_value=[user],
        ):
            mock_client.user_manager.is_subscribed.return_value = True
            result = await _set_presence(mock_client, "unavailable")

        assert "Away" in result


class TestEnsureUserRegistered:
    @pytest.mark.asyncio
    async def test_already_registered_returns_existing(self, mock_client):
        """Returns existing user when already registered."""
        from voice_mode.tools.connect_status import _ensure_user_registered

        user = _make_user()
        mock_client._primary_user = user
        mock_client.user_manager.get.return_value = user

        result = await _ensure_user_registered(mock_client)
        assert result == [user]
        mock_client.register_user.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_explicit_username_finds_existing(self, mock_client):
        """With username, finds existing user and registers on WebSocket."""
        from voice_mode.tools.connect_status import _ensure_user_registered

        user = _make_user()
        mock_client.user_manager.get.return_value = user

        result = await _ensure_user_registered(mock_client, username="cora")
        assert result == [user]
        mock_client.register_user.assert_awaited_once_with(user)

    @pytest.mark.asyncio
    async def test_explicit_username_creates_when_missing(self, mock_client):
        """With username, creates user when not found on filesystem."""
        from voice_mode.tools.connect_status import _ensure_user_registered

        new_user = _make_user(name="newbot", display_name="NewBot")
        mock_client.user_manager.get.return_value = None
        mock_client.user_manager.add.return_value = new_user

        with patch(
            "voice_mode.connect.config.get_agent_name",
            return_value="NewBot",
        ):
            result = await _ensure_user_registered(
                mock_client, username="newbot"
            )

        mock_client.user_manager.add.assert_called_once_with(
            name="newbot", display_name="NewBot"
        )
        mock_client.register_user.assert_awaited_once_with(new_user)
        assert result == [new_user]

    @pytest.mark.asyncio
    async def test_explicit_username_normalizes_case(self, mock_client):
        """Username is lowered and stripped."""
        from voice_mode.tools.connect_status import _ensure_user_registered

        user = _make_user()
        mock_client.user_manager.get.return_value = user

        await _ensure_user_registered(mock_client, username="  CORA  ")
        mock_client.user_manager.get.assert_called_with("cora")

    @pytest.mark.asyncio
    async def test_auto_discover_users(self, mock_client):
        """Without username, discovers users from filesystem."""
        from voice_mode.tools.connect_status import _ensure_user_registered

        user = _make_user()
        mock_client.user_manager.list.return_value = [user]

        result = await _ensure_user_registered(mock_client)
        assert result == [user]
        mock_client.register_user.assert_awaited_once_with(user)

    @pytest.mark.asyncio
    async def test_preconfigured_users_fallback(self, mock_client):
        """Falls back to preconfigured users when no subscribed users."""
        from voice_mode.tools.connect_status import _ensure_user_registered

        user = _make_user(name="alice")
        mock_client.user_manager.list.return_value = []
        mock_client.user_manager.get.return_value = user

        with patch(
            "voice_mode.connect.config.get_preconfigured_users",
            return_value=["alice"],
        ):
            result = await _ensure_user_registered(mock_client)

        assert result == [user]
        mock_client.register_user.assert_awaited_once_with(user)

    @pytest.mark.asyncio
    async def test_no_users_found_returns_empty(self, mock_client):
        """Returns empty list when no users found anywhere."""
        from voice_mode.tools.connect_status import _ensure_user_registered

        mock_client.user_manager.list.return_value = []

        with patch(
            "voice_mode.connect.config.get_preconfigured_users",
            return_value=[],
        ):
            result = await _ensure_user_registered(mock_client)

        assert result == []
        mock_client.register_user.assert_not_awaited()


class TestSetPresenceMissingUser:
    @pytest.mark.asyncio
    async def test_no_users_returns_error(self, mock_client):
        """Returns error when no users can be found."""
        from voice_mode.tools.connect_status import _set_presence

        with patch(
            "voice_mode.tools.connect_status._ensure_user_registered",
            new_callable=AsyncMock,
            return_value=[],
        ):
            result = await _set_presence(mock_client, "available")

        assert "No Connect users found" in result


class TestSetPresenceAvailable:
    @pytest.mark.asyncio
    async def test_available_succeeds_without_subscription(self, mock_client):
        """Going 'available' works without inbox-live symlink (no Teams dependency)."""
        from voice_mode.tools.connect_status import _set_presence

        user = _make_user()

        with patch(
            "voice_mode.tools.connect_status._ensure_user_registered",
            new_callable=AsyncMock,
            return_value=[user],
        ):
            result = await _set_presence(mock_client, "available")

        assert "Now Available" in result
        mock_client._ws.send.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_available_sends_capabilities_update(self, mock_client):
        """Going 'available' sends correct WebSocket message."""
        from voice_mode.tools.connect_status import _set_presence

        user = _make_user()
        mock_client.user_manager.is_subscribed.return_value = True

        with patch(
            "voice_mode.tools.connect_status._ensure_user_registered",
            new_callable=AsyncMock,
            return_value=[user],
        ):
            result = await _set_presence(mock_client, "available")

        mock_client._ws.send.assert_awaited_once()
        sent = json.loads(mock_client._ws.send.call_args[0][0])
        assert sent["type"] == "capabilities_update"
        assert sent["platform"] == "claude-code"
        assert len(sent["users"]) == 1
        assert sent["users"][0]["name"] == "cora"
        assert sent["users"][0]["presence"] == "available"
        assert "Now Available" in result

    @pytest.mark.asyncio
    async def test_available_includes_display_names(self, mock_client):
        """Available response lists user display names."""
        from voice_mode.tools.connect_status import _set_presence

        user = _make_user(display_name="Cora 7")
        mock_client.user_manager.is_subscribed.return_value = True

        with patch(
            "voice_mode.tools.connect_status._ensure_user_registered",
            new_callable=AsyncMock,
            return_value=[user],
        ):
            result = await _set_presence(mock_client, "available")

        assert "Cora 7" in result


class TestSetPresenceAway:
    @pytest.mark.asyncio
    async def test_away_sends_online_wire_presence(self, mock_client):
        """'away' maps to 'online' on the wire protocol."""
        from voice_mode.tools.connect_status import _set_presence

        user = _make_user()
        mock_client.user_manager.is_subscribed.return_value = True

        with patch(
            "voice_mode.tools.connect_status._ensure_user_registered",
            new_callable=AsyncMock,
            return_value=[user],
        ):
            result = await _set_presence(mock_client, "away")

        sent = json.loads(mock_client._ws.send.call_args[0][0])
        assert sent["users"][0]["presence"] == "online"
        assert "Now Away" in result

    @pytest.mark.asyncio
    async def test_away_does_not_check_subscription(self, mock_client):
        """'away' does not require inbox-live subscription."""
        from voice_mode.tools.connect_status import _set_presence

        user = _make_user()

        with patch(
            "voice_mode.tools.connect_status._ensure_user_registered",
            new_callable=AsyncMock,
            return_value=[user],
        ):
            result = await _set_presence(mock_client, "away")

        # is_subscribed should NOT have been checked for away
        mock_client.user_manager.is_subscribed.assert_not_called()
        assert "Now Away" in result


class TestSetPresenceWebSocketError:
    @pytest.mark.asyncio
    async def test_ws_send_failure(self, mock_client):
        """WebSocket send failure returns error message."""
        from voice_mode.tools.connect_status import _set_presence

        user = _make_user()
        mock_client.user_manager.is_subscribed.return_value = True
        mock_client._ws.send.side_effect = Exception("Connection lost")

        with patch(
            "voice_mode.tools.connect_status._ensure_user_registered",
            new_callable=AsyncMock,
            return_value=[user],
        ):
            result = await _set_presence(mock_client, "available")

        assert "Failed to set presence" in result
        assert "Connection lost" in result


class TestSetPresenceMultipleUsers:
    @pytest.mark.asyncio
    async def test_multiple_users_all_included(self, mock_client):
        """All users are included in the capabilities_update."""
        from voice_mode.tools.connect_status import _set_presence

        users = [
            _make_user(name="cora", display_name="Cora 7"),
            _make_user(name="echo", display_name="Echo"),
        ]
        mock_client.user_manager.is_subscribed.return_value = True

        with patch(
            "voice_mode.tools.connect_status._ensure_user_registered",
            new_callable=AsyncMock,
            return_value=users,
        ):
            result = await _set_presence(mock_client, "available")

        sent = json.loads(mock_client._ws.send.call_args[0][0])
        assert len(sent["users"]) == 2
        names = {u["name"] for u in sent["users"]}
        assert names == {"cora", "echo"}
        assert "Cora 7" in result
        assert "Echo" in result
