"""The M3 waiter: python -m voice_mode.heard_wait (VM-2274 do-003).

Synthetic lines in a tmp VOICEMODE_BASE_DIR, a fake clock for the ages:
no microphone, no sound, no real waiting.
"""

import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

import pytest

from voice_mode import heard
from voice_mode.heard_wait import Waiter, main


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICEMODE_BASE_DIR", str(tmp_path))
    for v in ("VOICEMODE_HEARD_BUDGET", "VOICEMODE_HEARD_MAX_LINES"):
        monkeypatch.delenv(v, raising=False)
    return tmp_path


class Clock:
    def __init__(self):
        self.t = time.time()

    def __call__(self):
        return self.t

    def sleep(self, s):
        self.t += s


def ts(rec):
    return datetime.fromisoformat(rec["ts"]).timestamp()


def capture_up(period=30):
    return heard.event(heard.EV_LISTEN_STARTED, device="airpods", period=period)


def waiter(clock, session="s", **kw):
    kw.setdefault("poll", 0.5)
    return Waiter(session, clock=clock, sleep=clock.sleep, **kw)


# --- the aged turn ------------------------------------------------------------

def test_an_aged_turn_wakes_with_take_and_the_cursor_moves(base):
    capture_up()
    clock = Clock()
    w = waiter(clock)
    heard.partial("hey", device="airpods")
    t = heard.turn("hey claude, the build is green", device="airpods")
    clock.t = ts(t) + 7.9
    assert w.check() is None                       # not aged yet
    clock.t = ts(t) + 8.0
    got = w.check()
    assert got["reason"] == "turn" and got["seq"] == t["seq"]
    assert got["text"].endswith("] hey claude, the build is green")
    assert got["cursor"] == t["seq"] == heard.load_cursor("s").seq
    assert "re-arm" in got["rearm"]


