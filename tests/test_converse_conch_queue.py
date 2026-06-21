"""Tests for converse()'s conch-queue integration (VM-1619).

When the conch is busy, ``converse`` no longer blind-polls. It is a first-class
participant in the VM-1613 waiter queue:

- ``wait_for_conch`` falsy (default): return IMMEDIATELY with a status, NEVER
  queue (Mike's hard constraint — never silently block an opt-out caller).
- ``wait_for_conch`` truthy: ``ConchQueue.register`` then branch on
  ``conch_mode``:
    - ``wait``     — block until granted (FIFO via the grant hint), bounded by
                     timeout; deregister cleanly on timeout.
    - ``callback`` — register and return immediately with the position, staying
                     registered; the turn is pushed out-of-band when granted
                     (a session nudge via ``conch_notify.notify_granted``, VM-1625).

Home isolation comes from the autouse ``isolate_home_directory`` fixture in
conftest.py, which re-pins ``Conch.LOCK_FILE`` into a per-test fake home;
``ConchQueue`` derives all its paths from ``Conch.LOCK_FILE.parent``, so the
whole queue lives in that isolated home automatically.

The two positive WAIT tests use a REAL in-process conch holder (an ``fcntl``
flock conflicts even between two fds in the same process), so ``try_acquire``
is exercised for real — only ``text_to_speech_with_failover`` is mocked, since
faithfully producing audio is irrelevant to the queue logic.
"""

import asyncio

import pytest
from unittest.mock import patch

from voice_mode.conch import Conch
from voice_mode.conch_queue import ConchQueue


def _converse():
    """The undecorated converse coroutine (FastMCP wraps it as ``.fn``)."""
    from voice_mode.tools.converse import converse
    return getattr(converse, "fn", converse)


def _sessions():
    """Session ids currently in the live queue, in order."""
    return [e.session_id for e in ConchQueue.list()]


def _entry(session_id):
    """The live queue entry for ``session_id`` (or None)."""
    for e in ConchQueue.list():
        if e.session_id == session_id:
            return e
    return None


@pytest.fixture
def clean_conch():
    """No conch lock or queue state before/after each test."""
    if Conch.LOCK_FILE.exists():
        Conch.LOCK_FILE.unlink()
    for e in ConchQueue.list():
        ConchQueue.deregister(e.session_id)
    ConchQueue.clear_grant()
    yield
    if Conch.LOCK_FILE.exists():
        Conch.LOCK_FILE.unlink()


FAKE_HOLDER = {"pid": 999999, "agent": "other_agent", "session_id": "holder-x"}


# --------------------------------------------------------------------------- #
# wait_for_conch falsy — immediate return, NEVER queue (back-compat + Mike's rule)
# --------------------------------------------------------------------------- #

class TestFalsyGateNeverQueues:
    @pytest.mark.asyncio
    async def test_busy_falsy_returns_immediately_no_registration(self, clean_conch):
        """Busy + wait_for_conch=False → immediate status, and NO queue entry."""
        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            result = await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=False,
                session_id="sess-a",
            )

        assert "other_agent" in result
        assert "NOT queued" in result
        # The opt-out caller must not be left registered anywhere.
        assert _sessions() == [], f"falsy gate must not register a waiter; got {_sessions()}"

    @pytest.mark.asyncio
    async def test_falsy_message_advertises_both_modes(self, clean_conch):
        """The immediate status tells the agent it can wait OR request a callback."""
        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            result = await _converse()(
                message="Hello",
                wait_for_response=False,
                session_id="sess-a",
            )
        assert "wait_for_conch=true" in result
        assert "conch_mode=callback" in result


# --------------------------------------------------------------------------- #
# CALLBACK — register + return immediately, stay registered
# --------------------------------------------------------------------------- #

