"""CLI commands for the conch — VoiceMode's single-speaker lock across agents.

Provides ``voicemode conch status / give / bump / release / wait`` to **observe
and manage** the conch:

- **status**  — show the current holder and the ordered waiter queue.
- **give**    — hand the floor to a named waiting session (it acquires next).
- **bump**    — drop the current holder and promote the head of the queue.
- **release** — force-clear a stale/stuck holder lock (alias: ``clear``).
- **wait**    — register as a waiter and block until it's your turn.

This group is a **pure front end** over two state layers and is never a second
authority (VM-1610 epic):

- :class:`voice_mode.conch.Conch` — the holder lock ("who is talking now").
- :class:`voice_mode.conch_queue.ConchQueue` — the ordered waiter registry
  ("who is waiting, in what order"), added in VM-1613. The FIFO grant machinery
  is already wired into ``Conch.try_acquire``/``release``; this CLI only reads
  that state and, for give/bump/release, writes the grant or clears the lock.

Mirrors the ``autofocus.py`` / ``soundfonts.py`` Click-group pattern.
"""

import json
import os
import time
from datetime import datetime
from typing import List, Optional

import click

from voice_mode.conch import Conch
from voice_mode.conch_queue import ConchQueue, WaiterEntry


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp (tolerating a trailing ``Z``); None on failure."""
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except (ValueError, TypeError, AttributeError):
        return None


def _age_seconds(value: Optional[str]) -> Optional[float]:
    """Seconds since an ISO timestamp, matching tz-awareness; None if unparseable."""
    ts = _parse_ts(value)
    if ts is None:
        return None
    now = datetime.now(ts.tzinfo) if ts.tzinfo is not None else datetime.now()
    return max(0.0, (now - ts).total_seconds())


def _fmt_duration(seconds: Optional[float]) -> str:
    """Render a duration compactly: ``45s`` / ``1m02s`` / ``2h03m``."""
    if seconds is None:
        return "?"
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def _short(session_id: Optional[str], n: int = 8) -> str:
    """First ``n`` chars of a session id, for compact display."""
    if not session_id:
        return "-"
    return session_id[:n]


def _holder_dict() -> Optional[dict]:
    """The live holder payload, or None. (``get_holder`` returns None if stale.)"""
    return Conch.get_holder()


def _position(session_id: str) -> Optional[int]:
    """1-based position of ``session_id`` in the live queue, or None if absent."""
    for i, e in enumerate(ConchQueue.list()):
        if e.session_id == session_id:
            return i + 1
    return None


def _resolve_session(token: str, waiters: List[WaiterEntry]) -> WaiterEntry:
    """Resolve ``token`` to exactly one waiter, mirroring ``session send``.

    Match order: session-id prefix, then exact agent name, then agent-name
    prefix. Raises ``click.ClickException`` on no match or ambiguity (listing
    the candidates), so a grant is never written for a guess.
    """
    sid_matches = [e for e in waiters if e.session_id and e.session_id.startswith(token)]
    if len(sid_matches) == 1:
        return sid_matches[0]
    if len(sid_matches) > 1:
        _ambiguous(token, sid_matches)

    exact_agent = [e for e in waiters if e.agent == token]
    if len(exact_agent) == 1:
        return exact_agent[0]
    if len(exact_agent) > 1:
        _ambiguous(token, exact_agent)

    agent_prefix = [e for e in waiters if e.agent and e.agent.startswith(token)]
    if len(agent_prefix) == 1:
        return agent_prefix[0]
    if len(agent_prefix) > 1:
        _ambiguous(token, agent_prefix)

    if not waiters:
        raise click.ClickException(
            f"No one is waiting, so there is no '{token}' to give the conch to. "
            "A session must join the queue first (via converse wait / MCP)."
        )
    listing = "\n".join(f"  - {e.agent or '?'}  (session {_short(e.session_id)})" for e in waiters)
    raise click.ClickException(f"No waiter matches '{token}'. Currently waiting:\n{listing}")


def _ambiguous(token: str, matches: List[WaiterEntry]) -> None:
    listing = "\n".join(f"  - {e.agent or '?'}  (session {e.session_id})" for e in matches)
    raise click.ClickException(f"'{token}' is ambiguous; it matches:\n{listing}")


def _notify_granted(session_id: str) -> None:
    """Seam for notify-on-give (VM-1625): ping a session that isn't watching.

    Intentionally a no-op here. ``give``/``bump`` call it after writing the
    grant so VM-1625 can wire a local tmux nudge (we have ``session_id`` +
    ``project_path`` in the queue entry) / remote MCP notification without
    touching this CLI's control flow.
    """
    return None


def _force_clear_lock() -> Optional[dict]:
    """Unlink the holder lock file (best effort); return the payload it held.

    Reads the raw lock payload first (even a *stale* one, unlike
    ``get_holder`` which returns None for a dead holder) so callers can report
    who was cleared. Deleting the inode lets a fresh lock be created even if a
    genuinely-stuck live holder still flocks the old inode — same approach as
    ``Conch._check_and_clear_stale_lock``.
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
# Rendering (status)
# --------------------------------------------------------------------------- #

