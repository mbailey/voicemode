"""`voicemode claude hooks add|remove|list heard` (VM-2270 2.1).

HOME and the settings paths point into tmp: nothing touches ~/.claude or
~/.voicemode.
"""

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from voice_mode import heard
from voice_mode.cli_commands import claude as claude_mod
from voice_mode.cli_commands.claude import (
    claude,
    get_installed_hook_names,
    is_heard_hook,
    is_voicemode_hook,
)

RECEIVER = "voicemode-hook-receiver || true"


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(claude_mod, "SETTINGS_PATHS", {
        "user": home / ".claude" / "settings.json",
        "project": tmp_path / "proj" / ".claude" / "settings.json",
        "local": tmp_path / "proj" / ".claude" / "settings.local.json",
    })
    return home


def invoke(*args):
    with patch("voice_mode.cli_commands.claude.resolve_hook_command", return_value=RECEIVER):
        r = CliRunner().invoke(claude, ["hooks", *args])
    assert r.exit_code == 0, r.output
    return r.output


def settings(home):
    return json.loads((home / ".claude" / "settings.json").read_text())


def cmds(home, event):
    return [h["command"] for e in settings(home)["hooks"].get(event, []) for h in e["hooks"]]


def test_add_heard_installs_the_script_on_two_events(env):
    out = invoke("add", "heard")
    assert "+ PostToolUse (heard)" in out and "+ PostToolBatch (heard)" in out
    script = env / ".voicemode" / "bin" / "voicemode-heard-hook"
    assert script.read_text() == Path(heard.__file__).read_text()
    assert os.access(script, os.X_OK)
    for event in ("PostToolUse", "PostToolBatch"):
        assert cmds(env, event) == [f"{script} hook || true"]
    assert get_installed_hook_names("user") == {"heard"}


def test_heard_sits_beside_the_soundfont_receiver(env):
    invoke("add", "post-tool-use")
    out = invoke("add", "heard")
    assert "+ PostToolUse (heard)" in out  # not refused as "already present"
    c = cmds(env, "PostToolUse")
    assert c[0] == RECEIVER and "voicemode-heard-hook" in c[1] and len(c) == 2


def test_add_heard_twice_adds_once(env):
    invoke("add", "heard")
    out = invoke("add", "heard")
    assert "- PostToolUse (heard, already present)" in out
    assert len(cmds(env, "PostToolUse")) == 1 and len(cmds(env, "PostToolBatch")) == 1


def test_a_bare_add_leaves_heard_out(env):
    invoke("add")
    s = settings(env)
    assert "PostToolBatch" not in s["hooks"]
    assert not any(is_heard_hook(e) for entries in s["hooks"].values() for e in entries)
    assert not (env / ".voicemode" / "bin" / "voicemode-heard-hook").exists()


def test_remove_heard_leaves_the_receiver_and_the_reverse(env):
    invoke("add", "post-tool-use")
    invoke("add", "heard")
    invoke("remove", "heard")
    assert cmds(env, "PostToolUse") == [RECEIVER]
    assert "PostToolBatch" not in settings(env)["hooks"]
    invoke("add", "heard")
    invoke("remove", "post-tool-use")
    assert len(cmds(env, "PostToolUse")) == 1 and "voicemode-heard-hook" in cmds(env, "PostToolUse")[0]


def test_a_bare_remove_takes_heard_too(env):
    invoke("add")
    invoke("add", "heard")
    out = invoke("remove")
    assert "PostToolBatch (removed)" in out
    assert "hooks" not in settings(env)


def test_list_shows_heard(env):
    assert "heard (opt-in)" in invoke("list")
    invoke("add", "heard")
    out = invoke("list")
    assert "heard (PostToolUse, PostToolBatch)" in out and "+ installed" in out


def test_soundfont_detection_does_not_count_heard():
    entry = {"hooks": [{"type": "command", "command": "/h/.voicemode/bin/voicemode-heard-hook hook || true"}]}
    assert is_heard_hook(entry) and not is_voicemode_hook(entry)


def test_the_installed_copy_runs_as_the_hook(env, tmp_path):
    invoke("add", "heard")
    script = env / ".voicemode" / "bin" / "voicemode-heard-hook"
    base = tmp_path / "vm"
    run_env = {"HOME": str(env), "PATH": os.environ["PATH"], "VOICEMODE_BASE_DIR": str(base)}
    stdin = json.dumps({"session_id": "installed", "hook_event_name": "PostToolUse"})
    first = subprocess.run([str(script), "hook"], input=stdin, capture_output=True, text=True,
                           env=run_env, timeout=30)
    assert first.returncode == 0 and first.stdout == ""
    subprocess.run([str(script), "write", "turn", "through the installed copy"],
                   env=run_env, check=True, capture_output=True, timeout=30)
    second = subprocess.run([str(script), "hook"], input=stdin, capture_output=True, text=True,
                            env=run_env, timeout=30)
    ctx = json.loads(second.stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx.endswith("] through the installed copy")