def _raw(kind, text, at):
    """A line with a chosen ts (heard.append always stamps now)."""
    rec = {"ts": datetime.fromtimestamp(at).astimezone().isoformat(timespec="milliseconds"),
           "seq": heard.last_seq() + 1, "kind": kind, "text": text, "source": "mic",
           "final": kind == "turn", "v": heard.SCHEMA}
    with open(heard.log_path(), "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def test_newer_speech_holds_the_wake_until_it_too_is_quiet(base):
    capture_up()
    clock = Clock()
    w = waiter(clock)
    t0 = clock.t
    _raw("turn", "first thought", t0)
    _raw("partial", "and another", t0 + 5)         # still talking, 5 s later
    clock.t = t0 + 9                               # the turn is 9 s old, the partial 4 s
    assert w.check() is None                       # held
    clock.t = t0 + 13                              # quiet for 8 s
    got = w.check()
    assert got["reason"] == "turn"
    assert "first thought" in got["text"] and "and another" in got["text"]


def test_a_dangling_partial_does_not_hold_the_wake_forever(base):
    capture_up()
    clock = Clock()
    w = waiter(clock)
    t0 = clock.t
    _raw("turn", "said", t0)
    _raw("partial", "noise that never became a turn", t0 + 1)
    clock.t = t0 + 9
    assert w.check()["reason"] == "turn"


def test_heartbeats_are_not_speech(base):
    capture_up(period=1)
    clock = Clock()
    w = waiter(clock)
    t = heard.turn("said")
    clock.t = ts(t) + 8
    heard.event(heard.EV_HEARTBEAT)                # written "now", after the turn
    assert w.check()["reason"] == "turn"


def test_a_rearmed_wait_does_not_repeat_the_turn(base):
    capture_up()
    clock = Clock()
    w = waiter(clock)
    t = heard.turn("once")
    clock.t = ts(t) + 9
    assert w.check()["reason"] == "turn"
    w2 = waiter(clock, timeout=5)
    assert w2.check() is None
    clock.t += 5
    assert w2.check()["reason"] == "timeout"


def test_a_turn_the_hook_already_showed_does_not_wake(base):
    capture_up()
    clock = Clock()
    w = waiter(clock)
    t = heard.turn("seen by a busy agent")
    out = heard.run_hook(json.dumps({"session_id": "s"}))
    assert "seen by a busy agent" in out
    clock.t = ts(t) + 60
    heard.event(heard.EV_HEARTBEAT)
    assert w.check() is None


def test_converse_turns_never_wake(base):
    capture_up()
    clock = Clock()
    w = waiter(clock)
    t = heard.turn("a reply to cora", via="converse", session="cora")
    clock.t = ts(t) + 60
    heard.event(heard.EV_HEARTBEAT)
    assert w.check() is None


def test_end_word_returns_at_once(base):
    capture_up()
    clock = Clock()
    w = waiter(clock)
    heard.turn("that's all, over")
    heard.event(heard.EV_END_WORD, word="over")
    got = w.check()                                # no waiting for age
    assert got["reason"] == "end-word" and "over" in got["text"]


# --- a dead ear is never a quiet room ----------------------------------------

def test_listen_stopped_is_capture_down_and_hands_over_what_was_heard(base):
    capture_up()
    clock = Clock()
    w = waiter(clock)
    heard.partial("half a sent")
    heard.event(heard.EV_LISTEN_STOPPED, reason="error: whisper unreachable")
    got = w.check()
    assert got["reason"] == "capture-down"
    assert "whisper unreachable" in got["detail"]
    assert "half a sent" in got["text"]
    assert "restart the capture" in got["rearm"]


def test_listen_stopped_is_seen_even_after_the_hook_consumed_it(base):
    capture_up()
    clock = Clock()
    w = waiter(clock)
    heard.event(heard.EV_LISTEN_STOPPED, reason="end-word")
    assert heard.run_hook(json.dumps({"session_id": "s"})) is None   # quiet event, cursor moved
    assert w.check()["reason"] == "capture-down"


def test_no_heartbeat_for_twice_the_period_is_capture_down(base):
    clock = Clock()
    w = waiter(clock)                              # armed, then the capture starts
    s = capture_up(period=10)
    clock.t = ts(s) + 19
    assert w.check() is None
    clock.t = ts(s) + 21
    got = w.check()
    assert got["reason"] == "capture-down" and "no heartbeat for 21s (period 10s)" == got["detail"]


# --- grace against the log's history (engineer's refine, 04:27) --------------

def test_arm_after_a_clean_stop_then_restart_within_grace(base):
    """Engineer's probe: history must not decide before a new capture can start."""
    capture_up(period=10)
    stop = heard.event(heard.EV_LISTEN_STOPPED, reason="stop")
    clock = Clock(); clock.t = ts(stop) + 60      # a minute after the old capture stopped
    w = waiter(clock)                             # arm FIRST (the M3 procedure) ...
    assert w.check() is None
    capture_up(period=10)                         # ... then the capture starts
    clock.t += 25
    assert w.check() is None                      # grace is over, and the ears are up


def test_arm_after_a_crashed_capture_then_restart_within_grace(base):
    """Engineer's probe: a capture that died hours ago with no listen-stopped."""
    up = capture_up(period=10)
    clock = Clock(); clock.t = ts(up) + 7200
    w = waiter(clock)
    assert w.check() is None


def test_history_that_stays_dead_is_reported_when_grace_runs_out(base):
    capture_up(period=10)
    stop = heard.event(heard.EV_LISTEN_STOPPED, reason="stop")
    clock = Clock(); clock.t = ts(stop) + 60
    w = waiter(clock, grace=30)
    clock.t += 29.9
    assert w.check() is None
    clock.t += 0.1
    got = w.check()
    assert got["reason"] == "capture-down"
    assert got["detail"] == "listen stopped (stop); no new capture in the 30s since arming"


def test_a_crash_that_stays_dead_is_reported_when_grace_runs_out(base):
    up = capture_up(period=10)
    clock = Clock(); clock.t = ts(up) + 7200
    w = waiter(clock, grace=30)
    clock.t += 30
    assert w.check()["reason"] == "capture-down"


def test_a_listen_started_with_no_ts_still_goes_stale(base):
    clock = Clock()
    w = waiter(clock, grace=30)
    heard.log_dir().mkdir(parents=True, exist_ok=True)
    with open(heard.log_path(), "a") as f:           # a writer that forgot ts
        f.write(json.dumps({"seq": heard.last_seq() + 1, "kind": "event",
                            "event": "listen-started", "period": 10, "source": "mic"}) + "\n")
    assert w.check() is None                          # seen now: up
    clock.t += 21
    assert w.check()["reason"] == "capture-down"      # and silent since: stale, not forever


# --- signals: between polls, never inside take() -------------------------------

def test_a_stop_between_polls_returns_stopped_and_consumes_nothing(base):
    capture_up()
    clock = Clock()
    w = waiter(clock)
    t = heard.turn("not yet taken")
    clock.t = ts(t) + 9
    got = w.run(should_stop=lambda: "SIGTERM")
    assert got["reason"] == "stopped" and got["signal"] == "SIGTERM"
    assert heard.load_cursor("s").seq < t["seq"]      # the turn is still there for the hook


def test_a_signal_during_a_take_still_prints_what_was_taken(base):
    capture_up()
    clock = Clock()
    w = waiter(clock)
    t = heard.turn("taken as the signal lands")
    clock.t = ts(t) + 9
    flags = []

    real_take = heard.take
    def take_then_signal(*a, **k):
        out = real_take(*a, **k)
        flags.append("SIGTERM")                         # the signal arrives inside take()
        return out
    heard.take, saved = take_then_signal, heard.take
    try:
        got = w.run(should_stop=lambda: flags[0] if flags else None)
    finally:
        heard.take = saved
    assert got["reason"] == "turn" and got["text"].endswith("taken as the signal lands")


def test_a_heartbeat_keeps_it_alive(base):
    s = capture_up(period=10)
    clock = Clock()
    w = waiter(clock)
    clock.t = ts(s) + 15
    hb = heard.event(heard.EV_HEARTBEAT)
    clock.t = ts(hb) + 19
    assert w.check() is None


def test_no_capture_within_grace_is_capture_down_capture_in_time_is_not(base):
    clock = Clock()
    w = waiter(clock, grace=30)
    clock.t += 29
    assert w.check() is None
    clock.t += 1
    assert w.check()["reason"] == "capture-down"
    clock2 = Clock()
    w2 = waiter(clock2, session="s2", grace=30)
    capture_up()
    clock2.t += 31
    assert w2.check() is None


def test_timeout(base):
    capture_up()
    clock = Clock()
    got = waiter(clock, timeout=3).run()
    assert got["reason"] == "timeout" and got["text"] == ""


# --- the CLI, as an agent runs it --------------------------------------------

def _env(base):
    env = {k: v for k, v in os.environ.items() if not k.startswith("VOICEMODE_HEARD")}
    env.update(VOICEMODE_BASE_DIR=str(base), CLAUDE_CODE_SESSION_ID="cli-sess",
               PYTHONDONTWRITEBYTECODE="1")
    return env


def test_cli_wakes_on_a_real_aged_turn_and_exits_0(base):
    capture_up(period=30)
    p = subprocess.Popen([sys.executable, "-m", "voice_mode.heard_wait", "--age", "0.5",
                          "--poll", "0.05"], env=_env(base), stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    time.sleep(1.5)                     # armed: the session's cursor is at the end
    heard.turn("from the cli test", device="airpods")
    out, err = p.communicate(timeout=30)
    assert p.returncode == 0, err
    got = json.loads(out.strip().splitlines()[-1])
    assert got["reason"] == "turn" and got["text"].endswith("] from the cli test")
    assert got["session"] == "cli-sess"
    assert err.startswith("heard_wait: session cli-sess, cursor ")


def test_cli_sigterm_is_stopped(base):
    capture_up(period=30)
    p = subprocess.Popen([sys.executable, "-m", "voice_mode.heard_wait"], env=_env(base),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(1.5)
    p.send_signal(signal.SIGTERM)
    out, _ = p.communicate(timeout=30)
    got = json.loads(out.strip().splitlines()[-1])
    assert p.returncode == 0 and got["reason"] == "stopped" and got["signal"] == "SIGTERM"


def test_cli_exit_codes_timeout_124_capture_down_3(base):
    capture_up(period=30)
    r = subprocess.run([sys.executable, "-m", "voice_mode.heard_wait", "--timeout", "0.3",
                        "--poll", "0.05"], env=_env(base), capture_output=True, text=True,
                       timeout=30)
    assert r.returncode == 124 and json.loads(r.stdout)["reason"] == "timeout"
    heard.event(heard.EV_LISTEN_STOPPED, reason="stop")
    r = subprocess.run([sys.executable, "-m", "voice_mode.heard_wait", "--poll", "0.05",
                        "--grace", "0.3"],
                       env=_env(base), capture_output=True, text=True, timeout=30)
    assert r.returncode == 3 and json.loads(r.stdout)["reason"] == "capture-down"


def test_cli_without_a_session_is_a_usage_error(base, capsys, monkeypatch):
    for v in ("CLAUDE_CODE_SESSION_ID", "CLAUDE_SESSION_ID", "VOICEMODE_SESSION_ID"):
        monkeypatch.delenv(v, raising=False)
    assert main([]) == 1
    assert "no session" in capsys.readouterr().err
