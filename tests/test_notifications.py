"""Tests for VM-613: Pluggable notification system."""

import json
from unittest.mock import patch

import pytest

from voice_mode.notifications import (
    parse_source_output,
    _format_for_level,
    NotificationManager,
    get_notification_manager,
    ensure_default_config,
    NOTIFICATIONS_CONFIG_PATH,
    _notification_manager,
)
from voice_mode.notifications.check_inbox import (
    check_inbox_messages,
    load_watermarks,
    save_watermarks,
    read_new_messages,
)


# ============================================================================
# parse_source_output tests
# ============================================================================


class TestParseSourceOutput:
    """Tests for parse_source_output() — Postel's Law parsing cascade."""

    def test_json_with_count(self):
        """JSON object with count field — richest format."""
        stdout = '{"count": 3}'
        result = parse_source_output("test", stdout)
        assert result is not None
        assert result["count"] == 3
        assert result["display"] == "3 from test"

    def test_json_with_all_levels(self):
        """JSON with count, summary, and detail fields."""
        data = {
            "count": 3,
            "summary": "3 messages (2 from Astrid, 1 from Mike)",
            "detail": [
                {"from": "Astrid", "count": 2, "text": "Car update"},
                {"from": "Mike", "count": 1, "text": "PR approved"},
            ],
        }
        stdout = json.dumps(data)

        # Count level — uses count field
        result = parse_source_output("test", stdout, level="count")
        assert result["display"] == "3 from test"

        # Summary level — uses summary field
        result = parse_source_output("test", stdout, level="summary")
        assert result["display"] == "3 messages (2 from Astrid, 1 from Mike)"

        # Detail level — uses detail field
        result = parse_source_output("test", stdout, level="detail")
        assert "Astrid: Car update" in result["display"]
        assert "Mike: PR approved" in result["display"]

    def test_json_zero_count(self):
        """JSON with count=0 returns None."""
        stdout = '{"count": 0}'
        result = parse_source_output("test", stdout)
        assert result is None

    def test_plain_integer(self):
        """Plain integer output — simple count."""
        result = parse_source_output("github", "5")
        assert result is not None
        assert result["count"] == 5
        assert result["display"] == "5 from github"

    def test_plain_zero(self):
        """Plain integer zero returns None."""
        result = parse_source_output("test", "0")
        assert result is None

    def test_leading_number_with_text(self):
        """Leading number followed by text — '3 messages'."""
        result = parse_source_output("test", "3 messages")
        assert result is not None
        assert result["count"] == 3
        assert result["display"] == "3 messages"

    def test_leading_number_zero(self):
        """Leading number zero returns None."""
        result = parse_source_output("test", "0 notifications")
        assert result is None

    def test_leading_number_with_description(self):
        """Leading number with longer description."""
        result = parse_source_output("ntfy", "17 unread notifications")
        assert result["count"] == 17
        assert result["display"] == "17 unread notifications"

    def test_empty_string(self):
        """Empty output returns None."""
        result = parse_source_output("test", "")
        assert result is None

    def test_whitespace_only(self):
        """Whitespace-only output returns None."""
        result = parse_source_output("test", "   \n  ")
        assert result is None

    def test_garbage_output(self):
        """Unparseable garbage output returns None."""
        result = parse_source_output("test", "error: something broke")
        assert result is None

    def test_json_with_whitespace(self):
        """JSON with surrounding whitespace still parses."""
        stdout = '  {"count": 2}  \n'
        result = parse_source_output("test", stdout)
        assert result is not None
        assert result["count"] == 2

    def test_detail_caps_at_three(self):
        """Detail level caps items at 3 and shows +N more."""
        data = {
            "count": 5,
            "detail": [
                {"from": "A", "text": "msg1"},
                {"from": "B", "text": "msg2"},
                {"from": "C", "text": "msg3"},
                {"from": "D", "text": "msg4"},
                {"from": "E", "text": "msg5"},
            ],
        }
        result = parse_source_output("test", json.dumps(data), level="detail")
        assert "+2 more" in result["display"]

    def test_detail_falls_back_to_summary(self):
        """Detail level falls back to summary when no detail field."""
        data = {"count": 3, "summary": "3 messages from team"}
        result = parse_source_output("test", json.dumps(data), level="detail")
        assert result["display"] == "3 messages from team"

    def test_summary_falls_back_to_count(self):
        """Summary level falls back to count when no summary field."""
        data = {"count": 3}
        result = parse_source_output("test", json.dumps(data), level="summary")
        assert result["display"] == "3 from test"


