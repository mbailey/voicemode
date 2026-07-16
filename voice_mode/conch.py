"""Conch - Simple lock file for voice conversation coordination.

The Conch provides a lock file mechanism to indicate when a voice conversation
is active. This allows other processes (like sound effect hooks) to check
whether to suppress their audio output.

Lock file location: ~/.voicemode/conch

Usage:
    # As context manager (recommended)
    with Conch(agent_name="claude"):
        # ... voice conversation logic ...

    # Manual acquire/release
    conch = Conch()
    conch.acquire(agent_name="claude")
    try:
        # ... voice conversation logic ...
    finally:
        conch.release()

    # Check if converse is active (for external scripts)
    if Conch.is_active():
        print("Someone is in a voice conversation")
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import psutil

from voice_mode.file_lock import lock_exclusive, unlock

# Import config for lock expiry - deferred to avoid circular import
def _get_lock_expiry() -> float:
    """Get lock expiry from config, with fallback."""
    try:
        from voice_mode.config import CONCH_LOCK_EXPIRY
        return CONCH_LOCK_EXPIRY
    except ImportError:
        return 120.0  # Default 2 minutes


def _get_hold_expiry() -> float:
    """Get the idle-expiry (seconds) for a between-turns *hold*, with fallback.

    A hold persists across turns while the kernel flock is released, so it can
    only be cleared by the holder dying (pid check) or by going stale. This is
    that staleness window. It is re-stamped every turn, so it only ever needs to
    cover the gap between two turns (agent thinking / light tool use). This is
    the *global* default fallback; a holder may stamp a per-hold TTL into the
    payload's ``expires`` field (VM-1649), which cross-process staleness checks
    honour ahead of this value.
    """
    try:
        from voice_mode.config import CONCH_HOLD_EXPIRY
        return CONCH_HOLD_EXPIRY
    except ImportError:
        return 10.0  # Default 10s short refreshed TTL (VM-1649)


def _hold_is_expired(data: dict) -> bool:
    """True if a between-turns *hold* payload has passed its idle-expiry.

    The per-hold TTL governs cross-process: a holder stamps an absolute
    ``expires`` (now + its chosen TTL) into the lock file, and any other
    process honours that here ahead of the global ``CONCH_HOLD_EXPIRY``
    default. This is what makes ``converse(conch_hold_timeout=...)`` work across
    agents — without it, a would-be acquirer reads only the global default and
    the override is a no-op (VM-1649 RCA).

    Resolution order:
      1. Absolute ``expires`` stamped by the holder — past it ⇒ expired.
      2. Fallback: ``acquired`` + the global ``_get_hold_expiry()`` window.

    Returns False (not expired) when expiry can't be determined or idle-expiry
    is disabled (global window <= 0 and no ``expires`` stamped), so an
    undecidable hold is treated as still live rather than stolen.
    """
    expires_str = data.get("expires")
    if expires_str:
        try:
            return datetime.now() > datetime.fromisoformat(expires_str)
        except (ValueError, TypeError):
            pass  # malformed expiry — fall back to acquired + global window
    hold_expiry = _get_hold_expiry()
    if hold_expiry <= 0:
        return False  # idle-expiry disabled and no absolute expiry to honour
    acquired_str = data.get("acquired")
    if not acquired_str:
        return False
    try:
        age = (datetime.now() - datetime.fromisoformat(acquired_str)).total_seconds()
    except (ValueError, TypeError):
        return False
    return age > hold_expiry


def _response_deadline_passed(data: dict) -> bool:
    """True if an ``awaiting_human_response`` payload has passed its own
    explicit ``response_deadline``.

    Mirrors ``_hold_is_expired()`` above, but this new state has exactly
    ONE timeout source -- the absolute ``response_deadline`` stamped by
    ``Conch.mark_awaiting_human_response()`` -- deliberately NOT the normal
    hold-expiry TTL (``CONCH_HOLD_EXPIRY``/``expires``) or the flock-lock
    staleness window (``CONCH_LOCK_EXPIRY``). A SEPARATE function from
    ``_hold_is_expired()`` on purpose, so a live wait for a human reply is
    never accidentally coupled to the normal 10s hold-expiry default -- the
    whole state is exempt from that refresh-TTL, since a real human
    decision can take much longer than a between-turns idle window.

    Returns False (not passed / still live) when ``response_deadline`` is
    missing or malformed -- same reasoning as ``_hold_is_expired()``: an
    undecidable deadline is treated as still active rather than stolen.
    """
    deadline_str = data.get("response_deadline")
    if not deadline_str:
        return False
    try:
        return datetime.now() > datetime.fromisoformat(deadline_str)
    except (ValueError, TypeError):
        return False


def _process_start_time(pid: int) -> Optional[str]:
    """A pid NUMBER alone is not a reliable process identity -- pids are
    reused. Scenario this guards against: process A calls
    mark_awaiting_human_response() then crashes; within the still-live
    response_deadline window (up to 300s by default), the OS reassigns A's
    old pid to a completely unrelated process B; B's own
    awaiting_human_response_active()/_held_by_other() check would then see
    ``pid == os.getpid()`` and wrongly treat itself as "the original
    holder," silently exempting itself from the safety gate this state
    exists to enforce.

    Uses ``psutil.Process(pid).create_time()`` (seconds since epoch, at
    float precision) as an opaque, monotonically-assigned identity token
    that a pid alone can't provide -- two DIFFERENT processes essentially
    never share both the same pid AND the same create_time. Combined with
    the pid itself (see call sites), this reliably distinguishes "truly the
    same process" from "a different process that happens to have the
    inherited pid number." Portable across platforms (Windows/macOS/Linux),
    matching this module's existing psutil-based liveness probes elsewhere
    (``_held_by_other()``, ``_check_and_clear_stale_lock()``, ``is_active()``)
    -- unlike an earlier draft of this function, which read Linux-only
    ``/proc/<pid>/stat`` and silently returned None (failing the same-
    process exemption closed) on every other platform, including the
    Windows-native path this file's own liveness probes were already made
    portable for.

    Returns None if unavailable (process gone, permission denied, or a
    malformed/negative pid). Callers MUST treat None as "cannot verify" and
    fail CLOSED (i.e. do NOT grant a same-process exemption) rather than
    silently falling back to a pid-only comparison, which is exactly the
    weaker check this function exists to replace.
    """
    try:
        return str(psutil.Process(pid).create_time())
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, ValueError):
        return None


def _is_same_process(data: dict) -> bool:
    """True only if ``data``'s stamped pid AND process-start-time both
    match the CURRENT process -- see ``_process_start_time()`` above for
    why pid alone is not sufficient. Fails CLOSED (returns False, meaning
    "not confirmed the same process," i.e. no exemption granted) whenever
    either side's start time can't be read -- an unverifiable identity must
    never be treated as a match for a safety-relevant exemption.
    """
    pid = data.get("pid")
    if pid is None or pid != os.getpid():
        return False
    own_start = _process_start_time(os.getpid())
    if own_start is None:
        return False
    return data.get("pid_start_time") == own_start


class Conch:
    """Simple lock file for voice conversation coordination.

    Creates a lock file at ~/.voicemode/conch when a voice conversation
    is active. The lock file contains:
    - pid: Process ID of the lock holder (for stale lock detection)
    - agent: Name of the agent holding the lock
    - session_id: Caller-provided harness session ID, or null (VM-1562)
    - project_path: Holder's working directory, or null (CID-62) — lets
      consumers (e.g. the Stream Deck) show who's talking on which project
      with zero lookups, even for a dead/cross-machine session
    - voice: TTS voice name in use, or null (VM-914) — lets another agent read
      the holder's voice and pick a different one to avoid a voice clash
    - acquired: ISO timestamp when the lock/hold was last (re-)stamped
    - held: True when this is a *hold* persisting between turns (the file is
      left in place with the kernel flock released); False during an active
      call (flock held)
    - expires: Absolute ISO time at which a *hold* idle-expires (VM-1649). The
      holder stamps now + its TTL here so OTHER processes — which otherwise read
      only the global CONCH_HOLD_EXPIRY — honour this holder's chosen window,
      making converse(conch_hold_timeout=...) effective across agents. None for
      an active (flock-held) lock and when idle-expiry is disabled.

    Two layers of liveness coordinate multiple agents:
    1. The kernel flock (held for the duration of a call) answers "is an
       exchange running right now?" — crash-safe, auto-released by the OS.
    2. The on-disk ``held`` marker answers "is the floor reserved between
       turns?" — guarded by a pid-alive check and an idle-expiry timestamp,
       since plain bytes do not self-clean when a process dies.
    """

    LOCK_FILE = Path.home() / ".voicemode" / "conch"

    def __init__(
        self,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
        project_path: Optional[str] = None,
        voice: Optional[str] = None,
        hold_timeout: Optional[float] = None,
    ):
        """Initialize Conch with optional agent name.

        Args:
            agent_name: Name of the agent (e.g., "claude"). Used for debugging/logging.
            session_id: Optional caller-provided harness session ID (VM-1562).
                Stored verbatim in the lock payload; null when not provided.
            project_path: Optional holder working directory (CID-62). Stored in
                the payload so consumers can render "who, on which project".
            voice: Optional TTS voice name in use (VM-914). Stored so another
                agent can read the holder's voice and pick a different one to
                avoid a voice clash.
            hold_timeout: Optional per-hold idle-expiry override in seconds
                (VM-1649). When this instance reserves the floor between turns
                (release(hold=True)), now + this TTL is stamped into the
                payload's ``expires`` so other agents honour it; None falls back
                to the configured CONCH_HOLD_EXPIRY default.
        """
        self.agent_name = agent_name
        self.session_id = session_id
        self.project_path = project_path
        self.voice = voice
        self.hold_timeout = hold_timeout
        self._acquired = False
        self._fd = None  # File descriptor for flock
        self._acquire_time = None  # Track when acquired

    def _hold_expires_at(self) -> Optional[str]:
        """Absolute ISO expiry for a hold this instance is stamping, or None.

        Uses the per-hold override (self.hold_timeout) when set, else the global
        CONCH_HOLD_EXPIRY default. Returns None when idle-expiry is disabled
        (TTL <= 0) — no absolute deadline to record. Anchored on the re-stamp
        time (self._acquire_time), which release(hold=True) sets to "now".
        """
        ttl = self.hold_timeout if self.hold_timeout is not None else _get_hold_expiry()
        if ttl is None or ttl <= 0:
            return None
        base = self._acquire_time or datetime.now()
        return (base + timedelta(seconds=ttl)).isoformat()

    def _payload(self, held: bool) -> dict:
        """Build the lock-file payload for this holder.

        ``expires`` is stamped only for a *hold* (held=True): an absolute
        deadline other processes honour so a per-call TTL governs cross-process
        (VM-1649). An active flock-backed lock (held=False) is governed by the
        flock plus CONCH_LOCK_EXPIRY, so it carries no expiry.
        """
        return {
            "pid": os.getpid(),
            "agent": self.agent_name or "unknown",
            "session_id": self.session_id,
            "project_path": self.project_path,
            "voice": self.voice,
            "acquired": (self._acquire_time or datetime.now()).isoformat(),
            "held": held,
            "expires": self._hold_expires_at() if held else None,
        }

    def _write_locked_payload(self, held: bool) -> None:
        """Overwrite the lock file via the held fd (atomic while we hold flock)."""
        data = json.dumps(self._payload(held), indent=2).encode()
        os.ftruncate(self._fd, 0)
        os.lseek(self._fd, 0, os.SEEK_SET)
        os.write(self._fd, data)
        os.fsync(self._fd)

    @classmethod
    def _held_by_other(cls) -> bool:
        """True if the lock file marks a live, non-expired *hold* by another process.

        Holds persist between turns with the kernel flock released, so a naive
        ``flock`` would succeed and steal a reserved floor. Acquirers must
        consult this explicitly. Returns False for: no file, no ``held`` flag,
        our own pid, a dead holder, or an idle-expired hold (those are all
        safe to take — stale clearance unlinks dead/expired holds separately).
        """
        try:
            data = json.loads(cls.LOCK_FILE.read_text())
        except (json.JSONDecodeError, OSError, ValueError):
            return False
        # A live awaiting_human_response state is a PRIORITY OVERRIDE: it
        # blocks ALL OTHER processes' floor-acquisition attempts
        # unconditionally -- regardless of ``held``, regardless of whether
        # the original holder's pid is even still alive -- until its own
        # explicit response_deadline passes. The ORIGINAL holder's own
        # process is exempt (see the check below) so it can resume the
        # instant the human answers, mirroring the normal ``held`` path's
        # own pid exemption. Checked first, ahead of (and independent of)
        # the normal held/pid-liveness path below: a dropped call's cleanup
        # is the CALLER's job (e.g. an external approval-queue's own
        # expiry, composed via the same response_deadline value), not a
        # pid-liveness check here -- conch itself has no concept of any
        # particular caller's approval mechanism and shouldn't gain one.
        #
        # The "own process" exemption is verified via _is_same_process()
        # (pid + process-start-time), NOT a bare pid comparison -- a bare
        # `pid == os.getpid()` check is fooled by pid reuse (a crashed
        # original holder's pid reassigned to an unrelated process within
        # the still-live response_deadline window), which would silently
        # exempt that unrelated process from the safety gate.
        if (
            data.get("awaiting_human_response")
            and not _response_deadline_passed(data)
            and not _is_same_process(data)
        ):
            return True
        if not data.get("held"):
            return False
        pid = data.get("pid")
        if pid is None or pid == os.getpid():
            return False
        # Holder process alive? (psutil probe: os.kill(pid, 0) is NOT a
        # portable liveness check — on Windows signal 0 TERMINATES the target.)
        try:
            if not psutil.pid_exists(pid):
                return False
        except (TypeError, ValueError):
            return False
        # Hold not idle-expired? Honour the holder's stamped per-hold TTL
        # (payload ``expires``) ahead of the global default (VM-1649).
        if _hold_is_expired(data):
            return False
        return True

    @classmethod
    def write_hold(
        cls,
        agent_name: str = "unknown",
        session_id: Optional[str] = None,
        project_path: Optional[str] = None,
        voice: Optional[str] = None,
        hold_timeout: Optional[float] = None,
    ) -> None:
        """Write a between-turns hold marker owned by the current process,
        WITHOUT taking the kernel flock.

        Used by ``pause_conversation``: it must not flock-block the same
        process's later ``converse`` call (flock locks conflict between two
        open file descriptions in one process). Callers must first ensure the
        conch is free or already theirs (see ``get_holder``) to avoid
        clobbering an active holder's payload.

        Stamps an absolute ``expires`` (now + ``hold_timeout`` or the global
        CONCH_HOLD_EXPIRY default) so the hold honours the same per-hold TTL
        machinery as a converse hold (VM-1649). ``pause_conversation``
        re-stamps well within the window, so a maintained pause never lapses;
        if the caller stops re-stamping, the hold idle-expires like any other.
        """
        cls.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        ttl = hold_timeout if hold_timeout is not None else _get_hold_expiry()
        now = datetime.now()
        expires = (now + timedelta(seconds=ttl)).isoformat() if ttl and ttl > 0 else None
        data = {
            "pid": os.getpid(),
            "agent": agent_name,
            "session_id": session_id,
            "project_path": project_path,
            "voice": voice,
            "acquired": now.isoformat(),
            "held": True,
            "expires": expires,
        }
        cls.LOCK_FILE.write_text(json.dumps(data, indent=2))

    @classmethod
    def mark_awaiting_human_response(cls, deadline_seconds: float = 300.0) -> None:
        """Re-stamp the lock file into the ``awaiting_human_response`` state --
        a live decision is pending a human reply and must block other
        acquirers unconditionally until it resolves or times out. Called by
        the CURRENT flock holder just before it yields the floor to wait;
        mirrors ``write_hold()`` above in that it does NOT take the kernel
        flock (same reasoning: this must not self-deadlock the same
        process's own later ``try_acquire``).

        Unlike a normal between-turns hold, this state is deliberately EXEMPT
        from the standard ``CONCH_HOLD_EXPIRY`` idle-refresh window (a real
        decision can take longer than 10s) -- it carries its own, explicit,
        absolute ``response_deadline`` (now + ``deadline_seconds``), read by
        ``_response_deadline_passed()`` above, a SEPARATE staleness function
        from ``_hold_is_expired()`` on purpose so it's never accidentally
        coupled to the normal hold default.

        This RE-STAMPS the existing lock-file payload (preserving whatever
        ``agent``/``session_id``/``project_path``/``voice``/``pid`` the
        current holder already wrote via ``acquire()``/``_write_locked_payload``)
        rather than building a fresh one from scratch -- unlike ``write_hold()``,
        which is called with no pre-existing holder payload to preserve. If no
        lock file exists yet (called without an active hold), a minimal
        self-contained marker is created instead of raising.

        Also re-stamps the EXISTING ``expires`` field to this same deadline
        (belt-and-suspenders, not just the new ``response_deadline`` field):
        ``_hold_is_expired()`` (used by ``_check_and_clear_stale_lock()``'s
        pre-existing timestamp-based clearance) reads ``expires`` first and
        would otherwise fall back to ``acquired`` + the global
        ``CONCH_HOLD_EXPIRY`` (10s default) -- silently deleting this marker
        after only 10s if ``expires`` were left stale or unset, defeating the
        whole point of a longer, explicit deadline. Stamping both fields to
        the same value keeps the pre-existing stale-lock-clearance code path
        aligned with the new one instead of racing it.
        """
        cls.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(cls.LOCK_FILE.read_text())
        except (json.JSONDecodeError, OSError, ValueError):
            data = {}
        now = datetime.now()
        ttl = deadline_seconds if deadline_seconds and deadline_seconds > 0 else 300.0
        deadline_iso = (now + timedelta(seconds=ttl)).isoformat()
        data["pid"] = data.get("pid", os.getpid())
        # Stamp a process-identity token alongside the pid so later
        # same-process checks can't be fooled by pid reuse -- see
        # _process_start_time()/_is_same_process() above. Only stamped when
        # this call is the one ESTABLISHING the pid (i.e. no pre-existing
        # pid_start_time in the file) -- if a payload already existed with a
        # pid, its own start-time (if any) is preserved rather than
        # overwritten, so a later re-stamp by the SAME original holder
        # doesn't clobber it.
        #
        # Derived from data["pid"] (the pid actually being kept -- possibly
        # PRESERVED from an existing payload written by a different process,
        # e.g. via write_hold()), NOT from os.getpid() unconditionally:
        # always using our own start-time here would make that OTHER,
        # genuine holder fail its own later _is_same_process() check and get
        # wrongly locked out of resuming.
        if "pid_start_time" not in data:
            data["pid_start_time"] = _process_start_time(data["pid"])
        data.setdefault("agent", "unknown")
        data.setdefault("session_id", None)
        data.setdefault("project_path", None)
        data.setdefault("voice", None)
        data["acquired"] = now.isoformat()
        data["held"] = True
        data["expires"] = deadline_iso  # keeps _hold_is_expired() aligned -- see docstring
        data["awaiting_human_response"] = True
        data["response_deadline"] = deadline_iso
        cls.LOCK_FILE.write_text(json.dumps(data, indent=2))

    @classmethod
    def awaiting_human_response_active(cls) -> Optional[dict]:
        """The correct, unconditional way for a CALLER (e.g. converse.py's
        skip_conch guard) to check "is a live awaiting_human_response state
        in effect right now" -- mirrors the exact same check
        ``_held_by_other()`` already uses internally -- NOT via
        ``get_holder()``/``is_active()``, which depend on the ORIGINAL
        holder's pid still being alive and on the unrelated
        ``CONCH_LOCK_EXPIRY`` staleness window. A dead holder or an elapsed
        CONCH_LOCK_EXPIRY must NOT clear this state (see
        ``_check_and_clear_stale_lock()``'s own guard for this same
        reasoning) -- so a check built on ``is_active()`` would silently
        stop seeing the block at exactly the moment (a crashed questioning
        process, or a long wait outliving the lock-staleness window) this
        state most needs to hold. Returns the lock-file payload dict while
        the state is genuinely active (deadline not yet passed), else None
        -- deliberately NOT gated on pid liveness, matching the priority-
        override semantics ``_held_by_other()`` already documents.

        Returns None (not blocking) if the CURRENT process is itself the
        holder that set this state -- mirrors ``_held_by_other()``'s own
        exemption (verified via ``_is_same_process()``, NOT a bare pid
        comparison, which pid reuse can fool), so the original holder can
        resume once the human has answered.
        """
        try:
            data = json.loads(cls.LOCK_FILE.read_text())
        except (json.JSONDecodeError, OSError, ValueError):
            return None
        if not data.get("awaiting_human_response"):
            return None
        if _response_deadline_passed(data):
            return None
        if _is_same_process(data):
            return None
        return data

    @classmethod
    def resolve_awaiting_human_response(cls) -> bool:
        """Explicit resume path for once the human has actually answered
        early. Without this, nothing clears ``awaiting_human_response`` on
        an early-approved path -- the same-process exemption in
        ``_held_by_other()`` only lets the ORIGINAL holder resume; a
        caller that wants to resolve the state (e.g. so a DIFFERENT process
        or a fresh acquirer can proceed immediately) needs an explicit
        clear, rather than waiting out the full response_deadline. Unlinks
        the lock file entirely (same effect as a normal ``release()``) so
        the next ``try_acquire()`` -- by the original holder resuming, or by
        any other process -- starts clean. Best-effort: a missing file is
        not an error (nothing to resolve). Returns True if a file was
        actually removed.

        Guarded by a precondition: this must never unlink a lock file that
        ISN'T currently in the awaiting_human_response state. Without this
        guard, calling it while an unrelated, genuinely active conversation
        holds the file (e.g. the original holder already auto-resumed and
        is now speaking normally) would delete THAT live holder's entry out
        from under it -- the exact "stale flock on an unlinked inode"
        foot-gun ``release()`` itself already guards against via its own
        ownership check.

        No caller in this module invokes this method today -- it is a
        primitive for whatever wires the human-response event (e.g. an
        approval workflow) into conch, exposed here so that integration
        doesn't need its own lock-file-unlink logic.
        """
        try:
            data = json.loads(cls.LOCK_FILE.read_text())
        except (json.JSONDecodeError, OSError, ValueError):
            return False
        if not data.get("awaiting_human_response"):
            return False
        try:
            cls.LOCK_FILE.unlink()
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False

    def acquire(
        self,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
        project_path: Optional[str] = None,
    ) -> bool:
        """Create the lock file.

        Args:
            agent_name: Override the agent name set in __init__

        Returns:
            True if lock was acquired successfully
        """
        self.agent_name = agent_name or self.agent_name or "unknown"
        if session_id is not None:
            self.session_id = session_id
        if project_path is not None:
            self.project_path = project_path

        # Ensure parent directory exists
        self.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

        self._acquire_time = datetime.now()
        self.LOCK_FILE.write_text(json.dumps(self._payload(held=False), indent=2))
        self._acquired = True
        return True

    def try_acquire(
        self,
        agent_name: Optional[str] = None,
        session_id: Optional[str] = None,
        project_path: Optional[str] = None,
    ) -> bool:
        """Atomically try to acquire the conch.

        Uses an exclusive file lock (flock/msvcrt via voice_mode.file_lock)
        for true atomic locking across processes.
        Also handles stale locks: a lock whose holder PID is dead, or that is
        older than its expiry window (CONCH_LOCK_EXPIRY for active locks,
        CONCH_HOLD_EXPIRY for between-turns holds), is forcibly cleared.

        Respects an active *hold* by another live process: between turns the
        holder releases the kernel flock but leaves a ``held`` marker in the
        file, so this returns False even though the flock is free.

        Args:
            agent_name: Name of the agent acquiring the lock
            session_id: Optional caller-provided session ID (stored verbatim)
            project_path: Optional holder working directory (stored verbatim)

        Returns:
            True if lock acquired, False if held (live flock) or reserved
            (live hold) by another process
        """
        if self._acquired:
            return True  # Already holding it

        self.agent_name = agent_name or self.agent_name or "unknown"
        if session_id is not None:
            self.session_id = session_id
        if project_path is not None:
            self.project_path = project_path
        self.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

        # First check: is there a dead/expired lock we can forcibly clear?
        self._check_and_clear_stale_lock()

        # Respect a live hold owned by another process. The flock is free
        # between turns, so without this we would clobber a reserved floor.
        if self._held_by_other():
            return False

        # Respect a live waiter-queue grant for another session (VM-1613). On
        # release the head of the queue is recorded as the designated next
        # acquirer; everyone else must keep waiting so FIFO order holds.
        if self._queue_grant_blocks():
            return False

        try:
            # Open file for read/write, create if doesn't exist
            self._fd = os.open(str(self.LOCK_FILE), os.O_CREAT | os.O_RDWR, 0o644)

            # Try to get exclusive lock (non-blocking)
            lock_exclusive(self._fd)

            # Got lock - write our info (held=False: we hold the flock now)
            self._acquire_time = datetime.now()
            self._write_locked_payload(held=False)

            self._acquired = True
            # We now hold the floor, so we are no longer waiting: leave the
            # queue and clear any grant we consumed (VM-1613).
            self._queue_on_acquired()
            return True

        except (BlockingIOError, OSError) as e:
            # Lock held by another process, or other OS error
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None
            return False

    def _check_and_clear_stale_lock(self) -> None:
        """Check for and clear stale locks.

        Two paths:
        1. Dead-holder fast-fail: if the recorded PID no longer exists,
           unlink the lock immediately. This runs even when timestamp-based
           expiry is disabled (CONCH_LOCK_EXPIRY <= 0) -- a dead holder is
           unambiguously stale.
        2. Timestamp-based expiry: if the lock is older than
           CONCH_LOCK_EXPIRY seconds, forcibly remove it. This handles the
           case where the holder is alive but stuck.

        Note: This deletes the file, creating a new inode. A stuck process
        still holds its flock on the old inode, but we can now create a fresh
        lock file.
        """
        if not self.LOCK_FILE.exists():
            return

        try:
            data = json.loads(self.LOCK_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return

        # A live awaiting_human_response state must never be cleared by this
        # method's pre-existing dead-pid-fast-fail or timestamp-based paths
        # below, even though neither knows about the new field. Without this
        # guard, the "process died mid-wait" scenario this state exists to
        # handle safely would instead hit the dead-pid fast-fail path a few
        # lines down and get unlinked immediately -- silently defeating
        # _held_by_other()'s "unconditional... regardless of pid" branch
        # above, since try_acquire() calls this method BEFORE it ever
        # consults _held_by_other(). Deferring cleanup to the caller's own
        # response-driven expiry requires this method to also leave the
        # marker alone until its own response_deadline passes.
        if data.get("awaiting_human_response") and not _response_deadline_passed(data):
            return

        # Fast-fail on dead holder -- no need to wait for timestamp expiry.
        pid = data.get("pid")
        if pid is not None:
            holder_dead = False
            try:
                # Portable liveness probe (os.kill(pid, 0) kills on Windows).
                # A process that exists but is not signalable counts as alive.
                holder_dead = not psutil.pid_exists(pid)
            except (TypeError, ValueError):
                # PID isn't a valid int -- skip dead-PID path,
                # fall through to timestamp check.
                pass
            if holder_dead:
                # Holder is dead -- clear the lock immediately.
                stale_agent = data.get("agent", "unknown")
                try:
                    self.LOCK_FILE.unlink()
                except OSError:
                    pass
                # Best-effort observability event. Safe no-op if logger unset
                # or import fails (avoids circular-import / startup-order issues).
                try:
                    from voice_mode.utils.event_logger import get_event_logger
                    event_logger = get_event_logger()
                    if event_logger:
                        event_logger.log_event("CONCH_DEAD_HOLDER_CLEARED", {
                            "stale_pid": pid,
                            "stale_agent": stale_agent,
                        })
                except Exception:
                    pass
                return

        # Timestamp-based stale clearance.
        if data.get("held"):
            # A between-turns hold: honour the holder's stamped per-hold TTL
            # (payload ``expires``), falling back to the global idle-expiry
            # window — the same resolution other acquirers use (VM-1649).
            if _hold_is_expired(data):
                try:
                    self.LOCK_FILE.unlink()
                except OSError:
                    pass
            return

        # An active (flock-held) lock uses the standard lock-expiry window.
        lock_expiry = _get_lock_expiry()
        if lock_expiry <= 0:
            return  # Stale lock detection disabled

        acquired_str = data.get("acquired")
        if not acquired_str:
            return

        try:
            acquired_time = datetime.fromisoformat(acquired_str)
        except ValueError:
            return

        age_seconds = (datetime.now() - acquired_time).total_seconds()
        if age_seconds > lock_expiry:
            # Lock is stale - forcibly remove it
            try:
                self.LOCK_FILE.unlink()
            except OSError:
                pass

    def release(self, hold: bool = False) -> float:
        """Release the lock and return seconds held.

        Only removes the lock file if this instance actually acquired the lock.
        Removing it when not acquired would destroy the lock held by another
        process (they'd be flocking different inodes after re-creation).

        Args:
            hold: If True, keep the floor between turns — re-stamp the payload
                with ``held=True`` (auto-extending the idle-expiry), drop the
                kernel flock so others can detect no call is running, but LEAVE
                the file so other agents queue behind the hold. The same
                process reclaims it on its next ``try_acquire`` (its own pid is
                not "another" holder). If False, fully release: drop flock and
                unlink (unchanged default behaviour).

        Returns:
            Seconds the lock was held this turn, or 0.0 if not acquired
        """
        held_seconds = 0.0

        if self._acquire_time:
            held_seconds = (datetime.now() - self._acquire_time).total_seconds()

        if hold and self._acquired and self._fd is not None:
            # Keep the floor: re-stamp + mark held while we still hold the
            # flock (atomic), then drop the flock but leave the file.
            self._acquire_time = datetime.now()
            try:
                self._write_locked_payload(held=True)
            except OSError:
                pass
            try:
                unlock(self._fd)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
            self._acquired = False
            self._acquire_time = None
            return held_seconds

        was_acquired = self._acquired

        if self._fd is not None:
            try:
                unlock(self._fd)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

        # Only remove the lock file if we actually acquired the lock.
        # If we didn't acquire it, the file belongs to another process.
        if self._acquired and self.LOCK_FILE.exists():
            try:
                self.LOCK_FILE.unlink()
            except OSError:
                pass

        self._acquired = False
        self._acquire_time = None

        # Full release of a floor we held: promote the head of the waiter queue
        # so the next-in-line becomes the designated acquirer (VM-1613). A
        # between-turns hold (handled above) keeps the floor and does NOT
        # promote; a non-holder release must not promote either.
        if was_acquired:
            self._queue_promote_next()

        return held_seconds

    # ---- waiter-queue integration (VM-1613) ----
    #
    # The queue layer (voice_mode.conch_queue.ConchQueue) is imported lazily to
    # avoid a circular import (it imports Conch for its base path), and every
    # call is fail-safe: a queue glitch must never break the holder lock, which
    # is critical-path coordination. When no queue is in use (the common
    # single-agent case) these are cheap no-ops -- there is no grant file and no
    # queue entry, so behaviour is unchanged.

    def _queue_grant_blocks(self) -> bool:
        """True if a live waiter-queue grant designates a session other than ours."""
        try:
            from voice_mode.conch_queue import ConchQueue
        except ImportError:
            return False
        try:
            grantee = ConchQueue.granted_to()
        except Exception:
            return False
        return grantee is not None and grantee != self.session_id

    def _queue_on_acquired(self) -> None:
        """Leave the waiter queue now that we hold the floor.

        ``deregister`` also clears the grant if it named us, so acquiring as the
        grantee both consumes the grant and removes us from the line -- letting
        the *next* release promote the following waiter.
        """
        if self.session_id is None:
            return
        try:
            from voice_mode.conch_queue import ConchQueue
        except ImportError:
            return
        try:
            ConchQueue.deregister(self.session_id)
        except Exception:
            pass

    def _queue_promote_next(self) -> None:
        """Record the head of the queue as the designated next acquirer.

        ``notify_block=False``: this runs on the holder's release (the converse
        hot path), so any ping to a skipped callback head is fire-and-forget --
        a wedged ``session send`` must never add latency to the release
        (VM-1625 impl-001 peer-review finding).
        """
        try:
            from voice_mode.conch_queue import ConchQueue
        except ImportError:
            return
        try:
            ConchQueue.grant_next(notify_block=False)
        except Exception:
            pass

    @classmethod
    def is_active(cls) -> bool:
        """Check if a voice conversation is currently active.

        A conversation is considered active if:
        1. The lock file exists
        2. The PID in the file corresponds to a running process
        3. The lock is not stale (acquired within CONCH_LOCK_EXPIRY seconds)

        Returns:
            True if converse is active, False otherwise
        """
        if not cls.LOCK_FILE.exists():
            return False

        try:
            data = json.loads(cls.LOCK_FILE.read_text())
            pid = data.get("pid")

            if pid is None:
                return False

            # Check if process is alive (portable probe; os.kill(pid, 0)
            # would TERMINATE the target on Windows)
            if not psutil.pid_exists(pid):
                return False

            # Check if lock is stale based on timestamp
            lock_expiry = _get_lock_expiry()
            if lock_expiry > 0:
                acquired_str = data.get("acquired")
                if acquired_str:
                    acquired_time = datetime.fromisoformat(acquired_str)
                    age_seconds = (datetime.now() - acquired_time).total_seconds()
                    if age_seconds > lock_expiry:
                        # Lock is stale - consider it inactive
                        return False

            return True
        except (json.JSONDecodeError, TypeError, ValueError, OSError):
            # JSON invalid, pid not an int (TypeError), invalid timestamp/pid
            # value (ValueError), or file unreadable (OSError). psutil.pid_exists
            # no longer raises ProcessLookupError/PermissionError -- it returns a
            # bool -- so those are dropped to match the other liveness probes.
            return False

    @classmethod
    def get_holder(cls) -> Optional[dict]:
        """Get information about the current lock holder.

        Returns:
            Dict with lock info if active, None otherwise
        """
        if not cls.is_active():
            return None

        try:
            return json.loads(cls.LOCK_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    def __enter__(self):
        """Context manager entry - acquire the lock."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - release the lock."""
        self.release()
        return False  # Don't suppress exceptions
