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

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Platform-specific file locking
IS_WINDOWS = sys.platform == 'win32'

if IS_WINDOWS:
    import msvcrt
else:
    import fcntl

# Import config for lock expiry - deferred to avoid circular import
def _get_lock_expiry() -> float:
    """Get lock expiry from config, with fallback."""
    try:
        from voice_mode.config import CONCH_LOCK_EXPIRY
        return CONCH_LOCK_EXPIRY
    except ImportError:
        return 120.0  # Default 2 minutes


def _lock_file(fd: int, exclusive: bool = True, blocking: bool = False) -> bool:
    """Platform-independent file locking.

    Args:
        fd: File descriptor
        exclusive: If True, exclusive lock; otherwise shared
        blocking: If True, wait for lock; otherwise fail immediately

    Returns:
        True if lock acquired, False otherwise
    """
    if IS_WINDOWS:
        try:
            # On Windows, lock the first byte of the file
            msvcrt.locking(fd, msvcrt.LK_NBLCK if not blocking else msvcrt.LK_LOCK, 1)
            return True
        except (IOError, OSError):
            return False
    else:
        try:
            flags = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            if not blocking:
                flags |= fcntl.LOCK_NB
            fcntl.flock(fd, flags)
            return True
        except (BlockingIOError, OSError):
            return False


def _unlock_file(fd: int) -> None:
    """Platform-independent file unlocking."""
    if IS_WINDOWS:
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except (IOError, OSError):
            pass
    else:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


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

        Uses file locking for true atomic locking across processes.
        Also handles stale locks: if a lock is older than CONCH_LOCK_EXPIRY
        seconds, it will be forcibly released and re-acquired.

        Args:
            agent_name: Name of the agent acquiring the lock

        Returns:
            True if lock acquired, False if already held by another process
        """
        if self._acquired:
            return True  # Already holding it

        agent = agent_name or self.agent_name or "unknown"
        self.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

        # First check: is there a stale lock we can forcibly clear?
        self._check_and_clear_stale_lock()

        try:
            # Open file for read/write, create if doesn't exist
            self._fd = os.open(str(self.LOCK_FILE), os.O_CREAT | os.O_RDWR, 0o644)

            # Try to get exclusive lock (non-blocking)
            if not _lock_file(self._fd, exclusive=True, blocking=False):
                if self._fd is not None:
                    try:
                        os.close(self._fd)
                    except OSError:
                        pass
                    self._fd = None
                return False

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
        """Check for and clear stale locks based on timestamp.

        If a lock file exists and its timestamp exceeds CONCH_LOCK_EXPIRY,
        forcibly remove it to allow new acquisitions. This handles the case
        where a process is alive but stuck and won't release the lock.

        Note: This deletes the file, creating a new inode. The stuck process
        still holds its flock on the old inode, but we can now create a fresh
        lock file.
        """
        lock_expiry = _get_lock_expiry()
        if lock_expiry <= 0:
            return  # Stale lock detection disabled

        if not self.LOCK_FILE.exists():
            return

        try:
            data = json.loads(self.LOCK_FILE.read_text())
            acquired_str = data.get("acquired")
            if not acquired_str:
                return

            acquired_time = datetime.fromisoformat(acquired_str)
            age_seconds = (datetime.now() - acquired_time).total_seconds()

            if age_seconds > lock_expiry:
                # Lock is stale - forcibly remove it
                stale_agent = data.get("agent", "unknown")
                stale_pid = data.get("pid", "unknown")
                try:
                    self.LOCK_FILE.unlink()
                    # Log would be nice here, but avoid import complexity
                except OSError:
                    pass
        except (json.JSONDecodeError, ValueError, OSError):
            # Can't read or parse - ignore
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
                _unlock_file(self._fd)
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