# ============================================================================
# _format_for_level tests
# ============================================================================


class TestFormatForLevel:
    """Tests for _format_for_level() helper."""

    def test_count_level(self):
        assert _format_for_level("src", {"count": 5}, "count") == "5 from src"

    def test_summary_level_with_summary(self):
        data = {"count": 3, "summary": "3 new items"}
        assert _format_for_level("src", data, "summary") == "3 new items"

    def test_detail_level_with_detail(self):
        data = {
            "count": 2,
            "detail": [
                {"from": "Alice", "text": "Hello"},
                {"from": "Bob", "text": "World"},
            ],
        }
        result = _format_for_level("src", data, "detail")
        assert "Alice: Hello" in result
        assert "Bob: World" in result


# ============================================================================
# NotificationManager tests
# ============================================================================


class TestNotificationManager:
    """Tests for NotificationManager class."""

    def test_no_sources(self, tmp_path):
        """No sources configured — returns empty string."""
        config_file = tmp_path / "notifications.json"
        config_file.write_text('{"sources": []}')
        nm = NotificationManager(config_path=config_file)
        assert nm.check_all() == ""

    def test_missing_config(self, tmp_path):
        """Missing config file — returns empty string."""
        config_file = tmp_path / "nonexistent.json"
        nm = NotificationManager(config_path=config_file)
        assert nm.check_all() == ""

    def test_single_source_with_results(self, tmp_path):
        """Single source returning notifications."""
        config_file = tmp_path / "notifications.json"
        config_file.write_text(json.dumps({
            "level": "count",
            "sources": [
                {"name": "test-src", "command": "echo 3", "timeout": 5}
            ],
        }))
        nm = NotificationManager(config_path=config_file)
        result = nm.check_all()
        assert "Notifications:" in result
        assert "3 from test-src" in result

    def test_single_source_zero_count(self, tmp_path):
        """Source returning zero — no notification shown."""
        config_file = tmp_path / "notifications.json"
        config_file.write_text(json.dumps({
            "sources": [
                {"name": "test-src", "command": "echo 0", "timeout": 5}
            ],
        }))
        nm = NotificationManager(config_path=config_file)
        assert nm.check_all() == ""

    def test_multiple_sources(self, tmp_path):
        """Multiple sources — results aggregated."""
        config_file = tmp_path / "notifications.json"
        config_file.write_text(json.dumps({
            "level": "count",
            "sources": [
                {"name": "inbox", "command": "echo 3", "timeout": 5},
                {"name": "github", "command": "echo 7", "timeout": 5},
            ],
        }))
        nm = NotificationManager(config_path=config_file)
        result = nm.check_all()
        assert "3 from inbox" in result
        assert "7 from github" in result

    def test_source_timeout(self, tmp_path):
        """Timed-out source is skipped gracefully."""
        config_file = tmp_path / "notifications.json"
        config_file.write_text(json.dumps({
            "sources": [
                {"name": "slow", "command": "sleep 10", "timeout": 1}
            ],
        }))
        nm = NotificationManager(config_path=config_file)
        assert nm.check_all() == ""

    def test_source_nonzero_exit(self, tmp_path):
        """Source exiting non-zero is skipped gracefully."""
        config_file = tmp_path / "notifications.json"
        config_file.write_text(json.dumps({
            "sources": [
                {"name": "broken", "command": "exit 1", "timeout": 5}
            ],
        }))
        nm = NotificationManager(config_path=config_file)
        assert nm.check_all() == ""

    def test_per_source_level_override(self, tmp_path):
        """Per-source level overrides global level."""
        data = json.dumps({"count": 2, "summary": "2 messages (from Alice)"})
        config_file = tmp_path / "notifications.json"
        config_file.write_text(json.dumps({
            "level": "count",
            "sources": [
                {
                    "name": "inbox",
                    "command": f"echo '{data}'",
                    "timeout": 5,
                    "level": "summary",
                }
            ],
        }))
        nm = NotificationManager(config_path=config_file)
        result = nm.check_all()
        assert "2 messages (from Alice)" in result

    def test_invalid_json_config(self, tmp_path):
        """Invalid JSON config file — graceful degradation."""
        config_file = tmp_path / "notifications.json"
        config_file.write_text("not valid json {{{")
        nm = NotificationManager(config_path=config_file)
        assert nm.check_all() == ""


