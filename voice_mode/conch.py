"""Conch - Simple lock file for voice conversation coordination.

The Conch provides a lock file mechanism to indicate when a voice conversation
is active. This allows other processes (like sound effect hooks) to check
whether to suppress their audio output.

Lock file location: ~/.voicemode/conch

Usage:
    # As context manager (recommended)
    with Conch(agent_name="cora"):
        # ... voice conversation logic ...

    # Manual acquire/release
    conch = Conch()
    conch.acquire(agent_name="cora")
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
from datetime import datetime
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


class Conch:
    """Simple lock file for voice conversation coordination.

    Creates a lock file at ~/.voicemode/conch when a voice conversation
    is active. The lock file contains:
    - pid: Process ID of the lock holder (for stale lock detection)
    - agent: Name of the agent holding the lock
    - acquired: ISO timestamp when lock was acquired
    - expires: Optional expiry time (reserved for future use)
    """

    LOCK_FILE = Path.home() / ".voicemode" / "conch"
    HOLD_FILE = Path.home() / ".voicemode" / "conch_hold"

    def __init__(self, agent_name: Optional[str] = None):
        """Initialize Conch with optional agent name.

        Args:
            agent_name: Name of the agent (e.g., "cora"). Used for debugging/logging.
        """
        self.agent_name = agent_name
        self._acquired = False
        self._fd = None  # File descriptor for flock
        self._acquire_time = None  # Track when acquired

    def acquire(self, agent_name: Optional[str] = None) -> bool:
        """Create the lock file.

        Args:
            agent_name: Override the agent name set in __init__

        Returns:
            True if lock was acquired successfully
        """
        agent = agent_name or self.agent_name or "unknown"

        # Ensure parent directory exists
        self.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "pid": os.getpid(),
            "agent": agent,
            "acquired": datetime.now().isoformat(),
            "expires": None
        }

        self.LOCK_FILE.write_text(json.dumps(data, indent=2))
        self._acquired = True
        return True

    def try_acquire(self, agent_name: Optional[str] = None) -> bool:
        """Atomically try to acquire the conch.

        Uses fcntl.flock() for true atomic locking across processes.
        Also handles stale locks: if a lock is older than CONCH_LOCK_EXPIRY
        seconds, it will be forcibly released and re-acquired.

        Args:
            agent_name: Name of the agent acquiring the lock

        Returns:
            True if lock acquired, False if already held by another process
        """
        if self._acquired:
            return True  # Already holding it

        # Check if another process has a hold on the conch
        if self.is_held_by_other():
            return False

        agent = agent_name or self.agent_name or "unknown"
        self.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

        # First check: is there a stale lock we can forcibly clear?
        self._check_and_clear_stale_lock()

        try:
            # Open file for read/write, create if doesn't exist
            self._fd = os.open(str(self.LOCK_FILE), os.O_CREAT | os.O_RDWR, 0o644)

            # Try to get exclusive lock (non-blocking)
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Got lock - write our info
            self._acquire_time = datetime.now()
            data = {
                "pid": os.getpid(),
                "agent": agent,
                "acquired": self._acquire_time.isoformat(),
                "expires": None
            }

            os.ftruncate(self._fd, 0)
            os.lseek(self._fd, 0, os.SEEK_SET)
            os.write(self._fd, json.dumps(data, indent=2).encode())
            os.fsync(self._fd)  # Ensure data is written

            self._acquired = True
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

    def release(self) -> float:
        """Release the lock and return seconds held.

        Only removes the lock file if this instance actually acquired the lock.
        Removing it when not acquired would destroy the lock held by another
        process (they'd be flocking different inodes after re-creation).

        Returns:
            Seconds the lock was held, or 0.0 if not acquired
        """
        held_seconds = 0.0

        if self._acquire_time:
            held_seconds = (datetime.now() - self._acquire_time).total_seconds()

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

        return held_seconds

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

    @classmethod
    def set_hold(cls, agent_name: str = "unknown") -> None:
        """Set a hold on the conch for the current process.

        While a hold is active, other processes' try_acquire will fail
        even when the conch lock file is not held (between turns).
        """
        cls.HOLD_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"pid": os.getpid(), "agent": agent_name}
        cls.HOLD_FILE.write_text(json.dumps(data))

    @classmethod
    def release_hold(cls) -> None:
        """Release the hold, allowing other agents to acquire the conch."""
        try:
            if cls.HOLD_FILE.exists():
                data = json.loads(cls.HOLD_FILE.read_text())
                if data.get("pid") == os.getpid():
                    cls.HOLD_FILE.unlink()
        except (json.JSONDecodeError, OSError):
            pass

    @classmethod
    def is_held_by_other(cls) -> bool:
        """Check if another process has a hold on the conch.

        Returns:
            True if another live process holds the conch, False otherwise
        """
        if not cls.HOLD_FILE.exists():
            return False
        try:
            data = json.loads(cls.HOLD_FILE.read_text())
            pid = data.get("pid")
            if pid is None or pid == os.getpid():
                return False
            os.kill(pid, 0)  # Check if process is alive
            return True
        except (json.JSONDecodeError, ProcessLookupError, PermissionError, OSError):
            return False
