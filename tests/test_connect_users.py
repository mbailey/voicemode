"""Tests for VoiceMode Connect user/mailbox management."""

import json
import time
from pathlib import Path

import pytest

from voice_mode.connect.types import Presence, UserInfo
from voice_mode.connect.users import UserManager


@pytest.fixture
def users_dir(tmp_path):
    """Create a temporary users directory."""
    d = tmp_path / "users"
    d.mkdir()
    return d


@pytest.fixture
def teams_dir(tmp_path):
    """Create a temporary Claude teams directory."""
    d = tmp_path / "claude" / "teams"
    d.mkdir(parents=True)
    return d


@pytest.fixture
def manager(users_dir):
    """Create a UserManager with temporary directory."""
    return UserManager(host="localhost", users_dir=users_dir)


class TestAdd:
    def test_creates_directory_and_meta(self, manager, users_dir):
        user = manager.add("cora", display_name="Cora 7")

        user_dir = users_dir / "cora"
        assert user_dir.is_dir()

        meta_path = user_dir / "meta.json"
        assert meta_path.exists()

        meta = json.loads(meta_path.read_text())
        assert meta["name"] == "cora"
        assert meta["display_name"] == "Cora 7"
        assert meta["host"] == "localhost"
        assert "created" in meta
        assert "last_seen" in meta

    def test_creates_empty_inbox(self, manager, users_dir):
        manager.add("cora")

        inbox_path = users_dir / "cora" / "inbox"
        assert inbox_path.exists()
        assert inbox_path.read_text() == ""

    def test_returns_user_info(self, manager):
        user = manager.add("cora", display_name="Cora 7")

        assert isinstance(user, UserInfo)
        assert user.name == "cora"
        assert user.display_name == "Cora 7"
        assert user.host == "localhost"
        assert user.presence == Presence.OFFLINE
        assert user.created is not None
        assert user.last_seen is not None

    def test_with_subscribe_team(self, manager, users_dir, teams_dir, monkeypatch):
        import voice_mode.connect.users as users_mod
        monkeypatch.setattr(users_mod, "CLAUDE_TEAMS_DIR", teams_dir)

        user = manager.add("cora", subscribe_team="my-team")

        symlink = users_dir / "cora" / "inbox-live"
        assert symlink.is_symlink()
        assert user.subscribed_team == "my-team"


class TestRemove:
    def test_removes_user_directory(self, manager, users_dir):
        manager.add("cora")
        assert (users_dir / "cora").exists()

        result = manager.remove("cora")

        assert result is True
        assert not (users_dir / "cora").exists()

    def test_returns_false_for_nonexistent(self, manager):
        result = manager.remove("nobody")
        assert result is False


class TestList:
    def test_returns_all_users(self, manager):
        manager.add("alice")
        manager.add("bob")
        manager.add("charlie")

        users = manager.list()
        names = [u.name for u in users]

        assert len(users) == 3
        assert "alice" in names
        assert "bob" in names
        assert "charlie" in names

    def test_returns_empty_when_no_users(self, manager):
        users = manager.list()
        assert users == []

    def test_returns_empty_when_dir_missing(self, tmp_path):
        mgr = UserManager(host="localhost", users_dir=tmp_path / "nonexistent")
        users = mgr.list()
        assert users == []


class TestGet:
    def test_returns_user_info(self, manager):
        manager.add("cora", display_name="Cora 7")

        user = manager.get("cora")

        assert user is not None
        assert user.name == "cora"
        assert user.display_name == "Cora 7"
        assert user.host == "localhost"
        assert user.presence == Presence.OFFLINE

    def test_returns_none_for_nonexistent(self, manager):
        user = manager.get("nobody")
        assert user is None

    def test_detects_subscribed_team(self, manager, users_dir, teams_dir, monkeypatch):
        import voice_mode.connect.users as users_mod
        monkeypatch.setattr(users_mod, "CLAUDE_TEAMS_DIR", teams_dir)

        manager.add("cora", subscribe_team="my-team")

        user = manager.get("cora")
        assert user is not None
        assert user.subscribed_team == "my-team"