# ============================================================================
# check-inbox command tests
# ============================================================================


class TestCheckInbox:
    """Tests for check_inbox_messages() — watermark-based inbox checking."""

    def test_no_users_dir(self, tmp_path):
        """No users directory — returns count 0."""
        users_dir = tmp_path / "users"
        watermark_file = tmp_path / "watermarks.json"
        result = check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)
        assert result["count"] == 0

    def test_empty_users_dir(self, tmp_path):
        """Empty users directory — returns count 0."""
        users_dir = tmp_path / "users"
        users_dir.mkdir()
        watermark_file = tmp_path / "watermarks.json"
        result = check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)
        assert result["count"] == 0

    def test_first_check_sets_baseline(self, tmp_path):
        """First check sets baseline — no notifications from existing messages."""
        users_dir = tmp_path / "users"
        user_dir = users_dir / "alice"
        user_dir.mkdir(parents=True)
        inbox = user_dir / "inbox"
        inbox.write_text('{"from": "Bob", "text": "Old message"}\n')

        watermark_file = tmp_path / "watermarks.json"
        result = check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)
        assert result["count"] == 0

        # Verify watermark was set
        watermarks = load_watermarks(watermark_file)
        assert "alice" in watermarks
        assert watermarks["alice"] == inbox.stat().st_size

    def test_new_messages_after_baseline(self, tmp_path):
        """New messages after baseline are counted."""
        users_dir = tmp_path / "users"
        user_dir = users_dir / "cora"
        user_dir.mkdir(parents=True)
        inbox = user_dir / "inbox"
        inbox.write_text('{"from": "Mike", "text": "Old message"}\n')

        watermark_file = tmp_path / "watermarks.json"

        # First check — sets baseline
        check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)

        # Append new message
        with open(inbox, 'a') as f:
            f.write('{"from": "Astrid", "text": "New message!"}\n')

        # Second check — detects new message
        result = check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)
        assert result["count"] == 1
        assert "summary" in result
        assert "Astrid" in result["summary"]
        assert result["detail"][0]["from"] == "Astrid"

    def test_multiple_new_messages(self, tmp_path):
        """Multiple new messages from different senders."""
        users_dir = tmp_path / "users"
        user_dir = users_dir / "voicemode"
        user_dir.mkdir(parents=True)
        inbox = user_dir / "inbox"
        inbox.write_text("")  # Empty baseline

        watermark_file = tmp_path / "watermarks.json"
        check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)

        # Append multiple messages
        with open(inbox, 'a') as f:
            f.write('{"from": "Alice", "text": "Hello"}\n')
            f.write('{"from": "Bob", "text": "World"}\n')
            f.write('{"from": "Alice", "text": "Again"}\n')

        result = check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)
        assert result["count"] == 3
        assert "Alice" in result["summary"]
        assert "Bob" in result["summary"]

    def test_skips_delivery_confirmations(self, tmp_path):
        """delivery_confirmation entries are not counted."""
        users_dir = tmp_path / "users"
        user_dir = users_dir / "test"
        user_dir.mkdir(parents=True)
        inbox = user_dir / "inbox"
        inbox.write_text("")

        watermark_file = tmp_path / "watermarks.json"
        check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)

        with open(inbox, 'a') as f:
            f.write('{"type": "delivery_confirmation", "id": "123"}\n')
            f.write('{"from": "Mike", "text": "Real message"}\n')

        result = check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)
        assert result["count"] == 1

    def test_no_new_messages(self, tmp_path):
        """No new messages after baseline — returns count 0."""
        users_dir = tmp_path / "users"
        user_dir = users_dir / "cora"
        user_dir.mkdir(parents=True)
        inbox = user_dir / "inbox"
        inbox.write_text('{"from": "Mike", "text": "Initial"}\n')

        watermark_file = tmp_path / "watermarks.json"
        check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)

        # Check again without new messages
        result = check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)
        assert result["count"] == 0

    def test_watermark_persistence(self, tmp_path):
        """Watermarks survive across calls."""
        users_dir = tmp_path / "users"
        user_dir = users_dir / "test"
        user_dir.mkdir(parents=True)
        inbox = user_dir / "inbox"
        inbox.write_text('{"from": "A", "text": "msg1"}\n')

        watermark_file = tmp_path / "watermarks.json"
        check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)

        # Verify watermark file exists and is valid JSON
        assert watermark_file.exists()
        watermarks = json.loads(watermark_file.read_text())
        assert "test" in watermarks

    def test_multiple_users(self, tmp_path):
        """Messages across multiple user inboxes are aggregated."""
        users_dir = tmp_path / "users"
        for name in ["alice", "bob"]:
            user_dir = users_dir / name
            user_dir.mkdir(parents=True)
            (user_dir / "inbox").write_text("")

        watermark_file = tmp_path / "watermarks.json"
        check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)

        # Add messages to both inboxes
        with open(users_dir / "alice" / "inbox", 'a') as f:
            f.write('{"from": "Carol", "text": "Hi Alice"}\n')
        with open(users_dir / "bob" / "inbox", 'a') as f:
            f.write('{"from": "Dave", "text": "Hi Bob"}\n')

        result = check_inbox_messages(users_dir=users_dir, watermark_file=watermark_file)
        assert result["count"] == 2


