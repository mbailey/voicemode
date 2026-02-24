"""Tests for connect-session-end.sh SessionEnd hook.

Tests the cleanup logic that fires when a Claude Code session ends:
- Removes inbox-live symlink only if this session is the team lead
- Removes the session identity file
- Leaves other sessions' artifacts untouched
"""

import json
import os
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def hook_script():
    """Path to the connect-session-end.sh hook script."""
    return Path(__file__).parent.parent / "voice_mode" / "data" / "hooks" / "connect-session-end.sh"


@pytest.fixture
def connect_env(tmp_path):
    """Set up a fake Connect environment with session files and inbox-live."""
    home = tmp_path / "fakehome"
    home.mkdir(exist_ok=True)

    # Create required directories
    sessions_dir = home / ".voicemode" / "sessions"
    sessions_dir.mkdir(parents=True)

    connect_dir = home / ".voicemode" / "connect" / "users" / "cora"
    connect_dir.mkdir(parents=True)

    teams_dir = home / ".claude" / "teams"
    teams_dir.mkdir(parents=True)

    logs_dir = home / ".voicemode" / "logs"
    logs_dir.mkdir(parents=True)

    # Create voicemode.env that enables Connect
    env_file = home / ".voicemode" / "voicemode.env"
    env_file.write_text("VOICEMODE_CONNECT_ENABLED=true\nVOICEMODE_DEBUG=true\n")

    return {
        "home": home,
        "sessions_dir": sessions_dir,
        "connect_dir": connect_dir,
        "teams_dir": teams_dir,
        "logs_dir": logs_dir,
        "env_file": env_file,
    }


