"""ConchQueue - ordered, concurrency-safe waiter registry for the conch.

The :class:`~voice_mode.conch.Conch` holder lock answers "who is talking right
now?". The ConchQueue adds the other half: "who is *waiting*, and in what
order?" -- the shared, on-disk state that both the CLI and MCP front ends
read and write (VM-1610 epic). This module builds the state layer only;
converse (VM-1619), CLI (VM-1616), MCP (VM-1622), and notify-on-give (VM-1625)
all sit on top of it.

On-disk layout (siblings of the holder lock under ``~/.voicemode/``)::

    conch                       # holder lock (existing, unchanged)
    conch.queue.d/              # one file per waiter
        000017-<session>.json   # <seq zero-padded>-<session>.json
    conch.queue.seq             # flock-guarded monotonic counter
    conch.grant                 # grant hint: {"session_id", "seq", "granted_at"}

Design notes:

- **Order** = ascending ``seq``. ``seq`` is allocated by flock-locking
  ``conch.queue.seq`` (read + increment + write) so two concurrent registrants
  get distinct, monotonically increasing numbers regardless of clock skew
  across machines (remote agents).
- **Per-waiter files** mean register/deregister are atomic create/unlink with
  no read-modify-write race over a shared array.
- **Cleanup** (run at the top of ``list()`` / ``head()``): a local waiter whose
  PID is dead is dropped; a remote waiter (no PID) past its ``expires``
  heartbeat TTL is dropped. Mirrors ``Conch._check_and_clear_stale_lock``.
- **Grant hint**: on release the head is recorded in ``conch.grant`` so only
  that waiter acquires next. Without it, every waiter would race to
  ``try_acquire`` on release and FIFO order would be lost (thundering herd).
  A grant is only valid while its grantee remains a live waiter, so a
  dead/deregistered grantee invalidates the grant automatically.
- **Grant claim TTL (VM-1967)**: the grant also carries ``granted_at``. A
  WAIT-mode grantee is expected to self-acquire within one poll cycle; if it
  hasn't claimed within ``CONCH_GRANT_TTL`` seconds, the grant self-heals
  (``ConchQueue._current_grant``): the stuck grantee is evicted and the next
  live waiter is promoted, so a single missed claim (e.g. an orphaned entry
  left by a cancelled ``converse()`` call, VM-1967's root cause) can never
  wedge the queue forever. CALLBACK-mode grants are exempt (claimed
  out-of-band, at agent/human pace).

Paths are resolved at call time from ``Conch.LOCK_FILE.parent`` (NOT frozen at
import) so they honour runtime home resolution (VM-1502) and test isolation
(VM-1224), both of which re-point the conch's base directory.
"""

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import psutil

from voice_mode.conch import Conch
from voice_mode.file_lock import lock_exclusive, unlock

# Sentinel: register() defaults ``pid`` to the caller's own PID. Resolved at
# call time (not as a default-arg value) so the PID is never frozen at import.
_SELF_PID = object()


def _get_grant_ttl() -> float:
    """Get the grant claim safety-net TTL (seconds) from config, with fallback.

    Deferred import mirrors ``Conch._get_lock_expiry`` / ``_get_hold_expiry``
    (avoids freezing the value at import time, so env-var overrides and test
    monkeypatching both take effect). See ``VOICEMODE_CONCH_GRANT_TTL`` in
    config.py for the safety net this guards (VM-1967).
    """
    try:
        from voice_mode.config import CONCH_GRANT_TTL
        return CONCH_GRANT_TTL
    except ImportError:
        return 30.0


@dataclass
class WaiterEntry:
    """One waiter's record in the queue.

    Fields mirror the on-disk JSON. ``pid`` is the local process ID, or
    ``None`` for a remote waiter whose liveness is tracked by ``expires``
    (an ISO-8601 heartbeat TTL refreshed by the MCP front end, VM-1622).
    """

    session_id: str
    seq: int
    agent: Optional[str] = None
    project_path: Optional[str] = None
    voice: Optional[str] = None
    pid: Optional[int] = None
    mode: str = "wait"  # wait | callback (acted on by VM-1619/VM-1622)
    requested_at: Optional[str] = None
    expires: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "WaiterEntry":
        return cls(
            session_id=data.get("session_id"),
            seq=int(data.get("seq", 0)),
            agent=data.get("agent"),
            project_path=data.get("project_path"),
            voice=data.get("voice"),
            pid=data.get("pid"),
            mode=data.get("mode", "wait"),
            requested_at=data.get("requested_at"),
            expires=data.get("expires"),
        )

    def to_dict(self) -> dict:
        return asdict(self)


