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

        Uses fcntl.flock() for true atomic locking across processes.

        Args:
            agent_name: Name of the agent acquiring the lock

        Returns:
            True if lock acquired, False if already held by another process
        """
        if self._acquired:
            return True  # Already holding it

        agent = agent_name or self.agent_name or "unknown"
        self.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)

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

    def release(self) -> float:
        """Release the lock and return seconds held.

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

        # Remove the lock file
        if self.LOCK_FILE.exists():
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

        A conversation is considered active if the lock file exists AND
        the PID in the file corresponds to a running process.

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
            return True
        except (json.JSONDecodeError, ProcessLookupError, PermissionError, OSError):
            # JSON invalid, process dead, or no permission to signal
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
