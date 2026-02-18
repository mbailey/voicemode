"""Tests for VoiceMode Connect file-watcher."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from voice_mode.connect.types import ConnectState
from voice_mode.connect.users import UserManager
from voice_mode.connect.watcher import diff_user_state, watch_user_changes


@pytest.fixture
def user_manager(tmp_path):
    """Create a UserManager with a temporary directory."""
    users_dir = tmp_path / "users"
    users_dir.mkdir()
    return UserManager(host="test-host", users_dir=users_dir)


class TestSnapshot:
    def test_empty_users(self, user_manager):
        state = user_manager.snapshot()
        assert state == {}

    def test_user_without_symlink(self, user_manager):
        user_manager.add("cora", display_name="Cora 7")
        state = user_manager.snapshot()
        assert "cora" in state
        assert state["cora"]["display_name"] == "Cora 7"
        assert state["cora"]["symlink_target"] is None
        assert state["cora"]["subscribed"] is False

    def test_user_with_symlink(self, user_manager, tmp_path):
        user_manager.add("cora", display_name="Cora 7")

        # Create a fake team inbox target
        team_dir = tmp_path / "teams" / "my-team" / "inboxes"
        team_dir.mkdir(parents=True)
        target = team_dir / "team-lead.json"
        target.touch()

        # Subscribe (creates symlink)
        user_manager.subscribe("cora", "my-team")

        # Patch CLAUDE_TEAMS_DIR for the subscribe call
        import voice_mode.connect.users as users_mod
        original_dir = users_mod.CLAUDE_TEAMS_DIR
        users_mod.CLAUDE_TEAMS_DIR = tmp_path / "teams"
        try:
            user_manager.subscribe("cora", "my-team")
            state = user_manager.snapshot()
            assert state["cora"]["subscribed"] is True
            assert state["cora"]["symlink_target"] is not None
        finally:
            users_mod.CLAUDE_TEAMS_DIR = original_dir

    def test_multiple_users(self, user_manager):
        user_manager.add("cora", display_name="Cora 7")
        user_manager.add("echo", display_name="Echo")
        state = user_manager.snapshot()
        assert len(state) == 2
        assert "cora" in state
        assert "echo" in state


class TestDiffUserState:
    def test_no_changes(self):
        state = {"cora": {"display_name": "Cora", "symlink_target": None, "subscribed": False}}
        changes = diff_user_state(state, state)
        assert changes == []

    def test_user_added(self):
        prev = {}
        curr = {"cora": {"display_name": "Cora", "symlink_target": None, "subscribed": False}}
        changes = diff_user_state(prev, curr)
        assert len(changes) == 1
        assert changes[0] == ("added", "cora", None)

    def test_user_removed(self):
        prev = {"cora": {"display_name": "Cora", "symlink_target": None, "subscribed": False}}
        curr = {}
        changes = diff_user_state(prev, curr)
        assert len(changes) == 1
        assert changes[0] == ("removed", "cora", None)

    def test_user_subscribed(self):
        prev = {"cora": {"display_name": "Cora", "symlink_target": None, "subscribed": False}}
        curr = {"cora": {"display_name": "Cora", "symlink_target": "/path/to/inbox", "subscribed": True}}
        changes = diff_user_state(prev, curr)
        assert len(changes) == 1
        assert changes[0] == ("subscribed", "cora", None)

    def test_user_unsubscribed(self):
        prev = {"cora": {"display_name": "Cora", "symlink_target": "/path/to/inbox", "subscribed": True}}
        curr = {"cora": {"display_name": "Cora", "symlink_target": None, "subscribed": False}}
        changes = diff_user_state(prev, curr)
        assert len(changes) == 1
        assert changes[0] == ("unsubscribed", "cora", None)

    def test_display_name_changed(self):
        prev = {"cora": {"display_name": "Cora 6", "symlink_target": None, "subscribed": False}}
        curr = {"cora": {"display_name": "Cora 7", "symlink_target": None, "subscribed": False}}
        changes = diff_user_state(prev, curr)
        assert len(changes) == 1
        assert changes[0] == ("changed", "cora", None)

    def test_multiple_changes(self):
        prev = {
            "cora": {"display_name": "Cora", "symlink_target": None, "subscribed": False},
            "old-user": {"display_name": "Old", "symlink_target": None, "subscribed": False},
        }
        curr = {
            "cora": {"display_name": "Cora", "symlink_target": "/path", "subscribed": True},
            "new-user": {"display_name": "New", "symlink_target": None, "subscribed": False},
        }
        changes = diff_user_state(prev, curr)
        types = {(c[0], c[1]) for c in changes}
        assert ("subscribed", "cora") in types
        assert ("removed", "old-user") in types
        assert ("added", "new-user") in types

    def test_symlink_target_changed(self):
        prev = {"cora": {"display_name": "Cora", "symlink_target": "/old/path", "subscribed": True}}
        curr = {"cora": {"display_name": "Cora", "symlink_target": "/new/path", "subscribed": True}}
        changes = diff_user_state(prev, curr)
        assert len(changes) == 1
        assert changes[0] == ("changed", "cora", None)


class TestWatchUserChanges:
    @pytest.mark.asyncio
    async def test_detects_new_user(self, user_manager):
        """Watcher detects when a new user is added."""
        mock_client = MagicMock()
        mock_client.is_connected = True
        mock_client.send_capabilities_update = AsyncMock()

        messages = []

        async def run_watcher():
            await watch_user_changes(
                mock_client, user_manager,
                poll_interval=0.1,
                echo=lambda msg: messages.append(msg),
            )

        task = asyncio.create_task(run_watcher())

        # Wait for first poll
        await asyncio.sleep(0.15)

        # Add a user while watcher is running
        user_manager.add("cora", display_name="Cora 7")

        # Wait for detection
        await asyncio.sleep(0.25)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should have detected the addition
        assert any("User added: cora" in m for m in messages)
        mock_client.send_capabilities_update.assert_called()

    @pytest.mark.asyncio
    async def test_no_change_no_announce(self, user_manager):
        """Watcher does not announce when nothing changes."""
        mock_client = MagicMock()
        mock_client.is_connected = True
        mock_client.send_capabilities_update = AsyncMock()

        task = asyncio.create_task(
            watch_user_changes(mock_client, user_manager, poll_interval=0.1)
        )

        await asyncio.sleep(0.35)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should NOT have called capabilities_update
        mock_client.send_capabilities_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_announce_when_disconnected(self, user_manager):
        """Watcher detects changes but doesn't announce when disconnected."""
        mock_client = MagicMock()
        mock_client.is_connected = False
        mock_client.send_capabilities_update = AsyncMock()

        messages = []

        task = asyncio.create_task(
            watch_user_changes(
                mock_client, user_manager,
                poll_interval=0.1,
                echo=lambda msg: messages.append(msg),
            )
        )

        await asyncio.sleep(0.15)
        user_manager.add("cora")
        await asyncio.sleep(0.25)

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Detected but not announced
        assert any("User added: cora" in m for m in messages)
        mock_client.send_capabilities_update.assert_not_called()
