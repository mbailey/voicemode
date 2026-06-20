"""notify_granted — the *push* half of the conch's pull/push delivery (VM-1625).

A waiter in ``wait`` mode is actively polling: when the conch becomes theirs
they *pull* it (their own loop self-acquires). A waiter in ``callback`` mode is
idle — it asked to be pinged rather than block — so when the floor falls to it,
or it is skipped so a blocking waiter behind it isn't starved (the F1 fix in
:meth:`voice_mode.conch_queue.ConchQueue.grant_next`), it must be *pushed*: told
to call ``converse()`` and (re)engage.

This module is the single home for that push so every grant site can share it:

- the CLI ``conch give`` / ``conch bump`` (via ``cli_commands.conch._notify_granted``),
- ``ConchQueue.grant_next`` pinging callback waiters it skips,
- and, when it lands, VM-1619's converse callback-return path.

Delivery is **best-effort and never raises** into a grant site — a missing
``session`` binary, no tmux, or a vanished waiter is a silent no-op, mirroring
``converse.focus_tmux_pane``:

- **Local grantee** (``pid`` set): a tmux pane nudge via the skillbox
  ``session send`` (matches on session-id prefix / project / name and types into
  the grantee's pane).
- **Remote grantee** (``pid`` is ``None``): no tmux to nudge — the grant file is
  itself the marker the remote agent discovers on its next ``converse()`` /
  ``conch status``. ``_remote_marker`` is left as the seam for VM-970's MCP
  channel notification to fill.

The function takes a ``WaiterEntry``-shaped object (duck-typed: ``mode``,
``pid``, ``session_id``, ``project_path``) so it carries no import dependency on
the queue layer and stays trivially callable from anywhere.
"""

import os
import subprocess

#: The nudge an idle (callback-mode) grantee receives. Short, names the action,
#: and is the single tunable string for the push (VM-1625 decision).
NUDGE_TEXT = "🐚 You've been granted the conch — call converse() to take the floor."

#: Bound the best-effort push so a grant site (including the converse release
#: hot path via ``grant_next``) can never hang on session discovery / tmux.
_SEND_TIMEOUT = 10.0


def notify_granted(entry) -> None:
    """Push a "your turn" nudge to a grantee that is **not** actively watching.

    The idempotency / "not watching" gate is mode-based (VM-1625 decision):

    - ``mode == "wait"`` ⇒ the grantee is polling; the *pull* wins ⇒ **no push**
      (a ``give`` to a wait-mode waiter is a silent no-push — its own loop takes
      the floor, so a double-delivery is impossible).
    - ``mode == "callback"`` ⇒ idle ⇒ **push**.

    Routing for a callback grantee: local (``pid`` set) ⇒ tmux pane nudge;
    remote (``pid is None``) ⇒ remote-marker seam (VM-970). A ``None`` entry (the
    waiter vanished between grant and notify) is a harmless no-op.

    Never raises: any failure is swallowed so ``give`` / ``bump`` / ``grant_next``
    are never broken by a notification glitch.
    """
    if entry is None:
        return
    # Only an idle callback waiter needs pushing; a wait-mode waiter self-acquires.
    if getattr(entry, "mode", "wait") != "callback":
        return
    try:
        if getattr(entry, "pid", None) is None:
            _remote_marker(entry)
        else:
            _local_nudge(entry)
    except Exception:
        # Best-effort: a push must never propagate into the grant site.
        pass


def _local_nudge(entry) -> None:
    """Best-effort tmux pane nudge to a local grantee via ``session send``.

    Tries the grantee's ``session_id`` first (``session send`` matches it as a
    session-id prefix); on a miss, falls back to the ``project_path`` basename as
    a match token. A missing ``session`` binary / no tmux / no match is a silent
    no-op — this never raises.
    """
    session_id = getattr(entry, "session_id", None)
    if session_id and _session_send(session_id):
        return
    project_path = getattr(entry, "project_path", None)
    if project_path:
        token = os.path.basename(os.path.normpath(str(project_path)))
        if token:
            _session_send(token)


def _session_send(target) -> bool:
    """Run ``session send <target> <nudge>``; return True iff it delivered.

    Best-effort wrapper: a missing binary, tmux absence, no-match (non-zero
    exit), or a timeout all return ``False`` without raising.
    """
    try:
        result = subprocess.run(
            ["session", "send", str(target), NUDGE_TEXT],
            capture_output=True,
            timeout=_SEND_TIMEOUT,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _remote_marker(entry) -> None:
    """Seam for VM-970's MCP channel notification to a remote grantee.

    No-op today: with VM-970 unmerged the grant file *is* the marker a remote
    agent discovers on its next ``converse()`` / ``conch status``. VM-970 fills
    this in to deliver an out-of-band push.
    """
    return None
