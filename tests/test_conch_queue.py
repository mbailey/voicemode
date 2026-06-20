"""Tests for the ConchQueue ordered waiter registry (VM-1613).

Home isolation is provided by the autouse ``isolate_home_directory`` fixture in
conftest.py, which re-pins ``Conch.LOCK_FILE`` into a per-test fake home.
ConchQueue derives all its paths from ``Conch.LOCK_FILE.parent``, so the whole
queue lives inside that isolated home automatically. Spawned subprocesses
re-import fresh and do NOT inherit the monkeypatch, so concurrency tests pass
the isolated lock path explicitly and re-pin it (see ``_pin_lock_file``).
"""

import json
import multiprocessing
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from voice_mode.conch import Conch
from voice_mode.conch_queue import ConchQueue, WaiterEntry


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _write_entry(seq, session_id, *, pid=-1, expires=None, agent="other",
                 mode="wait"):
    """Write a raw queue entry file directly (simulating another registrant).

    ``pid=-1`` means "use the current process" (a live local waiter). Pass
    ``pid=None`` for a remote waiter, or an explicit int (e.g. a reaped, dead
    PID) to fabricate a stale local entry.
    """
    if pid == -1:
        pid = os.getpid()
    qdir = ConchQueue._queue_dir()
    qdir.mkdir(parents=True, exist_ok=True)
    if isinstance(expires, datetime):
        expires = expires.isoformat()
    path = qdir / ConchQueue._filename(seq, session_id)
    path.write_text(json.dumps({
        "session_id": session_id,
        "seq": seq,
        "agent": agent,
        "project_path": None,
        "voice": None,
        "pid": pid,
        "mode": mode,
        "requested_at": datetime.now().isoformat(),
        "expires": expires,
    }))
    return path


def _dead_pid():
    """Fork a child, let it exit, reap it -> a genuinely dead PID."""
    pid = os.fork()
    if pid == 0:
        os._exit(0)
    os.waitpid(pid, 0)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
    return pid


# --------------------------------------------------------------------------- #
# Register / order / position
# --------------------------------------------------------------------------- #

class TestRegisterOrder:
    def test_register_returns_position(self):
        assert ConchQueue.register("a") == 1
        assert ConchQueue.register("b") == 2
        assert ConchQueue.register("c") == 3

    def test_list_and_head_agree_in_order(self):
        ConchQueue.register("a")
        ConchQueue.register("b")
        ConchQueue.register("c")

        order = [e.session_id for e in ConchQueue.list()]
        assert order == ["a", "b", "c"]
        assert ConchQueue.head().session_id == "a"

    def test_seq_is_monotonic_and_orders_entries(self):
        ConchQueue.register("a")
        ConchQueue.register("b")
        seqs = [e.seq for e in ConchQueue.list()]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == 2  # distinct

    def test_register_persists_all_fields(self):
        ConchQueue.register(
            "a", agent="cora", project_path="/p", voice="af_sky", mode="callback")
        entry = ConchQueue.head()
        assert entry.session_id == "a"
        assert entry.agent == "cora"
        assert entry.project_path == "/p"
        assert entry.voice == "af_sky"
        assert entry.mode == "callback"
        assert entry.pid == os.getpid()
        assert entry.requested_at is not None

    def test_empty_queue_head_is_none(self):
        assert ConchQueue.head() is None
        assert ConchQueue.list() == []

    def test_register_requires_session_id(self):
        with pytest.raises(ValueError):
            ConchQueue.register(None)


# --------------------------------------------------------------------------- #
# Idempotent re-register
# --------------------------------------------------------------------------- #

class TestReregister:
    def test_reregister_keeps_earliest_seq(self):
        ConchQueue.register("a")
        ConchQueue.register("b")
        first_seq = ConchQueue._find("a")[0].seq

        # a re-registers: must keep its place (seq), not jump to the back.
        pos = ConchQueue.register("a", voice="new_voice")
        assert pos == 1
        again = ConchQueue._find("a")[0]
        assert again.seq == first_seq
        assert again.voice == "new_voice"  # mutable fields updated
        # Still exactly two waiters, a still ahead of b.
        assert [e.session_id for e in ConchQueue.list()] == ["a", "b"]

    def test_reregister_preserves_requested_at(self):
        ConchQueue.register("a")
        first = ConchQueue._find("a")[0].requested_at
        time.sleep(0.01)
        ConchQueue.register("a")
        assert ConchQueue._find("a")[0].requested_at == first

    def test_reregister_does_not_create_duplicate_file(self):
        ConchQueue.register("a")
        ConchQueue.register("a")
        ConchQueue.register("a")
        files = list(ConchQueue._queue_dir().glob("*.json"))
        assert len(files) == 1


