"""Tests for the MCP ``conch`` tool (VM-1622).

The tool is a remote, streamable-HTTP front end with CLI parity over the same
on-disk conch state. Home isolation comes from the autouse
``isolate_home_directory`` fixture in conftest.py (re-pins ``Conch.LOCK_FILE``
into a per-test fake home; ``ConchQueue`` derives its paths from there), so the
whole conch state is isolated automatically.

Coverage mirrors the task's Testing Strategy:
- per-action unit tests (status / queue / wait / heartbeat / leave / give /
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


def _nudge_delivered(*a, **k):
    """``subprocess.run`` stand-in simulating a CONFIRMED-delivered nudge
    (VM-2078 D2): the summon path only grants when it can check this."""
    class _Result:
        returncode = 0
    return _Result()


def _nudge_failed(*a, **k):
    """``subprocess.run`` stand-in simulating an ATTEMPTED-but-failed nudge
    (no session match / tmux miss) — a non-zero exit, still no exception."""
    class _Result:
        returncode = 1
    return _Result()


def _tool():
    """The undecorated tool coroutine (FastMCP may wrap it as ``.fn``)."""
    return getattr(_conch_tool, "fn", _conch_tool)


async def call(**kwargs):
    return await _tool()(**kwargs)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _register_local(sid, *, agent=None):
    """Register a live LOCAL waiter (pid = current process)."""
    return ConchQueue.register(sid, agent=agent)


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
    the *meaningful* state (who holds, who is granted, who is queued) is what
    the two front ends must agree on.
    """
    return {
        "granted": ConchQueue.granted_to(),
        "holder": (Conch.get_holder() or {}).get("session_id"),
        "queue": [e.session_id for e in ConchQueue.list()],
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
        _register_local("beta-222", agent="beta")
        res = await call(action="status")
        assert res["holder"]["agent"] == "alpha"
        assert res["holder"]["session_id"] == "alpha-sess"
        assert [q["session_id"] for q in res["queue"]] == ["beta-222"]
        assert "mode" not in res["queue"][0]  # VM-2078: mode column removed


# --------------------------------------------------------------------------- #
# queue (the timeout-safe default for joining; VM-2078 D1 renamed from
# "callback" -- register-and-poll, never delivered a callback in the
# telephone sense)
# --------------------------------------------------------------------------- #

class TestQueue:
    @pytest.mark.asyncio
    async def test_queue_registers_remote_and_returns_position(self, clean_conch):
        res = await call(action="queue", session_id="remote-1", agent="r1")
        assert res["ok"] is True
        assert res["registered"] is True
        assert res["granted"] is False
        assert "mode" not in res  # VM-2078: no self-declared category field
        assert res["position"] == 1
        # Stays registered as a REMOTE waiter (pid is None) with a future TTL.
        entry = _entry("remote-1")
        assert entry is not None
        assert entry.pid is None
        assert entry.expires is not None
        assert res["expires"] == entry.expires

    @pytest.mark.asyncio
    async def test_queue_expires_is_in_the_future(self, clean_conch):
        from datetime import datetime
        res = await call(action="queue", session_id="remote-1")
        exp = parse_ts(res["expires"])
        assert exp is not None
        assert exp > datetime.now()


class TestCallbackRenamed:
    """D1: the literal string 'callback' is not a valid action any more --
    it returns a clear error naming the replacement, never a traceback and
    never the generic 'unknown action' message (so a caller upgrading from
    the old name gets pointed at exactly what changed)."""

    @pytest.mark.asyncio
    async def test_callback_is_a_named_error_not_a_generic_unknown_action(
        self, clean_conch
    ):
        res = await call(action="callback", session_id="remote-1")
        assert res["ok"] is False
        assert res["action"] == "callback"
        assert "queue" in res["message"].lower()
        assert "renamed" in res["message"].lower()
        # Never silently registers under the old name.
        assert _entry("remote-1") is None

    @pytest.mark.asyncio
    async def test_callback_is_case_insensitively_caught(self, clean_conch):
        res = await call(action="CallBack", session_id="remote-1")
        assert res["ok"] is False
        assert "queue" in res["message"].lower()


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
        _register_local("w1", agent="w1")
        assert ConchQueue.grant("w1") is True
        res = await call(action="wait", session_id="w1", timeout=5)
        assert res["granted"] is True
        assert _sessions() == []  # deregistered on grant

    @pytest.mark.asyncio
    async def test_wait_times_out_and_deregisters(self, clean_conch, monkeypatch):
        monkeypatch.setattr("voice_mode.tools.conch.CONCH_CHECK_INTERVAL", 0.02)
        _make_holder()  # live holder => never free for us
        # A separate granted waiter means our head-of-free path never fires.
        _register_local("other", agent="other")
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
        _register_local("other")
        ConchQueue.grant("other")
        res = await call(action="wait", session_id="w1", timeout=999)
        # min(timeout, cap) => the cap wins.
        assert res["cap_seconds"] == pytest.approx(0.1)
        assert res["granted"] is False


# --------------------------------------------------------------------------- #
# heartbeat (refresh TTL, keep place; VM-2078 do-003 also surfaces `granted`)
# --------------------------------------------------------------------------- #

class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_heartbeat_refreshes_expires_and_preserves_seq(self, clean_conch):
        first = await call(action="queue", session_id="r1")
        seq_before = _entry("r1").seq
        exp_before = first["expires"]

        res = await call(action="heartbeat", session_id="r1")
        assert res["ok"] is True
        assert "mode" not in res  # VM-2078: no self-declared category field
        assert res["granted"] is False
        entry = _entry("r1")
        assert entry.seq == seq_before  # place preserved
        # TTL moved forward (or stayed equal at worst — never earlier).
        assert parse_ts(res["expires"]) >= parse_ts(exp_before)

    @pytest.mark.asyncio
    async def test_heartbeat_when_not_registered_is_a_clear_error(self, clean_conch):
        res = await call(action="heartbeat", session_id="ghost")
        assert res["ok"] is False
        assert "not in the queue" in res["message"].lower()

    @pytest.mark.asyncio
    async def test_heartbeat_surfaces_granted_true_on_the_one_call_told_to_make(
        self, clean_conch
    ):
        """VM-2078 do-003: before this, a remote waiter's heartbeat could not
        tell it had been granted the floor — it needed a second,
        un-instructed status() call to find out. Now the one call the tool
        instructs it to make regularly IS the discovery channel."""
        await call(action="queue", session_id="r1")
        assert ConchQueue.grant("r1") is True

        res = await call(action="heartbeat", session_id="r1")
        assert res["ok"] is True
        assert res["granted"] is True
        assert "granted" in res["message"].lower()
        assert "claim_window_remaining" in res
        assert res["claim_window_remaining"] > 0

    @pytest.mark.asyncio
    async def test_heartbeat_not_granted_has_no_claim_window_key(self, clean_conch):
        await call(action="queue", session_id="r1")
        res = await call(action="heartbeat", session_id="r1")
        assert res["granted"] is False
        assert "claim_window_remaining" not in res


# --------------------------------------------------------------------------- #
# leave
# --------------------------------------------------------------------------- #

class TestLeave:
    @pytest.mark.asyncio
    async def test_leave_deregisters(self, clean_conch):
        await call(action="queue", session_id="r1")
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
    """give over MCP to a running non-waiter ⇒ summon (VM-1637), gated on the
    CHECKED, SURFACED nudge outcome (VM-2078 D2 amendment)."""

    @pytest.mark.asyncio
    async def test_summon_non_waiter_enqueues_and_grants_on_confirmed_delivery(
        self, clean_conch, monkeypatch
    ):
        monkeypatch.setattr(conch_ops, "_list_running_sessions",
                            lambda: [_running("run-1", agent="dora", cwd="/tmp/p")])
        monkeypatch.setattr("subprocess.run", _nudge_delivered)
        res = await call(action="give", target="dora")
        assert res["ok"] is True
        assert res["summoned"] is True
        assert res["target"] == "run-1"
        assert res["granted"] is True
        assert res["nudge"] == "delivered"
        entry = _entry("run-1")
        assert entry is not None and entry.pid == os.getpid()
        assert ConchQueue.granted_to() == "run-1"
        # D2: a confirmed-delivered summon nudge writes a BOUNDED, LONGER
        # claim window onto the grant record -- not the ordinary base TTL,
        # since the summoned target has no poll loop of its own.
        grant_payload = _grant_file_dict()
        assert grant_payload.get("claim_ttl") is not None

    @pytest.mark.asyncio
    async def test_summon_withholds_grant_when_nudge_fails(self, clean_conch, monkeypatch):
        """D2 amendment: an ATTEMPTED-but-failed nudge must NOT grant --
        handing the floor to a target just confirmed not to have been told
        is the original bug wearing a different hat. REFINE #1: the target
        must also be DEREGISTERED rather than left queued -- a queued entry
        nobody polls for would block every other waiter for a full claim
        window and then be evicted anyway, so leaving it behind would strand
        it (and everyone behind it), not protect it."""
        monkeypatch.setattr(conch_ops, "_list_running_sessions",
                            lambda: [_running("run-1", agent="dora", cwd="/tmp/p")])
        monkeypatch.setattr("subprocess.run", _nudge_failed)
        res = await call(action="give", target="dora")
        assert res["ok"] is True
        assert res["summoned"] is True
        assert res["granted"] is False
        assert res["nudge"] == "failed"
        assert "tell them yourself" in res["message"].lower()
        assert "not queu" in res["message"].lower()
        assert "wait_for_conch" in res["message"]
        assert ConchQueue.granted_to() is None
        entry = _entry("run-1")
        assert entry is None  # deregistered, not left stranded in the queue

    @pytest.mark.asyncio
    async def test_summon_withholds_grant_when_target_is_remote(self, clean_conch, monkeypatch):
        """D2 amendment: a remote target (no local pid) has NO nudge path at
        all -- must not be silently upgraded to 'delivered'. REFINE #1: also
        deregistered, same as the failed-nudge case."""
        # NOTE: _running()'s `pid=None` default means "use this live process"
        # (so the summoned waiter survives dead-PID cleanup) — construct the
        # RunningSession directly to get a genuinely pid-less (remote) target.
        remote = conch_ops.RunningSession(
            session_id="remote-run", pid=None, agent="dora", project_path=None,
        )
        monkeypatch.setattr(conch_ops, "_list_running_sessions", lambda: [remote])
        monkeypatch.setattr("subprocess.run", _nudge_delivered)  # must not even be reached
        res = await call(action="give", target="dora")
        assert res["ok"] is True
        assert res["granted"] is False
        assert res["nudge"] == "remote"
        assert "wait_for_conch" in res["message"]
        assert ConchQueue.granted_to() is None
        entry = _entry("remote-run")
        assert entry is None  # deregistered, not left stranded in the queue

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
    async def test_bump_reserves_first_waiter_during_clear_to_grant_gap(self, clean_conch, monkeypatch):
        _make_holder(agent="holder", sid="holder-sess")
        _register_local("bob", agent="bob")
        _register_local("sam", agent="sam")
        clear = conch_ops.force_clear_lock

        def probe_gap():
            clear()
            assert ConchQueue.granted_to() == "bob"
            assert Conch(agent_name="sam", session_id="sam").try_acquire() is False

        monkeypatch.setattr(conch_ops, "force_clear_lock", probe_gap)
        res = await call(action="bump")
        assert res["ok"] is True
        assert ConchQueue.granted_to() == "bob"
        assert Conch(agent_name="bob", session_id="bob").try_acquire() is True

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
        await call(action="queue", session_id="live-remote")
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
        monkeypatch.setattr("subprocess.run", _nudge_delivered)

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
        assert mcp_state["queue"] == ["run-1"]
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
    @pytest.mark.parametrize("action", ["wait", "queue", "heartbeat", "leave"])
    async def test_session_required_actions_error_without_session(self, clean_conch, action):
        res = await call(action=action)
        assert res["ok"] is False
        assert "session_id" in res["message"]

    @pytest.mark.asyncio
    async def test_unknown_action_is_clear_error(self, clean_conch):
        res = await call(action="frobnicate")
        assert res["ok"] is False
        assert "unknown action" in res["message"].lower()