class TestCallbackMode:
    @pytest.mark.asyncio
    async def test_callback_registers_and_returns_immediately(self, clean_conch):
        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            result = await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=True,
                conch_mode="callback",
                session_id="sess-a",
            )

        # Returned immediately with a clear "not spoken / will be delivered" note.
        assert "NOT spoken" in result
        assert "position #1" in result
        assert "delivered" in result
        # Stays registered as a callback waiter — that is the whole point.
        entry = _entry("sess-a")
        assert entry is not None, "callback waiter must remain registered"
        assert entry.mode == "callback"
        assert entry.agent == "converse"

    @pytest.mark.asyncio
    async def test_callback_message_is_truthful_about_delivery(self, clean_conch):
        """VM-1646 regression guard: the callback copy must NOT claim delivery is
        unimplemented now that VM-1625 has landed.

        The pre-fix message told callers the push was a future task ("the push
        is VM-1625" / "Out-of-band notification lands in VM-1625") and pointed at
        polling as the only path. It now actively delivers (a session nudge), so
        the copy must say so and offer `conch status` as a supplementary view.
        """
        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            result = await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=True,
                conch_mode="callback",
                session_id="sess-a",
            )

        # No stale "delivery doesn't exist yet" framing.
        assert "VM-1625" not in result
        assert "lands in" not in result.lower()
        # States active out-of-band delivery via a session nudge...
        assert "delivered" in result
        assert "nudge" in result.lower()
        # ...keeps `conch status` as a supplementary view, not the only path...
        assert "conch status" in result
        # ...and honestly discloses the session-id caveat (F2), in one clause.
        assert "session id" in result.lower()

    @pytest.mark.asyncio
    async def test_callback_reports_position_behind_existing_waiter(self, clean_conch):
        """Position reflects FIFO order: an existing waiter sits ahead."""
        ConchQueue.register("sess-ahead", agent="ahead", mode="wait")

        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            result = await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=True,
                conch_mode="callback",
                session_id="sess-b",
            )

        assert "position #2" in result
        assert _entry("sess-b").mode == "callback"

    @pytest.mark.asyncio
    async def test_callback_waiter_shows_up_in_conch_status(self, clean_conch):
        """Cross-check VM-1610 principle #1: the waiter is visible in `conch status`."""
        from voice_mode.cli_commands.conch import _status_payload

        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=True,
                conch_mode="callback",
                session_id="sess-a",
            )

        snap = _status_payload()
        queued = {q["session_id"]: q for q in snap["queue"]}
        assert "sess-a" in queued, "a queued callback caller must appear in conch status"
        assert queued["sess-a"]["mode"] == "callback"
        assert queued["sess-a"]["agent"] == "converse"

    @pytest.mark.asyncio
    async def test_callback_without_session_id_uses_process_fallback(
        self, clean_conch, monkeypatch
    ):
        """No session id supplied → a per-process id keeps us a tracked waiter."""
        for var in (
            "VOICEMODE_SESSION_ID",
            "CLAUDE_CODE_SESSION_ID",
            "CLAUDE_SESSION_ID",
        ):
            monkeypatch.delenv(var, raising=False)

        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=True,
                conch_mode="callback",
            )

        sids = _sessions()
        assert len(sids) == 1
        assert sids[0].startswith("converse-"), f"expected a converse-<pid> id, got {sids}"


# --------------------------------------------------------------------------- #
# WAIT — timeout deregisters cleanly; FIFO grant gates acquisition
# --------------------------------------------------------------------------- #

