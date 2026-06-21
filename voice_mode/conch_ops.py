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

    Returns a JSON-serialisable dict ``{"holder": <holder|None>, "queue":
    [<waiter>, ...]}`` where the queue is in FIFO order and each waiter carries
    its 1-based ``position`` and whether it is the current ``granted`` session.
    Runs the queue's stale-cleanup as a side effect of ``ConchQueue.list()``.
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
    for i, e in enumerate(ConchQueue.list()):
        queue.append({
            "position": i + 1,
            "session_id": e.session_id,
            "agent": e.agent,
            "project_path": e.project_path,
            "voice": e.voice,
            "mode": e.mode,
            "pid": e.pid,
            "granted": e.session_id == granted,
            "waiting_seconds": age_seconds(e.requested_at),
        })
    return {"holder": holder_out, "queue": queue}


# --------------------------------------------------------------------------- #
# Token -> waiter resolution (for `give`)
# --------------------------------------------------------------------------- #

class ConchResolveError(Exception):
    """Raised when an operator token resolves to zero or multiple waiters.

    UI-agnostic so each front end renders it its own way: the CLI wraps it in a
    ``click.ClickException``; the MCP tool returns it as ``{"ok": False,
    "message": ...}``. ``candidates`` carries the ambiguous/closest matches (may
    be empty) for richer rendering.
    """

    def __init__(self, message: str, candidates: Optional[List[WaiterEntry]] = None):
        super().__init__(message)
        self.message = message
        self.candidates = candidates or []


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
    raise ConchResolveError(f"'{token}' is ambiguous; it matches:\n{listing}", matches)


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
