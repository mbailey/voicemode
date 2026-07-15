"""conch_ops — front-end-neutral conch operations shared by the CLI and MCP.

The CLI (``cli_commands/conch.py``, VM-1616) and the MCP tool
(``tools/conch.py``, VM-1622) are two **equal front ends** over the same
on-disk conch state — the holder lock (:class:`voice_mode.conch.Conch`) and the
ordered waiter registry (:class:`voice_mode.conch_queue.ConchQueue`, VM-1613).
To guarantee they can never diverge (epic VM-1610 principle #1: files are the
single source of truth), the logic *both* need lives here, exactly once:

- :func:`status_payload` — the structured holder+queue snapshot.
- :func:`resolve_session` — resolve an operator token (session-id / agent
  prefix) to exactly one live waiter, for ``give``.
- :func:`force_clear_lock` — unlink a stale/stuck holder lock, returning its
  last payload, for ``bump`` / ``release``.
- :func:`notify_granted_session` — the notify-on-give push (VM-1625) keyed by
  session id.
- small ISO-timestamp / display helpers used by the snapshot.

This module is deliberately UI-agnostic: it raises :class:`ConchResolveError`
(not ``click.ClickException``) so the CLI can render it as a Click error and the
MCP tool can return it as a structured error dict, each without importing the
other. ``tools/`` therefore never depends on ``cli_commands/`` (the import-
direction risk called out in the VM-1622 design).
"""

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from voice_mode.conch import Conch
from voice_mode.conch_queue import ConchQueue, WaiterEntry


# --------------------------------------------------------------------------- #
# ISO-timestamp / display helpers
# --------------------------------------------------------------------------- #