# --------------------------------------------------------------------------- #
# Deregister
# --------------------------------------------------------------------------- #

class TestDeregister:
    def test_deregister_removes_entry(self):
        ConchQueue.register("a")
        ConchQueue.register("b")
        ConchQueue.deregister("a")
        assert [e.session_id for e in ConchQueue.list()] == ["b"]

    def test_deregister_is_safe_to_call_twice(self):
        ConchQueue.register("a")
        ConchQueue.deregister("a")
        # Second call must not raise and must be a no-op.
        ConchQueue.deregister("a")
        assert ConchQueue.list() == []

    def test_deregister_absent_session_is_noop(self):
        ConchQueue.deregister("never-registered")  # no error
        assert ConchQueue.list() == []


# --------------------------------------------------------------------------- #
# Stale cleanup
# --------------------------------------------------------------------------- #

class TestCleanup:
    def test_dead_local_pid_is_removed_on_list(self):
        dead = _dead_pid()
        _write_entry(1, "dead", pid=dead)
        ConchQueue.register("alive")  # live local waiter (our pid)

        order = [e.session_id for e in ConchQueue.list()]
        assert order == ["alive"]
        assert "dead" not in order

    def test_dead_local_pid_at_head_is_removed(self):
        dead = _dead_pid()
        _write_entry(1, "dead", pid=dead)   # lowest seq
        _write_entry(2, "alive", pid=os.getpid())
        assert ConchQueue.head().session_id == "alive"

    def test_remote_expired_heartbeat_is_removed(self):
        # Remote waiter (pid None) whose heartbeat TTL has already passed.
        _write_entry(1, "remote-stale", pid=None,
                     expires=datetime.now() - timedelta(seconds=30))
        assert ConchQueue.list() == []

    def test_remote_live_heartbeat_is_kept(self):
        _write_entry(1, "remote-live", pid=None,
                     expires=datetime.now() + timedelta(seconds=300))
        order = [e.session_id for e in ConchQueue.list()]
        assert order == ["remote-live"]

    def test_remote_tz_aware_future_heartbeat_is_kept(self):
        # A cross-machine remote agent naturally heartbeats with a tz-aware UTC
        # expiry. It must survive cleanup, not be pruned by a naive-vs-aware
        # comparison (VM-1613 review fix).
        _write_entry(1, "remote-utc", pid=None,
                     expires=datetime.now(timezone.utc) + timedelta(seconds=300))
        assert [e.session_id for e in ConchQueue.list()] == ["remote-utc"]

    def test_remote_tz_aware_expired_heartbeat_is_removed(self):
        # The same tz-aware path must still expire a stale heartbeat.
        _write_entry(1, "remote-utc-stale", pid=None,
                     expires=datetime.now(timezone.utc) - timedelta(seconds=30))
        assert ConchQueue.list() == []

    def test_remote_z_suffixed_heartbeat_is_parsed(self):
        # The 'Z' UTC designator (rejected by 3.10's fromisoformat) must be
        # tolerated, else a live remote waiter is wrongly pruned.
        qdir = ConchQueue._queue_dir()
        qdir.mkdir(parents=True, exist_ok=True)
        zstr = (datetime.now(timezone.utc) + timedelta(seconds=300)
                ).isoformat().replace("+00:00", "Z")
        (qdir / ConchQueue._filename(1, "rz")).write_text(json.dumps({
            "session_id": "rz", "seq": 1, "agent": "remote", "project_path": None,
            "voice": None, "pid": None, "mode": "wait",
            "requested_at": datetime.now().isoformat(), "expires": zstr,
        }))
        assert [e.session_id for e in ConchQueue.list()] == ["rz"]

    def test_register_remote_with_tz_aware_expires_persists(self):
        # End-to-end via the public API: registering a remote waiter with a
        # tz-aware UTC heartbeat must return its real position and survive the
        # cleanup that register() itself runs to compute that position.
        pos = ConchQueue.register(
            "remote", pid=None,
            expires=datetime.now(timezone.utc) + timedelta(seconds=300))
        assert pos == 1
        assert [e.session_id for e in ConchQueue.list()] == ["remote"]

    def test_corrupt_entry_is_removed(self):
        qdir = ConchQueue._queue_dir()
        qdir.mkdir(parents=True, exist_ok=True)
        (qdir / "000001-broken.json").write_text("not json {{{")
        ConchQueue.register("good")
        assert [e.session_id for e in ConchQueue.list()] == ["good"]

    def test_cleanup_stale_is_idempotent(self):
        dead = _dead_pid()
        _write_entry(1, "dead", pid=dead)
        ConchQueue.cleanup_stale()
        ConchQueue.cleanup_stale()  # no error second time
        assert ConchQueue.list() == []