# ============================================================================
# Watermark utility tests
# ============================================================================


class TestWatermarkUtils:
    """Tests for watermark load/save utilities."""

    def test_load_missing_file(self, tmp_path):
        """Load from missing file returns empty dict."""
        wm = load_watermarks(tmp_path / "nonexistent.json")
        assert wm == {}

    def test_save_and_load_roundtrip(self, tmp_path):
        """Save then load preserves data."""
        wfile = tmp_path / "watermarks.json"
        data = {"alice": 100, "bob": 200}
        save_watermarks(data, wfile)
        loaded = load_watermarks(wfile)
        assert loaded == data

    def test_load_invalid_json(self, tmp_path):
        """Load invalid JSON returns empty dict."""
        wfile = tmp_path / "watermarks.json"
        wfile.write_text("not json")
        wm = load_watermarks(wfile)
        assert wm == {}


# ============================================================================
# read_new_messages tests
# ============================================================================


class TestReadNewMessages:
    """Tests for read_new_messages() JSONL parser."""

    def test_read_from_offset(self, tmp_path):
        """Reads messages starting from byte offset."""
        inbox = tmp_path / "inbox"
        first_line = '{"from": "Old", "text": "old msg"}\n'
        second_line = '{"from": "New", "text": "new msg"}\n'
        inbox.write_text(first_line + second_line)

        messages = read_new_messages(inbox, len(first_line))
        assert len(messages) == 1
        assert messages[0]["from"] == "New"

    def test_skips_invalid_json_lines(self, tmp_path):
        """Invalid JSON lines are skipped."""
        inbox = tmp_path / "inbox"
        inbox.write_text('not json\n{"from": "Valid", "text": "ok"}\n')
        messages = read_new_messages(inbox, 0)
        assert len(messages) == 1
        assert messages[0]["from"] == "Valid"

    def test_skips_delivery_confirmations(self, tmp_path):
        """delivery_confirmation type messages are filtered out."""
        inbox = tmp_path / "inbox"
        inbox.write_text(
            '{"type": "delivery_confirmation", "id": "abc"}\n'
            '{"from": "Mike", "text": "hello"}\n'
        )
        messages = read_new_messages(inbox, 0)
        assert len(messages) == 1
        assert messages[0]["from"] == "Mike"

    def test_empty_lines_skipped(self, tmp_path):
        """Empty lines are skipped."""
        inbox = tmp_path / "inbox"
        inbox.write_text('\n\n{"from": "A", "text": "msg"}\n\n')
        messages = read_new_messages(inbox, 0)
        assert len(messages) == 1


# ============================================================================
# ensure_default_config tests
# ============================================================================


