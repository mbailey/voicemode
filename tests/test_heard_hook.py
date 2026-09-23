"""The heard ride-along: cursor, collapse, budget, hook (VM-2270 2.1-2.4).

Synthetic lines only, in a tmp VOICEMODE_BASE_DIR: no microphone, no sound.
"""

import fcntl
import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from voice_mode import heard

HEARD_PY = Path(heard.__file__)


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(tmp_path))
    for var in ("VOICEMODE_HEARD_BUDGET", "VOICEMODE_HEARD_MAX_LINES",
                "VOICEMODE_HEARD_HOOK", "CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID",
                "VOICEMODE_SESSION_ID"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def hook(session="s1", event="PostToolUse", **kw):
    out = heard.run_hook(json.dumps({"session_id": session, "hook_event_name": event}), **kw)
    if out is None:
        return None
    payload = json.loads(out)["hookSpecificOutput"]
    assert payload["hookEventName"] == event
    return re.sub(r"\d\d:\d\d:\d\d", "T", payload["additionalContext"])


def cursor(session="s1"):
    return heard.load_cursor(session).seq


def start(session="s1"):
    """First call for a session: sets its cursor at the end, prints nothing."""
    assert hook(session) is None


# --- starting a session ---------------------------------------------------

def test_a_new_session_starts_at_the_end_and_is_shown_nothing_old(base):
    heard.turn("said before the session existed")
    start()
    assert cursor() == 1
    heard.turn("said after")
    assert hook() == "[heard mic T] said after"
    assert cursor() == 2
    assert hook() is None  # silent when nothing is past the cursor


def test_a_session_that_started_before_any_log_sees_from_seq_one(base):
    start()
    assert cursor() == 0
    heard.turn("the first words ever", device="airpods")
    assert hook() == "[heard mic/airpods T] the first words ever"


# --- collapse ---------------------------------------------------------------

def test_busy_agent_sees_the_turn_once_not_its_partials(base):
    """Spec scenario: six partials and one turn -> the turn, once."""
    start()
    for chunk in ("so", "the bot", "will post", "what I", "say into", "the group"):
        heard.partial(chunk, device="airpods")
    t = heard.turn("so the bot will post what I say into the group",
                   device="airpods", detector="vad-silence")
    assert hook() == "[heard mic/airpods T] so the bot will post what I say into the group"
    assert cursor() == t["seq"]


def test_partials_with_no_turn_yet_show_as_a_preview_then_the_turn_whole(base):
    start()
    heard.partial("hey claude", device="airpods")
    heard.partial("can you check", device="airpods")
    assert hook() == "[heard mic/airpods T partial] hey claude can you check …"
    heard.partial("the build", device="airpods")
    heard.turn("hey claude can you check the build", device="airpods")
    assert hook() == "[heard mic/airpods T] hey claude can you check the build"


def test_quiet_events_move_the_cursor_and_cost_nothing(base):
    start()
    heard.event(heard.EV_LISTEN_STARTED)
    heard.event(heard.EV_HEARTBEAT)
    e = heard.event(heard.EV_HEARTBEAT)
    assert hook() is None
    assert cursor() == e["seq"]
    heard.event(heard.EV_WAKE_WORD, word="hey claude", device="airpods")
    heard.event(heard.EV_DEVICE_CHANGED, device="MacBook Pro Microphone", reason="airpods gone")
    assert hook() == ("[heard mic/airpods T wake-word] hey claude\n"
                      "[heard mic/MacBook Pro Microphone T device-changed] (airpods gone)")


def test_own_converse_turn_is_silent_another_sessions_is_shown(base):
    start("pip")
    start("cora")
    heard.turn("yes, go ahead", via="converse", session="pip", agent="pip", device="airpods")
    assert hook("pip") is None
    assert cursor("pip") == 1
    assert hook("cora") == "[heard mic/airpods T converse:pip] yes, go ahead"


# --- two sessions -----------------------------------------------------------

def test_two_agents_two_cursors(base):
    """Spec scenario: Cora's hook advancing does not move Pip's."""
    start("cora")
    start("pip")
    heard.turn("one")
    heard.turn("two")
    assert hook("cora") == "[heard mic T] one\n[heard mic T] two"
    assert cursor("pip") == 0
    assert hook("pip") == "[heard mic T] one\n[heard mic T] two"


# --- the budget ---------------------------------------------------------------

def _fill_to(n):
    """Write n heartbeats so the next real line is seq n+1."""
    for _ in range(n):
        heard.event(heard.EV_HEARTBEAT)


def test_budget_cuts_without_losing_lines_spec_scenario(base):
    """Spec: forty past the cursor, room for twelve -> twelve, +28, cursor 430."""
    _fill_to(418)
    start()
    assert cursor() == 418
    for i in range(419, 459):
        heard.turn(f"line {i}")
    out = hook(max_lines=12)
    lines = out.splitlines()
    assert lines[:12] == [f"[heard mic T] line {i}" for i in range(419, 431)]
    assert lines[12] == "[heard] +28 more, seq 431-458"
    assert cursor() == 430
    assert hook(max_lines=12).splitlines()[0] == "[heard mic T] line 431"


def test_watch_it_fail_once_one_line_against_forty(base):
    """Task 2.4: a budget of 1 line against 40, and every next call resumes right."""
    start()
    for i in range(1, 41):
        heard.turn(f"line {i}")
    first = hook(max_lines=1)
    assert first == "[heard mic T] line 1\n[heard] +39 more, seq 2-40"
    assert cursor() == 1
    seen = [1]
    while True:
        out = hook(max_lines=1)
        if out is None:
            break
        head = out.splitlines()[0]
        seen.append(int(head.rsplit(" ", 1)[1]))
        assert cursor() == seen[-1]
    assert seen == list(range(1, 41))  # each exactly once, in order


def test_token_budget_cuts_too(base):
    start()
    for i in range(10):
        heard.turn(f"{i} " + "word " * 20)  # ~26 tokens a line
    out = hook(budget_tokens=100)
    lines = out.splitlines()
    assert lines[-1].startswith("[heard] +") and "more, seq" in lines[-1]
    shown = len(lines) - 1
    assert 1 <= shown < 10
    assert cursor() == shown


def test_one_line_over_budget_is_cut_short_and_the_cursor_passes_it(base):
    start()
    t = heard.turn("x" * 5000)
    heard.turn("after")
    out = hook(budget_tokens=100)
    first = out.splitlines()[0]
    assert first.startswith("[heard mic T] xxxx") and f"whole line: seq {t['seq']}" in first
    assert len(out) < 100 * 4
    assert cursor() == t["seq"]
    assert hook(budget_tokens=100) == "[heard mic T] after"


def test_budget_from_the_environment(base, monkeypatch):
    start()
    for i in range(5):
        heard.turn(f"line {i}")
    monkeypatch.setenv("VOICEMODE_HEARD_MAX_LINES", "2")
    assert hook().splitlines()[-1] == "[heard] +3 more, seq 3-5"


# --- the cursor ---------------------------------------------------------------

def test_listen_advances_the_cursor_past_the_turn_it_returned(base):
    start()
    heard.turn("returned to wake the agent")
    assert heard.advance_cursor("s1", 1)
    assert hook() is None
    assert heard.advance_cursor("s1", 0)  # never moves back
    assert cursor() == 1


def test_cursor_keeps_a_byte_hint_so_a_read_starts_where_the_last_stopped(base):
    start()
    heard.turn("one")
    hook()
    cur = heard.load_cursor("s1")
    assert cur.file == heard.log_path().name
    assert cur.offset == heard.log_path().stat().st_size


def test_a_torn_last_line_waits_for_its_newline(base):
    start()
    heard.turn("whole")
    with open(heard.log_path(), "a") as f:
        f.write('{"ts": "2026-09-24T04:00:00.000+10:00", "seq": 2, "kind": "turn", "text": "ha')
    assert hook() == "[heard mic T] whole"
    with open(heard.log_path(), "a") as f:
        f.write('lf", "source": "mic"}\n')
    assert hook() == "[heard mic T] half"


def test_across_midnight(base):
    d = heard.log_dir()
    d.mkdir(parents=True)
    yday = heard.log_path(date.today() - timedelta(days=1))
    yday.write_text(json.dumps({"ts": "2026-09-23T23:59:58.000+10:00", "seq": 7,
                                "kind": "turn", "text": "late", "source": "mic"}) + "\n")
    start()
    assert cursor() == 7
    heard.turn("early")
    assert hook() == "[heard mic T] early"
    assert cursor() == 8


def test_a_held_lock_means_silence_never_a_wait(base):
    start()
    heard.turn("one")
    lock = heard.cursor_dir() / "s1.lock"
    fd = os.open(str(lock), os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        assert heard.run_hook(json.dumps({"session_id": "s1"}), lock_timeout=0.05) is None
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
    assert hook() == "[heard mic T] one"  # nothing lost to the skipped run


def test_session_names_cannot_escape_the_cursor_dir(base):
    start("../../etc/passwd")
    assert not (base / "etc").exists()
    assert list(heard.cursor_dir().glob("*passwd*"))


# --- the script, as Claude Code runs it -------------------------------------

def _script(args, stdin="", env_extra=None, base_dir=None):
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(("VOICEMODE_HEARD", "CLAUDE_CODE_SESSION", "CLAUDE_SESSION"))}
    env["VOICEMODE_BASE_DIR"] = str(base_dir)
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(HEARD_PY), *args], input=stdin,
                          capture_output=True, text=True, env=env, timeout=30)


