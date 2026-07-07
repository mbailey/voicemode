"""Cross-platform advisory file locking.

Wraps the platform's exclusive-lock primitive behind two functions so callers
(conch, conch_queue) stay platform-agnostic:

- Unix: ``fcntl.flock()`` on the whole file.
- Windows: ``msvcrt.locking()`` on a single byte at a large fixed offset
  (fcntl does not exist there). Unlike flock, Windows region locks are
  MANDATORY - they block reads/writes of the locked region by any other
  handle - so the lock byte sits far past any real payload (the region may
  extend beyond EOF), leaving the payload readable while the lock is held.
  This is the same trick SQLite uses for its locking byte range.

Both sides raise ``OSError`` when a non-blocking acquisition fails, so caller
error handling is identical across platforms.
"""

import os
import sys

if sys.platform != "win32":
    import fcntl

    def lock_exclusive(fd: int, blocking: bool = False) -> None:
        """Take an exclusive lock on fd; raises OSError if non-blocking and held."""
        flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
        fcntl.flock(fd, flags)

    def unlock(fd: int) -> None:
        """Release the lock taken by lock_exclusive()."""
        fcntl.flock(fd, fcntl.LOCK_UN)

else:
    import msvcrt

    # 1-byte lock region far beyond any plausible payload size.
    _LOCK_BYTE_OFFSET = 0x7FFF0000

    def _seek_lock_byte(fd: int) -> int:
        """Position fd at the lock byte, returning the previous position."""
        prev = os.lseek(fd, 0, os.SEEK_CUR)
        os.lseek(fd, _LOCK_BYTE_OFFSET, os.SEEK_SET)
        return prev

    def lock_exclusive(fd: int, blocking: bool = False) -> None:
        """Take an exclusive lock on fd; raises OSError if non-blocking and held."""
        prev = _seek_lock_byte(fd)
        try:
            if blocking:
                # LK_LOCK gives up after ~10s; loop to match flock's indefinite wait.
                while True:
                    try:
                        msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                        return
                    except OSError:
                        continue
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        finally:
            os.lseek(fd, prev, os.SEEK_SET)

    def unlock(fd: int) -> None:
        """Release the lock taken by lock_exclusive(); raises OSError if not held."""
        prev = _seek_lock_byte(fd)
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.lseek(fd, prev, os.SEEK_SET)
