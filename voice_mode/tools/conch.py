"""MCP ``conch`` tool — remote, CLI-parity access to the conch queue (VM-1622).

A single composite tool, ``conch(action, …)``, that lets an agent on a
**streamable-HTTP** voicemode server — which has no access to the host's
``~/.voicemode/`` conch files — see the queue, join it, take its turn, and
manage it. The CLI (``voicemode conch …``, VM-1616) and this tool are two
**equal front ends** over the same on-disk state (the holder lock
:class:`voice_mode.conch.Conch` + the waiter registry
:class:`voice_mode.conch_queue.ConchQueue`, VM-1613). Both import
:mod:`voice_mode.conch_ops` for the shared logic, so ``give``/``bump``/``release``
issued over MCP mutate exactly the same files the CLI does — the two can never
diverge (epic VM-1610 principle #1).

**Default delivery is queue.** A blocking await-turn can exceed a
streamable-HTTP client's request timeout, so the recommended way to join the
queue is ``action="queue"`` (register-and-return, register-and-**poll**): you
get your queue position immediately and discover your grant on your next
``heartbeat`` / ``status`` call. ``action="wait"`` is also offered but is
**hard-capped** (env ``VOICEMODE_CONCH_MCP_WAIT_CAP``, default 25 s) well
under typical client timeouts; on timeout you are deregistered cleanly.

*(VM-2078: this action was previously named ``"callback"`` — the literal
string still resolves, but now returns a clear error naming the replacement
above, since it never delivered a callback in the telephone sense: nothing
was ever called back, it was register-and-poll all along.)*

**Remote-waiter identity.** A remote agent has no host PID and no
``CLAUDE_CODE_SESSION_ID`` env, so ``session_id`` is a **required** arg for
``wait``/``queue``/``heartbeat``/``leave`` — it is the queue key and the grant
key. Registration passes ``pid=None``, so liveness is tracked by an ``expires``
heartbeat TTL (env ``VOICEMODE_CONCH_REMOTE_TTL``, default 90 s) the front end
refreshes on every ``wait``/``queue``/``heartbeat`` call; a remote waiter past
its TTL is auto-pruned so the queue never wedges. Send ``heartbeat`` roughly
every ~30 s while queued to stay live -- and check the response's ``granted``
field every time: that heartbeat is also how you discover your grant, since a
remote waiter has no poll loop of its own to notice it any other way.

**Remote notify-on-give** lands with VM-970 (MCP channel notifications); until
then the grant file *is* the marker, discovered on your next ``status`` /
``heartbeat`` / ``queue`` call (the pull-only path) -- or, since VM-2078
do-003, directly in the ``heartbeat`` response's ``granted`` field.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from voice_mode.server import mcp
from voice_mode import conch_ops
from voice_mode.conch import Conch
from voice_mode.conch_ops import ConchResolveError
from voice_mode.conch_queue import ConchQueue
from voice_mode.config import (
    CONCH_CHECK_INTERVAL,
    CONCH_MCP_WAIT_CAP,
    CONCH_REMOTE_TTL,
)

logger = logging.getLogger("voicemode")

#: The actions this tool dispatches on (CLI verbs + the two remote-liveness
#: actions ``heartbeat``/``leave`` that the local-PID CLI has no need for).
#: VM-2078 D1: "callback" was renamed to "queue" (see module docstring) --
#: it is deliberately NOT in this tuple, so the literal string falls through
#: to the dedicated, replacement-naming error below rather than the generic
#: "unknown action" one.
VALID_ACTIONS = (
    "status", "wait", "queue", "heartbeat", "leave", "give", "bump", "release",
)

#: Actions that key on the remote agent's ``session_id`` (its queue/grant key).
_NEEDS_SESSION = ("wait", "queue", "heartbeat", "leave")


def _expiry_iso() -> str:
    """The remote heartbeat-TTL deadline (now + ``CONCH_REMOTE_TTL``), ISO-8601.

    Naive local time: the MCP front end and the queue live on the same host, so
    ``ConchQueue._is_live`` compares this against a naive local ``now``.
    """
    return (datetime.now() + timedelta(seconds=CONCH_REMOTE_TTL)).isoformat()


def _entry_of(session_id: str):
    """The live queue entry for ``session_id`` (runs cleanup), or None."""
    for e in ConchQueue.list():
        if e.session_id == session_id:
            return e
    return None


@mcp.tool()
async def conch(
    action: str = "status",
    session_id: Optional[str] = None,
    target: Optional[str] = None,
    agent: Optional[str] = None,
    project_path: Optional[str] = None,
    voice: Optional[str] = None,
    timeout: Optional[float] = None,
) -> dict:
    """Observe and manage the conch (VoiceMode's single-speaker lock) over MCP.

    Args:
        action: One of ``status | wait | queue | heartbeat | leave | give |
            bump | release`` (default ``status``).

            • ``status`` — return the current holder and the ordered waiter
              queue. No ``session_id`` needed.
            • ``queue`` — **recommended for joining when busy.** Register and
              return immediately with your position; you discover your grant
              by heartbeating or polling ``status`` (register-and-**poll**).
              Stays registered.
            • ``wait`` — register and block until it's your turn, bounded by
              ``min(timeout, VOICEMODE_CONCH_MCP_WAIT_CAP)`` (default cap 25 s).
              On success the conch is free for you — call ``converse()`` next. On
              timeout you are deregistered.
            • ``heartbeat`` — refresh your remote-liveness TTL while idle
              (keeps your place). Send ~every 30 s while queued, and check the
              response's ``granted`` field every time — that is how a queued
              waiter discovers its grant.
            • ``leave`` — deregister (give up your place).
            • ``give`` — hand the floor to a waiting ``target`` (resolved by
              session-id or agent name); it acquires when the holder releases.
            • ``bump`` — drop the current holder and promote the head of the
              queue. (Use ``release`` for a stale lock with no live holder.)
            • ``release`` — force-clear a stale/stuck holder lock and any grant.

          *(``"callback"`` was renamed to ``"queue"`` — VM-2078. The literal
          string still resolves, but only to a clear error naming the
          replacement; it is not a valid action any more.)*
        session_id: REQUIRED for ``wait``/``queue``/``heartbeat``/``leave`` —
            the remote agent's stable queue/grant key.
        target: REQUIRED for ``give`` — the waiting session id or agent name to
            hand the floor to.
        agent / project_path / voice: descriptive fields stored on your waiter
            entry (shown in ``status``), mirroring the holder payload.
        timeout: ``wait`` only — desired max seconds to block; still hard-capped
            by ``VOICEMODE_CONCH_MCP_WAIT_CAP``.

    Returns:
        A JSON-serialisable dict. ``status`` returns ``{ok, action, holder,
        queue, free}`` — ``free`` (VM-1967) is ``True`` only when there is
        neither a live holder NOR an outstanding-but-unclaimed grant; a
        queued waiter with ``granted: true`` and no live ``holder`` means the
        conch is momentarily deadlocked-looking (grant issued, not yet
        claimed), not actually free. Register actions return ``{ok,
        registered, session_id, position, expires, message, …}``;
        ``heartbeat`` additionally returns ``{granted, claim_window_remaining}``
        (VM-2078 do-003) so a queued waiter can discover its own grant on the
        one call it is told to make regularly. ``give``/``bump``/``release``
        return ``{ok, message, …}`` — ``give``'s summon path additionally
        returns ``{granted, nudge}`` (``nudge`` is one of ``"delivered" |
        "failed" | "remote"``): a summon nudge that could not be confirmed
        delivered withholds the grant entirely (D2) rather than handing the
        floor to a target that was never told. Every ``message`` states
        plainly whether the turn was taken or merely queued. Invalid input
        returns ``{ok: False, message}`` — never a traceback.
    """
    action = (action or "").strip().lower()
    if action == "callback":
        return {
            "ok": False,
            "action": action,
            "message": (
                "action='callback' was renamed to action='queue' (VM-2078) — "
                "same register-and-poll behaviour, an honest name. Call "
                "conch(action='queue', session_id=…) instead."
            ),
        }
    if action not in VALID_ACTIONS:
        return {
            "ok": False,
            "action": action,
            "message": f"Unknown action '{action}'. Valid actions: {', '.join(VALID_ACTIONS)}.",
        }
    if action in _NEEDS_SESSION and not session_id:
        return {
            "ok": False,
            "action": action,
            "message": f"{action} requires `session_id` (the remote agent's queue/grant key).",
        }

    try:
        if action == "status":
            return {"ok": True, "action": "status", **conch_ops.status_payload()}

        if action == "queue":
            return _do_queue(session_id, agent, project_path, voice)

        if action == "wait":
            return await _do_wait(session_id, agent, project_path, voice, timeout)

        if action == "heartbeat":
            return _do_heartbeat(session_id, agent, project_path, voice)

        if action == "leave":
            ConchQueue.deregister(session_id)
            return {
                "ok": True, "action": "leave", "session_id": session_id,
                "message": "Left the queue.",
            }

        if action == "give":
            return _do_give(target)

        if action == "bump":
            return _do_bump()

        if action == "release":
            return _do_release()

    except Exception as e:  # never leak a traceback to an MCP client
        logger.error(f"conch({action}) failed: {e}", exc_info=True)
        return {"ok": False, "action": action, "message": f"conch {action} failed: {e}"}


# --------------------------------------------------------------------------- #
# Register actions (queue / wait / heartbeat)
# --------------------------------------------------------------------------- #

def _do_queue(session_id, agent, project_path, voice) -> dict:
    """Register-and-return: the timeout-safe default for joining a busy conch.

    VM-2078 D1: this was ``_do_callback`` / ``action="callback"``. Renamed,
    not just relabelled — the behaviour was always register-and-**poll** (no
    message discarded, no tmux nudge; see the module docstring), so the old
    name promised something it structurally could not do.
    """
    expires = _expiry_iso()
    position = ConchQueue.register(
        session_id, agent=agent, project_path=project_path, voice=voice,
        pid=None, expires=expires,
    )
    return {
        "ok": True, "action": "queue", "registered": True, "granted": False,
        "session_id": session_id, "position": position,
        "expires": expires,
        "message": (
            f"Registered at position #{position} — your message was NOT spoken. "
            "Send conch(action='heartbeat', session_id=…) every ~30s (checking its "
            "`granted` field) to stay live and discover your grant, or poll "
            "conch(action='status')."
        ),
    }


async def _do_wait(session_id, agent, project_path, voice, timeout) -> dict:
    """Block until it's our turn, hard-capped — a gate, not a held floor.

    Mirrors the CLI ``wait`` gate: we never hold the floor on the remote agent's
    behalf (the holder lock would be owned by the long-lived server process and
    wedge the conch), so on success we deregister and tell the agent to call
    ``converse()`` to take the now-free floor. ``expires`` is refreshed each poll
    so a long-ish wait is never pruned mid-loop.
    """
    cap = CONCH_MCP_WAIT_CAP
    if timeout is not None and timeout > 0:
        cap = min(float(timeout), CONCH_MCP_WAIT_CAP)

    ConchQueue.register(
        session_id, agent=agent, project_path=project_path, voice=voice,
        pid=None, expires=_expiry_iso(),
    )

    interval = CONCH_CHECK_INTERVAL if CONCH_CHECK_INTERVAL > 0 else 0.5
    waited = 0.0
    granted = False
    while True:
        if ConchQueue.is_granted(session_id):
            granted = True
            break
        holder = Conch.get_holder()
        head = ConchQueue.head()
        # Head of a free conch is our turn — UNLESS an explicit give points at
        # someone else (then their grant gates the next acquire).
        if (holder is None and head is not None and head.session_id == session_id
                and ConchQueue.granted_to() in (None, session_id)):
            granted = True
            break
        if waited >= cap:
            break
        ConchQueue.register(
            session_id, agent=agent, project_path=project_path, voice=voice,
            pid=None, expires=_expiry_iso(),
        )
        await asyncio.sleep(interval)
        waited += interval

    # Gate model: we do not hold the floor, so leave cleanly either way.
    ConchQueue.deregister(session_id)
    if granted:
        return {
            "ok": True, "action": "wait", "granted": True, "registered": False,
            "session_id": session_id, "waited_seconds": round(waited, 1),
            "message": (
                "Your turn — the conch is free for you. Call converse() now to "
                "take the floor."
            ),
        }
    return {
        "ok": True, "action": "wait", "granted": False, "registered": False,
        "session_id": session_id, "waited_seconds": round(waited, 1),
        "cap_seconds": cap,
        "message": (
            f"No turn after {round(waited, 1)}s (wait is hard-capped at {cap:.0f}s) "
            "— you are NOT queued. Re-call conch(action='queue', session_id=…) to "
            "hold your place and discover your turn via heartbeat/status."
        ),
    }


def _do_heartbeat(session_id, agent, project_path, voice) -> dict:
    """Refresh a remote waiter's TTL, preserving its place (seq).

    VM-2078 do-003: also reports ``granted`` (and, when it can be computed,
    ``claim_window_remaining``) — a queued waiter's poll loop IS this call,
    so heartbeat is the one place it is guaranteed to look; before this it
    could heartbeat forever without ever learning the floor was held for it,
    and would have needed a second, un-instructed ``status`` call to find out.
    """
    entry = _entry_of(session_id)
    if entry is None:
        return {
            "ok": False, "action": "heartbeat", "session_id": session_id,
            "message": (
                "Not in the queue (or already expired). Call "
                "conch(action='queue'|'wait', session_id=…) to register first."
            ),
        }
    expires = _expiry_iso()
    # register() keeps the original seq + requested_at for an existing session,
    # so this refreshes the TTL without losing the waiter's place. Carry the
    # existing fields forward unless the caller supplied new ones.
    position = ConchQueue.register(
        session_id,
        agent=agent if agent is not None else entry.agent,
        project_path=project_path if project_path is not None else entry.project_path,
        voice=voice if voice is not None else entry.voice,
        pid=None,
        expires=expires,
    )
    granted = ConchQueue.is_granted(session_id)
    remaining = ConchQueue.claim_window_remaining(session_id) if granted else None
    result = {
        "ok": True, "action": "heartbeat", "registered": True,
        "session_id": session_id, "granted": granted, "position": position,
        "expires": expires,
    }
    if granted:
        if remaining is not None:
            result["claim_window_remaining"] = round(remaining, 1)
            result["message"] = (
                f"Heartbeat acknowledged — you have been GRANTED the conch! Call "
                f"converse() now; ~{remaining:.0f}s left to claim it."
            )
        else:
            result["message"] = (
                "Heartbeat acknowledged — you have been GRANTED the conch! "
                "Call converse() now."
            )
    else:
        result["message"] = f"Heartbeat acknowledged; still at position #{position}."
    return result


# --------------------------------------------------------------------------- #
# Management actions (give / bump / release) — shared with the CLI via conch_ops
# --------------------------------------------------------------------------- #

def _do_give(target) -> dict:
    """Hand the floor to a session — a waiter, else summon a running one (VM-1637).

    Mirrors the CLI ``give`` (parity, via the shared ``conch_ops`` core):
    resolve a waiter first; on a genuine no-match fall back to summoning a
    running non-waiter (auto-enqueue + checked-nudge + grant-iff-delivered,
    D2). An *ambiguous* token is surfaced rather than summoned.
    """
    if not target:
        return {
            "ok": False, "action": "give",
            "message": "give requires `target` (a waiting session id or agent name).",
        }
    try:
        waiter = conch_ops.resolve_session(target, ConchQueue.list())
    except ConchResolveError as e:
        if e.ambiguous:
            return {"ok": False, "action": "give", "message": e.message}
        try:
            outcome = conch_ops.summon_and_grant(target)
        except ConchResolveError as summon_err:
            return {"ok": False, "action": "give", "message": summon_err.message}
        # "granted"/"nudge" are absent on the target-is-holder noop (nothing
        # to nudge or grant) -- .get() leaves them out of the response there,
        # rather than reporting a False/None that never happened.
        return {
            "ok": True, "action": "give",
            "target": outcome["session_id"], "agent": outcome["agent"],
            "summoned": outcome["summoned"],
            **({"granted": outcome["granted"]} if "granted" in outcome else {}),
            **({"nudge": outcome["nudge"]} if "nudge" in outcome else {}),
            "message": outcome["message"],
        }
    if not ConchQueue.grant(waiter.session_id):
        # Race: the waiter vanished between list() and grant().
        return {
            "ok": False, "action": "give",
            "message": f"{waiter.agent or waiter.session_id} is no longer waiting; nothing granted.",
        }
    # No nudge here (VM-2078): an ordinary waiter polls and self-acquires, so
    # pinging it is redundant. Only the summon path (no poll loop of its own)
    # still needs one -- see conch_ops.summon_and_grant.
    holder = Conch.get_holder()
    when = "now (the conch is free)" if holder is None else \
        f"when {holder.get('agent') or 'the holder'} releases"
    return {
        "ok": True, "action": "give",
        "target": waiter.session_id, "agent": waiter.agent,
        "summoned": False,
        "message": (
            f"Gave the conch to {waiter.agent or conch_ops.short(waiter.session_id)} "
            f"(session {conch_ops.short(waiter.session_id)}); they acquire {when}."
        ),
    }


def _do_bump() -> dict:
    """Drop the current holder and promote the head of the queue."""
    holder = Conch.get_holder()
    if holder is None:
        if Conch.LOCK_FILE.exists():
            return {
                "ok": False, "action": "bump",
                "message": "No live holder — the lock looks stale. Use conch(action='release') to clear it.",
            }
        # bump always promotes the head — clear any pending give first so this
        # path matches the holder-bump path below.
        ConchQueue.clear_grant()
        head = ConchQueue.grant_next()
        if head is None:
            return {
                "ok": True, "action": "bump", "bumped": None, "next": None,
                "message": "Conch is free and no one is waiting — nothing to bump.",
            }
        # No nudge here (VM-2078): the promoted head polls and self-acquires.
        return {
            "ok": True, "action": "bump", "bumped": None, "next": head.session_id,
            "message": (
                f"Conch was already free; promoted {head.agent or conch_ops.short(head.session_id)} "
                f"(session {conch_ops.short(head.session_id)}) as next in line."
            ),
        }

    bumped_agent = holder.get("agent") or "unknown"
    bumped_sid = holder.get("session_id")
    conch_ops.force_clear_lock()
    ConchQueue.clear_grant()
    head = ConchQueue.grant_next()
    if head is None:
        return {
            "ok": True, "action": "bump", "bumped": bumped_sid, "next": None,
            "message": (
                f"Bumped {bumped_agent} (session {conch_ops.short(bumped_sid)}); they must "
                "re-request. Queue is empty — the conch is now free."
            ),
        }
    # No nudge here (VM-2078): the promoted head polls and self-acquires.
    return {
        "ok": True, "action": "bump", "bumped": bumped_sid, "next": head.session_id,
        "message": (
            f"Bumped {bumped_agent} (session {conch_ops.short(bumped_sid)}); they must "
            f"re-request. Next up: {head.agent or conch_ops.short(head.session_id)} "
            f"(session {conch_ops.short(head.session_id)})."
        ),
    }


def _do_release() -> dict:
    """Force-clear a stale/stuck holder lock and any grant (idempotent)."""
    existed = Conch.LOCK_FILE.exists()
    conch_ops.force_clear_lock()
    ConchQueue.clear_grant()
    if existed:
        return {
            "ok": True, "action": "release",
            "message": "Released the conch lock and cleared any grant.",
        }
    return {
        "ok": True, "action": "release",
        "message": "Conch was already free; cleared any stray grant.",
    }