def test_script_end_to_end_json_form_for_post_tool_batch(base):
    stdin = json.dumps({"session_id": "e2e", "hook_event_name": "PostToolBatch"})
    assert _script(["hook"], stdin, base_dir=base).stdout == ""
    w = _script(["write", "turn", "from a shell writer", "--source", "call",
                 "--device", "delta:kith/13"], base_dir=base)
    assert w.returncode == 0 and json.loads(w.stdout)["seq"] == 1
    r = _script(["hook"], stdin, base_dir=base)
    assert r.returncode == 0
    ctx = json.loads(r.stdout)["hookSpecificOutput"]
    assert ctx["hookEventName"] == "PostToolBatch"
    assert re.fullmatch(r"\[heard call/delta:kith/13 \d\d:\d\d:\d\d\] from a shell writer",
                        ctx["additionalContext"])


def test_script_can_be_switched_off(base):
    stdin = json.dumps({"session_id": "off"})
    _script(["hook"], stdin, base_dir=base)
    _script(["write", "turn", "hello"], base_dir=base)
    r = _script(["hook"], stdin, env_extra={"VOICEMODE_HEARD_HOOK": "off"}, base_dir=base)
    assert r.returncode == 0 and r.stdout == ""


def test_script_imports_nothing_from_voice_mode(base):
    r = _script(["last-seq"], base_dir=base,
                env_extra={"PYTHONPATH": "", "PYTHONNOUSERSITE": "1"})
    assert r.returncode == 0 and r.stdout.strip() == "0"
    src = HEARD_PY.read_text()
    assert "from voice_mode" not in src and "import voice_mode" not in src