class TestWaitMode:
    @pytest.mark.asyncio
    async def test_wait_timeout_deregisters_cleanly(self, clean_conch, monkeypatch):
        """WAIT that never gets granted times out AND leaves no wedged entry."""
        monkeypatch.setattr("voice_mode.tools.converse.CONCH_CHECK_INTERVAL", 0.01)

        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            result = await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=0.03,   # number ⇒ wait, timeout 0.03s
                conch_mode="wait",
                session_id="sess-a",
            )

        assert "Timed out" in result
        assert "callback" in result, "timeout message should point at the callback escape hatch"
        assert _sessions() == [], f"timeout must deregister the waiter; got {_sessions()}"

    @pytest.mark.asyncio
    async def test_wait_does_not_steal_when_grant_names_another(self, clean_conch, monkeypatch):
        """FIFO / no thundering-herd: a non-granted WAITer cannot jump the head.

        sess-ahead is the head and holds the grant (written when the holder
        released). sess-a (registered later) must NOT acquire even though the
        floor is free — the grant gates it — and must time out + deregister,
        leaving sess-ahead untouched at the front of the line.
        """
        monkeypatch.setattr("voice_mode.tools.converse.CONCH_CHECK_INTERVAL", 0.01)

        # sess-ahead joins first, then a real holder grabs + releases the floor,
        # which promotes the head (sess-ahead) as the designated next acquirer.
        ConchQueue.register("sess-ahead", agent="ahead", mode="wait")
        holder = Conch(agent_name="holder")
        assert holder.try_acquire()
        holder.release()  # grant_next() → grants sess-ahead (the head)
        assert ConchQueue.granted_to() == "sess-ahead"

        result = await _converse()(
            message="Hello",
            wait_for_response=False,
            wait_for_conch=0.03,
            conch_mode="wait",
            session_id="sess-a",
        )

        assert "Timed out" in result
        assert _sessions() == ["sess-ahead"], (
            f"head must keep its place and the non-granted waiter must deregister; got {_sessions()}"
        )

    @pytest.mark.asyncio
    async def test_wait_acquires_exactly_when_granted(self, clean_conch, monkeypatch):
        """WAIT blocks while busy, then acquires the instant it is granted.

        Real in-process holder + real try_acquire (not mocked). Releasing the
        holder mid-wait promotes sess-a (the only waiter) and the WAIT loop
        acquires — consuming the grant and deregistering us.
        """
        monkeypatch.setattr("voice_mode.tools.converse.CONCH_CHECK_INTERVAL", 0.01)

        holder = Conch(agent_name="holder")
        assert holder.try_acquire()  # floor is genuinely busy

        with patch(
            "voice_mode.tools.converse.text_to_speech_with_failover",
            return_value=(False, {}, {"provider": "test"}),
        ):
            task = asyncio.create_task(_converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=5,
                conch_mode="wait",
                session_id="sess-a",
            ))
            # Let converse register and enter the WAIT loop.
            await asyncio.sleep(0.05)
            assert "sess-a" in _sessions(), "WAITer should be registered while blocked"

            holder.release()  # promote sess-a + free the floor
            result = await asyncio.wait_for(task, timeout=5)

        assert "Timed out" not in result
        assert "NOT spoken" not in result
        # Acquiring consumes the grant and deregisters us — no ghost entry.
        assert _sessions() == [], f"acquire must deregister the waiter; got {_sessions()}"


# --------------------------------------------------------------------------- #
# conch_mode resolution: arg > VOICEMODE_CONCH_MODE default; unknown ⇒ wait
# --------------------------------------------------------------------------- #

class TestModeResolution:
    @pytest.mark.asyncio
    async def test_config_default_callback_is_honoured(self, clean_conch, monkeypatch):
        """With no arg, the VOICEMODE_CONCH_MODE default ('callback') is used."""
        monkeypatch.setattr("voice_mode.tools.converse.CONCH_MODE", "callback")

        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            result = await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=True,
                session_id="sess-a",
            )

        assert "NOT spoken" in result  # callback's immediate-return signature
        assert _entry("sess-a").mode == "callback"

    @pytest.mark.asyncio
    async def test_arg_overrides_config_default(self, clean_conch, monkeypatch):
        """conch_mode arg wins over the config default ('callback' → forced wait)."""
        monkeypatch.setattr("voice_mode.tools.converse.CONCH_MODE", "callback")
        monkeypatch.setattr("voice_mode.tools.converse.CONCH_CHECK_INTERVAL", 0.01)

        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            result = await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=0.03,
                conch_mode="wait",
                session_id="sess-a",
            )

        assert "Timed out" in result  # waited, did not return immediately
        assert _sessions() == []

    @pytest.mark.asyncio
    async def test_unknown_mode_falls_back_to_wait(self, clean_conch, monkeypatch):
        """A bogus conch_mode must not silently downgrade to callback."""
        monkeypatch.setattr("voice_mode.tools.converse.CONCH_CHECK_INTERVAL", 0.01)

        with patch.object(Conch, "try_acquire", return_value=False), \
             patch.object(Conch, "get_holder", return_value=FAKE_HOLDER):
            result = await _converse()(
                message="Hello",
                wait_for_response=False,
                wait_for_conch=0.03,
                conch_mode="bogus",
                session_id="sess-a",
            )

        assert "Timed out" in result  # fell back to WAIT, not an instant callback
        assert _sessions() == []


