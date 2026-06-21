"""Tests for the MCP ``conch`` tool (VM-1622).

The tool is a remote, streamable-HTTP front end with CLI parity over the same
on-disk conch state. Home isolation comes from the autouse
``isolate_home_directory`` fixture in conftest.py (re-pins ``Conch.LOCK_FILE``
into a per-test fake home; ``ConchQueue`` derives its paths from there), so the
whole conch state is isolated automatically.

Coverage mirrors the task's Testing Strategy:
- per-action unit tests (status / callback / wait / heartbeat / leave / give /
  bump / release),
- remote-waiter liveness via the ``expires`` TTL (pruned when past, kept when
  future),
- no-divergence parity: give / bump / release driven over MCP land the same
  on-disk state the CLI command produces from the same start,
- validation: actions missing their required key return a clear error, never a
  traceback.
"""

import json
import os

import pytest
from click.testing import CliRunner

from voice_mode.conch import Conch
from voice_mode.conch_queue import ConchQueue
from voice_mode import conch_ops
from voice_mode.conch_ops import parse_ts
from voice_mode.tools.conch import conch as _conch_tool
from voice_mode.cli_commands.conch import conch as conch_cli


@pytest.fixture(autouse=True)
def _no_discovery(monkeypatch):
    """Default: ``session list`` discovery finds nothing (VM-1637) — keeps the
    waiter-only give tests pre-VM-1637 and stops any shell-out to ``session``.
    Summon tests override this with their own running-session list."""
    monkeypatch.setattr(conch_ops, "_list_running_sessions", lambda: [])


def _running(sid, *, agent=None, name=None, pid=None, cwd=None):
    """A fake discovered running session; pid defaults to this (live) process so
    the summoned waiter survives ConchQueue's dead-PID cleanup."""
    return conch_ops.RunningSession(
        session_id=sid, pid=pid if pid is not None else os.getpid(),
        agent=agent, name=name, project_path=cwd,
    )


def _tool():
    """The undecorated tool coroutine (FastMCP may wrap it as ``.fn``)."""
    return getattr(_conch_tool, "fn", _conch_tool)


async def call(**kwargs):
    return await _tool()(**kwargs)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _register_local(sid, *, agent=None, mode="wait"):
    """Register a live LOCAL waiter (pid = current process)."""
    return ConchQueue.register(sid, agent=agent, mode=mode)


def _make_holder(agent="holder", sid="holder-sess"):
    """Write a live holder lock (current-process pid => get_holder sees it)."""
    Conch().acquire(agent_name=agent, session_id=sid)


def _sessions():
    return [e.session_id for e in ConchQueue.list()]


def _entry(sid):
    for e in ConchQueue.list():
        if e.session_id == sid:
            return e
    return None