def run_hook(hook_script, session_id, home, extra_env=None):
    """Run the SessionEnd hook script with given input."""
    input_json = json.dumps({"session_id": session_id})

    env = os.environ.copy()
    env["HOME"] = str(home)
    if extra_env:
        env.update(extra_env)

    result = subprocess.run(
        ["bash", str(hook_script)],
        input=input_json,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    return result


class TestSessionEndTeamLeadCleanup:
    """Tests for team lead session cleanup (has team_name in session file)."""

    def test_removes_inbox_live_when_owned_by_session(self, hook_script, connect_env):
        """Team lead's inbox-live symlink should be removed on session end."""
        home = connect_env["home"]
        session_id = "test-session-001"
        team_name = "my-test-team"

        # Create team inbox directory
        team_inbox = home / ".claude" / "teams" / team_name / "inboxes" / "team-lead.json"
        team_inbox.parent.mkdir(parents=True)
        team_inbox.write_text("{}")

        # Create session file WITH team_name (= team lead)
        session_file = connect_env["sessions_dir"] / f"{session_id}.json"
        session_file.write_text(json.dumps({
            "session_id": session_id,
            "agent_name": "cora",
            "agent_type": "cora",
            "team_name": team_name,
        }))

        # Create inbox-live pointing to this team
        inbox_live = connect_env["connect_dir"] / "inbox-live"
        inbox_live.symlink_to(str(team_inbox))

        assert inbox_live.is_symlink()
        assert session_file.exists()

        # Run the hook
        result = run_hook(hook_script, session_id, home)
        assert result.returncode == 0, f"Hook failed: {result.stderr}"

        # inbox-live should be removed (we own it)
        assert not inbox_live.exists(), "inbox-live should be removed for team lead"

        # Session file should be removed
        assert not session_file.exists(), "Session file should be removed"

    def test_leaves_inbox_live_when_owned_by_different_team(self, hook_script, connect_env):
        """Should NOT remove inbox-live if it points to a different team."""
        home = connect_env["home"]
        session_id = "test-session-002"
        my_team = "my-team"
        other_team = "other-team"

        # Create both team inboxes
        my_inbox = home / ".claude" / "teams" / my_team / "inboxes" / "team-lead.json"
        my_inbox.parent.mkdir(parents=True)
        my_inbox.write_text("{}")

        other_inbox = home / ".claude" / "teams" / other_team / "inboxes" / "team-lead.json"
        other_inbox.parent.mkdir(parents=True)
        other_inbox.write_text("{}")

        # Session file says this session is lead of my_team
        session_file = connect_env["sessions_dir"] / f"{session_id}.json"
        session_file.write_text(json.dumps({
            "session_id": session_id,
            "agent_name": "cora",
            "agent_type": "cora",
            "team_name": my_team,
        }))

        # But inbox-live points to OTHER team (another session must have updated it)
        inbox_live = connect_env["connect_dir"] / "inbox-live"
        inbox_live.symlink_to(str(other_inbox))

        result = run_hook(hook_script, session_id, home)
        assert result.returncode == 0

        # inbox-live should be left alone — it belongs to another session
        assert inbox_live.is_symlink(), "inbox-live should NOT be removed (different team)"
        assert os.readlink(str(inbox_live)) == str(other_inbox)

        # Session file should still be removed
        assert not session_file.exists()


class TestSessionEndSubagentCleanup:
    """Tests for subagent/teammate session cleanup (no team_name)."""

    def test_does_not_touch_inbox_live_without_team(self, hook_script, connect_env):
        """Subagent session without team_name should NOT touch inbox-live."""
        home = connect_env["home"]
        session_id = "test-subagent-001"

        # Session file WITHOUT team_name (subagent)
        session_file = connect_env["sessions_dir"] / f"{session_id}.json"
        session_file.write_text(json.dumps({
            "session_id": session_id,
            "agent_name": "cora",
            "agent_type": "cora",
            # No team_name field
        }))

        # Some other session's inbox-live
        other_inbox = home / ".claude" / "teams" / "other-team" / "inboxes" / "team-lead.json"
        other_inbox.parent.mkdir(parents=True)
        other_inbox.write_text("{}")

        inbox_live = connect_env["connect_dir"] / "inbox-live"
        inbox_live.symlink_to(str(other_inbox))

        result = run_hook(hook_script, session_id, home)
        assert result.returncode == 0

        # inbox-live must be untouched
        assert inbox_live.is_symlink(), "Subagent must not remove inbox-live"
        assert os.readlink(str(inbox_live)) == str(other_inbox)

        # Session file should still be cleaned up
        assert not session_file.exists()

    def test_cleans_up_session_file_only(self, hook_script, connect_env):
        """Session without team should only remove session file."""
        home = connect_env["home"]
        session_id = "test-subagent-002"

        session_file = connect_env["sessions_dir"] / f"{session_id}.json"
        session_file.write_text(json.dumps({
            "session_id": session_id,
            "agent_name": "cora",
            "agent_type": "cora",
        }))

        # No inbox-live exists at all
        inbox_live = connect_env["connect_dir"] / "inbox-live"
        assert not inbox_live.exists()

        result = run_hook(hook_script, session_id, home)
        assert result.returncode == 0

        assert not session_file.exists(), "Session file should be removed"
        assert not inbox_live.exists(), "inbox-live should still not exist"


class TestSessionEndEdgeCases:
    """Tests for edge cases and error handling."""

    def test_no_session_file_exits_cleanly(self, hook_script, connect_env):
        """Should exit cleanly if session file doesn't exist."""
        home = connect_env["home"]
        session_id = "nonexistent-session"

        result = run_hook(hook_script, session_id, home)
        assert result.returncode == 0

    def test_no_session_id_exits_cleanly(self, hook_script, connect_env):
        """Should exit cleanly if no session_id in input."""
        home = connect_env["home"]

        env = os.environ.copy()
        env["HOME"] = str(home)

        result = subprocess.run(
            ["bash", str(hook_script)],
            input="{}",
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert result.returncode == 0

    def test_connect_disabled_exits_early(self, hook_script, connect_env):
        """Should exit early when VOICEMODE_CONNECT_ENABLED is false."""
        home = connect_env["home"]

        # Overwrite env file to disable Connect
        connect_env["env_file"].write_text("VOICEMODE_CONNECT_ENABLED=false\n")

        session_id = "test-session-disabled"

        # Create a session file that should NOT be touched
        session_file = connect_env["sessions_dir"] / f"{session_id}.json"
        session_file.write_text(json.dumps({
            "session_id": session_id,
            "agent_name": "cora",
            "team_name": "my-team",
        }))

        result = run_hook(hook_script, session_id, home)
        assert result.returncode == 0

        # Session file should NOT be removed (hook exited early)
        assert session_file.exists(), "Hook should exit early when Connect disabled"

    def test_inbox_live_not_a_symlink(self, hook_script, connect_env):
        """Should handle inbox-live being a regular file gracefully."""
        home = connect_env["home"]
        session_id = "test-session-regular-file"
        team_name = "my-team"

        # Create team inbox
        team_inbox = home / ".claude" / "teams" / team_name / "inboxes" / "team-lead.json"
        team_inbox.parent.mkdir(parents=True)
        team_inbox.write_text("{}")

        # Session file with team
        session_file = connect_env["sessions_dir"] / f"{session_id}.json"
        session_file.write_text(json.dumps({
            "session_id": session_id,
            "agent_name": "cora",
            "agent_type": "cora",
            "team_name": team_name,
        }))

        # inbox-live is a regular file, not a symlink
        inbox_live = connect_env["connect_dir"] / "inbox-live"
        inbox_live.write_text("not a symlink")

        result = run_hook(hook_script, session_id, home)
        assert result.returncode == 0

        # Regular file should not be touched (we only handle symlinks)
        assert inbox_live.exists()
        assert not inbox_live.is_symlink()

        # Session file should still be cleaned up
        assert not session_file.exists()

    def test_debug_log_written(self, hook_script, connect_env):
        """Should write debug log when VOICEMODE_DEBUG is enabled."""
        home = connect_env["home"]
        session_id = "test-session-debug"

        session_file = connect_env["sessions_dir"] / f"{session_id}.json"
        session_file.write_text(json.dumps({
            "session_id": session_id,
            "agent_name": "cora",
        }))

        result = run_hook(hook_script, session_id, home)
        assert result.returncode == 0

        debug_log = home / ".voicemode" / "logs" / "connect-hook-debug.log"
        assert debug_log.exists()
        log_content = debug_log.read_text()
        assert "connect-session-end.sh" in log_content
        assert session_id in log_content
        assert "DONE" in log_content
