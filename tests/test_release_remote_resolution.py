"""Regression tests for VM-1565: release.py must push the v-tag to the GitHub
remote (canonical mbailey/voicemode), not a hardcoded 'origin'.

Post the 2026-06-10 failmode migration, `origin` points at ms2 (a bare git host
with no Actions). The old hardcoded `git push origin` shipped the tag to ms2 only,
so PyPI publish + GitHub Release workflows never fired. These tests pin the new
dynamic, fork-safe remote resolution and the loud-failure contract.

The test loads scripts/release.py directly (it is a script, not a package module).
"""

import importlib.util
import subprocess
from pathlib import Path

import pytest

_RELEASE_PY = Path(__file__).resolve().parent.parent / "scripts" / "release.py"
_spec = importlib.util.spec_from_file_location("release_under_test", _RELEASE_PY)
release = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release)


# The real-world post-migration layout this bug was filed against.
REMOTES_POST_MIGRATION = {
    "origin": "ms2:git/repos/voicemode",
    "github": "https://github.com/mbailey/voicemode.git",
    "fork": "https://github.com/Sallvainian/voicemode.git",
}


class TestResolveGithubRemote:
    def test_selects_canonical_github_not_origin_or_fork(self):
        # The crux of the bug: origin is NOT github, and a fork that lives on
        # github.com must not be mistaken for the canonical repo.
        assert release.resolve_github_remote(REMOTES_POST_MIGRATION) == "github"

    def test_missing_github_remote_returns_none(self):
        remotes = {
            "origin": "ms2:git/repos/voicemode",
            "fork": "https://github.com/Sallvainian/voicemode.git",
        }
        assert release.resolve_github_remote(remotes) is None

    def test_matches_ssh_scp_form(self):
        remotes = {"origin": "git@github.com:mbailey/voicemode.git"}
        assert release.resolve_github_remote(remotes) == "origin"

    def test_matches_ssh_host_alias(self):
        # ssh-config Host alias form (git@github.com_work:...) must still match.
        remotes = {"gh": "git@github.com_work:mbailey/voicemode.git"}
        assert release.resolve_github_remote(remotes) == "gh"

    def test_matches_ssh_url_form(self):
        remotes = {"gh": "ssh://git@github.com/mbailey/voicemode.git"}
        assert release.resolve_github_remote(remotes) == "gh"

    def test_origin_can_be_the_github_remote(self):
        # Pre-migration / CI clones where origin IS github should still resolve.
        remotes = {"origin": "https://github.com/mbailey/voicemode.git"}
        assert release.resolve_github_remote(remotes) == "origin"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("VOICEMODE_GITHUB_REMOTE", "origin")
        # Override wins even though 'github' would otherwise be canonical.
        assert release.resolve_github_remote(REMOTES_POST_MIGRATION) == "origin"


class TestPushToRemote:
    def test_pushes_tag_to_github_not_origin(self, monkeypatch):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(release, "get_remotes", lambda: REMOTES_POST_MIGRATION)
        monkeypatch.setattr(release.subprocess, "run", fake_run)

        assert release.push_to_remote("9.9.9") is True

        # The v-tag MUST be pushed to the github remote (this is the whole point).
        assert ["git", "push", "github", "v9.9.9"] in calls
        # And NOT pushed to the fork.
        assert ["git", "push", "fork", "v9.9.9"] not in calls
        # origin is still mirrored (kept in sync), but it is not the only target.
        assert ["git", "push", "origin", "v9.9.9"] in calls

    def test_missing_github_remote_blocks_loudly(self, monkeypatch, capsys):
        remotes = {
            "origin": "ms2:git/repos/voicemode",
            "fork": "https://github.com/Sallvainian/voicemode.git",
        }
        pushed = []

        def fake_run(cmd, **kwargs):
            pushed.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(release, "get_remotes", lambda: remotes)
        monkeypatch.setattr(release.subprocess, "run", fake_run)

        # Loud + blocking: returns False and pushes NOTHING (no silent ms2-only ship).
        assert release.push_to_remote("9.9.9") is False
        assert pushed == []
        assert "❌" in capsys.readouterr().out

    def test_github_push_failure_blocks(self, monkeypatch):
        def fake_run(cmd, **kwargs):
            if cmd[:3] == ["git", "push", "github"]:
                raise subprocess.CalledProcessError(1, cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(release, "get_remotes", lambda: REMOTES_POST_MIGRATION)
        monkeypatch.setattr(release.subprocess, "run", fake_run)

        assert release.push_to_remote("9.9.9") is False