def _status_payload() -> dict:
    """Build the structured status snapshot used by both human and --json output."""
    holder = _holder_dict()
    holder_out = None
    if holder:
        holder_out = {
            "agent": holder.get("agent"),
            "session_id": holder.get("session_id"),
            "project_path": holder.get("project_path"),
            "voice": holder.get("voice"),
            "pid": holder.get("pid"),
            "held": bool(holder.get("held")),
            "held_seconds": _age_seconds(holder.get("acquired")),
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
            "waiting_seconds": _age_seconds(e.requested_at),
        })
    return {"holder": holder_out, "queue": queue}


def _render_status_human(snap: dict) -> None:
    holder = snap["holder"]
    queue = snap["queue"]
    if holder:
        proj = holder.get("project_path") or "-"
        flag = "held between turns" if holder.get("held") else "speaking"
        voice = holder.get("voice") or "-"
        click.echo(
            f"Holder: {holder.get('agent') or 'unknown'}  "
            f"(session {_short(holder.get('session_id'))}, project {proj})  "
            f"voice {voice}  {flag} for {_fmt_duration(holder.get('held_seconds'))}"
        )
    else:
        click.echo("Holder: none — the conch is free.")

    if queue:
        click.echo(f"Queue ({len(queue)}):")
        for e in queue:
            mark = " *granted*" if e.get("granted") else ""
            click.echo(
                f"  #{e['position']}  {e.get('agent') or '?':<10}  "
                f"session {_short(e.get('session_id'))}  "
                f"{e.get('mode') or 'wait':<8}  "
                f"waiting {_fmt_duration(e.get('waiting_seconds'))}{mark}"
            )
    else:
        click.echo("Queue: empty — no one waiting.")


# --------------------------------------------------------------------------- #
# Command group
# --------------------------------------------------------------------------- #

@click.group(name="conch")
@click.help_option("-h", "--help", help="Show this message and exit")
def conch():
    """Observe and manage the conch (VoiceMode's single-speaker lock).

    \b
    voicemode conch status            # who holds it + who's waiting
    voicemode conch give <session>    # hand the floor to a waiting session
    voicemode conch bump              # drop the holder, promote the next in line
    voicemode conch release           # force-clear a stale/stuck lock
    voicemode conch wait              # block until it's your turn

    The conch state lives on disk under ~/.voicemode/ and is the single source
    of truth; this CLI only reads and nudges it — it never holds a second copy.
    """
    pass


@conch.command("status")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def conch_status(as_json):
    """Show the current holder and the ordered waiter queue."""
    snap = _status_payload()
    if as_json:
        click.echo(json.dumps(snap, indent=2))
    else:
        _render_status_human(snap)


@conch.command("give")
@click.argument("session")
def conch_give(session):
    """Hand the floor to a waiting SESSION (resolved by session-id or agent).

    Writes the grant so SESSION is the designated next acquirer; it takes the
    floor when the current holder releases. This does NOT evict the holder —
    use 'bump' for an immediate hand-off. SESSION must currently be in the
    queue (a non-waiting session has no place to grant).
    """
    waiters = ConchQueue.list()
    target = _resolve_session(session, waiters)
    if not ConchQueue.grant(target.session_id):
        # Race: the waiter vanished between list() and grant().
        raise click.ClickException(
            f"{target.agent or target.session_id} is no longer waiting; nothing granted."
        )
    _notify_granted(target.session_id)
    holder = _holder_dict()
    when = "now (conch is free)" if holder is None else f"when {holder.get('agent') or 'the holder'} releases"
    click.echo(
        f"Gave the conch to {target.agent or _short(target.session_id)} "
        f"(session {_short(target.session_id)}); they acquire {when}."
    )


