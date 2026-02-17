"""Tests for VoiceMode Connect message delivery."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from voice_mode.connect.messaging import (
    deliver_message,
    read_inbox,
    _write_persistent_inbox,
    _write_live_inbox,
)


@pytest.fixture
def user_dir(tmp_path):
    """Create a temporary user directory with empty inbox."""
    d = tmp_path / "users" / "cora"
    d.mkdir(parents=True)
    (d / "inbox").touch()
    return d


class TestDeliverMessage:
    def test_creates_jsonl_entry(self, user_dir):
        result = deliver_message(user_dir, "hello", sender="user", source="dashboard")

        inbox = user_dir / "inbox"
        lines = inbox.read_text().strip().splitlines()
        assert len(lines) == 1

        msg = json.loads(lines[0])
        assert msg["text"] == "hello"
        assert msg["from"] == "user"
        assert msg["source"] == "dashboard"
        assert "id" in msg
        assert "timestamp" in msg

    def test_appends_to_existing_inbox(self, user_dir):
        deliver_message(user_dir, "first")
        deliver_message(user_dir, "second")
        deliver_message(user_dir, "third")

        inbox = user_dir / "inbox"
        lines = [l for l in inbox.read_text().strip().splitlines() if l.strip()]
        assert len(lines) == 3

        texts = [json.loads(l)["text"] for l in lines]
        assert texts == ["first", "second", "third"]

    def test_writes_to_live_inbox(self, user_dir, tmp_path):
        # Set up a live inbox symlink
        live_target_dir = tmp_path / "teams" / "test-team" / "inboxes"
        live_target_dir.mkdir(parents=True)
        live_target = live_target_dir / "team-lead.json"

        symlink = user_dir / "inbox-live"
        symlink.symlink_to(live_target)

        result = deliver_message(user_dir, "hello from web")

        assert result["delivered"] is True

        # Check live inbox has correct format
        content = json.loads(live_target.read_text())
        assert isinstance(content, list)
        assert len(content) == 1
        assert content[0]["role"] == "user"
        assert "hello from web" in content[0]["content"]

    def test_works_without_symlink(self, user_dir):
        result = deliver_message(user_dir, "hello")

        assert result["delivered"] is False
        # Message should still be in persistent inbox
        inbox = user_dir / "inbox"
        assert inbox.read_text().strip() != ""

    def test_custom_message_id(self, user_dir):
        result = deliver_message(user_dir, "hello", message_id="custom-123")
        assert result["id"] == "custom-123"

    def test_delivery_confirmation_appended(self, user_dir, tmp_path):
        # Set up live inbox
        live_target_dir = tmp_path / "teams" / "test-team" / "inboxes"
        live_target_dir.mkdir(parents=True)
        live_target = live_target_dir / "team-lead.json"
        symlink = user_dir / "inbox-live"
        symlink.symlink_to(live_target)

        deliver_message(user_dir, "hello")

        # Should have message + delivery confirmation in persistent inbox
        inbox = user_dir / "inbox"
        lines = [l for l in inbox.read_text().strip().splitlines() if l.strip()]
        assert len(lines) == 2

        confirmation = json.loads(lines[1])
        assert confirmation["type"] == "delivery_confirmation"
        assert confirmation["delivered"] is True


class TestReadInbox:
    def test_reads_messages(self, user_dir):
        deliver_message(user_dir, "hello")
        deliver_message(user_dir, "world")

        messages = read_inbox(user_dir)

        assert len(messages) == 2
        assert messages[0]["text"] == "hello"
        assert messages[1]["text"] == "world"

    def test_filters_by_since(self, user_dir):
        # Write messages with known timestamps
        now = datetime.now(timezone.utc)
        past = now - timedelta(hours=2)
        recent = now - timedelta(minutes=5)

        inbox = user_dir / "inbox"
        inbox.write_text("")  # Clear

        # Old message
        _write_persistent_inbox(inbox, {
            "id": "old",
            "text": "old message",
            "from": "user",
            "timestamp": past.isoformat(),
            "source": "test",
        })
        # Recent message
        _write_persistent_inbox(inbox, {
            "id": "new",
            "text": "new message",
            "from": "user",
            "timestamp": now.isoformat(),
            "source": "test",
        })

        cutoff = now - timedelta(hours=1)
        messages = read_inbox(user_dir, since=cutoff)

        assert len(messages) == 1
        assert messages[0]["text"] == "new message"

    def test_respects_limit(self, user_dir):
        for i in range(10):
            deliver_message(user_dir, f"message {i}")

        messages = read_inbox(user_dir, limit=3)

        assert len(messages) == 3
        # Should be the most recent 3
        assert messages[0]["text"] == "message 7"
        assert messages[1]["text"] == "message 8"
        assert messages[2]["text"] == "message 9"

    def test_skips_delivery_confirmations(self, user_dir, tmp_path):
        # Set up live inbox so delivery confirmations are written
        live_target_dir = tmp_path / "teams" / "test-team" / "inboxes"
        live_target_dir.mkdir(parents=True)
        live_target = live_target_dir / "team-lead.json"
        symlink = user_dir / "inbox-live"
        symlink.symlink_to(live_target)

        deliver_message(user_dir, "hello")

        messages = read_inbox(user_dir)
        # Should only see the actual message, not the delivery confirmation
        assert len(messages) == 1
        assert messages[0]["text"] == "hello"

    def test_handles_empty_inbox(self, user_dir):
        messages = read_inbox(user_dir)
        assert messages == []

    def test_handles_missing_inbox(self, tmp_path):
        nonexistent = tmp_path / "no-such-user"
        nonexistent.mkdir()
        messages = read_inbox(nonexistent)
        assert messages == []


class TestWritePersistentInbox:
    def test_creates_file_if_missing(self, tmp_path):
        inbox = tmp_path / "new_user" / "inbox"
        message = {"id": "test", "text": "hello", "timestamp": "2024-01-01T00:00:00+00:00"}

        _write_persistent_inbox(inbox, message)

        assert inbox.exists()
        content = inbox.read_text().strip()
        assert json.loads(content) == message

    def test_appends_to_existing(self, tmp_path):
        inbox = tmp_path / "inbox"
        inbox.write_text('{"id":"1","text":"first"}\n')

        _write_persistent_inbox(inbox, {"id": "2", "text": "second"})

        lines = inbox.read_text().strip().splitlines()
        assert len(lines) == 2


class TestWriteLiveInbox:
    def test_creates_json_array(self, tmp_path):
        target = tmp_path / "team-lead.json"
        symlink = tmp_path / "inbox-live"
        symlink.symlink_to(target)

        now = datetime.now(timezone.utc)
        result = _write_live_inbox(symlink, "hello", "user", "dashboard", now)

        assert result is True
        content = json.loads(target.read_text())
        assert isinstance(content, list)
        assert len(content) == 1
        assert content[0]["role"] == "user"
        assert "[VoiceMode Connect]" in content[0]["content"]
        assert "hello" in content[0]["content"]

    def test_appends_to_existing_array(self, tmp_path):
        target = tmp_path / "team-lead.json"
        target.write_text('[{"role":"user","content":"existing","timestamp":"2024-01-01T00:00:00+00:00"}]\n')

        symlink = tmp_path / "inbox-live"
        symlink.symlink_to(target)

        now = datetime.now(timezone.utc)
        _write_live_inbox(symlink, "new message", "user", "api", now)

        content = json.loads(target.read_text())
        assert len(content) == 2
        assert content[0]["content"] == "existing"
        assert "new message" in content[1]["content"]

    def test_returns_false_when_target_dir_missing(self, tmp_path):
        target = tmp_path / "nonexistent" / "team-lead.json"
        symlink = tmp_path / "inbox-live"
        symlink.symlink_to(target)

        now = datetime.now(timezone.utc)
        result = _write_live_inbox(symlink, "hello", "user", "dashboard", now)
        assert result is False
