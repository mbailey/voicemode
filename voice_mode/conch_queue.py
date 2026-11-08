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
    conch.grant                 # grant hint: {"session_id", "seq", "granted_at",
                                 #              "claim_ttl" (optional)}

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
- **Grant claim TTL (VM-1967, widened VM-2078)**: the grant also carries
  ``granted_at``. A grantee is expected to self-acquire within one poll
  cycle; if it hasn't claimed within ``CONCH_GRANT_TTL`` seconds (or the
  grant's own ``claim_ttl`` override, see below), the grant self-heals
  (``ConchQueue._current_grant``): the stuck grantee is evicted and the next
  live waiter is promoted, so a single missed claim (e.g. an orphaned entry
  left by a cancelled ``converse()`` call, VM-1967's root cause) can never
  wedge the queue forever. Every grant is now covered -- VM-2078 removed the
  callback mode whose exemption from this TTL is what let a single unclaimed
  grant wedge the queue permanently. The judgement also holds off entirely
  while a live holder still blocks the claim (``_grant_wedged``'s holder
  gate) -- a grantee cannot claim a floor nobody has released yet.
- **``claim_ttl`` (VM-2078 fix-002)**: an optional, bounded override
  (seconds, must be > 0) on a single grant record, recorded in place of the
  base ``CONCH_GRANT_TTL``. Written by TWO grant-issuing paths, each from
  evidence the GRANTER observes at grant time -- never a self-declared
  property of the waiter: ``grant()`` (the ``conch give`` / summon path)
  when it has direct evidence the claim mechanism differs from an ordinary
  poll loop (e.g. a ``summon_and_grant`` nudge confirmed delivered, D2); and
  ``grant_next()``'s ordinary head-promotion, when the promoted waiter has
  no local ``pid`` -- a remote waiter's claim is a heartbeat round trip, not
  a poll loop, so it gets ``max(CONCH_GRANT_TTL, CONCH_REMOTE_TTL)``.
  Deliberately not a field on ``WaiterEntry``: it describes what was
  observed about *this grant*, not a category of waiter, so it cannot
  resurrect the removed ``mode`` concept under a new name.

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


def _get_remote_ttl() -> float:
    """Heartbeat-cadence claim window (seconds) for a grantee with no local
    poll loop (``pid is None``).

    Deferred import for the same reason as ``_get_grant_ttl`` -- env-var
    overrides and test monkeypatching must both take effect, and this module
    deliberately carries no top-level config import (VM-1502). Reuses the
    existing ``VOICEMODE_CONCH_REMOTE_TTL`` (already the remote heartbeat
    TTL front ends stamp onto ``expires``, see ``tools/conch.py``) rather
    than inventing a second remote-timing knob.
    """
    try:
        from voice_mode.config import CONCH_REMOTE_TTL
        return CONCH_REMOTE_TTL
    except ImportError:
        return 90.0


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
    voice_requested: Optional[str] = None  # VM-1901: caller's verbatim expression
    voice_via: Optional[str] = None        # VM-1901: resolution route
    pid: Optional[int] = None
    requested_at: Optional[str] = None
    expires: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "WaiterEntry":
        # field-explicit on purpose -- never refactor to cls(**data). Reading
        # named keys via data.get(...) means a legacy or future unknown key
        # (e.g. VM-2078's now-removed "mode": "callback") is silently
        # ignored rather than raising TypeError.
        return cls(
            session_id=data.get("session_id"),
            seq=int(data.get("seq", 0)),
            agent=data.get("agent"),
            project_path=data.get("project_path"),
            voice=data.get("voice"),
            voice_requested=data.get("voice_requested"),
            voice_via=data.get("voice_via"),
            pid=data.get("pid"),
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
        voice_requested: Optional[str] = None,
        voice_via: Optional[str] = None,
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
                holder payload. ``voice`` is the RESOLVED voice (VM-1901).
            voice_requested / voice_via: additive VM-1901 fields — the
                caller's verbatim expression and its resolution route,
                mirroring the conch holder payload.
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
            "voice_requested": voice_requested,
            "voice_via": voice_via,
            "pid": pid,
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
    def _write_grant_decision(
        cls, entry: "WaiterEntry", *, claim_ttl: Optional[float] = None
    ) -> None:
        """Write a NEW grant to ``entry`` -- the single writer for both
        grant-issuing DECISION points (VM-2078 fix-002 REFINE #2).

        This module has four writes to the grant record that look identical
        at a glance but split into two categories: **decisions** (this
        method -- ``grant_next()``'s head-promotion and ``grant()``'s
        named-waiter grant) derive ``claim_ttl`` from scratch for a *new*
        grant; **refreshes** (``grant_next()``'s honour-an-existing-give
        re-stamp, and ``_current_grant``'s granted_at-missing self-heal
        stamp) preserve whatever ``claim_ttl`` a previous decision wrote,
        verbatim, and must NOT re-derive it here -- doing so would quietly
        turn a preserver into a decider and erase the split this method
        exists to keep legible in code, not just in a comment (mirrors the
        read-side split between ``_raw_grant``, unjudged, and
        ``_current_grant``, judged).

        Args:
            entry: the waiter being granted to.
            claim_ttl: an explicit, GRANTER-observed override (``grant()``'s
                confirmed-delivered summon nudge) -- always wins over the
                fallback below. If ``None`` and ``entry.pid is None``,
                falls back to the bounded remote window
                (``max(_get_grant_ttl(), _get_remote_ttl())``): a pid-less
                waiter's claim is a heartbeat/status round trip, not a poll
                loop, so the base window is structurally unwinnable for it,
                whether it arrived here via ordinary head-promotion or an
                explicit ``conch give`` with no delivery evidence to
                report. ``max()``, never a replacement -- an
                administratively widened ``CONCH_GRANT_TTL`` (e.g. for
                debugging) must not be cut back to the remote default.
        """
        payload = {
            "session_id": entry.session_id,
            "seq": entry.seq,
            # VM-1967 safety net: stamp when this grant was issued so a
            # grant that never gets claimed can self-heal past
            # CONCH_GRANT_TTL (see ``_grant_wedged`` / ``_current_grant``).
            "granted_at": datetime.now().isoformat(),
        }
        if claim_ttl is not None:
            payload["claim_ttl"] = claim_ttl
        elif entry.pid is None:
            payload["claim_ttl"] = cls.remote_claim_window()
        cls._atomic_write_json(cls._grant_file(), payload)

    @classmethod
    def remote_claim_window(cls) -> float:
        """The bounded claim window (seconds) for a grantee with no poll loop
        of its own -- ``max(_get_grant_ttl(), _get_remote_ttl())``.

        The single source of truth for that value, used two ways: (1) as the
        ``pid is None`` fallback in :meth:`_write_grant_decision` above, and
        (2) as the explicit ``claim_ttl`` a caller with its OWN delivery
        evidence passes to :meth:`grant` (e.g.
        ``conch_ops.summon_and_grant``'s confirmed-delivered nudge, VM-2078
        D2) -- a summoned *local*-pid target answered via a pane nudge claims
        at human/agent reaction speed, the same order of magnitude as a
        remote heartbeat round trip, not a poll cycle, so it needs the same
        bounded widening even though it has a pid.
        """
        return max(_get_grant_ttl(), _get_remote_ttl())

    @classmethod
    def grant_next(cls) -> Optional[WaiterEntry]:
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

        Grants the head, always. There is deliberately **no** mode-based skip:
        callback mode was removed in VM-2078 because a grant that nobody polls
        for cannot be reasoned about at grant time -- the starvation guard was
        evaluated only when a grant was made, so a lone callback waiter granted
        before its victim existed wedged the queue permanently. Every waiter now
        polls; every grant is TTL-covered.
        """
        # Deliberately reads the RAW grant record (``_raw_grant``), NOT the
        # TTL-judged ``_current_grant``/``granted_to``. Judging staleness
        # here -- before this branch gets to re-stamp -- would evict a
        # legitimate give for having sat exactly as long as the holder it
        # was waiting behind was still speaking: the holder-gate in
        # ``_grant_wedged`` protects reads made *while the holder is still
        # active*, but by the time ``grant_next()`` runs on release, the
        # holder lock is already gone (``Conch.release`` unlinks it before
        # calling ``_queue_promote_next``), so a judged read at this exact
        # instant would see no holder and immediately evict the give it is
        # about to honour. Liveness (is the named session still a live
        # waiter?) is the only validity check this branch needs -- staleness
        # of the OLD timestamp is moot, since honouring it re-stamps to now
        # regardless of how old it was (VM-2078 Q3 design review).
        raw_grant = cls._raw_grant()
        existing = raw_grant.get("session_id") if raw_grant else None
        if existing is not None:
            for e in cls.list():
                if e.session_id == existing:
                    # Re-stamp granted_at: THIS is the moment the floor
                    # actually frees and the grantee's claim window begins --
                    # not whenever the operator originally ran `conch give`
                    # while a previous holder was still speaking. Without
                    # this the grant would already be old at the exact
                    # moment it becomes claimable, and get judged wedged on
                    # the very next read. Preserve any other keys on the
                    # existing grant record verbatim (e.g. ``claim_ttl`` --
                    # see ``grant()``): re-stamping is a timestamp refresh,
                    # not a new grant decision, so a bounded window the
                    # granter earlier wrote on observed delivery evidence
                    # must survive it.
                    payload = dict(raw_grant)
                    payload["granted_at"] = datetime.now().isoformat()
                    cls._atomic_write_json(cls._grant_file(), payload)
                    return e  # explicit give stands -- do not clobber, only re-stamp
            # Named session is no longer a live waiter: a dead/departed give
            # must not wedge the queue. No explicit clear needed here -- the
            # head-promotion write below (or clear_grant on an empty queue)
            # unconditionally overwrites/removes this stale record.

        waiters = cls.list()  # live, ordered; runs cleanup
        if not waiters:
            cls.clear_grant()
            return None

        target = waiters[0]
        # A NEW grant decision (not a refresh) -- see ``_write_grant_decision``
        # for why that distinction is written into the code, not left as a
        # comment. No explicit ``claim_ttl``: this is ordinary head-promotion,
        # not the summon carve-out, so the only evidence available is
        # ``target.pid``, which the helper itself keys on.
        cls._write_grant_decision(target)
        return target

    @classmethod
    def grant(cls, session_id: str, *, claim_ttl: Optional[float] = None) -> bool:
        """Grant the conch to a *named* live waiter (used by ``conch give``).

        Unlike :meth:`grant_next` (which always promotes the head), this writes
        the grant for an arbitrary session -- but only if that session is
        currently a live waiter, preserving the invariant that a grant always
        names someone in the queue (``granted_to`` validates against the live
        scan, so a grant to a non-waiter would be cleared on the next read).

        Args:
            session_id: the waiter to grant to.
            claim_ttl: an optional bounded claim-window override (seconds,
                must be > 0 -- a value <= 0 is ignored by ``_grant_wedged``
                rather than treated as "no TTL"), recorded on the GRANT
                RECORD in place of the base ``CONCH_GRANT_TTL`` (see
                ``_grant_wedged``). This exists for
                the D2 operator-summon carve-out: a summoned session has no
                poll loop of its own, so the base window (sized for a poll
                loop) is too short for it to answer a pane nudge. The window
                is set here by the GRANTER, from evidence the granter itself
                observed (e.g. do-003's checked-and-surfaced nudge-delivery
                result) -- never self-declared by the grantee's entry. This
                is deliberately NOT a category field: it lives on the
                one-shot grant record, not on ``WaiterEntry``, so it says
                nothing about the *kind* of waiter, only about what was
                observed for THIS grant. Callers that have no such evidence
                must leave this ``None`` -- and a caller that observed the
                nudge FAIL (or the target being remote, where no nudge is
                even possible) must not call ``grant()`` at all, per the
                same ruling. ``None`` does not always mean "base TTL
                applies" though: if the target waiter has no local ``pid``,
                this method itself falls back to the same bounded remote
                window ``grant_next()`` uses for ordinary head-promotion
                (VM-2078 fix-002 REFINE #2) -- ``conch give`` to a remote
                waiter is the same unwinnable poll-cycle arithmetic as an
                ordinary remote promotion, through a different door, and a
                caller-supplied ``claim_ttl`` still wins over it.

        Returns:
            ``True`` if the session was a live waiter and the grant was written;
            ``False`` (no grant written) if it is not in the queue.
        """
        if session_id is None:
            return False
        for e in cls.list():  # runs cleanup; only live waiters
            if e.session_id == session_id:
                # A NEW grant decision -- see ``_write_grant_decision``. An
                # explicit ``claim_ttl`` (this method's own summon carve-out)
                # always wins; failing that, the helper still falls back to
                # the bounded remote window if ``e.pid is None`` -- `conch
                # give` to a remote waiter is the same unwinnable poll-cycle
                # arithmetic as an ordinary remote head-promotion
                # (``grant_next()``), through a different door.
                cls._write_grant_decision(e, claim_ttl=claim_ttl)
                return True
        return False

    @classmethod
    def _effective_claim_ttl(cls, grant: dict) -> Optional[float]:
        """The claim-window TTL (seconds) governing ``grant``, or ``None`` if
        the TTL net is administratively disabled -- i.e. there is no
        deadline at all, never "the deadline already passed".

        Single source of truth for the ENFORCER (``_grant_wedged``) and the
        REPORTER (``claim_window_remaining``) -- they must never be able to
        disagree about what the window IS, only about what to DO with it
        (evict vs. report seconds left). Before this extraction each
        computed its own answer and drifted: with ``CONCH_GRANT_TTL=0`` the
        enforcer correctly never expired the grant, but the reporter said
        "0.0 seconds remaining" for that same grant -- which reads as
        *already expired*, the opposite of what is true. That is the same
        family of bug ``_write_grant_decision`` exists to prevent on the
        write side, reproduced on the read side (VM-2078 do-003 REFINE #1).

        A disabled base TTL (``CONCH_GRANT_TTL <= 0``) turns TTL judgement
        off PROJECT-WIDE, including any per-grant ``claim_ttl`` override --
        an operator who sets ``CONCH_GRANT_TTL=0`` to disable the safety net
        entirely should not have a summon/remote override quietly keep a
        piece of it running (mirrors ``grant()``'s own doc on this point).
        """
        base = _get_grant_ttl()
        if not base or base <= 0:
            return None  # administratively disabled -- no deadline at all
        claim_ttl = grant.get("claim_ttl")
        if claim_ttl is not None and claim_ttl > 0:
            # A bounded, GRANTER-observed override for this specific grant
            # (e.g. a confirmed-delivered summon nudge, or a remote
            # head-promotion) -- OVERRIDES the base window and must be > 0;
            # it happens to widen in every caller today, but nothing here
            # requires that (a narrower override would just evict sooner,
            # harmlessly). Ignored if <= 0 (malformed) rather than treated
            # as "no TTL", so a corrupt claim_ttl can't reintroduce an
            # un-expiring grant.
            return claim_ttl
        return base

    @classmethod
    def _grant_wedged(cls, grant: dict, entry: "WaiterEntry") -> bool:
        """True if a grant has sat unclaimed past its claim window.

        Every ordinary grantee is expected to self-acquire within one poll
        cycle of being granted (the ``converse()`` loop polls
        ``try_acquire()`` every ``CONCH_CHECK_INTERVAL``), so "still
        unclaimed after the TTL" means the claim was missed -- exactly
        VM-1967's root cause (a cancelled caller's orphaned, still-"live"
        queue entry gets granted and nothing ever claims it, and with no TTL
        the grant blocked the whole queue forever). VM-2078 removed callback
        mode's TTL exemption -- there is no grant class left that
        self-declares its way out of the TTL.

        But "every grant TTL-covered" is not "every grant uses the same
        window" -- two grant-issuing paths write a wider ``claim_ttl``, each
        from evidence the GRANTER observes at grant time, never a
        self-declared property of the waiter: (1) ``grant()``'s
        ``summon_and_grant`` (D2 operator-path carve-out) target has a local
        ``pid`` but no poll loop of its own -- it is nudged, not polling --
        so the ordinary poll-cycle window is too short for a human/agent to
        answer a pane nudge and call ``converse()`` again; (2)
        ``grant_next()``'s ordinary head-promotion, when the promoted waiter
        has no local ``pid`` at all -- a remote waiter's claim is a
        heartbeat/status round trip, not a poll loop, so the poll-cycle
        window is structurally unwinnable for it (VM-2078 fix-002 REFINE
        #1). A category field on the *waiter* (local vs remote, summoned vs
        ordinary) would resurrect the removed ``mode`` concept under a new
        name, so the window is instead a property of the *grant record*
        (``claim_ttl``, see ``grant()`` / ``grant_next()``). No ``claim_ttl``
        on the record means the ordinary base TTL applies.
        """
        # Holder gate FIRST, before any TTL arithmetic -- order matters, not
        # just presence. A grant cannot be judged "wedged" while a live
        # holder still occupies the floor: the grantee structurally cannot
        # claim yet, no matter how long ago the grant was issued (`conch
        # give` / `summon_and_grant` both issue grants WHILE the holder is
        # still speaking -- VM-2078 Q3 repro). If this ran after the
        # granted_at parse below, a missing/malformed timestamp would
        # short-circuit past it and the gate would never fire. A wedged
        # HOLDER is the holder lock's own problem (CONCH_HOLD_EXPIRY /
        # stale-lock clearance) -- not the grant TTL's -- so this opens no
        # new gap. Goes through Conch.get_holder() (which does the liveness
        # check via is_active()), never a raw lock-file read, or a stale
        # holder record would gate on a lock that's already dead and
        # reintroduce an un-expiring grant.
        if Conch.get_holder() is not None:
            return False

        ttl = cls._effective_claim_ttl(grant)
        if ttl is None:
            return False  # administratively disabled -- no TTL judgement at all
        granted_at = cls._parse_iso(grant.get("granted_at"))
        if granted_at is None:
            # No timestamp (grant predates VM-1967, was written by something
            # else, or -- previously -- lived forever unexempted). Rather
            # than exempt it forever, stamp it now (persisted, atomic write)
            # so it becomes judgeable from first sighting, and return False
            # this once so the grantee gets one full TTL window from here.
            cls._atomic_write_json(
                cls._grant_file(),
                {**grant, "granted_at": datetime.now().isoformat()},
            )
            return False
        now = datetime.now(granted_at.tzinfo) if granted_at.tzinfo is not None else datetime.now()
        return (now - granted_at).total_seconds() > ttl

    @classmethod
    def _raw_grant(cls) -> Optional[dict]:
        """The on-disk grant record verbatim, or ``None`` if absent/corrupt.

        No liveness or TTL judgment -- see ``_current_grant`` for the judged
        version. Exists for callers that are about to re-validate/re-stamp
        the record themselves, where running the judged read first would
        evict what they are about to honour (``grant_next()``'s
        honour-an-existing-give branch -- see its comment).
        """
        gf = cls._grant_file()
        try:
            return json.loads(gf.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            return None

    @classmethod
    def _current_grant(cls) -> Optional[dict]:
        """The current grant record (``session_id``/``seq``/``granted_at``), or ``None``.

        A grant is only valid while its grantee is still a live waiter; a
        dead or deregistered grantee leaves the grant stale, which this
        clears (pre-VM-1967 behaviour, unchanged). VM-1967 safety net: a
        grant nobody ever claims within ``CONCH_GRANT_TTL`` is ALSO
        treated as stale here -- the stuck grantee is evicted from the queue
        and the next live waiter is promoted (mirroring the manual
        ``conch give`` recovery an operator would otherwise have to do), so
        one missed claim can never wedge the queue permanently. This runs as
        a side effect of every read (``granted_to`` / ``_queue_grant_blocks``
        / status), mirroring ``_scan``'s existing prune-on-read pattern -- in
        practice it self-heals the moment any other queued waiter's poll
        loop (or a status check) next asks "who is granted?".
        """
        g = cls._raw_grant()
        if g is None:
            return None
        gf = cls._grant_file()
        sid = g.get("session_id")
        if sid is None:
            cls._unlink(gf)
            return None
        for e in cls._scan(clean=True):
            if e.session_id == sid:
                if cls._grant_wedged(g, e):
                    cls.deregister(sid)
                    cls.grant_next()
                    return cls._current_grant()
                return g
        cls._unlink(gf)  # grantee gone -- stale grant
        return None

    @classmethod
    def granted_to(cls) -> Optional[str]:
        """The session id of the current live grantee, or ``None``.

        A grant is only valid while its grantee is still a live waiter, or
        (VM-1967) while the grant remains within its claim TTL --
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
    def claim_window_remaining(cls, session_id: str) -> Optional[float]:
        """Seconds left for ``session_id`` to claim its grant, or ``None``.

        ``None`` when ``session_id`` is not the current live grantee, the
        grant carries no ``granted_at`` timestamp, or the TTL net is
        administratively disabled (``CONCH_GRANT_TTL <= 0``) -- that last
        case is "no deadline exists", not "0.0 seconds left", and is shared
        with the enforcer via ``_effective_claim_ttl`` (REFINE #1: this
        reporter previously derived its own TTL independently and drifted
        from ``_grant_wedged`` -- with ``CONCH_GRANT_TTL=0`` the enforcer
        never expired the grant, but this method said "0.0 seconds
        remaining", telling an agent obediently heartbeating on this exact
        call it was out of time while it in fact held the floor
        indefinitely). Falls back to the base ``CONCH_GRANT_TTL`` when the
        grant carries no ``claim_ttl`` override.

        VM-2078 do-003: lets a passively-granted party discover it *on the
        one call it was told to make regularly* -- e.g. the MCP
        ``heartbeat`` action -- instead of needing a second, un-instructed
        ``status`` call to find out it is even holding a grant at all.
        """
        g = cls._current_grant()
        if g is None or g.get("session_id") != session_id:
            return None
        granted_at = cls._parse_iso(g.get("granted_at"))
        if granted_at is None:
            return None
        ttl = cls._effective_claim_ttl(g)
        if ttl is None:
            return None  # administratively disabled -- no deadline at all
        now = datetime.now(granted_at.tzinfo) if granted_at.tzinfo is not None else datetime.now()
        return max(0.0, ttl - (now - granted_at).total_seconds())

    @classmethod
    def clear_grant(cls) -> None:
        """Remove the grant hint (no-op if absent)."""
        cls._unlink(cls._grant_file())
