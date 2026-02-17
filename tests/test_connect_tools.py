"""Tests for VoiceMode Connect MCP tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from voice_mode.connect.types import UserInfo, Presence

# Access the underlying async functions via .fn (MCP tool wrapper)
from voice_mode.tools.connect import (
    connect_inbox as connect_inbox_tool,
    connect_status as connect_status_tool,
    connect_user_add as connect_user_add_tool,
    connect_user_remove as connect_user_remove_tool,
    register_wakeable as register_wakeable_tool,
    unregister_wakeable as unregister_wakeable_tool,
)

connect_inbox = connect_inbox_tool.fn
connect_status = connect_status_tool.fn
connect_user_add = connect_user_add_tool.fn
connect_user_remove = connect_user_remove_tool.fn
register_wakeable = register_wakeable_tool.fn
unregister_wakeable = unregister_wakeable_tool.fn


# Helpers

def _make_user(name="test", display_name="Test User", host="localhost"):
    return UserInfo(
        name=name,
        display_name=display_name,
        host=host,
        presence=Presence.OFFLINE,
    )


def _mock_client(users=None):
    """Create a mock ConnectClient with user_manager."""
    client = AsyncMock()
    client.user_manager = MagicMock()
    client.user_manager.list.return_value = users or []
    client.user_manager.get.return_value = None
    client.user_manager.add.return_value = _make_user()
    client.user_manager.remove.return_value = True
    client.user_manager._user_dir.return_value = "/tmp/test-user"
    # get_status_text is a sync method, override the AsyncMock default
    client.get_status_text = MagicMock(
        return_value="VoiceMode Connect:\n  Status: Connected"
    )
    return client


# Patches applied to every test

PATCH_ENABLED = "voice_mode.tools.connect.connect_config.is_enabled"
PATCH_CLIENT = "voice_mode.tools.connect.get_client"
PATCH_INBOX = "voice_mode.tools.connect.read_inbox"


# --- connect_user_add ---


@pytest.mark.asyncio
async def test_connect_user_add():
    """Creating a user returns confirmation."""
    client = _mock_client()
    with patch(PATCH_ENABLED, return_value=True), patch(PATCH_CLIENT, return_value=client):
        result = await connect_user_add(name="cora")

    client.user_manager.add.assert_called_once_with("cora", display_name="", subscribe_team=None)
    client.register_user.assert_awaited_once()
    assert "cora" in result


@pytest.mark.asyncio
async def test_connect_user_add_with_subscribe():
    """Creating a user with subscribe_team includes team in result."""
    client = _mock_client()
    with patch(PATCH_ENABLED, return_value=True), patch(PATCH_CLIENT, return_value=client):
        result = await connect_user_add(name="cora", display_name="Cora 7", subscribe_team="my-team")

    client.user_manager.add.assert_called_once_with("cora", display_name="Cora 7", subscribe_team="my-team")
    assert "my-team" in result
    assert "Cora 7" in result


@pytest.mark.asyncio
async def test_connect_user_add_disabled():
    """Adding user when Connect is disabled returns error."""
    with patch(PATCH_ENABLED, return_value=False):
        result = await connect_user_add(name="cora")

    assert "not enabled" in result.lower()


# --- connect_user_remove ---


@pytest.mark.asyncio
async def test_connect_user_remove():
    """Removing an existing user returns confirmation."""
    client = _mock_client()
    client.user_manager.remove.return_value = True
    with patch(PATCH_ENABLED, return_value=True), patch(PATCH_CLIENT, return_value=client):
        result = await connect_user_remove(name="cora")

    client.user_manager.remove.assert_called_once_with("cora")
    client.unregister_user.assert_awaited_once_with("cora")
    assert "cora" in result


@pytest.mark.asyncio
async def test_connect_user_remove_nonexistent():
    """Removing a nonexistent user returns not-found message."""
    client = _mock_client()
    client.user_manager.remove.return_value = False
    with patch(PATCH_ENABLED, return_value=True), patch(PATCH_CLIENT, return_value=client):
        result = await connect_user_remove(name="nope")

    assert "not found" in result.lower()


# --- connect_status ---


@pytest.mark.asyncio
async def test_connect_status():
    """Status returns client status text."""
    client = _mock_client()
    with patch(PATCH_ENABLED, return_value=True), patch(PATCH_CLIENT, return_value=client):
        result = await connect_status()

    assert "Connected" in result


@pytest.mark.asyncio
async def test_connect_status_disabled():
    """Status when disabled returns error."""
    with patch(PATCH_ENABLED, return_value=False):
        result = await connect_status()

    assert "not enabled" in result.lower()


# --- connect_inbox ---


@pytest.mark.asyncio
async def test_connect_inbox():
    """Reading inbox returns formatted messages."""
    user = _make_user(name="cora")
    client = _mock_client(users=[user])
    client.user_manager.get.return_value = user

    messages = [
        {"from": "user", "text": "Hello!", "timestamp": "2026-01-01T00:00:00Z"},
        {"from": "user", "text": "How are you?", "timestamp": "2026-01-01T00:01:00Z"},
    ]

    with (
        patch(PATCH_ENABLED, return_value=True),
        patch(PATCH_CLIENT, return_value=client),
        patch(PATCH_INBOX, return_value=messages),
    ):
        result = await connect_inbox(name="cora", limit=10)

    assert "Hello!" in result
    assert "How are you?" in result
    assert "2 message" in result


@pytest.mark.asyncio
async def test_connect_inbox_empty():
    """Empty inbox returns appropriate message."""
    user = _make_user(name="cora")
    client = _mock_client(users=[user])
    client.user_manager.get.return_value = user

    with (
        patch(PATCH_ENABLED, return_value=True),
        patch(PATCH_CLIENT, return_value=client),
        patch(PATCH_INBOX, return_value=[]),
    ):
        result = await connect_inbox(name="cora")

    assert "empty" in result.lower()


@pytest.mark.asyncio
async def test_connect_inbox_default_user():
    """Inbox without name uses first registered user."""
    user = _make_user(name="first")
    client = _mock_client(users=[user])
    client.user_manager.get.return_value = user

    with (
        patch(PATCH_ENABLED, return_value=True),
        patch(PATCH_CLIENT, return_value=client),
        patch(PATCH_INBOX, return_value=[]),
    ):
        result = await connect_inbox()

    # Should have used "first" as the user name
    client.user_manager._user_dir.assert_called_with("first")


# --- register_wakeable (backward compat) ---


@pytest.mark.asyncio
async def test_register_wakeable():
    """register_wakeable delegates to connect_user_add."""
    client = _mock_client()
    with patch(PATCH_ENABLED, return_value=True), patch(PATCH_CLIENT, return_value=client):
        result = await register_wakeable(team_name="my-team", agent_name="Cora")

    client.user_manager.add.assert_called_once_with(
        "my-team", display_name="Cora", subscribe_team="my-team"
    )
    assert "my-team" in result


# --- unregister_wakeable (backward compat) ---


@pytest.mark.asyncio
async def test_unregister_wakeable():
    """unregister_wakeable removes all users."""
    user = _make_user(name="team1")
    client = _mock_client(users=[user])
    with patch(PATCH_ENABLED, return_value=True), patch(PATCH_CLIENT, return_value=client):
        result = await unregister_wakeable()

    client.user_manager.remove.assert_called_once_with("team1")
    client.unregister_user.assert_awaited_once_with("team1")
    assert "unregistered" in result.lower()


@pytest.mark.asyncio
async def test_unregister_wakeable_no_users():
    """unregister_wakeable with no users returns message."""
    client = _mock_client(users=[])
    with patch(PATCH_ENABLED, return_value=True), patch(PATCH_CLIENT, return_value=client):
        result = await unregister_wakeable()

    assert "no users" in result.lower()
