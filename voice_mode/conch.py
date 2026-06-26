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

import fcntl
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

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
        if not data.get("held"):
            return False
        pid = data.get("pid")
        if pid is None or pid == os.getpid():
            return False
        # Holder process alive?
        try:
            os.kill(pid, 0)
        except PermissionError:
            pass  # exists but not signalable by us — treat as alive
        except (ProcessLookupError, TypeError, OSError):
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

        Uses fcntl.flock() for true atomic locking across processes.
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
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

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

        # Fast-fail on dead holder -- no need to wait for timestamp expiry.
        pid = data.get("pid")
        if pid is not None:
            try:
                os.kill(pid, 0)
                # Process is alive -- fall through to timestamp check.
            except ProcessLookupError:
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
            except PermissionError:
                # Process exists but we can't signal it -- treat as alive.
                pass
            except (TypeError, OSError):
                # PID isn't a valid int or other OS error -- skip dead-PID path,
                # fall through to timestamp check.
                pass

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
                fcntl.flock(self._fd, fcntl.LOCK_UN)
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
                fcntl.flock(self._fd, fcntl.LOCK_UN)
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

            # Check if process is alive (signal 0 doesn't actually send a signal)
            os.kill(pid, 0)

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
        except (json.JSONDecodeError, ProcessLookupError, PermissionError, OSError, ValueError):
            # JSON invalid, process dead, no permission to signal, or invalid timestamp
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