class ConchQueue:
    """Ordered waiter registry alongside the conch holder lock.

    All methods are classmethods operating on the shared on-disk state; there
    is no per-instance state to keep, which is what lets independent CLI and
    MCP processes agree on the same queue.
    """

    QUEUE_DIRNAME = "conch.queue.d"
    SEQ_FILENAME = "conch.queue.seq"
    GRANT_FILENAME = "conch.grant"

    # ---- runtime-resolved paths (VM-1502: never freeze Path.home() at import) ----

    @classmethod
    def _base_dir(cls) -> Path:
        # Siblings of the holder lock, derived at call time. Conch.LOCK_FILE is
        # the single point both production (real home) and tests (isolated
        # home, re-pinned in conftest) resolve through.
        return Conch.LOCK_FILE.parent

    @classmethod
    def _queue_dir(cls) -> Path:
        return cls._base_dir() / cls.QUEUE_DIRNAME

    @classmethod
    def _seq_file(cls) -> Path:
        return cls._base_dir() / cls.SEQ_FILENAME

    @classmethod
    def _grant_file(cls) -> Path:
        return cls._base_dir() / cls.GRANT_FILENAME

    # ---- low-level helpers ----

    @staticmethod
    def _filename(seq: int, session_id: str) -> str:
        """Build a queue entry filename: ``<seq zero-padded>-<safe-session>.json``.

        The session id is sanitised for filesystem safety; uniqueness is
        guaranteed by the (monotonic, unique) seq prefix, and the canonical
        session id always lives in the JSON body -- lookups match on that, not
        on the filename, so sanitisation can never cause a mismatch.
        """
        safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in str(session_id))
        return f"{seq:06d}-{safe}.json"

    @staticmethod
    def _unlink(path: Path) -> None:
        """Best-effort unlink; safe if the file is already gone."""
        try:
            path.unlink()
        except (FileNotFoundError, OSError):
            pass

    @staticmethod
    def _atomic_write_json(path: Path, data: dict) -> None:
        """Write JSON atomically: temp file + ``os.replace`` (readers never see
        a partial write, and the rename is atomic on POSIX)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
        blob = json.dumps(data, indent=2).encode()
        fd = os.open(str(tmp), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
        try:
            os.write(fd, blob)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, path)

    @staticmethod
    def _normalize_expires(expires) -> Optional[str]:
        if expires is None:
            return None
        if isinstance(expires, datetime):
            return expires.isoformat()
        return str(expires)

    @staticmethod
    def _parse_iso(value) -> Optional[datetime]:
        """Parse an ISO-8601 timestamp, tolerating a trailing ``Z`` (UTC).

        Python 3.10's ``datetime.fromisoformat`` does not accept the ``Z``
        designator, yet remote front ends (JS/Go MCP clients, VM-1622) routinely
        emit it, so normalise ``Z`` -> ``+00:00`` first. Returns ``None`` when
        the value cannot be parsed.
        """
        try:
            if value.endswith("Z"):
                value = value[:-1] + "+00:00"
            return datetime.fromisoformat(value)
        except (ValueError, TypeError, AttributeError):
            return None

    @classmethod
    def _is_live(cls, data: dict) -> bool:
        """Is this waiter still alive?

        Local waiter (``pid`` set): liveness by PID probe (psutil; os.kill
        with signal 0 is not portable -- it terminates the target on
        Windows). A process that exists but is owned by another user is
        treated as alive. Remote waiter (``pid`` is ``None``): liveness
        by the ``expires`` heartbeat TTL. A remote waiter with no TTL is kept
        (we cannot prove it dead).
        """
        pid = data.get("pid")
        if pid is not None:
            try:
                return psutil.pid_exists(pid)
            except (TypeError, ValueError):
                return False
        expires = data.get("expires")
        if not expires:
            return True
        exp = cls._parse_iso(expires)
        if exp is None:
            return False
        # Compare in the timestamp's own awareness. A cross-machine remote agent
        # naturally heartbeats with a tz-aware UTC ``expires``; judging that
        # against a naive local clock raises ``TypeError`` and would wrongly
        # prune a live waiter, so pair a naive ``now`` with naive ``exp`` and an
        # aware ``now`` with aware ``exp``.
        now = datetime.now(exp.tzinfo) if exp.tzinfo is not None else datetime.now()
        return now <= exp

    @classmethod
    def _next_seq(cls) -> int:
        """Allocate the next monotonic sequence number (flock-guarded)."""
        seq_file = cls._seq_file()
        seq_file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(seq_file), os.O_CREAT | os.O_RDWR, 0o644)
        try:
            lock_exclusive(fd, blocking=True)  # blocking: serialise the bump
            os.lseek(fd, 0, os.SEEK_SET)
            raw = os.read(fd, 64).decode().strip()
            current = int(raw) if raw else 0
            nxt = current + 1
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, os.SEEK_SET)
            os.write(fd, str(nxt).encode())
            os.fsync(fd)
            return nxt
        finally:
            try:
                unlock(fd)
            finally:
                os.close(fd)

    @classmethod
    def _scan(cls, clean: bool = True) -> List[WaiterEntry]:
        """Read all waiter entries in order, optionally pruning stale/dup files.

        Dedupes by ``session_id`` keeping the lowest seq (fairness: a session's
        earliest place in line wins). When ``clean`` is True, dead/expired,
        corrupt, and higher-seq duplicate files are unlinked.
        """
        qdir = cls._queue_dir()
        if not qdir.exists():
            return []
        best = {}  # session_id -> (WaiterEntry, Path)
        for f in sorted(qdir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError, ValueError):
                if clean:
                    cls._unlink(f)  # corrupt entry
                continue
            if not cls._is_live(data):
                if clean:
                    cls._unlink(f)
                continue
            entry = WaiterEntry.from_dict(data)
            sid = entry.session_id
            cur = best.get(sid)
            if cur is None:
                best[sid] = (entry, f)
            else:
                # Keep the lowest seq; drop the higher-seq duplicate.
                if entry.seq < cur[0].seq:
                    if clean:
                        cls._unlink(cur[1])
                    best[sid] = (entry, f)
                elif clean:
                    cls._unlink(f)
        entries = [e for (e, _p) in best.values()]
        entries.sort(key=lambda e: e.seq)
        return entries

    @classmethod
    def _find(cls, session_id):
        """Return ``(WaiterEntry, Path)`` for this session, or ``(None, None)``.

        Matches on the JSON ``session_id`` (not the filename) and returns the
        lowest-seq file if duplicates somehow exist.
        """
        qdir = cls._queue_dir()
        if not qdir.exists():
            return None, None
        match = None
        for f in sorted(qdir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
            except (json.JSONDecodeError, OSError, ValueError):
                continue
            if data.get("session_id") == session_id:
                entry = WaiterEntry.from_dict(data)
                if match is None or entry.seq < match[0].seq:
                    match = (entry, f)
        return match if match is not None else (None, None)

    @classmethod
    def _clear_stale_grant(cls, live_sessions: set) -> None:
        """Drop the grant if it names no one or a session that is no longer live."""
        gf = cls._grant_file()
        try:
            g = json.loads(gf.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            return
        sid = g.get("session_id")
        if sid is None or sid not in live_sessions:
            cls._unlink(gf)

    @classmethod
    def _maybe_clear_grant_for(cls, session_id) -> None:
        """Clear the grant if it currently names ``session_id``."""
        gf = cls._grant_file()
        try:
            g = json.loads(gf.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            return
        if g.get("session_id") == session_id:
            cls._unlink(gf)

    # ---- public API ----

    @classmethod
    def register(
        cls,
        session_id: str,
        *,
        agent: Optional[str] = None,
        project_path: Optional[str] = None,
        voice: Optional[str] = None,
        mode: str = "wait",
        pid=_SELF_PID,
        expires=None,
    ) -> int:
        """Register (or refresh) a waiter; return its 1-based position in line.

        Idempotent per session: re-registering the same ``session_id`` keeps
        its original ``seq`` and ``requested_at`` (so a heartbeat refresh does
        not lose its place) while updating the mutable fields and ``expires``.

        Args:
            session_id: Caller-provided session id (required, the queue key).
            agent / project_path / voice: descriptive fields, mirror the conch
                holder payload.
            mode: ``wait`` or ``callback`` (stored now; acted on by VM-1619).
            pid: defaults to the caller's PID (local waiter). Pass ``None`` for
                a remote waiter (liveness then tracked by ``expires``); pass an
                explicit int to register on behalf of another process.
            expires: heartbeat TTL for a remote waiter -- a ``datetime`` or
                ISO-8601 string. Optional for local waiters.

        Returns:
            The waiter's 1-based position among current live waiters.
        """
        if session_id is None:
            raise ValueError("session_id is required to register a waiter")
        if pid is _SELF_PID:
            pid = os.getpid()
        expires = cls._normalize_expires(expires)

        qdir = cls._queue_dir()
        qdir.mkdir(parents=True, exist_ok=True)

        existing, existing_path = cls._find(session_id)
        if existing is not None:
            seq = existing.seq
            requested_at = existing.requested_at or datetime.now().isoformat()
            target = existing_path
        else:
            seq = cls._next_seq()
            requested_at = datetime.now().isoformat()
            target = qdir / cls._filename(seq, session_id)

        data = {
            "session_id": session_id,
            "seq": seq,
            "agent": agent,
            "project_path": project_path,
            "voice": voice,
            "pid": pid,
            "mode": mode,
            "requested_at": requested_at,
            "expires": expires,
        }
        cls._atomic_write_json(target, data)

        order = cls.list()
        for i, e in enumerate(order):
            if e.session_id == session_id:
                return i + 1
        return len(order)

    @classmethod
    def deregister(cls, session_id: str) -> None:
        """Remove a waiter (atomic unlink). Safe to call twice / when absent.

        Also clears the grant if it currently names this session.
        """
        qdir = cls._queue_dir()
        if qdir.exists():
            for f in sorted(qdir.glob("*.json")):
                try:
                    data = json.loads(f.read_text())
                except (json.JSONDecodeError, OSError, ValueError):
                    continue
                if data.get("session_id") == session_id:
                    cls._unlink(f)
        cls._maybe_clear_grant_for(session_id)

    @classmethod
    def list(cls) -> List[WaiterEntry]:
        """Live waiters in order (runs stale cleanup first)."""
        entries = cls._scan(clean=True)
        cls._clear_stale_grant({e.session_id for e in entries})
        return entries

    @classmethod
    def head(cls) -> Optional[WaiterEntry]:
        """The next-in-line waiter, or ``None`` (runs stale cleanup first)."""
        entries = cls.list()
        return entries[0] if entries else None

    @classmethod
    def cleanup_stale(cls) -> None:
        """Drop dead-PID (local) and expired-heartbeat (remote) waiters, plus a
        stale grant. Idempotent; folded into ``list()``/``head()``."""
        cls.list()

    @classmethod
    def grant_next(cls, *, notify_block: bool = True) -> Optional[WaiterEntry]:
        """Promote the next acquirer on release -- unless an explicit give stands.

        Called on the holder's full release. Normally records a live waiter in
        ``conch.grant`` so only that session acquires next (FIFO, no
        thundering-herd re-acquire), returning it -- or ``None`` (clearing any
        grant) when the queue is empty.

        **Explicit give wins (VM-1616):** if a grant already names a still-live
        waiter, it is preserved rather than overwritten by head-promotion. That
        grant can only exist because an operator ran ``conch give <session>``
        while the holder was still speaking; honouring it here is what lets
        ``give`` survive the holder's release and jump a chosen waiter ahead of
        the head. In the normal flow no grant exists at release time (the
        previous grantee consumed it on acquire), so this defers *only* to a
        deliberate give. A stale give (grantee died/left) is cleared by
        ``granted_to`` and falls through to promotion, so a dead give can never
        wedge the queue.

        **Skip leading callback waiters (VM-1625, F1):** a ``callback`` waiter
        never self-acquires (delivery is out-of-band) yet stays a live waiter,
        so a grant standing on it gates **every** ``wait`` waiter behind it via
        ``Conch._queue_grant_blocks`` -- starving blocking waiters until they
        time out. So when at least one ``wait`` waiter exists, grant the
        first one, skipping any leading callback waiters, and ping each skipped
        callback waiter to return (``conch_notify.notify_granted``). With **only**
        callback waiters (no blocking waiter to starve) the head is granted
        unchanged -- the lone-callback case VM-1619's converse delivery handles.

        Trade-off (intended): a later ``wait`` waiter can acquire ahead of an
        idle callback waiter -- callback means "ping me, I'm not blocking", so a
        blocking waiter should not starve behind it.

        ``notify_block`` controls how the skipped-callback pings are delivered.
        Default ``True`` runs them synchronously -- right for the one-shot CLI
        ``bump`` path. The converse **release** hot path
        (``Conch._queue_promote_next``) passes ``notify_block=False`` so each
        ping is fire-and-forget and a wedged ``session send`` can never add to
        the holder's release latency (VM-1625 impl-001 peer-review finding).
        """
        existing = cls.granted_to()  # validates liveness; clears a stale grant
        if existing is not None:
            for e in cls.list():
                if e.session_id == existing:
                    return e  # explicit give stands -- do not clobber

        waiters = cls.list()  # live, ordered; runs cleanup
        if not waiters:
            cls.clear_grant()
            return None

        # First wait-mode waiter wins; everything ahead of it is a callback
        # waiter we skip (and ping). No wait waiter => only callbacks => grant
        # the head unchanged (nothing to starve).
        target = None
        skipped = []
        for e in waiters:
            if e.mode == "wait":
                target = e
                break
            skipped.append(e)
        if target is None:
            target = waiters[0]
        else:
            for e in skipped:
                if e.mode == "callback":
                    cls._notify_callback(e, block=notify_block)

        cls._atomic_write_json(
            cls._grant_file(),
            {
                "session_id": target.session_id,
                "seq": target.seq,
                # VM-1967 safety net: stamp when this grant was issued so a
                # WAIT-mode grant that never gets claimed can self-heal past
                # CONCH_GRANT_TTL (see ``_grant_wedged`` / ``_current_grant``).
                "granted_at": datetime.now().isoformat(),
            },
        )
        return target

    @classmethod
    def _notify_callback(cls, entry, *, block: bool = True) -> None:
        """Best-effort ping to a skipped callback waiter (VM-1625).

        Lazy import + swallow-all, matching the fail-safe queue integration in
        ``Conch``: notifying is never allowed to break grant promotion, which is
        critical-path coordination, and the queue stays usable when the notify
        module / ``session`` binary is absent.

        ``block`` is forwarded to ``notify_granted``: the release hot path passes
        ``block=False`` so the ping is dispatched off-thread and never delays the
        holder's release; the CLI ``bump`` path keeps the synchronous default.
        """
        try:
            from voice_mode.conch_notify import notify_granted
            notify_granted(entry, block=block)
        except Exception:
            pass

    @classmethod
    def grant(cls, session_id: str) -> bool:
        """Grant the conch to a *named* live waiter (used by ``conch give``).

        Unlike :meth:`grant_next` (which always promotes the head), this writes
        the grant for an arbitrary session -- but only if that session is
        currently a live waiter, preserving the invariant that a grant always
        names someone in the queue (``granted_to`` validates against the live
        scan, so a grant to a non-waiter would be cleared on the next read).

        Args:
            session_id: the waiter to grant to.

        Returns:
            ``True`` if the session was a live waiter and the grant was written;
            ``False`` (no grant written) if it is not in the queue.
        """
        if session_id is None:
            return False
        for e in cls.list():  # runs cleanup; only live waiters
            if e.session_id == session_id:
                cls._atomic_write_json(
                    cls._grant_file(),
                    {
                        "session_id": e.session_id,
                        "seq": e.seq,
                        # VM-1967 safety net -- see grant_next().
                        "granted_at": datetime.now().isoformat(),
                    },
                )
                return True
        return False

    @classmethod
    def _grant_wedged(cls, grant: dict, entry: "WaiterEntry") -> bool:
        """True if a WAIT-mode grant has sat unclaimed past ``CONCH_GRANT_TTL``.

        Only WAIT-mode grantees are safety-netted: a WAIT waiter is expected
        to self-acquire within one poll cycle of being granted (the
        ``converse()`` WAIT loop polls ``try_acquire()`` every
        ``CONCH_CHECK_INTERVAL``), so "still unclaimed after
        ``CONCH_GRANT_TTL``" means the claim was missed -- exactly VM-1967's
        root cause (a cancelled WAIT caller's orphaned, still-"live" queue
        entry gets granted and nothing ever claims it, and with no TTL the
        grant blocked the whole queue forever). A CALLBACK grantee is
        claimed out-of-band at agent/human pace (VM-1625) -- unclaimed for a
        while is normal there, not stuck, so it is exempt.
        """
        if entry.mode != "wait":
            return False
        ttl = _get_grant_ttl()
        if not ttl or ttl <= 0:
            return False
        granted_at = cls._parse_iso(grant.get("granted_at"))
        if granted_at is None:
            # No timestamp (grant predates VM-1967, or was written by
            # something else) -- can't judge age, so don't guess stuck. The
            # next grant_next()/grant() call stamps one.
            return False
        now = datetime.now(granted_at.tzinfo) if granted_at.tzinfo is not None else datetime.now()
        return (now - granted_at).total_seconds() > ttl

    @classmethod
    def _current_grant(cls) -> Optional[dict]:
        """The current grant record (``session_id``/``seq``/``granted_at``), or ``None``.

        A grant is only valid while its grantee is still a live waiter; a
        dead or deregistered grantee leaves the grant stale, which this
        clears (pre-VM-1967 behaviour, unchanged). VM-1967 safety net: a
        WAIT-mode grant nobody ever claims within ``CONCH_GRANT_TTL`` is ALSO
        treated as stale here -- the stuck grantee is evicted from the queue
        and the next live waiter is promoted (mirroring the manual
        ``conch give`` recovery an operator would otherwise have to do), so
        one missed claim can never wedge the queue permanently. This runs as
        a side effect of every read (``granted_to`` / ``_queue_grant_blocks``
        / status), mirroring ``_scan``'s existing prune-on-read pattern -- in
        practice it self-heals the moment any other queued waiter's poll
        loop (or a status check) next asks "who is granted?".
        """
        gf = cls._grant_file()
        try:
            g = json.loads(gf.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            return None
        sid = g.get("session_id")
        if sid is None:
            cls._unlink(gf)
            return None
        for e in cls._scan(clean=True):
            if e.session_id == sid:
                if cls._grant_wedged(g, e):
                    cls.deregister(sid)
                    cls.grant_next(notify_block=False)
                    return cls._current_grant()
                return g
        cls._unlink(gf)  # grantee gone -- stale grant
        return None

    @classmethod
    def granted_to(cls) -> Optional[str]:
        """The session id of the current live grantee, or ``None``.

        A grant is only valid while its grantee is still a live waiter, or
        (VM-1967) while a WAIT-mode grant remains within its claim TTL --
        see ``_current_grant``.
        """
        g = cls._current_grant()
        return g.get("session_id") if g else None

    @classmethod
    def grant_age_seconds(cls) -> Optional[float]:
        """Seconds since the current grant was issued, or ``None``.

        ``None`` when there is no live grant, or the grant predates VM-1967
        and carries no ``granted_at`` timestamp. Used by status front ends
        (``conch_ops.status_payload``) to surface how long a grant has gone
        unclaimed.
        """
        g = cls._current_grant()
        if g is None:
            return None
        granted_at = cls._parse_iso(g.get("granted_at"))
        if granted_at is None:
            return None
        now = datetime.now(granted_at.tzinfo) if granted_at.tzinfo is not None else datetime.now()
        return max(0.0, (now - granted_at).total_seconds())

    @classmethod
    def is_granted(cls, session_id: str) -> bool:
        """Is ``session_id`` the current grantee (the only one allowed to acquire)?"""
        if session_id is None:
            return False
        return cls.granted_to() == session_id

    @classmethod
    def clear_grant(cls) -> None:
        """Remove the grant hint (no-op if absent)."""
        cls._unlink(cls._grant_file())