# --------------------------------------------------------------------------- #
# Grant hint
# --------------------------------------------------------------------------- #

class TestGrant:
    def test_grant_next_picks_head(self):
        ConchQueue.register("a")
        ConchQueue.register("b")
        granted = ConchQueue.grant_next()
        assert granted.session_id == "a"
        assert ConchQueue.granted_to() == "a"
        assert ConchQueue.is_granted("a") is True
        assert ConchQueue.is_granted("b") is False

    def test_grant_next_empty_queue_returns_none(self):
        assert ConchQueue.grant_next() is None
        assert ConchQueue.granted_to() is None

    def test_grant_cleared_when_grantee_deregisters(self):
        ConchQueue.register("a")
        ConchQueue.register("b")
        ConchQueue.grant_next()  # grants a
        ConchQueue.deregister("a")
        assert ConchQueue.granted_to() is None  # stale grant cleared

    def test_grant_invalidated_when_grantee_dies(self):
        dead = _dead_pid()
        _write_entry(1, "dead-grantee", pid=dead)
        _write_entry(2, "b", pid=os.getpid())
        # Manually grant the (soon-detected-dead) head, then query.
        ConchQueue._atomic_write_json(
            ConchQueue._grant_file(), {"session_id": "dead-grantee", "seq": 1})
        # granted_to runs cleanup: the dead grantee's entry goes, grant invalid.
        assert ConchQueue.granted_to() is None

    def test_clear_grant(self):
        ConchQueue.register("a")
        ConchQueue.grant_next()
        ConchQueue.clear_grant()
        assert ConchQueue.granted_to() is None
        assert ConchQueue.clear_grant() is None  # idempotent / no error

    def test_is_granted_none_session(self):
        ConchQueue.register("a")
        ConchQueue.grant_next()
        assert ConchQueue.is_granted(None) is False

    def test_grant_named_waiter(self):
        ConchQueue.register("a")
        ConchQueue.register("b")
        assert ConchQueue.grant("b") is True   # grant the non-head explicitly
        assert ConchQueue.granted_to() == "b"
        assert ConchQueue.grant("ghost") is False  # not a waiter
        assert ConchQueue.granted_to() == "b"      # unchanged

    def test_grant_next_respects_explicit_give(self):
        # An explicit give (conch give) sets a grant for a non-head waiter; a
        # later head-promotion on the holder's release must NOT clobber it.
        ConchQueue.register("a")  # head
        ConchQueue.register("b")
        ConchQueue.grant("b")     # operator gave the conch to b
        granted = ConchQueue.grant_next()  # holder releases -> promote next
        assert granted.session_id == "b"   # give stands, not head 'a'
        assert ConchQueue.granted_to() == "b"

    def test_grant_next_falls_through_when_give_is_stale(self):
        # A give to a dead/departed waiter must not wedge the queue: grant_next
        # clears the stale grant and promotes the head instead.
        ConchQueue.register("a")  # head, live
        ConchQueue._atomic_write_json(
            ConchQueue._grant_file(), {"session_id": "gone", "seq": 99})
        granted = ConchQueue.grant_next()
        assert granted.session_id == "a"
        assert ConchQueue.granted_to() == "a"


# --------------------------------------------------------------------------- #
# Conch <-> queue integration (try_acquire grant-respect, release promotion)
# --------------------------------------------------------------------------- #

