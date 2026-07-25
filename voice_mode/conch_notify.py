"""conch_notify -- the operator-path summon nudge (VM-1625, narrowed VM-2078 D2).

Converse's ``callback`` mode (register-and-discard, pinged out-of-band) is
gone: every ordinary waiter now polls and *pulls* its own grant, so the
ordinary give/bump nudges this module used to fire are gone too. The ONE
caller left is :func:`voice_mode.conch_ops.summon_and_grant` (VM-1637,
``conch give`` to a running non-waiter): a summoned session has no poll loop
of its own, so it still needs telling.

**D2's whole point:** the original bug was silence -- a best-effort push
whose return value nothing checked, feeding an un-expiring grant. This
module now does the opposite: :func:`push_nudge` is a small, synchronous,
CHECKED-return function. It never raises, but it never swallows the outcome
either -- it reports one of three cases, and the caller (``summon_and_grant``)
decides whether to grant AT ALL based on which one it got:

- ``"delivered"`` -- the tmux pane nudge landed. Safe to grant, with a
  bounded, longer claim window (the target has no poll loop, so the ordinary
  poll-cycle window is unwinnable for it).
- ``"failed"`` -- a local target was nudged, but delivery could not be
  confirmed (no session match, tmux missing, timeout). MUST NOT grant --
  handing the floor to a target you just confirmed was not told is the
  original bug wearing a different hat.
- ``"remote"`` -- the target has no local pid, so no nudge is even possible
  (the VM-970 seam that never landed). MUST NOT grant, for the same reason.

Kept deliberately BORING AND SMALL (super.voicemode's standing caution): no
modes, no thresholds, no async dispatch. The old ``block=False`` fire-and-
forget path is gone with it -- the one caller left is a one-shot CLI/MCP
``give`` summon that is about to return anyway, so there is nothing left to
avoid blocking on.
"""

import os
import subprocess

#: The nudge a summoned grantee (no poll loop of its own) receives. Short,
#: names the action, and is the single tunable string for the push.
NUDGE_TEXT = "🐚 You've been granted the conch — call converse() to take the floor."

#: Bound the push so a grant decision can never hang on session discovery / tmux.
_SEND_TIMEOUT = 10.0


def push_nudge(entry) -> str:
    """Attempt to tell ``entry`` it has been summoned. Never raises.

    Returns one of ``"delivered"`` / ``"failed"`` / ``"remote"`` -- see the
    module docstring for what each means and what the caller must do with
    it. ``entry`` is duck-typed (``pid``, ``session_id``, ``project_path``)
    so it accepts either a ``WaiterEntry`` or a
    :class:`voice_mode.conch_ops.RunningSession`.

    A ``None`` entry (the target vanished before the nudge could be
    attempted) is reported as ``"failed"`` -- there is no delivery evidence,
    so the caller must not grant, exactly as if a real nudge attempt failed.
    """
    if entry is None:
        return "failed"
    if getattr(entry, "pid", None) is None:
        return "remote"
    try:
        return "delivered" if _local_nudge(entry) else "failed"
    except Exception:
        # Never let a notification glitch propagate into the grant decision
        # -- but unlike the old best-effort push, the CALLER still learns
        # delivery did not happen and must act on that (D2).
        return "failed"


def _local_nudge(entry) -> bool:
    """Try a tmux pane nudge to a local ``entry``; return whether it landed.

    Tries the grantee's ``session_id`` first (``session send`` matches it as
    a session-id prefix); on a miss, falls back to the ``project_path``
    basename as a match token.
    """
    session_id = getattr(entry, "session_id", None)
    if session_id and _session_send(session_id):
        return True
    project_path = getattr(entry, "project_path", None)
    if project_path:
        token = os.path.basename(os.path.normpath(str(project_path)))
        if token and _session_send(token):
            return True
    return False


def _session_send(target) -> bool:
    """Run ``session send <target> <nudge>``; return True iff it delivered.

    A missing binary, tmux absence, no-match (non-zero exit), a bad/None
    result, or a timeout all return ``False`` without raising.
    """
    try:
        result = subprocess.run(
            ["session", "send", str(target), NUDGE_TEXT],
            capture_output=True,
            timeout=_SEND_TIMEOUT,
        )
        return getattr(result, "returncode", None) == 0
    except (OSError, subprocess.SubprocessError):
        return False