# --- the waiter's half: pending() and take() --------------------------------

def test_pending_does_not_move_the_cursor_take_does(base):
    assert heard.pending("w") == []  # a new session: cursor at the end
    heard.partial("wake", device="airpods")
    t = heard.turn("wake up", device="airpods")
    got = heard.pending("w")
    assert [r["kind"] for r in got] == ["partial", "turn"]
    assert heard.load_cursor("w").seq == 0
    text, seq = heard.take("w")
    assert re.sub(r"\d\d:\d\d:\d\d", "T", text) == "[heard mic/airpods T] wake up"
    assert seq == t["seq"] == heard.load_cursor("w").seq
    assert heard.pending("w") == []


def test_what_the_waiter_took_the_hook_does_not_repeat(base):
    start("idle")
    heard.turn("said while the agent was idle")
    text, _ = heard.take("idle")
    assert text.endswith("said while the agent was idle")
    assert hook("idle") is None


def test_what_the_hook_showed_the_waiter_does_not_wake_for(base):
    """The pager's rule: wake only for what the agent has not been shown."""
    start("busy")
    heard.turn("said while the agent was busy")
    assert hook("busy").endswith("said while the agent was busy")
    assert heard.pending("busy") == []


def test_a_converse_turn_never_swallows_a_listeners_partials(base):
    start("pip")
    heard.partial("mike still talking")          # the listener: mic, no device
    heard.turn("pip's own reply", via="converse", session="pip")   # silent for pip
    out = hook("pip")
    assert out == "[heard mic T partial] mike still talking …"


def test_script_failure_is_exit_1_with_stderr_never_silent(base, tmp_path):
    not_a_dir = tmp_path / "file"
    not_a_dir.write_text("x")
    r = _script(["hook"], json.dumps({"session_id": "x"}), base_dir=not_a_dir)
    assert r.returncode == 1 and r.stdout == ""
    assert r.stderr.startswith("[heard] the hook failed:")