# --------------------------------------------------------------------------- #
# E2E: the VM-1619 → VM-1625 notify seam
#
# A real converse(conch_mode="callback") registration (VM-1619) wired through a
# genuine Conch.release() to the notify push (VM-1625). The unit-level coverage
# in test_conch_queue.py fabricates queue entries via _write_entry and/or calls
# grant_next directly; this drives the whole seam end to end — converse() itself
# registers the callback waiter, then a real holder release promotes the wait
# waiter behind it and pushes the skipped callback head via
# conch_notify.notify_granted.
# --------------------------------------------------------------------------- #

def _join_notify_threads(timeout=5.0):
    """Join the fire-and-forget notify threads the release hot path spawns
    (``notify_block=False``), so the ``session send`` side effect can be asserted
    deterministically rather than raced. Named ``conch-notify`` by
    ``conch_notify._dispatch_async``.
    """
    import threading

    for t in list(threading.enumerate()):
        if t.name == "conch-notify":
            t.join(timeout)


class TestCallbackNotifySeamE2E:
    @pytest.mark.asyncio
    async def test_converse_callback_waiter_is_pushed_on_real_release(
        self, clean_conch, monkeypatch
    ):
        """A converse()-registered callback waiter gets an active notify push
        when a real holder releases the floor.

        Real holder + real converse() callback registration + real
        ``Conch.release()``. Only the ``session send`` shell-out is stubbed (so
        the test never types into a live tmux pane); ``notify_granted`` is
        wrapped to record that the push fired for the callback waiter while the
        real push still runs through to ``session send``.
        """
        import voice_mode.conch_notify as conch_notify

        # Stub the actual `session send` shell-out: capture argv, never spawn it.
        sends = []

        def _fake_run(*args, **kwargs):
            sends.append(args[0] if args else kwargs.get("args"))

            class _Result:
                returncode = 0

            return _Result()

        monkeypatch.setattr("subprocess.run", _fake_run)

        # Wrap notify_granted to record the seam firing AND let the real push
        # run. grant_next lazy-imports it from the module at call time, so
        # patching the module attribute is what the release path picks up.
        notify_calls = []
        real_notify = conch_notify.notify_granted

        def _spy(entry, *, block=True):
            notify_calls.append((entry, block))
            return real_notify(entry, block=block)

        monkeypatch.setattr(conch_notify, "notify_granted", _spy)

        # A genuine in-process holder makes the floor really busy (an fcntl
        # flock conflicts even between two fds in one process), so converse()'s
        # try_acquire fails for real and it takes the callback-register path.
        holder = Conch(agent_name="holder", session_id="holder")
        assert holder.try_acquire()

        # VM-1619: converse() registers a CALLBACK waiter and returns at once.
        result = await _converse()(
            message="Hello",
            wait_for_response=False,
            wait_for_conch=True,
            conch_mode="callback",
            session_id="cb-e2e",
        )
        assert "NOT spoken" in result
        assert _entry("cb-e2e").mode == "callback"

        # A wait waiter joins behind it so the callback head is *skipped* (and
        # therefore pushed) when the floor is promoted — grant_next pings a
        # leading callback only when a blocking waiter would otherwise starve
        # behind it.
        ConchQueue.register("wait-behind", agent="ahead", mode="wait")
        assert _sessions() == ["cb-e2e", "wait-behind"]

        # VM-1625: a real release promotes the wait waiter and pushes the head.
        holder.release()

        # F1: the wait waiter is the grantee — the callback head never starves it.
        assert ConchQueue.granted_to() == "wait-behind"
        # The seam fired notify_granted exactly once, for the callback waiter,
        # fire-and-forget off the release thread (block=False).
        assert len(notify_calls) == 1, f"expected exactly one push; got {notify_calls}"
        entry, block = notify_calls[0]
        assert entry.session_id == "cb-e2e"
        assert entry.mode == "callback"
        assert block is False, "release hot path must push fire-and-forget"

        # The actual push reached the converse-registered callback waiter.
        _join_notify_threads()
        assert any("cb-e2e" in argv for argv in sends), (
            f"the session nudge must target the callback waiter; got {sends}"
        )
