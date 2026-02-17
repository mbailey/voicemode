"""Tests for voice_mode.connect.types."""

from datetime import datetime

from voice_mode.connect.types import (
    ConnectState,
    InboxMessage,
    Presence,
    UserInfo,
)


class TestPresence:
    def test_values(self):
        assert Presence.AVAILABLE.value == "available"
        assert Presence.ONLINE.value == "online"
        assert Presence.OFFLINE.value == "offline"

    def test_all_members(self):
        assert set(Presence) == {Presence.AVAILABLE, Presence.ONLINE, Presence.OFFLINE}


class TestConnectState:
    def test_values(self):
        assert ConnectState.DISCONNECTED.value == "disconnected"
        assert ConnectState.CONNECTING.value == "connecting"
        assert ConnectState.CONNECTED.value == "connected"
        assert ConnectState.RECONNECTING.value == "reconnecting"

    def test_all_members(self):
        assert set(ConnectState) == {
            ConnectState.DISCONNECTED,
            ConnectState.CONNECTING,
            ConnectState.CONNECTED,
            ConnectState.RECONNECTING,
        }


class TestUserInfo:
    def test_address_with_host(self):
        user = UserInfo(name="cora", host="mikes-mbp")
        assert user.address == "cora@mikes-mbp"

    def test_address_without_host(self):
        user = UserInfo(name="cora")
        assert user.address == "cora"

    def test_defaults(self):
        user = UserInfo(name="test")
        assert user.display_name == ""
        assert user.host == ""
        assert user.presence == Presence.OFFLINE
        assert user.subscribed_team is None
        assert user.created is None
        assert user.last_seen is None


class TestInboxMessage:
    def test_defaults(self):
        now = datetime.now()
        msg = InboxMessage(id="msg-1", sender="user", text="hello", timestamp=now)
        assert msg.source == "dashboard"
        assert msg.delivered is False

    def test_all_fields(self):
        now = datetime.now()
        msg = InboxMessage(
            id="msg-2",
            sender="agent:cora",
            text="hi there",
            timestamp=now,
            source="api",
            delivered=True,
        )
        assert msg.id == "msg-2"
        assert msg.sender == "agent:cora"
        assert msg.text == "hi there"
        assert msg.timestamp == now
        assert msg.source == "api"
        assert msg.delivered is True