class TestSubscribe:
    def test_creates_symlink(self, manager, users_dir, teams_dir, monkeypatch):
        import voice_mode.connect.users as users_mod
        monkeypatch.setattr(users_mod, "CLAUDE_TEAMS_DIR", teams_dir)

        manager.add("cora")
        result = manager.subscribe("cora", "my-team")

        assert result.is_symlink()
        target = result.readlink()
        assert "my-team" in str(target)
        assert "team-lead.json" in str(target)

    def test_creates_target_parent_dir(self, manager, users_dir, teams_dir, monkeypatch):
        import voice_mode.connect.users as users_mod
        monkeypatch.setattr(users_mod, "CLAUDE_TEAMS_DIR", teams_dir)

        manager.add("cora")
        manager.subscribe("cora", "my-team")

        inboxes_dir = teams_dir / "my-team" / "inboxes"
        assert inboxes_dir.is_dir()

    def test_replaces_stale_symlink(self, manager, users_dir, teams_dir, monkeypatch):
        import voice_mode.connect.users as users_mod
        monkeypatch.setattr(users_mod, "CLAUDE_TEAMS_DIR", teams_dir)

        manager.add("cora")

        # Create symlink to old team
        manager.subscribe("cora", "old-team")
        symlink = users_dir / "cora" / "inbox-live"
        assert "old-team" in str(symlink.readlink())

        # Subscribe to new team — should replace
        manager.subscribe("cora", "new-team")
        assert "new-team" in str(symlink.readlink())

    def test_handles_unexpected_file(self, manager, users_dir, teams_dir, monkeypatch):
        import voice_mode.connect.users as users_mod
        monkeypatch.setattr(users_mod, "CLAUDE_TEAMS_DIR", teams_dir)

        manager.add("cora")

        # Create a regular file at the symlink path
        inbox_live = users_dir / "cora" / "inbox-live"
        inbox_live.write_text("unexpected content")

        # Subscribe should rename the file and create symlink
        result = manager.subscribe("cora", "my-team")
        assert result.is_symlink()

        # Check stale file was renamed
        stale_files = list((users_dir / "cora").glob("inbox-live.stale-*"))
        assert len(stale_files) == 1
        assert stale_files[0].read_text() == "unexpected content"

    def test_noops_when_already_correct(self, manager, users_dir, teams_dir, monkeypatch):
        import voice_mode.connect.users as users_mod
        monkeypatch.setattr(users_mod, "CLAUDE_TEAMS_DIR", teams_dir)

        manager.add("cora")
        manager.subscribe("cora", "my-team")

        symlink = users_dir / "cora" / "inbox-live"
        original_target = symlink.readlink()

        # Subscribe again — should not recreate
        result = manager.subscribe("cora", "my-team")
        assert result.is_symlink()
        assert symlink.readlink() == original_target


class TestUnsubscribe:
    def test_removes_symlink(self, manager, users_dir, teams_dir, monkeypatch):
        import voice_mode.connect.users as users_mod
        monkeypatch.setattr(users_mod, "CLAUDE_TEAMS_DIR", teams_dir)

        manager.add("cora", subscribe_team="my-team")

        result = manager.unsubscribe("cora")
        assert result is True
        assert not (users_dir / "cora" / "inbox-live").exists()

    def test_returns_false_when_not_subscribed(self, manager):
        manager.add("cora")
        result = manager.unsubscribe("cora")
        assert result is False


class TestIsSubscribed:
    def test_true_when_subscribed(self, manager, teams_dir, monkeypatch):
        import voice_mode.connect.users as users_mod
        monkeypatch.setattr(users_mod, "CLAUDE_TEAMS_DIR", teams_dir)

        manager.add("cora", subscribe_team="my-team")
        assert manager.is_subscribed("cora") is True

    def test_false_when_not_subscribed(self, manager):
        manager.add("cora")
        assert manager.is_subscribed("cora") is False

    def test_false_when_user_missing(self, manager):
        assert manager.is_subscribed("nobody") is False


class TestGetPresence:
    def test_offline_when_user_missing(self, manager):
        assert manager.get_presence("nobody") == Presence.OFFLINE

    def test_online_when_not_subscribed(self, manager):
        manager.add("cora")
        assert manager.get_presence("cora") == Presence.ONLINE

    def test_available_when_subscribed(self, manager, teams_dir, monkeypatch):
        import voice_mode.connect.users as users_mod
        monkeypatch.setattr(users_mod, "CLAUDE_TEAMS_DIR", teams_dir)

        manager.add("cora", subscribe_team="my-team")
        assert manager.get_presence("cora") == Presence.AVAILABLE