def _grant_file_dict():
    gf = Conch.LOCK_FILE.parent / "conch.grant"
    try:
        return json.loads(gf.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _norm_state():
    """Normalised, seq-independent snapshot of the shared conch state.

    The grant ``seq`` is a monotonic internal hint that drifts between two runs;
    the *meaningful* state (who holds, who is granted, who is queued in what
    mode) is what the two front ends must agree on.
    """
    return {
        "granted": ConchQueue.granted_to(),
        "holder": (Conch.get_holder() or {}).get("session_id"),
        "queue": [(e.session_id, e.mode) for e in ConchQueue.list()],
    }


def _clear_all():
    if Conch.LOCK_FILE.exists():
        Conch.LOCK_FILE.unlink()
    for e in ConchQueue.list():
        ConchQueue.deregister(e.session_id)
    ConchQueue.clear_grant()


@pytest.fixture
def clean_conch():
    """No conch lock / queue / grant before and after each test."""
    _clear_all()
    yield
    _clear_all()


@pytest.fixture
def runner():
    return CliRunner()


# --------------------------------------------------------------------------- #
# status
# --------------------------------------------------------------------------- #

class TestStatus:
    @pytest.mark.asyncio
    async def test_status_empty(self, clean_conch):
        res = await call(action="status")
        assert res["ok"] is True
        assert res["holder"] is None
        assert res["queue"] == []

    @pytest.mark.asyncio
    async def test_status_default_action_is_status(self, clean_conch):
        # action defaults to "status" — a bare call is a safe read.
        res = await call()
        assert res["ok"] is True
        assert "holder" in res and "queue" in res

    @pytest.mark.asyncio
    async def test_status_shows_holder_and_queue(self, clean_conch):
        _make_holder(agent="alpha", sid="alpha-sess")
        _register_local("beta-222", agent="beta", mode="wait")
        res = await call(action="status")
        assert res["holder"]["agent"] == "alpha"
        assert res["holder"]["session_id"] == "alpha-sess"
        assert [q["session_id"] for q in res["queue"]] == ["beta-222"]
        assert res["queue"][0]["mode"] == "wait"


# --------------------------------------------------------------------------- #
# callback (the timeout-safe default for joining)
# --------------------------------------------------------------------------- #

class TestCallback:
    @pytest.mark.asyncio
    async def test_callback_registers_remote_and_returns_position(self, clean_conch):
        res = await call(action="callback", session_id="remote-1", agent="r1")
        assert res["ok"] is True
        assert res["registered"] is True
        assert res["granted"] is False
        assert res["mode"] == "callback"
        assert res["position"] == 1
        # Stays registered as a REMOTE waiter (pid is None) with a future TTL.
        entry = _entry("remote-1")
        assert entry is not None
        assert entry.pid is None
        assert entry.mode == "callback"
        assert entry.expires is not None
        assert res["expires"] == entry.expires

    @pytest.mark.asyncio
    async def test_callback_expires_is_in_the_future(self, clean_conch):
        from datetime import datetime
        res = await call(action="callback", session_id="remote-1")
        exp = parse_ts(res["expires"])
        assert exp is not None
        assert exp > datetime.now()


# --------------------------------------------------------------------------- #
# wait (a hard-capped gate; never holds the floor)
# --------------------------------------------------------------------------- #

class TestWait:
    @pytest.mark.asyncio
    async def test_wait_granted_when_free_and_head(self, clean_conch):
        # Free conch + we become the head => our turn immediately.
        res = await call(action="wait", session_id="w1", timeout=5)
        assert res["ok"] is True
        assert res["granted"] is True
        # Gate model: leaves cleanly (does not hold the floor / no ghost entry).
        assert _sessions() == []

    @pytest.mark.asyncio
    async def test_wait_granted_via_explicit_grant(self, clean_conch):
        _make_holder()  # busy: not the free-head path
        _register_local("w1", agent="w1", mode="callback")
        assert ConchQueue.grant("w1") is True
        res = await call(action="wait", session_id="w1", timeout=5)
        assert res["granted"] is True
        assert _sessions() == []  # deregistered on grant

    @pytest.mark.asyncio
    async def test_wait_times_out_and_deregisters(self, clean_conch, monkeypatch):
        monkeypatch.setattr("voice_mode.tools.conch.CONCH_CHECK_INTERVAL", 0.02)
        _make_holder()  # live holder => never free for us
        # A separate granted waiter means our head-of-free path never fires.
        _register_local("other", agent="other", mode="wait")
        assert ConchQueue.grant("other") is True
        res = await call(action="wait", session_id="w1", timeout=0.2)
        assert res["ok"] is True
        assert res["granted"] is False
        assert res["cap_seconds"] == pytest.approx(0.2)
        # Deregistered cleanly on timeout — no wedged head left behind.
        assert "w1" not in _sessions()

    @pytest.mark.asyncio
    async def test_wait_cap_clamps_large_timeout(self, clean_conch, monkeypatch):
        monkeypatch.setattr("voice_mode.tools.conch.CONCH_CHECK_INTERVAL", 0.02)
        monkeypatch.setattr("voice_mode.tools.conch.CONCH_MCP_WAIT_CAP", 0.1)
        _make_holder()
        _register_local("other", mode="wait")
        ConchQueue.grant("other")
        res = await call(action="wait", session_id="w1", timeout=999)
        # min(timeout, cap) => the cap wins.
        assert res["cap_seconds"] == pytest.approx(0.1)
        assert res["granted"] is False


# --------------------------------------------------------------------------- #
# heartbeat (refresh TTL, keep place + mode)
# --------------------------------------------------------------------------- #

class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_refreshes_expires_and_preserves_seq_and_mode(self, clean_conch):
        first = await call(action="callback", session_id="r1")
        seq_before = _entry("r1").seq
        exp_before = first["expires"]

        res = await call(action="heartbeat", session_id="r1")
        assert res["ok"] is True
        assert res["mode"] == "callback"  # mode preserved (not flipped to wait)
        entry = _entry("r1")
        assert entry.seq == seq_before  # place preserved
        assert entry.mode == "callback"
        # TTL moved forward (or stayed equal at worst — never earlier).
        assert parse_ts(res["expires"]) >= parse_ts(exp_before)

    @pytest.mark.asyncio
    async def test_heartbeat_when_not_registered_is_a_clear_error(self, clean_conch):
        res = await call(action="heartbeat", session_id="ghost")
        assert res["ok"] is False
        assert "not in the queue" in res["message"].lower()


# --------------------------------------------------------------------------- #
# leave
# --------------------------------------------------------------------------- #

class TestLeave:
    @pytest.mark.asyncio
    async def test_leave_deregisters(self, clean_conch):
        await call(action="callback", session_id="r1")
        assert "r1" in _sessions()
        res = await call(action="leave", session_id="r1")
        assert res["ok"] is True
        assert "r1" not in _sessions()

    @pytest.mark.asyncio
    async def test_leave_is_idempotent(self, clean_conch):
        res = await call(action="leave", session_id="never-here")
        assert res["ok"] is True


# --------------------------------------------------------------------------- #
# give / bump / release
# --------------------------------------------------------------------------- #

class TestGive:
    @pytest.mark.asyncio
    async def test_give_grants_named_waiter(self, clean_conch):
        _register_local("alpha-1", agent="alpha")
        _register_local("beta-2", agent="beta")
        res = await call(action="give", target="beta")
        assert res["ok"] is True
        assert ConchQueue.granted_to() == "beta-2"

    @pytest.mark.asyncio
    async def test_give_requires_target(self, clean_conch):
        res = await call(action="give")
        assert res["ok"] is False
        assert "target" in res["message"].lower()

    @pytest.mark.asyncio
    async def test_give_no_waiters_is_clear_error(self, clean_conch):
        res = await call(action="give", target="cora")
        assert res["ok"] is False
        assert "no one is waiting" in res["message"].lower()
        assert ConchQueue.granted_to() is None

    @pytest.mark.asyncio
    async def test_give_ambiguous_is_clear_error(self, clean_conch):
        _register_local("dup-1", agent="a")
        _register_local("dup-2", agent="b")
        res = await call(action="give", target="dup-")
        assert res["ok"] is False
        assert "ambiguous" in res["message"].lower()
        assert ConchQueue.granted_to() is None


class TestSummon:
    """give over MCP to a running non-waiter ⇒ summon (VM-1637)."""

    @pytest.mark.asyncio
    async def test_summon_non_waiter_enqueues_and_grants(self, clean_conch, monkeypatch):
        monkeypatch.setattr(conch_ops, "_list_running_sessions",
                            lambda: [_running("run-1", agent="dora", cwd="/tmp/p")])
        monkeypatch.setattr("subprocess.run", lambda *a, **k: None)
        res = await call(action="give", target="dora")
        assert res["ok"] is True
        assert res["summoned"] is True
        assert res["target"] == "run-1"
        entry = _entry("run-1")
        assert entry is not None and entry.mode == "callback" and entry.pid == os.getpid()
        assert ConchQueue.granted_to() == "run-1"

    @pytest.mark.asyncio
    async def test_summon_target_is_holder_is_noop(self, clean_conch, monkeypatch):
        _make_holder(agent="boss", sid="held-1")
        monkeypatch.setattr(conch_ops, "_list_running_sessions",
                            lambda: [_running("held-1", agent="boss")])
        res = await call(action="give", target="boss")
        assert res["ok"] is True
        assert res["summoned"] is False
        assert "already holds" in res["message"].lower()
        assert ConchQueue.list() == []      # not enqueued
        assert ConchQueue.granted_to() is None

    @pytest.mark.asyncio
    async def test_summon_ambiguous_no_orphan(self, clean_conch, monkeypatch):
        monkeypatch.setattr(conch_ops, "_list_running_sessions",
                            lambda: [_running("dup-1", agent="a"),
                                     _running("dup-2", agent="b")])
        res = await call(action="give", target="dup-")
        assert res["ok"] is False
        assert "ambiguous" in res["message"].lower()
        assert ConchQueue.list() == []
        assert ConchQueue.granted_to() is None

    @pytest.mark.asyncio
    async def test_summon_no_match_degrades(self, clean_conch, monkeypatch):
        monkeypatch.setattr(conch_ops, "_list_running_sessions",
                            lambda: [_running("other", agent="zzz")])
        res = await call(action="give", target="ghost")
        assert res["ok"] is False
        assert "no one is waiting" in res["message"].lower()
        assert ConchQueue.granted_to() is None


class TestBump:
    @pytest.mark.asyncio
    async def test_bump_drops_holder_and_promotes_head(self, clean_conch):
        _make_holder(agent="holder", sid="holder-sess")
        _register_local("next-1", agent="next")
        res = await call(action="bump")
        assert res["ok"] is True
        assert Conch.get_holder() is None
        assert ConchQueue.granted_to() == "next-1"

    @pytest.mark.asyncio
    async def test_bump_stale_lock_directs_to_release(self, clean_conch):
        # Lock file exists but holder is dead (unsignalable pid).
        Conch.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        Conch.LOCK_FILE.write_text(json.dumps({"pid": 999999, "agent": "ghost"}))
        res = await call(action="bump")
        assert res["ok"] is False
        assert "release" in res["message"].lower()


class TestRelease:
    @pytest.mark.asyncio
    async def test_release_clears_lock_and_grant(self, clean_conch):
        _make_holder()
        _register_local("w1")
        ConchQueue.grant("w1")
        res = await call(action="release")
        assert res["ok"] is True
        assert Conch.get_holder() is None
        assert ConchQueue.granted_to() is None

    @pytest.mark.asyncio
    async def test_release_when_free_is_idempotent(self, clean_conch):
        res = await call(action="release")
        assert res["ok"] is True
        assert "already free" in res["message"].lower()


# --------------------------------------------------------------------------- #
# Remote-waiter liveness (the expires TTL the MCP front end relies on)
# --------------------------------------------------------------------------- #

class TestRemoteLiveness:
    @pytest.mark.asyncio
    async def test_expired_remote_waiter_is_pruned(self, clean_conch):
        # A remote waiter (pid=None) whose TTL is in the past is pruned by list().
        ConchQueue.register("dead-remote", pid=None,
                            expires="2000-01-01T00:00:00")
        assert "dead-remote" not in _sessions()

    @pytest.mark.asyncio
    async def test_future_remote_waiter_survives(self, clean_conch):
        await call(action="callback", session_id="live-remote")
        assert "live-remote" in _sessions()  # future TTL => kept

    @pytest.mark.asyncio
    async def test_expired_remote_waiter_does_not_wedge_status(self, clean_conch):
        ConchQueue.register("dead-remote", pid=None,
                            expires="2000-01-01T00:00:00")
        res = await call(action="status")
        assert res["queue"] == []  # no wedged queue


# --------------------------------------------------------------------------- #
# No-divergence parity: MCP and CLI land the same state from the same start
# --------------------------------------------------------------------------- #

class TestParityWithCLI:
    @pytest.mark.asyncio
    async def test_give_parity(self, clean_conch, runner):
        _register_local("alpha-1", agent="alpha")
        _register_local("beta-2", agent="beta")
        await call(action="give", target="beta")
        mcp_state = _norm_state()
        mcp_grant_sid = _grant_file_dict()["session_id"]

        _clear_all()
        _register_local("alpha-1", agent="alpha")
        _register_local("beta-2", agent="beta")
        result = runner.invoke(conch_cli, ["give", "beta"])
        assert result.exit_code == 0
        cli_state = _norm_state()
        cli_grant_sid = _grant_file_dict()["session_id"]

        assert mcp_state == cli_state
        assert mcp_state["granted"] == "beta-2"
        assert mcp_grant_sid == cli_grant_sid == "beta-2"

    @pytest.mark.asyncio
    async def test_summon_parity(self, clean_conch, runner, monkeypatch):
        """MCP and CLI summon land the identical queue + grant state (SC5)."""
        monkeypatch.setattr(conch_ops, "_list_running_sessions",
                            lambda: [_running("run-1", agent="dora", cwd="/tmp/p")])
        monkeypatch.setattr("subprocess.run", lambda *a, **k: None)

        await call(action="give", target="dora")
        mcp_state = _norm_state()
        mcp_grant_sid = _grant_file_dict()["session_id"]

        _clear_all()
        result = runner.invoke(conch_cli, ["give", "dora"])
        assert result.exit_code == 0
        cli_state = _norm_state()
        cli_grant_sid = _grant_file_dict()["session_id"]

        assert mcp_state == cli_state
        assert mcp_state["granted"] == "run-1"
        assert mcp_state["queue"] == [("run-1", "callback")]
        assert mcp_grant_sid == cli_grant_sid == "run-1"

    @pytest.mark.asyncio
    async def test_bump_parity(self, clean_conch, runner):
        _make_holder(agent="holder", sid="holder-sess")
        _register_local("beta-2", agent="beta")
        await call(action="bump")
        mcp_state = _norm_state()

        _clear_all()
        _make_holder(agent="holder", sid="holder-sess")
        _register_local("beta-2", agent="beta")
        result = runner.invoke(conch_cli, ["bump"])
        assert result.exit_code == 0
        cli_state = _norm_state()

        assert mcp_state == cli_state
        assert mcp_state["holder"] is None
        assert mcp_state["granted"] == "beta-2"

    @pytest.mark.asyncio
    async def test_release_parity(self, clean_conch, runner):
        _make_holder(agent="holder", sid="holder-sess")
        _register_local("beta-2", agent="beta")
        ConchQueue.grant("beta-2")
        await call(action="release")
        mcp_state = _norm_state()

        _clear_all()
        _make_holder(agent="holder", sid="holder-sess")
        _register_local("beta-2", agent="beta")
        ConchQueue.grant("beta-2")
        result = runner.invoke(conch_cli, ["release", "-y"])
        assert result.exit_code == 0
        cli_state = _norm_state()

        assert mcp_state == cli_state
        assert mcp_state["holder"] is None
        assert mcp_state["granted"] is None  # grant cleared by release


# --------------------------------------------------------------------------- #
# Validation — clear errors, never tracebacks
# --------------------------------------------------------------------------- #

class TestValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("action", ["wait", "callback", "heartbeat", "leave"])
    async def test_session_required_actions_error_without_session(self, clean_conch, action):
        res = await call(action=action)
        assert res["ok"] is False
        assert "session_id" in res["message"]

    @pytest.mark.asyncio
    async def test_unknown_action_is_clear_error(self, clean_conch):
        res = await call(action="frobnicate")
        assert res["ok"] is False
        assert "unknown action" in res["message"].lower()