def parse_ts(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp (tolerating a trailing ``Z``); None on failure."""
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except (ValueError, TypeError, AttributeError):
        return None


def age_seconds(value: Optional[str]) -> Optional[float]:
    """Seconds since an ISO timestamp, matching tz-awareness; None if unparseable."""
    ts = parse_ts(value)
    if ts is None:
        return None
    now = datetime.now(ts.tzinfo) if ts.tzinfo is not None else datetime.now()
    return max(0.0, (now - ts).total_seconds())


def short(session_id: Optional[str], n: int = 8) -> str:
    """First ``n`` chars of a session id, for compact display."""
    if not session_id:
        return "-"
    return session_id[:n]


# --------------------------------------------------------------------------- #
# Status snapshot (holder + ordered queue)
# --------------------------------------------------------------------------- #

def status_payload() -> dict:
    """Build the structured status snapshot used by every front end.

    Returns a JSON-serialisable dict::

        {
            "holder": <holder|None>,
            "queue": [<waiter>, ...],
            "free": <bool>,
        }

    where the queue is in FIFO order and each waiter carries its 1-based
    ``position``, whether it is the current ``granted`` session, and (when
    granted) how long ago (``granted_seconds``). Runs the queue's
    stale-cleanup, and the VM-1967 grant-TTL self-heal, as a side effect of
    ``ConchQueue.granted_to()`` / ``list()``.

    ``free`` (VM-1967) is the single unambiguous "is the conch actually
    usable right now" signal: ``holder is None`` alone is NOT sufficient --
    a live WAIT-mode grant can be outstanding-but-unclaimed (nobody holds the
    flock, yet every other acquirer is gated behind that grant), which
    ``holder`` reports as free while the conch is, in fact, deadlocked
    (the "status line seems to be lying" field report this fixes). ``free``
    is only ``True`` when there is neither a live holder NOR an outstanding
    grant.
    """
    holder = Conch.get_holder()
    holder_out = None
    if holder:
        holder_out = {
            "agent": holder.get("agent"),
            "session_id": holder.get("session_id"),
            "project_path": holder.get("project_path"),
            "voice": holder.get("voice"),
            "pid": holder.get("pid"),
            "held": bool(holder.get("held")),
            "held_seconds": age_seconds(holder.get("acquired")),
        }
    queue = []
    granted = ConchQueue.granted_to()
    granted_age = ConchQueue.grant_age_seconds() if granted is not None else None
    for i, e in enumerate(ConchQueue.list()):
        is_granted = e.session_id == granted
        queue.append({
            "position": i + 1,
            "session_id": e.session_id,
            "agent": e.agent,
            "project_path": e.project_path,
            "voice": e.voice,
            "mode": e.mode,
            "pid": e.pid,
            "granted": is_granted,
            "granted_seconds": granted_age if is_granted else None,
            "waiting_seconds": age_seconds(e.requested_at),
        })
    return {
        "holder": holder_out,
        "queue": queue,
        "free": holder_out is None and granted is None,
    }


# --------------------------------------------------------------------------- #
# Token -> waiter resolution (for `give`)
# --------------------------------------------------------------------------- #

class ConchResolveError(Exception):
    """Raised when an operator token resolves to zero or multiple waiters.

    UI-agnostic so each front end renders it its own way: the CLI wraps it in a
    ``click.ClickException``; the MCP tool returns it as ``{"ok": False,
    "message": ...}``. ``candidates`` carries the ambiguous/closest matches (may
    be empty) for richer rendering.

    ``ambiguous`` distinguishes a *too-many-matches* failure from a *no-match*
    one. The ``give`` front ends (VM-1637) use it to decide the no-waiter
    fallback: a genuine no-match falls through to summoning a running session,
    but an *ambiguous* waiter token is surfaced as-is — the operator must
    disambiguate rather than have a different session silently summoned.
    """

    def __init__(self, message: str, candidates: Optional[List] = None,
                 *, ambiguous: bool = False):
        super().__init__(message)
        self.message = message
        self.candidates = candidates or []
        self.ambiguous = ambiguous


def resolve_session(token: str, waiters: List[WaiterEntry]) -> WaiterEntry:
    """Resolve ``token`` to exactly one waiter, mirroring ``session send``.

    Match order: session-id prefix, then exact agent name, then agent-name
    prefix. Raises :class:`ConchResolveError` on no match or ambiguity (listing
    the candidates), so a grant is never written for a guess.
    """
    sid_matches = [e for e in waiters if e.session_id and e.session_id.startswith(token)]
    if len(sid_matches) == 1:
        return sid_matches[0]
    if len(sid_matches) > 1:
        _raise_ambiguous(token, sid_matches)

    exact_agent = [e for e in waiters if e.agent == token]
    if len(exact_agent) == 1:
        return exact_agent[0]
    if len(exact_agent) > 1:
        _raise_ambiguous(token, exact_agent)

    agent_prefix = [e for e in waiters if e.agent and e.agent.startswith(token)]
    if len(agent_prefix) == 1:
        return agent_prefix[0]
    if len(agent_prefix) > 1:
        _raise_ambiguous(token, agent_prefix)

    if not waiters:
        raise ConchResolveError(
            f"No one is waiting, so there is no '{token}' to give the conch to. "
            "A session must join the queue first (via converse wait / MCP)."
        )
    listing = "\n".join(f"  - {e.agent or '?'}  (session {short(e.session_id)})" for e in waiters)
    raise ConchResolveError(
        f"No waiter matches '{token}'. Currently waiting:\n{listing}", waiters
    )


def _raise_ambiguous(token: str, matches: List[WaiterEntry]) -> None:
    listing = "\n".join(f"  - {e.agent or '?'}  (session {e.session_id})" for e in matches)
    raise ConchResolveError(
        f"'{token}' is ambiguous; it matches:\n{listing}", matches, ambiguous=True
    )


# --------------------------------------------------------------------------- #
# Running-session discovery + summon (for `give` to a non-waiter, VM-1637)
# --------------------------------------------------------------------------- #

#: Bound the best-effort discovery shell-out so `give` can never hang on it.
_SESSION_LIST_TIMEOUT = 5.0


@dataclass
class RunningSession:
    """A discovered running session (one entry of ``session list --json``).

    Carries exactly the fields the summon path needs: ``session_id`` (queue +
    grant key), ``pid`` (local liveness + local/remote notify routing),
    ``project_path`` (from the session's ``cwd``, the notify fallback token) and
    the human labels ``agent`` / ``name`` used for token resolution.
    """

    session_id: str
    pid: Optional[int] = None
    agent: Optional[str] = None
    name: Optional[str] = None
    project_path: Optional[str] = None

    @property
    def label(self) -> str:
        """Best display label: agent, else name, else the short session id."""
        return self.agent or self.name or short(self.session_id)


def _list_running_sessions() -> List[RunningSession]:
    """Discover running sessions via ``session list --json`` (best-effort).

    The skillbox ``session`` binary is already a runtime dependency of the
    notify path (``session send``). A missing binary, a non-zero exit, or
    unparseable JSON is treated as **"no running sessions"** (returns ``[]``) so
    the summon path degrades gracefully to today's "not waiting" error (R7/SC6)
    rather than raising.
    """
    try:
        result = subprocess.run(
            ["session", "list", "--json"],
            capture_output=True, text=True, timeout=_SESSION_LIST_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout or "[]")
    except (json.JSONDecodeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    sessions: List[RunningSession] = []
    for d in data:
        if not isinstance(d, dict):
            continue
        sid = d.get("session_id")
        if not sid:
            continue
        sessions.append(RunningSession(
            session_id=sid,
            pid=d.get("pid"),
            agent=d.get("agent"),
            name=d.get("name"),
            project_path=d.get("cwd"),
        ))
    return sessions


def _running_labels(s: RunningSession) -> List[str]:
    """The non-empty match labels for a running session (``agent`` and ``name``)."""
    return [lbl for lbl in (s.agent, s.name) if lbl]


def resolve_running_session(token: str) -> RunningSession:
    """Resolve ``token`` to exactly one running session, mirroring ``resolve_session``.

    Discovery is via :func:`_list_running_sessions`. Match order matches the
    waiter resolver: session-id prefix, then exact agent/name, then agent/name
    prefix. Raises :class:`ConchResolveError` (``ambiguous=True`` on multiple
    matches) so a guess is never summoned. When nothing matches — including the
    discovery-unavailable case (empty list) — it raises the same "no one is
    waiting" style message the waiter path uses, so ``give <non-waiter>``
    degrades cleanly (R7/SC6).
    """
    sessions = _list_running_sessions()

    sid_matches = [s for s in sessions if s.session_id and s.session_id.startswith(token)]
    if len(sid_matches) == 1:
        return sid_matches[0]
    if len(sid_matches) > 1:
        _raise_ambiguous_running(token, sid_matches)

    exact = [s for s in sessions if token in _running_labels(s)]
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        _raise_ambiguous_running(token, exact)

    prefix = [s for s in sessions if any(lbl.startswith(token) for lbl in _running_labels(s))]
    if len(prefix) == 1:
        return prefix[0]
    if len(prefix) > 1:
        _raise_ambiguous_running(token, prefix)

    raise ConchResolveError(
        f"No one is waiting and no running session matches '{token}', so there's "
        f"nobody to give the conch to. A session must join the queue first (via "
        f"converse wait / MCP) or be reachable via `session list`."
    )


def _raise_ambiguous_running(token: str, matches: List[RunningSession]) -> None:
    listing = "\n".join(f"  - {s.label}  (session {short(s.session_id)})" for s in matches)
    raise ConchResolveError(
        f"'{token}' is ambiguous; it matches running sessions:\n{listing}",
        matches, ambiguous=True,
    )


# --------------------------------------------------------------------------- #
# Holder-lock clearing (for `bump` / `release`)
# --------------------------------------------------------------------------- #

def force_clear_lock() -> Optional[dict]:
    """Unlink the holder lock file (best effort); return the payload it held.

    Reads the raw lock payload first (even a *stale* one, unlike
    ``Conch.get_holder`` which returns None for a dead holder) so callers can
    report who was cleared. Deleting the inode lets a fresh lock be created even
    if a genuinely-stuck live holder still flocks the old inode — same approach
    as ``Conch._check_and_clear_stale_lock``.
    """
    payload = None
    lock = Conch.LOCK_FILE
    try:
        payload = json.loads(lock.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        payload = None
    try:
        lock.unlink()
    except (FileNotFoundError, OSError):
        pass
    return payload


# --------------------------------------------------------------------------- #
# Notify-on-give (VM-1625), keyed by session id
# --------------------------------------------------------------------------- #

def notify_granted_session(session_id: Optional[str]) -> None:
    """Push a "your turn" nudge to ``session_id`` after a grant (VM-1625).

    ``give``/``bump`` call this after writing the grant. It resolves the
    grantee's live queue entry and delegates to
    :func:`voice_mode.conch_notify.notify_granted`, which owns the mode gate
    (callback ⇒ push, wait ⇒ pull/no-push) and the local/remote routing.
    Best-effort: a vanished waiter or any notify glitch is a silent no-op and
    never breaks the command.
    """
    if not session_id:
        return
    try:
        from voice_mode.conch_notify import notify_granted
        entry = next(
            (e for e in ConchQueue.list() if e.session_id == session_id), None
        )
        notify_granted(entry)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Summon-and-grant (the `give` no-waiter fallback, VM-1637)
# --------------------------------------------------------------------------- #

def summon_and_grant(token: str) -> dict:
    """Summon a running non-waiter and hand it the conch — the ``give`` fallback.

    Called by both front ends only when ``token`` resolves to no waiter. It:

    1. resolves ``token`` to one running session (``resolve_running_session``;
       may raise :class:`ConchResolveError`),
    2. no-ops if that session is the **current holder** (it already has the
       floor — do not double-enqueue),
    3. otherwise auto-enqueues it as a ``callback``-mode waiter carrying the
       fields notify needs (``session_id``, ``pid``, ``project_path``, ``agent``),
       grants it the conch (now a live waiter, so ``ConchQueue.grant`` succeeds
       and the grant hint makes it the next acquirer), and pushes the VM-1625
       nudge,

    returning a structured outcome dict (``summoned``/``noop`` + identity +
    ``message``) that each front end renders in its own style.

    **No orphan entry (SC4):** the resolve — which can raise — happens *before*
    ``register``, so a failed or ambiguous resolve never leaves a half-enqueued
    waiter. ``ConchQueue.grant()`` itself is unchanged: we satisfy its
    live-waiter invariant by registering first.
    """
    target = resolve_running_session(token)  # may raise — before any register

    holder = Conch.get_holder()
    if holder is not None and holder.get("session_id") == target.session_id:
        return {
            "action": "give",
            "summoned": False,
            "noop": True,
            "session_id": target.session_id,
            "agent": target.label,
            "message": (
                f"{target.label} (session {short(target.session_id)}) already holds "
                f"the conch — nothing to do."
            ),
        }

    ConchQueue.register(
        target.session_id,
        agent=target.agent or target.name,
        project_path=target.project_path,
        voice=None,
        mode="callback",
        pid=target.pid,
    )
    granted = ConchQueue.grant(target.session_id)
    notify_granted_session(target.session_id)

    when = "now (the conch is free)" if holder is None else \
        f"when {holder.get('agent') or 'the holder'} releases"
    return {
        "action": "give",
        "summoned": True,
        "noop": False,
        "granted": granted,
        "session_id": target.session_id,
        "agent": target.label,
        "when": when,
        "message": (
            f"Summoned {target.label} (session {short(target.session_id)}) and gave "
            f"them the conch; they acquire {when}."
        ),
    }
