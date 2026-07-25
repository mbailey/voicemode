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
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import psutil
import pytest

from voice_mode.conch import Conch
from voice_mode.conch_queue import ConchQueue


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _write_entry(seq, session_id, *, pid=-1, expires=None, agent="other",
                 extra=None):
    """Write a raw queue entry file directly (simulating another registrant).

    ``pid=-1`` means "use the current process" (a live local waiter). Pass
    ``pid=None`` for a remote waiter, or an explicit int (e.g. a reaped, dead
    PID) to fabricate a stale local entry. ``extra`` merges in additional raw
    keys -- e.g. a legacy ``"mode": "callback"`` (VM-2078 dropped the field;
    ``from_dict`` must tolerate and discard an unknown key like this).
    """
    if pid == -1:
        pid = os.getpid()
    qdir = ConchQueue._queue_dir()
    qdir.mkdir(parents=True, exist_ok=True)
    if isinstance(expires, datetime):
        expires = expires.isoformat()
    path = qdir / ConchQueue._filename(seq, session_id)
    payload = {
        "session_id": session_id,
        "seq": seq,
        "agent": agent,
        "project_path": None,
        "voice": None,
        "pid": pid,
        "requested_at": datetime.now().isoformat(),
        "expires": expires,
    }
    if extra:
        payload.update(extra)
    path.write_text(json.dumps(payload))
    return path


def _dead_pid():
    """Spawn a child, let it exit, reap it -> a genuinely dead PID.

    subprocess instead of os.fork() so it also works on Windows.
    """
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert not psutil.pid_exists(proc.pid)
    return proc.pid


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
            "a", agent="cora", project_path="/p", voice="af_sky")
        entry = ConchQueue.head()
        assert entry.session_id == "a"
        assert entry.agent == "cora"
        assert entry.project_path == "/p"
        assert entry.voice == "af_sky"
        assert entry.pid == os.getpid()
        assert entry.requested_at is not None

    def test_register_rejects_mode_kwarg(self):
        """VM-2078 dropped the mode concept entirely -- register() no longer
        accepts it (no retain-and-ignore)."""
        with pytest.raises(TypeError):
            ConchQueue.register("a", mode="wait")

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
            "voice": None, "pid": None,
            "requested_at": datetime.now().isoformat(), "expires": zstr,
        }))
        assert [e.session_id for e in ConchQueue.list()] == ["rz"]

    def test_legacy_mode_key_is_tolerated_and_discarded(self):
        """VM-2078 Q1: a legacy on-disk entry carrying "mode": "callback" (plus
        any other unknown/future key) must not crash -- from_dict is
        field-explicit, so it is silently ignored, and the entry is granted
        like any ordinary waiter."""
        _write_entry(1, "legacy-cb", extra={"mode": "callback", "future_key": "x"})
        entries = ConchQueue.list()
        assert [e.session_id for e in entries] == ["legacy-cb"]
        assert not hasattr(entries[0], "mode")
        granted = ConchQueue.grant_next()
        assert granted.session_id == "legacy-cb"

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

    def test_grant_next_stamps_granted_at(self):
        ConchQueue.register("a")
        ConchQueue.grant_next()
        grant_payload = json.loads(ConchQueue._grant_file().read_text())
        assert grant_payload.get("granted_at") is not None

    def test_grant_stamps_granted_at(self):
        ConchQueue.register("a")
        ConchQueue.grant("a")
        grant_payload = json.loads(ConchQueue._grant_file().read_text())
        assert grant_payload.get("granted_at") is not None


# --------------------------------------------------------------------------- #
# VM-1967: grant claim TTL safety net -- a grant nobody ever claims self-heals
# past CONCH_GRANT_TTL instead of wedging the queue forever. VM-2078 removed
# the one exemption this TTL used to carry (callback mode) -- every grant is
# now covered, with no grant class exempt.
# --------------------------------------------------------------------------- #

