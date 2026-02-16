"""Tests for the VoiceMode messaging library."""

import json
from pathlib import Path

import pytest

from voice_mode.messaging import deliver_message, setup_live_inbox


class TestDeliverMessage:
    """Tests for deliver_message function."""

    def test_creates_agent_dir_and_inbox_file(self, tmp_path, monkeypatch):
        """Creates agent directory and inbox file when they don't exist."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)

        deliver_message("Cora 7", "Hello world")

        agent_dir = agents_dir / "Cora 7"
        assert agent_dir.exists()
        inbox_file = agent_dir / "inbox"
        assert inbox_file.exists()

    def test_writes_correct_json_format(self, tmp_path, monkeypatch):
        """Writes correct JSON array with all required fields."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)

        deliver_message("Cora 7", "Hello world", sender="mike")

        inbox_file = agents_dir / "Cora 7" / "inbox"
        messages = json.loads(inbox_file.read_text())

        assert isinstance(messages, list)
        assert len(messages) == 1
        msg = messages[0]
        assert msg["from"] == "mike"
        assert msg["text"] == "Hello world"
        assert msg["read"] is False
        assert "timestamp" in msg
        assert "summary" in msg

    def test_appends_to_existing_inbox(self, tmp_path, monkeypatch):
        """Appends to existing inbox maintaining valid JSON array."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)

        deliver_message("Cora 7", "First message")
        deliver_message("Cora 7", "Second message")

        inbox_file = agents_dir / "Cora 7" / "inbox"
        messages = json.loads(inbox_file.read_text())

        assert len(messages) == 2
        assert messages[0]["text"] == "First message"
        assert messages[1]["text"] == "Second message"

    def test_auto_generates_summary_from_text(self, tmp_path, monkeypatch):
        """Auto-generates summary from first 50 chars when not provided."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)

        long_text = "A" * 100
        deliver_message("Cora 7", long_text)

        inbox_file = agents_dir / "Cora 7" / "inbox"
        messages = json.loads(inbox_file.read_text())

        # Summary should be truncated to ~50 chars
        assert len(messages[0]["summary"]) <= 53  # 50 chars + "..."

    def test_uses_provided_summary(self, tmp_path, monkeypatch):
        """Uses provided summary when given."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)

        deliver_message("Cora 7", "Hello world", summary="Custom summary")

        inbox_file = agents_dir / "Cora 7" / "inbox"
        messages = json.loads(inbox_file.read_text())

        assert messages[0]["summary"] == "Custom summary"

    def test_default_sender_is_user(self, tmp_path, monkeypatch):
        """Default sender is 'user' when not specified."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)

        deliver_message("Cora 7", "Hello")

        inbox_file = agents_dir / "Cora 7" / "inbox"
        messages = json.loads(inbox_file.read_text())

        assert messages[0]["from"] == "user"

    def test_writes_to_live_inbox_symlink(self, tmp_path, monkeypatch):
        """Writes to live-inbox symlink target when symlink exists and resolves."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)

        # Set up the live-inbox symlink target directory and file
        live_inbox_target = tmp_path / "live-inbox-target.json"
        live_inbox_target.write_text("[]")

        agent_dir = agents_dir / "Cora 7"
        agent_dir.mkdir(parents=True)
        live_inbox = agent_dir / "live-inbox"
        live_inbox.symlink_to(live_inbox_target)

        deliver_message("Cora 7", "Hello via live inbox")

        # Check that live-inbox target was written to
        live_messages = json.loads(live_inbox_target.read_text())
        assert len(live_messages) == 1
        assert live_messages[0]["text"] == "Hello via live inbox"

    def test_skips_live_inbox_when_no_symlink(self, tmp_path, monkeypatch):
        """Only writes to inbox when live-inbox symlink doesn't exist."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)

        deliver_message("Cora 7", "Hello")

        # Regular inbox should exist
        inbox_file = agents_dir / "Cora 7" / "inbox"
        assert inbox_file.exists()

        # live-inbox should not exist
        live_inbox = agents_dir / "Cora 7" / "live-inbox"
        assert not live_inbox.exists()

    def test_skips_broken_live_inbox_symlink(self, tmp_path, monkeypatch):
        """Skips live-inbox gracefully when symlink is broken."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)

        # Create a broken symlink
        agent_dir = agents_dir / "Cora 7"
        agent_dir.mkdir(parents=True)
        live_inbox = agent_dir / "live-inbox"
        live_inbox.symlink_to(tmp_path / "nonexistent-target.json")

        # Should not raise
        result = deliver_message("Cora 7", "Hello with broken symlink")

        # Regular inbox should still work
        inbox_file = agent_dir / "inbox"
        assert inbox_file.exists()
        messages = json.loads(inbox_file.read_text())
        assert len(messages) == 1

    def test_returns_delivery_status(self, tmp_path, monkeypatch):
        """Returns correct delivery status dict."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)

        result = deliver_message("Cora 7", "Hello")

        assert isinstance(result, dict)
        assert "delivered_to" in result
        assert "agent_name" in result
        assert result["agent_name"] == "Cora 7"
        assert isinstance(result["delivered_to"], list)
        assert len(result["delivered_to"]) >= 1  # at least inbox