class TestConchIntegration:
    def test_grant_blocks_non_grantee_acquire(self):
        ConchQueue.register("a")
        ConchQueue.register("b")
        ConchQueue.grant_next()  # grants a

        # b is NOT the grantee -> must not steal the floor.
        b = Conch(agent_name="b", session_id="b")
        assert b.try_acquire() is False

        # a IS the grantee -> acquires, and on acquiring leaves the queue and
        # consumes the grant.
        a = Conch(agent_name="a", session_id="a")
        assert a.try_acquire() is True
        assert ConchQueue.granted_to() is None
        assert ConchQueue._find("a")[0] is None  # deregistered on acquire
        a.release()

    def test_release_promotes_head(self):
        # Two agents waiting behind a holder.
        ConchQueue.register("w1")
        ConchQueue.register("w2")

        holder = Conch(agent_name="holder", session_id="holder")
        assert holder.try_acquire() is True
        # Full release must promote the head of the queue.
        holder.release()
        assert ConchQueue.granted_to() == "w1"

    def test_hold_does_not_promote(self):
        ConchQueue.register("w1")
        holder = Conch(agent_name="holder", session_id="holder")
        assert holder.try_acquire() is True
        holder.release(hold=True)  # keep the floor between turns
        assert ConchQueue.granted_to() is None  # no promotion on hold
        # Clean up the hold.
        holder.try_acquire()
        holder.release()

    def test_full_fifo_progression(self):
        """Head acquires, releases, next is promoted -- strict FIFO."""
        ConchQueue.register("w1")
        ConchQueue.register("w2")

        # Simulate the prior holder releasing -> w1 granted.
        ConchQueue.grant_next()
        assert ConchQueue.granted_to() == "w1"

        # w2 cannot jump the line.
        w2 = Conch(agent_name="w2", session_id="w2")
        assert w2.try_acquire() is False

        # w1 acquires (leaves queue, clears grant), then releases -> w2 promoted.
        w1 = Conch(agent_name="w1", session_id="w1")
        assert w1.try_acquire() is True
        w1.release()
        assert ConchQueue.granted_to() == "w2"

        # Now w2 can acquire.
        assert w2.try_acquire() is True
        w2.release()
        assert ConchQueue.list() == []

    def test_no_queue_acquire_is_unchanged(self):
        """With no waiters/grant, try_acquire/release behave exactly as before."""
        c = Conch(agent_name="solo", session_id="solo")
        assert c.try_acquire() is True
        assert Conch.is_active() is True
        c.release()
        assert Conch.is_active() is False


# --------------------------------------------------------------------------- #
# Concurrency (subprocesses)
# --------------------------------------------------------------------------- #

def _pin_lock_file(lock_file):
    """Point this (possibly spawned) process's Conch at the isolated lock path,
    so ConchQueue derives the same isolated directory as the parent test."""
    if lock_file is not None:
        Conch.LOCK_FILE = lock_file
        Conch.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)


def _register_worker(session_id, queue, lock_file, expires):
    """Register concurrently, then report the allocated seq.

    Registers as a *remote* waiter (pid=None) with a far-future heartbeat TTL
    so the entry survives this short-lived process exiting -- otherwise the
    parent's final read would (correctly) prune it as a dead local PID before
    it could verify the total order. The concurrency-sensitive path (the
    flock-guarded seq counter) is exercised identically either way.
    """
    _pin_lock_file(lock_file)
    seq = None
    try:
        ConchQueue.register(session_id, pid=None, expires=expires)
        entry = ConchQueue._find(session_id)[0]
        seq = entry.seq if entry else None
    finally:
        queue.put((session_id, seq))


class TestConcurrency:
    def test_concurrent_registration_yields_distinct_order(self):
        """N processes registering concurrently get distinct seqs and a stable
        total order that every reader agrees on."""
        n = 6
        results = multiprocessing.Queue()
        lock_file = Conch.LOCK_FILE  # the isolated path pinned by conftest
        expires = (datetime.now() + timedelta(seconds=300)).isoformat()

        procs = [
            multiprocessing.Process(
                target=_register_worker, args=(f"s{i}", results, lock_file, expires))
            for i in range(n)
        ]
        for p in procs:
            p.start()
        for p in procs:
            p.join(timeout=10)

        seen = {}
        while not results.empty():
            sid, seq = results.get()
            seen[sid] = seq

        assert len(seen) == n, f"expected {n} registrants, got {seen}"
        # Every process got a seq, and all seqs are distinct (the flock-guarded
        # counter handed out no duplicates).
        seqs = [s for s in seen.values() if s is not None]
        assert len(seqs) == n
        assert len(set(seqs)) == n, f"duplicate seqs allocated: {seqs}"

        # The parent reader agrees: every registrant is present, ordered by seq.
        entries = ConchQueue.list()
        assert {e.session_id for e in entries} == set(seen)
        ordered_seqs = [e.seq for e in entries]
        assert ordered_seqs == sorted(ordered_seqs)