class TestGrantTTLSafetyNet:
    def _backdate_grant(self, seconds):
        """Rewrite the on-disk grant with ``granted_at`` ``seconds`` in the past."""
        gf = ConchQueue._grant_file()
        g = json.loads(gf.read_text())
        g["granted_at"] = (datetime.now() - timedelta(seconds=seconds)).isoformat()
        ConchQueue._atomic_write_json(gf, g)

    def test_stale_grant_self_heals_and_promotes_next(self, monkeypatch):
        """The exact VM-1967 deadlock shape: a grant that is never claimed
        must NOT wedge the queue forever -- past CONCH_GRANT_TTL it is
        treated as abandoned, the stuck grantee is evicted, and the next live
        waiter is promoted, matching the manual `conch give` recovery an
        operator would otherwise have to perform.
        """
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        ConchQueue.register("stuck-head")
        ConchQueue.register("next-in-line")
        ConchQueue.grant_next()  # promotes stuck-head, never claimed
        assert ConchQueue.granted_to() == "stuck-head"

        self._backdate_grant(11)  # past the 10s TTL

        # A single read (mirroring any other waiter's poll, or a status
        # check) self-heals: the stuck head is evicted and the next waiter
        # promoted -- no manual intervention required.
        assert ConchQueue.granted_to() == "next-in-line"
        assert [e.session_id for e in ConchQueue.list()] == ["next-in-line"]

    def test_stale_grant_with_no_other_waiters_clears_to_free(self, monkeypatch):
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        ConchQueue.register("stuck-head")
        ConchQueue.grant_next()
        self._backdate_grant(11)

        assert ConchQueue.granted_to() is None
        assert ConchQueue.list() == []

    def test_fresh_grant_within_ttl_is_not_disturbed(self, monkeypatch):
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        ConchQueue.register("head")
        ConchQueue.grant_next()
        self._backdate_grant(5)  # within the 10s TTL

        assert ConchQueue.granted_to() == "head"
        assert "head" in [e.session_id for e in ConchQueue.list()]

    def test_lone_waiter_grant_is_no_longer_exempt(self, monkeypatch):
        """VM-2078: the exact wedge this task closes. Previously a lone
        callback waiter granted the head (nothing to starve) was EXEMPT from
        the TTL, so it never expired even when never claimed. There is no
        such exemption any more -- a lone head grant self-heals past TTL
        exactly like any other."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        ConchQueue.register("idle-waiter")
        ConchQueue.grant_next()  # only waiter -> grants head unchanged
        assert ConchQueue.granted_to() == "idle-waiter"

        self._backdate_grant(9999)  # ancient -- would have been exempt pre-VM-2078

        assert ConchQueue.granted_to() is None
        assert ConchQueue.list() == []

    def test_ttl_disabled_when_zero(self, monkeypatch):
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 0)
        ConchQueue.register("stuck-head")
        ConchQueue.grant_next()
        self._backdate_grant(9999)

        assert ConchQueue.granted_to() == "stuck-head"

    def test_missing_granted_at_is_stamped_on_first_sighting_then_judged_normally(
        self, monkeypatch
    ):
        """VM-2078 fix-002: a grant carrying no ``granted_at`` (predates
        VM-1967, or was written by something else) must NOT be exempt
        forever -- that is itself an un-expiring grant, exactly the class
        this task exists to eliminate. First read stamps it (persisted,
        atomic) and treats it as fresh-from-now; only once THAT stamp ages
        past the TTL is it judged wedged, same as any other grant.

        Supersedes the old ``test_legacy_grant_with_no_granted_at_is_not_
        treated_as_wedged``, which asserted the pre-fix-002 contract
        (exempt forever) -- that test encoded the bug this one closes, per
        the fix-002-prescription-corrected decision in progress.json.
        """
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        ConchQueue.register("a")
        ConchQueue._atomic_write_json(
            ConchQueue._grant_file(), {"session_id": "a", "seq": 1})

        # First sighting: judged fresh (not wedged), AND now stamped on disk
        # -- the bonus gap this closes: "no timestamp" no longer means
        # "exempt forever".
        assert ConchQueue.granted_to() == "a"
        grant_payload = json.loads(ConchQueue._grant_file().read_text())
        assert grant_payload.get("granted_at") is not None

        # Now that it carries a real stamp, ageing it past the TTL judges
        # and evicts it exactly like any other grant.
        self._backdate_grant(11)
        assert ConchQueue.granted_to() is None
        assert ConchQueue.list() == []

    def test_holder_gate_precedes_missing_granted_at_stamp(self, monkeypatch):
        """Order matters, not just presence (fix-002 checklist #1). With a
        missing ``granted_at`` AND a live holder, the holder gate must
        short-circuit FIRST -- if the granted_at parse ran first, a live
        holder would be irrelevant to the missing-timestamp branch, but the
        real risk is the reverse: the gate placed AFTER the parse would
        never run at all when the timestamp is malformed. Assert the
        stamp-on-first-sighting write from the missing-timestamp branch does
        NOT fire while the holder gate is the one short-circuiting."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        holder = Conch(agent_name="holder", session_id="holder")
        assert holder.try_acquire() is True
        try:
            ConchQueue.register("a")
            ConchQueue._atomic_write_json(
                ConchQueue._grant_file(), {"session_id": "a", "seq": 1})  # no granted_at

            assert ConchQueue.granted_to() == "a"  # holder gate -> not wedged
            grant_payload = json.loads(ConchQueue._grant_file().read_text())
            assert grant_payload.get("granted_at") is None  # gate ran first; no stamp write
        finally:
            holder.release()

    def test_give_during_live_holder_speech_survives_past_ttl(self, monkeypatch):
        """VM-2078 Q3 repro, inverted into a regression test. Reproduced
        against unmodified master with mode='wait' throughout (no callback
        involved): ``conch give`` while the holder is still speaking used to
        evaporate once the grant aged past ``CONCH_GRANT_TTL``, evicting the
        innocent, still-polling waiter. A grant cannot be judged wedged while
        a live holder still blocks the claim -- the grantee cannot claim
        yet, no matter how long ago the grant was issued."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        holder = Conch(agent_name="holder", session_id="holder")
        assert holder.try_acquire() is True
        try:
            ConchQueue.register("A")
            assert ConchQueue.grant("A") is True  # operator: `conch give A`
            self._backdate_grant(9999)  # ancient, but the holder is still speaking

            # Must NOT evaporate and must NOT evict the waiter -- this is the
            # exact bug reproduced against unmodified master.
            assert ConchQueue.granted_to() == "A"
            assert [e.session_id for e in ConchQueue.list()] == ["A"]
        finally:
            holder.release()

    def test_give_re_stamped_on_release_then_claims_normally(self, monkeypatch):
        """The companion half of the give-during-hold fix: when the holder
        finally releases, ``grant_next``'s honour-an-existing-give early
        return must re-stamp ``granted_at`` -- the claim window begins when
        the floor actually frees, not whenever the operator originally ran
        `conch give`. Without the re-stamp the grant is already ancient at
        the exact moment it becomes claimable and would be judged wedged on
        the very next read."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        holder = Conch(agent_name="holder", session_id="holder")
        assert holder.try_acquire() is True
        ConchQueue.register("A")
        assert ConchQueue.grant("A") is True
        self._backdate_grant(9999)  # already "ancient" while the holder still speaks

        holder.release()  # full release -> grant_next() honours the existing give

        grant_payload = json.loads(ConchQueue._grant_file().read_text())
        granted_at = datetime.fromisoformat(grant_payload["granted_at"])
        assert (datetime.now() - granted_at).total_seconds() < 2  # freshly re-stamped

        # And the grantee can now claim normally -- the re-stamp did not
        # merely avoid eviction, it produced a genuinely fresh claim window.
        a = Conch(agent_name="a", session_id="A")
        assert a.try_acquire() is True
        a.release()

    def test_stacked_wedged_grants_recursion_bound(self, monkeypatch):
        """``_current_grant``'s self-heal recursion (deregister -> grant_next
        -> recursive ``_current_grant``) goes from a rare path to a routine
        one once every grant is TTL-covered (no more callback exemption) --
        exercise it two deep: each self-heal promotes a freshly-stamped
        grant, so a single stale read never cascades past the next live
        waiter."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        ConchQueue.register("first")
        ConchQueue.register("second")
        ConchQueue.register("third")
        ConchQueue.grant_next()  # grants "first"
        self._backdate_grant(11)  # wedge #1

        # One read self-heals through the first wedge and lands on a fresh
        # grant for "second" -- not a second wedge, no stack blow-up.
        assert ConchQueue.granted_to() == "second"
        assert [e.session_id for e in ConchQueue.list()] == ["second", "third"]

        # Wedge the newly-promoted grant too -> self-heals again, to "third".
        self._backdate_grant(11)
        assert ConchQueue.granted_to() == "third"
        assert [e.session_id for e in ConchQueue.list()] == ["third"]

    def test_grant_age_seconds(self, monkeypatch):
        ConchQueue.register("a")
        assert ConchQueue.grant_age_seconds() is None  # no grant yet
        ConchQueue.grant_next()
        self._backdate_grant(5)
        age = ConchQueue.grant_age_seconds()
        assert age is not None and 4.5 <= age <= 6.0


# --------------------------------------------------------------------------- #
# VM-2078 fix-002: claim_ttl -- a bounded override on a SINGLE grant record,
# widening (never disabling, never a category on the waiter) the claim window
# from evidence the GRANTER directly observed -- e.g. a summon_and_grant nudge
# (D2) confirmed delivered. do-003 is the intended caller; this is the
# queue-side primitive it will drive once its checked-and-surfaced delivery
# result exists (see the "SHAPE SETTLED" note in fix-002's slice notes).
# --------------------------------------------------------------------------- #

class TestGrantClaimTTLOverride:
    def _backdate_grant(self, seconds):
        """Rewrite the on-disk grant with ``granted_at`` ``seconds`` in the past."""
        gf = ConchQueue._grant_file()
        g = json.loads(gf.read_text())
        g["granted_at"] = (datetime.now() - timedelta(seconds=seconds)).isoformat()
        ConchQueue._atomic_write_json(gf, g)

    def test_grant_without_claim_ttl_uses_base_ttl(self, monkeypatch):
        """Regression: an ordinary `grant()` call (no observed-delivery
        evidence passed) must be unaffected -- same base-TTL behaviour as
        before ``claim_ttl`` existed, and no stray key on the grant record."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        ConchQueue.register("a")
        assert ConchQueue.grant("a") is True
        grant_payload = json.loads(ConchQueue._grant_file().read_text())
        assert "claim_ttl" not in grant_payload

        self._backdate_grant(11)  # past the 10s base TTL
        assert ConchQueue.granted_to() is None  # evicted, same as always

    def test_claim_ttl_is_persisted_on_the_grant_record(self):
        ConchQueue.register("a")
        assert ConchQueue.grant("a", claim_ttl=90.0) is True
        grant_payload = json.loads(ConchQueue._grant_file().read_text())
        assert grant_payload.get("claim_ttl") == 90.0

    def test_claim_ttl_widens_the_window_past_the_base_ttl(self, monkeypatch):
        """The whole point of the override: a summoned session (D2) with a
        CONFIRMED-delivered nudge must survive well past the ordinary
        poll-loop TTL, since it has no poll loop -- but the window stays
        FINITE, not exempt."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        ConchQueue.register("summoned")
        assert ConchQueue.grant("summoned", claim_ttl=90.0) is True

        self._backdate_grant(30)  # past the 10s base TTL, well within 90s
        assert ConchQueue.granted_to() == "summoned"  # survives -- override applies

        self._backdate_grant(91)  # past the claim_ttl override too
        assert ConchQueue.granted_to() is None  # still finite -- eventually evicted
        assert ConchQueue.list() == []

    def test_claim_ttl_survives_the_re_stamp_on_release(self, monkeypatch):
        """``grant_next()``'s honour-an-existing-give re-stamp (VM-2078 Q3)
        must PRESERVE a ``claim_ttl`` override, not silently drop it back to
        the base TTL -- the moment the floor frees is exactly when a
        summoned session most needs its widened window."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        holder = Conch(agent_name="holder", session_id="holder")
        assert holder.try_acquire() is True
        ConchQueue.register("summoned")
        assert ConchQueue.grant("summoned", claim_ttl=90.0) is True

        holder.release()  # -> grant_next() honours the existing give, re-stamps

        grant_payload = json.loads(ConchQueue._grant_file().read_text())
        assert grant_payload.get("claim_ttl") == 90.0
        granted_at = datetime.fromisoformat(grant_payload["granted_at"])
        assert (datetime.now() - granted_at).total_seconds() < 2  # freshly re-stamped

        self._backdate_grant(30)  # past the base 10s, within the preserved 90s
        assert ConchQueue.granted_to() == "summoned"

    def test_disabled_base_ttl_ignores_claim_ttl_too(self, monkeypatch):
        """``CONCH_GRANT_TTL=0`` is the administrative "disable the safety
        net entirely" switch -- a per-grant ``claim_ttl`` override must not
        partially re-enable judgement while the base is off."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 0)
        ConchQueue.register("a")
        assert ConchQueue.grant("a", claim_ttl=5.0) is True
        self._backdate_grant(9999)
        assert ConchQueue.granted_to() == "a"

    def test_remote_head_promotion_gets_the_remote_claim_window(self, monkeypatch):
        """REFINE #1 (fix-002, retry 1/3): ``claim_ttl`` is only ever written
        by ``grant()`` -- the SUMMON path. ``grant_next()``'s ordinary
        HEAD-PROMOTION never wrote it, so a REMOTE waiter (``pid=None``,
        whose claim is a heartbeat/status round trip) promoted on release
        was judged against the local poll-cycle window and evicted before
        it could structurally ever claim in time -- a regression this
        branch introduced by removing callback mode's TTL exemption without
        giving ordinary-promoted remote waiters a correct window.

        Restored in the shape the reviewer asked for: monkeypatch BOTH
        getters so it reads like its neighbours, promote a ``pid=None``
        waiter via ``grant_next()`` (the ordinary promotion path -- the
        uncovered one, not ``grant()``'s summon path), then assert the
        window is bounded, not exempt: survives the local TTL, still
        eventually evicted past the remote one.
        """
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        monkeypatch.setattr("voice_mode.conch_queue._get_remote_ttl", lambda: 60.0)
        ConchQueue.register("remote-waiter", pid=None)
        assert ConchQueue.grant_next() is not None  # ordinary head-promotion

        grant_payload = json.loads(ConchQueue._grant_file().read_text())
        assert grant_payload.get("claim_ttl") == 60.0  # max(10, 60)

        self._backdate_grant(30)  # past the 10s local TTL, within the 60s remote one
        assert ConchQueue.granted_to() == "remote-waiter"  # survives -- can still claim

        self._backdate_grant(9999)  # past the remote TTL too
        assert ConchQueue.granted_to() is None  # still finite -- eventually evicted
        assert ConchQueue.list() == []

    def test_local_head_promotion_is_unaffected_by_the_remote_window(self, monkeypatch):
        """Companion to the remote case: an ordinary LOCAL promotion (a real
        ``pid``) must carry no ``claim_ttl`` at all and keep using the base
        TTL exactly as before -- the remote window is scoped to ``pid is
        None``, not a blanket widening of every head-promotion."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        monkeypatch.setattr("voice_mode.conch_queue._get_remote_ttl", lambda: 60.0)
        ConchQueue.register("local-waiter")  # defaults pid to this process
        assert ConchQueue.grant_next() is not None

        grant_payload = json.loads(ConchQueue._grant_file().read_text())
        assert "claim_ttl" not in grant_payload

        self._backdate_grant(11)  # past the 10s base TTL
        assert ConchQueue.granted_to() is None  # evicted, same as always

    def test_give_to_a_remote_waiter_with_no_explicit_claim_ttl_gets_the_remote_window(
        self, monkeypatch
    ):
        """REFINE #2 (fix-002, retry 2/3): ``claim_ttl`` was previously only
        ever defaulted by ``grant_next()``'s ordinary head-promotion
        (REFINE #1). ``grant()`` -- the ``conch give`` / summon path -- still
        wrote a BASE-TTL grant whenever its caller passed no ``claim_ttl``,
        even when the target waiter has no local ``pid``: ``tools/conch.py``
        ``_do_give`` and the CLI ``give`` both call ``grant()`` with no
        ``claim_ttl``, so 'conch give' to a remote waiter was the same
        unwinnable heartbeat-round-trip arithmetic as REFINE #1's bug,
        through a different door.

        The fix lives in ``grant()`` (via the shared ``_write_grant_decision``
        writer), not in its call sites, so no caller has to remember it.
        Asserts both halves of the bounded window: survives past the base
        TTL, still eventually evicted past the remote one -- not a new
        exemption."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        monkeypatch.setattr("voice_mode.conch_queue._get_remote_ttl", lambda: 60.0)
        ConchQueue.register("remote-waiter", pid=None)
        assert ConchQueue.grant("remote-waiter") is True  # no explicit claim_ttl

        grant_payload = json.loads(ConchQueue._grant_file().read_text())
        assert grant_payload.get("claim_ttl") == 60.0  # max(10, 60)

        self._backdate_grant(30)  # past the 10s local TTL, within the 60s remote one
        assert ConchQueue.granted_to() == "remote-waiter"  # survives -- can still claim

        self._backdate_grant(9999)  # past the remote TTL too
        assert ConchQueue.granted_to() is None  # still finite -- eventually evicted
        assert ConchQueue.list() == []

    def test_give_to_a_remote_waiter_with_an_explicit_claim_ttl_still_wins(
        self, monkeypatch
    ):
        """The caller-supplied override must still win over the pid-based
        fallback -- a summon carve-out that has real delivery evidence
        should not be silently overridden by the structural pid-is-None
        default."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        monkeypatch.setattr("voice_mode.conch_queue._get_remote_ttl", lambda: 60.0)
        ConchQueue.register("remote-waiter", pid=None)
        assert ConchQueue.grant("remote-waiter", claim_ttl=5.0) is True

        grant_payload = json.loads(ConchQueue._grant_file().read_text())
        assert grant_payload.get("claim_ttl") == 5.0  # explicit value, not max(10, 60)

        self._backdate_grant(6)  # past the explicit 5s override
        assert ConchQueue.granted_to() is None  # evicted per the explicit override


# --------------------------------------------------------------------------- #
# VM-2078 do-003: remote_claim_window / claim_window_remaining
#
# remote_claim_window() is the single source of truth _write_grant_decision's
# pid-based fallback (tested above via TestGrantClaimTTLOverride) already
# exercises indirectly; these tests cover it -- and the heartbeat-facing
# claim_window_remaining() -- directly.
# --------------------------------------------------------------------------- #

class TestRemoteClaimWindow:
    def test_is_max_of_base_and_remote_ttl(self, monkeypatch):
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        monkeypatch.setattr("voice_mode.conch_queue._get_remote_ttl", lambda: 60.0)
        assert ConchQueue.remote_claim_window() == 60.0

    def test_never_narrows_an_administratively_widened_base_ttl(self, monkeypatch):
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 300.0)
        monkeypatch.setattr("voice_mode.conch_queue._get_remote_ttl", lambda: 90.0)
        assert ConchQueue.remote_claim_window() == 300.0

    def test_summon_confirmed_delivered_uses_it_as_the_explicit_claim_ttl(
        self, monkeypatch
    ):
        """The exact do-003/fix-002 interlock: a LOCAL-pid summon target
        (nudged, not polling) still needs the bounded window, via an
        explicit ``claim_ttl`` -- ``grant()``'s own pid-based fallback would
        NOT fire for it (it has a pid), so the caller must pass it."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        monkeypatch.setattr("voice_mode.conch_queue._get_remote_ttl", lambda: 60.0)
        ConchQueue.register("summoned-local")  # local pid -- nudged, not polling
        assert ConchQueue.grant(
            "summoned-local", claim_ttl=ConchQueue.remote_claim_window()
        ) is True
        grant_payload = json.loads(ConchQueue._grant_file().read_text())
        assert grant_payload.get("claim_ttl") == 60.0


class TestClaimWindowRemaining:
    def _backdate_grant(self, seconds):
        gf = ConchQueue._grant_file()
        payload = json.loads(gf.read_text())
        past = datetime.now() - timedelta(seconds=seconds)
        payload["granted_at"] = past.isoformat()
        gf.write_text(json.dumps(payload))

    def test_none_when_not_the_current_grantee(self):
        ConchQueue.register("a")
        ConchQueue.register("b")
        ConchQueue.grant_next()  # grants "a"
        assert ConchQueue.claim_window_remaining("b") is None

    def test_none_when_no_grant_at_all(self):
        ConchQueue.register("a")
        assert ConchQueue.claim_window_remaining("a") is None

    def test_full_window_right_after_grant(self, monkeypatch):
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 30.0)
        ConchQueue.register("a")
        ConchQueue.grant_next()
        remaining = ConchQueue.claim_window_remaining("a")
        assert remaining is not None
        assert remaining == pytest.approx(30.0, abs=1.0)

    def test_counts_down_and_reflects_a_claim_ttl_override(self, monkeypatch):
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        ConchQueue.register("summoned")
        assert ConchQueue.grant("summoned", claim_ttl=90.0) is True
        self._backdate_grant(30)
        remaining = ConchQueue.claim_window_remaining("summoned")
        assert remaining == pytest.approx(60.0, abs=1.0)  # 90 - 30

    def test_never_negative_once_past_the_window(self, monkeypatch):
        """Past the window the grant is ordinarily self-healed away (evicted)
        on the very next judged read, so there is no "stale but still
        present" case to clamp -- UNLESS a live holder still gates the
        judgement (fix-002's holder gate: a grant cannot be wedged while the
        floor is still occupied). That is the one real case where
        ``claim_window_remaining`` sees a grant whose TTL has already run out
        and must clamp rather than go negative."""
        monkeypatch.setattr("voice_mode.conch_queue._get_grant_ttl", lambda: 10.0)
        Conch(session_id="holder-sess").acquire(agent_name="holder")
        ConchQueue.register("a")
        assert ConchQueue.grant("a") is True
        self._backdate_grant(9999)
        assert ConchQueue.claim_window_remaining("a") == 0.0


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