class TestSetupLiveInbox:
    """Tests for setup_live_inbox function."""

    def test_creates_symlink(self, tmp_path, monkeypatch):
        """Creates symlink at ~/.voicemode/agents/{agent}/live-inbox."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)
        monkeypatch.setattr("voice_mode.messaging.Path.home", lambda: tmp_path)

        setup_live_inbox("Cora 7", "cora")

        live_inbox = agents_dir / "Cora 7" / "live-inbox"
        assert live_inbox.is_symlink()

    def test_creates_parent_directories(self, tmp_path, monkeypatch):
        """Creates parent directories if they don't exist."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)
        monkeypatch.setattr("voice_mode.messaging.Path.home", lambda: tmp_path)

        setup_live_inbox("Cora 7", "cora")

        agent_dir = agents_dir / "Cora 7"
        assert agent_dir.exists()

    def test_replaces_existing_symlink(self, tmp_path, monkeypatch):
        """Replaces existing symlink."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)
        monkeypatch.setattr("voice_mode.messaging.Path.home", lambda: tmp_path)

        # Create initial symlink pointing to old target
        agent_dir = agents_dir / "Cora 7"
        agent_dir.mkdir(parents=True)
        live_inbox = agent_dir / "live-inbox"
        old_target = tmp_path / "old-target.json"
        live_inbox.symlink_to(old_target)

        # Setup should replace with new symlink
        setup_live_inbox("Cora 7", "new-team")

        # Symlink should point to the new target
        expected_target = tmp_path / ".claude" / "teams" / "new-team" / "inboxes" / "team-lead.json"
        assert live_inbox.is_symlink()
        assert live_inbox.readlink() == expected_target

    def test_default_recipient_is_team_lead(self, tmp_path, monkeypatch):
        """Default recipient is 'team-lead'."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)
        monkeypatch.setattr("voice_mode.messaging.Path.home", lambda: tmp_path)

        setup_live_inbox("Cora 7", "cora")

        live_inbox = agents_dir / "Cora 7" / "live-inbox"
        target = live_inbox.readlink()
        assert str(target).endswith("team-lead.json")

    def test_symlink_target_path(self, tmp_path, monkeypatch):
        """Symlink target is ~/.claude/teams/{team}/inboxes/{recipient}.json."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)
        monkeypatch.setattr("voice_mode.messaging.Path.home", lambda: tmp_path)

        setup_live_inbox("Cora 7", "cora", recipient="researcher")

        live_inbox = agents_dir / "Cora 7" / "live-inbox"
        target = live_inbox.readlink()
        expected = tmp_path / ".claude" / "teams" / "cora" / "inboxes" / "researcher.json"
        assert target == expected

    def test_returns_symlink_path(self, tmp_path, monkeypatch):
        """Returns the symlink path."""
        agents_dir = tmp_path / ".voicemode" / "agents"
        monkeypatch.setattr("voice_mode.messaging.AGENTS_DIR", agents_dir)
        monkeypatch.setattr("voice_mode.messaging.Path.home", lambda: tmp_path)

        result = setup_live_inbox("Cora 7", "cora")

        assert isinstance(result, Path)
        expected = agents_dir / "Cora 7" / "live-inbox"
        assert result == expected