class TestEnsureDefaultConfig:
    """Tests for auto-generation of default notifications.json."""

    def test_creates_default_config(self, isolate_home_directory):
        """Creates default config when file doesn't exist."""
        config_path = isolate_home_directory / ".voicemode" / "notifications.json"
        assert not config_path.exists()

        with patch("voice_mode.notifications.NOTIFICATIONS_CONFIG_PATH", config_path):
            ensure_default_config()

        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert config["level"] == "count"
        assert len(config["sources"]) == 1
        assert config["sources"][0]["name"] == "connect-inbox"

    def test_does_not_overwrite_existing(self, isolate_home_directory):
        """Does not overwrite existing config file."""
        config_path = isolate_home_directory / ".voicemode" / "notifications.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"sources": [{"name": "custom"}]}')

        with patch("voice_mode.notifications.NOTIFICATIONS_CONFIG_PATH", config_path):
            ensure_default_config()

        config = json.loads(config_path.read_text())
        assert config["sources"][0]["name"] == "custom"


# ============================================================================
# get_notification_manager tests
# ============================================================================


class TestGetNotificationManager:
    """Tests for lazy singleton initialization."""

    def setup_method(self):
        """Reset singleton before each test."""
        import voice_mode.notifications as nm_mod
        nm_mod._notification_manager = None

    def test_returns_none_when_disabled(self):
        """Returns None when notifications are disabled."""
        with patch("voice_mode.notifications.get_notification_manager.__module__", "voice_mode.notifications"):
            import voice_mode.notifications as nm_mod
            nm_mod._notification_manager = None
            with patch("voice_mode.config.NOTIFICATIONS_ENABLED", False):
                result = get_notification_manager()
                assert result is None

    def test_returns_manager_when_enabled(self, isolate_home_directory):
        """Returns NotificationManager when enabled."""
        import voice_mode.notifications as nm_mod
        nm_mod._notification_manager = None

        config_path = isolate_home_directory / ".voicemode" / "notifications.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text('{"sources": []}')

        with patch("voice_mode.config.NOTIFICATIONS_ENABLED", True), \
             patch("voice_mode.config.CONNECT_ENABLED", False), \
             patch("voice_mode.notifications.NOTIFICATIONS_CONFIG_PATH", config_path):
            result = get_notification_manager()
            assert result is not None
            assert isinstance(result, NotificationManager)


# ============================================================================
# Integration test: converse notification suffix
# ============================================================================


class TestConverseIntegration:
    """Integration tests for notification strings in converse output format."""

    def test_notification_string_format(self):
        """Notification string follows the | Notifications: pattern."""
        nm = NotificationManager.__new__(NotificationManager)
        nm.sources = []
        nm.global_level = "count"
        nm.config = {"sources": []}
        assert nm.check_all() == ""

    def test_notification_appends_to_result(self, tmp_path):
        """Notification string appends cleanly to converse-style result."""
        config_file = tmp_path / "notifications.json"
        config_file.write_text(json.dumps({
            "level": "count",
            "sources": [
                {"name": "inbox", "command": "echo 3", "timeout": 5}
            ],
        }))
        nm = NotificationManager(config_path=config_file)
        notification_str = nm.check_all()

        # Simulate converse result formatting
        voice_result = "Voice response: Hello there (STT: whisper) | Timing: total 5.2s"
        final = f"{voice_result}{notification_str}"
        assert final == "Voice response: Hello there (STT: whisper) | Timing: total 5.2s | Notifications: 3 from inbox"

        # No speech result
        no_speech = "No speech detected | Timing: total 3.1s"
        final_no_speech = f"{no_speech}{notification_str}"
        assert "| Notifications:" in final_no_speech

    def test_empty_notifications_no_suffix(self, tmp_path):
        """Empty notifications don't add anything to result."""
        config_file = tmp_path / "notifications.json"
        config_file.write_text(json.dumps({
            "sources": [
                {"name": "empty", "command": "echo 0", "timeout": 5}
            ],
        }))
        nm = NotificationManager(config_path=config_file)
        notification_str = nm.check_all()

        result = f"Voice response: Hello{notification_str}"
        assert result == "Voice response: Hello"