@conch.command("bump")
def conch_bump():
    """Drop the current holder and promote the head of the queue.

    The bumped holder is **dropped** — it must re-request the conch (via
    converse / wait) to get back in line. The head of the waiter queue becomes
    the designated next acquirer. For a stale lock with no live holder, use
    'release' instead.
    """
    holder = _holder_dict()
    if holder is None:
        # No *live* holder. Distinguish a stale lock from a genuinely-free conch.
        if Conch.LOCK_FILE.exists():
            raise click.ClickException(
                "No live holder — the lock looks stale. Use 'voicemode conch release' to clear it."
            )
        head = ConchQueue.grant_next()
        if head is None:
            click.echo("Conch is free and no one is waiting — nothing to bump.")
        else:
            _notify_granted(head.session_id)
            click.echo(
                f"Conch was already free; promoted {head.agent or _short(head.session_id)} "
                f"(session {_short(head.session_id)}) as next in line."
            )
        return

    bumped_agent = holder.get("agent") or "unknown"
    bumped_sid = holder.get("session_id")
    _force_clear_lock()
    ConchQueue.clear_grant()
    head = ConchQueue.grant_next()
    if head is None:
        click.echo(
            f"Bumped {bumped_agent} (session {_short(bumped_sid)}); they must re-request. "
            "Queue is empty — the conch is now free."
        )
    else:
        _notify_granted(head.session_id)
        click.echo(
            f"Bumped {bumped_agent} (session {_short(bumped_sid)}); they must re-request. "
            f"Next up: {head.agent or _short(head.session_id)} (session {_short(head.session_id)})."
        )


@conch.command("release")
@click.option("--yes", "-y", is_flag=True, help="Skip the confirmation prompt.")
def conch_release(yes):
    """Force-clear a stale/stuck holder lock (alias: clear).

    Unlinks the holder lock file and clears any grant. Use when a crashed or
    wedged session has left the conch held with no one actually speaking.
    Idempotent: harmless if the conch is already free.
    """
    holder = _holder_dict()
    if holder and not yes:
        click.confirm(
            f"{holder.get('agent') or 'A session'} appears to be holding the conch "
            f"(session {_short(holder.get('session_id'))}). Force-release anyway?",
            abort=True,
        )
    existed = Conch.LOCK_FILE.exists()
    _force_clear_lock()
    ConchQueue.clear_grant()
    if existed:
        click.echo("Released the conch lock and cleared any grant.")
    else:
        click.echo("Conch was already free; cleared any stray grant.")


# 'clear' alias for 'release'.
conch.add_command(conch_release, name="clear")


@conch.command("wait")
@click.option("--session", "session_id", default=None,
              help="Session id to register as (default: ephemeral cli-wait-<pid>).")
@click.option("--timeout", default=300.0, type=float,
              help="Max seconds to wait (default: 300).")
@click.option("--json", "as_json", is_flag=True, help="Emit machine-readable JSON.")
def conch_wait(session_id, timeout, as_json):
    """Register as a waiter and block until it's your turn.

    Joins the queue (so you appear in 'status' and hold FIFO order), then polls
    until you are granted the conch or you reach the head while it's free,
    bounded by --timeout. This is a *gate*, not a reservation: on success it
    returns 0 so your next 'voicemode converse' (or any acquire) can take the
    floor. For an atomic acquire with no gap, prefer converse's own
    wait_for_conch instead.
    """
    from voice_mode.config import CONCH_CHECK_INTERVAL

    sid = session_id or f"cli-wait-{os.getpid()}"
    ConchQueue.register(sid, agent="conch-wait", mode="wait")

    interval = CONCH_CHECK_INTERVAL if CONCH_CHECK_INTERVAL > 0 else 0.5
    waited = 0.0
    last_pos = None
    granted = False

    try:
        while True:
            if ConchQueue.is_granted(sid):
                granted = True
                break
            holder = _holder_dict()
            head = ConchQueue.head()
            if holder is None and head is not None and head.session_id == sid:
                granted = True
                break
            if waited >= timeout:
                break
            if not as_json:
                pos = _position(sid)
                if pos != last_pos:
                    where = f"holder: {holder.get('agent')}" if holder else "conch free"
                    click.echo(f"Waiting… position #{pos} ({where})")
                    last_pos = pos
            time.sleep(interval)
            waited += interval
    except KeyboardInterrupt:
        ConchQueue.deregister(sid)
        raise click.Abort()

    if granted:
        if as_json:
            click.echo(json.dumps({"granted": True, "session_id": sid,
                                   "waited_seconds": round(waited, 1)}))
        else:
            click.echo("Your turn — the conch is free for you. "
                       "Run 'voicemode converse …' now to take the floor.")
        # Gate model: leave cleanly. We do NOT hold the floor (a CLI process
        # can't keep it past exit), so deregister to avoid a ghost entry.
        ConchQueue.deregister(sid)
        return

    ConchQueue.deregister(sid)
    if as_json:
        click.echo(json.dumps({"granted": False, "session_id": sid,
                               "timeout": timeout}))
    else:
        click.echo(f"Timed out after {_fmt_duration(timeout)} waiting for the conch.")
    raise SystemExit(1)
