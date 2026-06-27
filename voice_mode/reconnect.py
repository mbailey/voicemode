"""Self-reconnect the voicemode MCP server by driving the Claude Code ``/mcp`` menu.

This is the executable form of the ``voice-self-reconnect`` slipbox recipe
(VM-1727). When the voicemode MCP server drops mid-session (``-32000 Connection
closed``) or fails to register its tools at launch, *its* MCP tools vanish --
so the recovery cannot itself be an MCP tool. ``tmux`` and ``subprocess``
survive the drop, so the agent heals the session with a single
``voicemode reconnect`` Bash call that walks the ``/mcp`` menu on its own pane.

**Deliberately MCP-independent and import-light.** This module imports only the
standard library plus ``click`` (a core dependency that the CLI already loads).
It pulls in *nothing* from ``voice_mode.server`` / ``voice_mode.tools`` so it
imports and runs cleanly when the MCP server is down -- the exact moment it is
needed. For the same reason the command lives here (a top-level module wired
into ``cli.py``) rather than under ``voice_mode/cli_commands/`` with the
MCP-coupled groups; see VM-1727 ``## Design``.

The design splits into two clean halves:

* **A pure menu parser** (:func:`parse_mcp_menu`, :func:`find_voicemode_row`)
  -- ``captured /mcp text -> server rows``. No side effects, no tmux; this is
  where correctness lives and what the unit tests pin down. It locates the
  voicemode row *by text* (never a fixed Down-count: the ``/mcp`` list order
  shifts as servers come and go) and reads its connection state.
* **A tmux driver** (:func:`reconnect`) -- opens the menu, navigates to the
  voicemode row, hits Reconnect *only when it is failed*, polls until connected
  (bounded by a timeout), and reports a distinct outcome. All tmux interaction
  goes through an injectable :class:`TmuxRunner` so the driver's state machine
  is unit-testable without a live tmux/Claude Code.

The exact keystroke choreography drives a Claude Code TUI menu whose layout can
shift across CC versions, so the driver parses defensively and **fails loud**
(``ERROR``) on an unexpected screen rather than blindly sending keys. The
end-to-end choreography against a real menu is validated by the ``manual``
integration test (VM-1727 verify-001).
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, List, Optional


# ---------------------------------------------------------------------------
# Outcomes
# ---------------------------------------------------------------------------

class ExitCode(IntEnum):
    """Process exit codes -- one per distinct outcome so a calling agent can branch.

    ``RECONNECTED`` is ``0`` (the canonical Unix success). ``ALREADY_CONNECTED``
    is a *successful* no-op but gets its own code so the agent can tell "I fixed
    it" from "nothing to do"; the human-readable ``RESULT:`` line on stdout
    carries the same distinction. The remaining codes are could-not-complete /
    abnormal outcomes.
    """

    RECONNECTED = 0          # was failed; reconnect performed and now connected
    ALREADY_CONNECTED = 10   # already connected; no action taken (benign no-op)
    NOT_FOUND = 11           # voicemode not present in the /mcp server list
    TIMEOUT = 12             # reconnect triggered but did not connect in time
    NOT_IN_TMUX = 13         # not running inside a tmux pane (TMUX_PANE unset)
    ERROR = 1                # unexpected screen / could not drive the menu (fail loud)


@dataclass
class ReconnectResult:
    """Structured result of a reconnect attempt.

    ``outcome`` is a stable machine token (matches the ``ExitCode`` name,
    lower-cased with ``-``); ``message`` is the human line; ``reload_line`` is
    the exact ``ToolSearch`` command the agent must run to reload the converse
    schema after a (re)connect -- ``None`` when there is nothing to reload.
    """

    exit_code: ExitCode
    outcome: str
    message: str
    reload_line: Optional[str] = None


# ---------------------------------------------------------------------------
# Connection-state detection
# ---------------------------------------------------------------------------

# State tokens, checked in priority order. Substring match on the lower-cased
# row text, plus the glyphs Claude Code renders. Order matters:
#   * "disconnected" *contains* "connected", so FAILED must be tested first.
#   * "connecting" and "connected" are distinct substrings (neither contains
#     the other), so they don't collide.
_STATE_TOKENS = (
    ("needs_auth", ("needs authentication", "authenticate", "auth required",
                    "not authenticated", "needs login")),
    ("failed",     ("✘", "✗", "❌", "failed", "disconnected", "error", "✖")),
    ("connecting", ("connecting", "reconnecting", "pending", "starting")),
    ("connected",  ("✔", "✓", "●", "connected", "ready")),
)

# State priority for *choosing* which voicemode row to act on when several
# match (e.g. a plugin entry and a stdio entry). We act on the most-broken one.
_ACTION_PRIORITY = {
    "failed": 0,
    "needs_auth": 1,
    "connecting": 2,
    "unknown": 3,
    "connected": 4,
}


def detect_state(row_text: str) -> str:
    """Classify a single server row's connection state.

    Returns one of ``failed`` / ``needs_auth`` / ``connecting`` / ``connected``
    / ``unknown``. ``unknown`` means a row we recognise as a server entry but
    whose status glyph/word we don't understand -- the driver treats that as a
    fail-loud condition rather than guessing.
    """
    low = row_text.lower()
    for state, tokens in _STATE_TOKENS:
        # Lower-casing leaves the status glyphs (✔ ✘ …) unchanged, so a single
        # substring test on the lower-cased row matches both glyphs and words.
        if any(tok in low for tok in tokens):
            return state
    return "unknown"


# ---------------------------------------------------------------------------
# Pure menu parser
# ---------------------------------------------------------------------------

# Box-drawing / border glyphs tmux capture-pane leaves around the menu.
_BORDER = "│║╮╭╯╰─━┌┐└┘╔╗╚╝═▌▐|"
# Selection markers Claude Code puts before the active row.
_MARKERS = "❯>›▶▸→*•·"
# The active-row CURSOR specifically. Narrower than _MARKERS on purpose: the
# live /mcp list also renders *content* markers that are NOT the cursor --
# action rows like ``→ Show unused connectors`` and ``·`` separators -- so
# cursor detection (which row is selected RIGHT NOW) must not mistake them for
# the selection. This precision is what makes cursor-driven navigation correct
# (VM-1727 impl-002).
_CURSOR = "❯>›▶▸"

_NUM_RE = re.compile(r"^(\d+)[.)]\s+(.*)$")

# A server NAME as the /mcp menu renders it: an identifier-like first token --
# alphanumeric/underscore start, then word chars / : . / @ -. This deliberately
# rejects decoration and prose first tokens (the debug-hint footer ``※ Run
# claude --debug …``, the ``↑/↓ to navigate …`` footer, group bullets), so a
# non-server line is never mis-parsed as a server row (VM-1727 impl-003 / live
# finding #2).
_NAME_RE = re.compile(r"^[A-Za-z0-9_][\w:./@-]*$")

# Status GLYPHS Claude Code renders in a server row's status column. Requiring
# one (or a list number) to accept an UN-numbered row keeps hint/footer prose
# out of the server list: a line like ``※ … to see error logs`` carries the
# *word* "error" but no status glyph, so it is not a server row. ``◯`` (disabled)
# is deliberately excluded -- a disabled built-in is not a reconnectable server.
_STATUS_GLYPHS = "✔✓●✘✗❌✖⚠"


@dataclass
class ServerRow:
    """One parsed entry from the ``/mcp`` server-list screen.

    ``index`` is the 0-based position among *parsed server rows*. It is **not**
    the number of ``Down`` presses to reach the row: the live ``/mcp`` list
    interleaves group labels, disabled built-ins, and action rows (e.g.
    ``→ Show unused connectors``) that the parser skips, so the cursor needs
    *more* Downs than this index implies. Navigation is therefore cursor-driven
    (:func:`_navigate_to_row`), never index-driven (VM-1727 impl-002).
    ``number`` is the 1-based number the menu prints, if any.
    """

    name: str
    state: str
    index: int
    number: Optional[int] = None
    raw: str = ""


def _clean_line(line: str) -> str:
    """Strip border glyphs and a leading selection marker from a captured line."""
    s = line.strip().strip(_BORDER).strip()
    while s and s[0] in _MARKERS:
        s = s[1:].lstrip()
    return s


def _has_status_glyph(text: str) -> bool:
    """True if a real status *glyph* sits in the row, vs. a status word in prose.

    Recognises the connected/failed/auth marks in :data:`_STATUS_GLYPHS` plus any
    braille spinner frame (``connecting`` / ``reconnecting`` animate through
    U+2800–U+28FF). A footer/hint line that merely *contains* a status word --
    ``※ Run claude --debug to see error logs`` -- has none of these, so it is
    correctly rejected as a server row (VM-1727 impl-003). Numbered list items
    don't need a glyph; they are explicit menu rows.
    """
    if any(g in text for g in _STATUS_GLYPHS):
        return True
    # Braille spinner frames (connecting/reconnecting) live in U+2800–U+28FF.
    return any(chr(0x2800) <= ch <= chr(0x28FF) for ch in text)


def parse_mcp_menu(text: str) -> List[ServerRow]:
    """Parse captured ``/mcp`` server-list text into :class:`ServerRow` entries.

    Once borders and the selection marker are stripped, a line is a server row
    only when **both** hold:

    * its first token is an identifier-like server name (:data:`_NAME_RE`) -- so
      decoration/prose first tokens (``※``, ``→``, ``↑/↓``) are rejected; and
    * it is a numbered list item (``N. name ...``) **or**, on an un-numbered
      menu, it carries a status *glyph* in the status column
      (:func:`_has_status_glyph`).

    Header, footer, and hint lines (``Manage MCP servers``, ``Esc to exit``, the
    debug-hint ``※ Run claude --debug to see error logs``) fail one of these and
    are skipped -- crucially, a bare ``error``/``connected`` *word* buried in a
    prose footer is not enough to be classified as a server (VM-1727 impl-003).
    """
    rows: List[ServerRow] = []
    for line in text.splitlines():
        cleaned = _clean_line(line)
        if not cleaned:
            continue

        number: Optional[int] = None
        body = cleaned
        m = _NUM_RE.match(cleaned)
        if m:
            number = int(m.group(1))
            body = m.group(2).strip()
        if not body:
            continue

        name = body.split()[0]
        # A server row needs a real identifier-like name; un-numbered rows
        # additionally need a status glyph in position. This keeps prose
        # footer/hint lines (e.g. ``※ … to see error logs``) out of the list.
        if not _NAME_RE.match(name):
            continue
        if number is None and not _has_status_glyph(body):
            continue

        rows.append(ServerRow(
            name=name,
            state=detect_state(body),
            index=len(rows),
            number=number,
            raw=line.rstrip(),
        ))
    return rows


def looks_like_mcp_menu(text: str) -> bool:
    """Heuristic: did the ``/mcp`` menu actually open?

    True if we parsed at least one server row, or the screen shows the menu's
    header text. Used to distinguish "menu open, voicemode just isn't listed"
    (NOT_FOUND) from "the menu never opened" (ERROR / fail loud) -- e.g. not
    running under Claude Code.
    """
    if parse_mcp_menu(text):
        return True
    low = text.lower()
    return "mcp server" in low or "manage mcp" in low


def find_voicemode_row(
    rows: List[ServerRow], server_match: str = "voicemode"
) -> Optional[ServerRow]:
    """Pick the voicemode row to act on, by text match (case-insensitive substring).

    When several rows match (a plugin entry *and* a stdio entry, say), return
    the most-broken one -- failed before connecting before connected -- so a
    failed voicemode is healed even if another voicemode entry is fine.
    Returns ``None`` when no row matches.
    """
    needle = server_match.lower()
    matches = [r for r in rows if needle in r.name.lower()]
    if not matches:
        return None
    return min(matches, key=lambda r: _ACTION_PRIORITY.get(r.state, 3))


# ---------------------------------------------------------------------------
# Cursor (selected-row) detection -- the basis of cursor-driven navigation
# ---------------------------------------------------------------------------

# The active /mcp menu is drawn at the BOTTOM of the captured pane; terminal
# scrollback sits ABOVE it -- including stale ``❯ /mcp`` REPL-prompt echoes whose
# ``❯`` is the SAME glyph as the menu's selection cursor. Cursor/marked detection
# must therefore look ONLY inside the live menu block, or it locks onto a prompt
# echo and never finds the real cursor (VM-1727 impl-003 / live finding #2). The
# block is bounded BELOW by its footer and ABOVE by its header.
_MENU_FOOTER_TOKENS = ("esc to", "to navigate", "for help")
_MENU_HEADER_TOKENS = ("manage mcp", "status:")


def _menu_region(text: str) -> List[str]:
    """The raw lines of the active (bottom-most) modal ``/mcp`` menu block.

    Trims terminal scrollback so a stale ``❯ /mcp`` prompt echo above the menu is
    never mistaken for the menu cursor. The block ends at the LAST footer line
    (``… to navigate`` / ``Esc to …`` / ``… for help``) and starts at the nearest
    preceding header -- ``Manage MCP servers`` for the server list, or
    ``Status:`` for a server submenu. Falls back to the whole capture when
    neither delimiter is present (keeps bare-string callers / unit fixtures
    working).
    """
    lines = text.splitlines()
    if not lines:
        return lines
    end = len(lines) - 1
    for i, line in enumerate(lines):
        if any(tok in line.lower() for tok in _MENU_FOOTER_TOKENS):
            end = i
    start = 0
    for i in range(end, -1, -1):
        if any(tok in lines[i].lower() for tok in _MENU_HEADER_TOKENS):
            start = i
            break
    return lines[start:end + 1]


def marked_row(text: str) -> Optional[str]:
    """Return the text of the cursor-marked (``❯``) row in a captured menu.

    Strips borders and the leading cursor glyph; returns the remaining row text,
    or ``None`` if no row is currently selected. Searches only the active
    :func:`_menu_region`, so a stale ``❯ /mcp`` REPL-prompt echo in scrollback
    above the menu is not mistaken for the cursor (VM-1727 impl-003). Uses the
    narrow :data:`_CURSOR` set (not :data:`_MARKERS`) so an action row such as
    ``→ Show unused connectors`` is never mistaken for the selection either.
    """
    for line in _menu_region(text):
        s = line.strip().strip(_BORDER).strip()
        if not s:
            continue
        if s[0] in _CURSOR:
            return s[1:].lstrip()
    return None


def marked_row_name(text: str) -> Optional[str]:
    """The server *name* of the cursor-marked row, parsed like :func:`parse_mcp_menu`.

    Lets navigation ask "is the cursor on the row I want?" by comparing names --
    more precise than a substring test, so a connected ``voicemode`` row is not
    confused with a failed ``plugin:voicemode:voicemode`` row. ``None`` when no
    row is selected (or the selected line has no name token).
    """
    body = marked_row(text)
    if body is None:
        return None
    m = _NUM_RE.match(body)
    if m:
        body = m.group(2).strip()
    if not body:
        return None
    return body.split()[0]


# ---------------------------------------------------------------------------
# Submenu inspection
# ---------------------------------------------------------------------------

def submenu_reconnect_first(text: str) -> bool:
    """True iff the server submenu shows **Reconnect** as the selected/first action.

    When a server is failed, Reconnect is item 1 and already selected, so a bare
    Enter triggers it. When connected, item 1 is *View tools* instead -- this
    returns False so the driver bails rather than blindly hitting Enter and
    opening the tools list. We check the marked (``❯``) line first, then fall
    back to the first numbered action line. Like :func:`marked_row`, this scans
    only the active :func:`_menu_region`, so a stale ``❯ /mcp`` REPL-prompt echo
    in scrollback isn't read as the selected action (VM-1727 impl-003).
    """
    marked: Optional[str] = None
    first_numbered: Optional[str] = None
    for line in _menu_region(text):
        cleaned = line.strip().strip(_BORDER).strip()
        if not cleaned:
            continue
        if cleaned[0] in _MARKERS:
            marked = cleaned[1:].lstrip()
            break
        if first_numbered is None and _NUM_RE.match(cleaned):
            first_numbered = cleaned
    candidate = marked if marked is not None else first_numbered
    if candidate is None:
        return False
    m = _NUM_RE.match(candidate)
    if m:
        candidate = m.group(2)
    return "reconnect" in candidate.lower()


# ---------------------------------------------------------------------------
# Schema-reload line
# ---------------------------------------------------------------------------

_RELOAD_PLUGIN = "ToolSearch select:mcp__plugin_voicemode_voicemode__converse"
_RELOAD_STDIO = "ToolSearch select:mcp__voicemode__converse"


def reload_line_for(name: Optional[str]) -> str:
    """The exact ``ToolSearch`` line the agent must run to reload converse.

    The CLI cannot reload the *agent's* tool schema -- only the agent can -- so
    the command's job ends at "reconnected" and it prints this line for the
    agent (reading the Bash output) to fire. Plugin installs expose
    ``mcp__plugin_voicemode_voicemode__converse``; stdio installs
    ``mcp__voicemode__converse``. We pick by the menu's name token, and print
    both when it's ambiguous.
    """
    if name:
        low = name.lower()
        if "plugin" in low:
            return _RELOAD_PLUGIN
        if low == "voicemode":
            return _RELOAD_STDIO
    return _RELOAD_PLUGIN + "\n" + _RELOAD_STDIO


# ---------------------------------------------------------------------------
# tmux driver
# ---------------------------------------------------------------------------

class TmuxRunner:
    """Thin, injectable wrapper over the tmux calls the driver makes.

    Real use targets a pane via ``send-keys`` / ``capture-pane``. Tests inject a
    fake with scripted captures and a controllable clock, so the driver's state
    machine is exercised without a live tmux or Claude Code.
    """

    def __init__(self, pane: str):
        self.pane = pane

    def send_keys(self, *keys: str) -> None:
        subprocess.run(
            ["tmux", "send-keys", "-t", self.pane, *keys],
            capture_output=True,
        )

    def capture(self) -> str:
        result = subprocess.run(
            ["tmux", "capture-pane", "-t", self.pane, "-p"],
            capture_output=True, text=True,
        )
        return result.stdout or ""

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def now(self) -> float:
        return time.monotonic()


def _noop_emit(_msg: str) -> None:
    pass


def _close_menu(runner: TmuxRunner, *, settle: float, tries: int = 3) -> None:
    """Best-effort: send Esc until the menu is gone, so we never leave it half-open.

    An extra Esc at the Claude Code prompt only clears the (empty) input, so
    over-sending is harmless.
    """
    for _ in range(tries):
        runner.send_keys("Escape")
        runner.sleep(settle)
        if not looks_like_mcp_menu(runner.capture()):
            return


def _navigate_to_row(
    runner: TmuxRunner,
    target_name: str,
    initial_capture: str,
    *,
    settle: float,
    emit: Callable[[str], None] = _noop_emit,
) -> bool:
    """Move the ``/mcp`` cursor onto the row named ``target_name``, by the cursor.

    **Cursor-driven, never count-driven.** The live ``/mcp`` list interleaves
    group labels, disabled built-ins, and action rows (``→ Show unused
    connectors``) that the parser skips, so a *parsed* row index is NOT the
    number of ``Down`` presses needed (the VM-1727 impl-002 defect: parsed index
    3, cursor needed 5). Instead we press ``Down``, re-capture, and check whether
    the ``❯``-marked row IS the target -- repeating until it is. The rendered
    cursor is ground truth, so this is robust to any row interleaving.

    Bounded by the visible line count (plus slack for a full wrap-around if
    ``Down`` cycles at the bottom): returns ``True`` once the cursor sits on
    ``target_name``, ``False`` if it never lands there within that bound (the
    caller then fails loud rather than pressing Enter on the wrong row).
    """
    current = initial_capture
    # Generous upper bound: every visible line + slack. A real list has far
    # fewer navigable rows than lines, so this guarantees at least one full
    # cycle even if Down wraps -- without ever looping forever.
    max_steps = current.count("\n") + 8
    for _ in range(max_steps):
        if marked_row_name(current) == target_name:
            return True
        runner.send_keys("Down")
        runner.sleep(settle)
        current = runner.capture()
    # One last check after the final Down.
    return marked_row_name(current) == target_name


def reconnect(
    *,
    pane: Optional[str] = None,
    server_match: str = "voicemode",
    timeout: float = 75.0,
    poll_interval: float = 2.0,
    settle: float = 0.5,
    dry_run: bool = False,
    runner: Optional[TmuxRunner] = None,
    emit: Optional[Callable[[str], None]] = None,
) -> ReconnectResult:
    """Drive the ``/mcp`` menu on the agent's pane to reconnect voicemode.

    Returns a :class:`ReconnectResult`; never raises for an expected condition
    (not-in-tmux, not-found, timeout, unexpected screen) -- each maps to a
    distinct :class:`ExitCode`. ``emit`` receives progress lines (the CLI wires
    it to ``click.echo``; tests pass ``None``).

    The dance mirrors the slipbox recipe: open the menu, parse it, and act on
    the voicemode row's *state* read from the list -- if connected, bail as a
    no-op; if failed, navigate in, assert Reconnect is the first action, hit it,
    then poll until it reads connected (bounded by ``timeout``). On CC v2.1.186
    hitting Reconnect *closes* the whole ``/mcp`` dialog, so each poll re-opens
    ``/mcp`` and re-parses the authoritative server list (VM-1727 impl-004).
    """
    emit = emit or _noop_emit

    pane = pane or os.environ.get("TMUX_PANE")
    if not pane or not os.environ.get("TMUX"):
        return ReconnectResult(
            ExitCode.NOT_IN_TMUX, "not-in-tmux",
            "❌ Not inside a tmux pane (TMUX_PANE unset). The /mcp reconnect "
            "dance needs a tmux pane running Claude Code.",
        )

    if dry_run:
        return ReconnectResult(
            ExitCode.RECONNECTED, "dry-run",
            f"🩺 [dry-run] Would open /mcp on pane {pane} and reconnect a failed "
            f"'{server_match}' server (no keys sent).",
            reload_line=reload_line_for(None),
        )

    runner = runner or TmuxRunner(pane)

    # 1. Open the menu and read it.
    emit(f"⏳ Opening /mcp on pane {pane}…")
    runner.send_keys("/mcp", "Enter")
    runner.sleep(settle)
    text = runner.capture()

    if not looks_like_mcp_menu(text):
        _close_menu(runner, settle=settle)
        return ReconnectResult(
            ExitCode.ERROR, "error",
            "❌ The /mcp menu did not open (no MCP server list detected). Are we "
            "running under Claude Code? Aborting without sending blind keystrokes.",
        )

    rows = parse_mcp_menu(text)
    row = find_voicemode_row(rows, server_match)
    if row is None:
        listed = ", ".join(r.name for r in rows) or "(none parsed)"
        _close_menu(runner, settle=settle)
        return ReconnectResult(
            ExitCode.NOT_FOUND, "not-found",
            f"❌ No '{server_match}' server in the /mcp list. Servers seen: {listed}.",
        )

    reload_line = reload_line_for(row.name)

    # 2. Already connected -> clean no-op.
    if row.state == "connected":
        _close_menu(runner, settle=settle)
        return ReconnectResult(
            ExitCode.ALREADY_CONNECTED, "already-connected",
            f"✅ '{row.name}' is already connected — nothing to do.",
            reload_line=reload_line,
        )

    # An unrecognised or auth-required state is not something we can heal by
    # hitting Reconnect -- fail loud rather than guess.
    if row.state in ("unknown", "needs_auth"):
        _close_menu(runner, settle=settle)
        return ReconnectResult(
            ExitCode.ERROR, "error",
            f"❌ '{row.name}' is in state '{row.state}', which reconnect can't "
            f"safely handle. Resolve it manually via /mcp.",
        )

    # 3. Failed/connecting -> drive Reconnect. For 'connecting' the server is
    #    already (re)connecting, so skip straight to polling without re-pressing.
    if row.state == "failed":
        emit(f"🔌 '{row.name}' is failed; moving the cursor onto it…")
        # Navigate by reading the cursor, not by counting parsed rows -- the list
        # has navigable rows the parser skips, so a parsed index under-counts the
        # Downs needed (VM-1727 impl-002).
        if not _navigate_to_row(runner, row.name, text, settle=settle, emit=emit):
            _close_menu(runner, settle=settle)
            return ReconnectResult(
                ExitCode.ERROR, "error",
                f"❌ Could not move the /mcp cursor onto '{row.name}'. It is in the "
                f"list but the cursor never landed on it — aborting rather than "
                f"pressing Enter on the wrong row.",
            )
        runner.send_keys("Enter")            # open the server submenu
        runner.sleep(settle)

        if not submenu_reconnect_first(runner.capture()):
            _close_menu(runner, settle=settle)
            return ReconnectResult(
                ExitCode.ERROR, "error",
                f"❌ The '{row.name}' submenu did not show Reconnect as the first "
                f"action. Aborting rather than hitting an unexpected menu item.",
            )

        runner.send_keys("Enter")            # hit Reconnect (item 1)
        runner.sleep(settle)
    else:  # connecting
        emit(f"⏳ '{row.name}' is already reconnecting; waiting for it to settle…")

    # Normalise to a closed menu before polling. On CC v2.1.186 hitting Reconnect
    # CLOSES the whole /mcp dialog (it does NOT stay an open, live-updating list
    # -- the original code's wrong assumption, surfaced live as VM-1727 verify-001
    # finding #3); for the 'connecting' branch the list opened in step 1 is still
    # up. Either way, close it now so every poll re-opens a fresh, authoritative
    # list. This replaces the old stray `Escape` (which, post-close, just cleared
    # the empty REPL prompt with a misleading "back to the live list" comment).
    _close_menu(runner, settle=settle)

    # 4. Poll until voicemode reads connected (or we time out). Because Reconnect
    #    closed the dialog, RE-OPEN /mcp each poll and re-parse the live server
    #    list -- reusing the proven parser (the already-connected no-op path reads
    #    'connected' from a freshly-opened menu correctly). Re-open-and-parse is
    #    immune to the stale '⎿ Reconnected to <server>.' transcript line a
    #    confirmation-scraping signal would have to baseline against (the same
    #    scrollback-contamination class impl-003 handled for the '❯' cursor glyph):
    #    success is read ONLY from the freshly-parsed live state, never scrollback.
    emit(f"⏳ Waiting up to {timeout:.0f}s for '{row.name}' to connect…")
    deadline = runner.now() + timeout
    while runner.now() < deadline:
        runner.sleep(poll_interval)
        runner.send_keys("/mcp", "Enter")    # re-open the list Reconnect closed
        runner.sleep(settle)
        current = find_voicemode_row(parse_mcp_menu(runner.capture()), server_match)
        if current is not None and current.state == "connected":
            _close_menu(runner, settle=settle)
            return ReconnectResult(
                ExitCode.RECONNECTED, "reconnected",
                f"✅ Reconnected '{row.name}'.",
                reload_line=reload_line,
            )
        _close_menu(runner, settle=settle)   # clear the REPL before the next re-open

    _close_menu(runner, settle=settle)
    return ReconnectResult(
        ExitCode.TIMEOUT, "timeout",
        f"⏱️  '{row.name}' did not reach connected within {timeout:.0f}s. "
        f"It may still be reconnecting — re-run `voicemode reconnect` or check /mcp.",
        reload_line=reload_line,
    )


def run_reconnect(
    *,
    pane: Optional[str],
    server_match: str,
    timeout: float,
    dry_run: bool,
) -> ReconnectResult:
    """CLI-facing wrapper: run :func:`reconnect`, print its result, return it.

    Prints progress to stderr-free stdout (the agent reads Bash output), a
    ``RESULT:`` machine token, the human message, and -- on (re)connect -- the
    exact ``ToolSearch`` reload line for the agent to fire next.
    """
    import click

    result = reconnect(
        pane=pane,
        server_match=server_match,
        timeout=timeout,
        dry_run=dry_run,
        emit=click.echo,
    )
    click.echo(f"RESULT: {result.outcome}")
    click.echo(result.message)
    if result.reload_line:
        click.echo("")
        click.echo("Reload the converse tool schema with:")
        click.echo(result.reload_line)
    return result


# ---------------------------------------------------------------------------
# Click command (wired into voice_mode/cli.py)
# ---------------------------------------------------------------------------

try:
    import click

    @click.command("reconnect")
    @click.help_option("-h", "--help")
    @click.option("--timeout", type=float, default=75.0, show_default=True,
                  help="Seconds to wait for the server to reconnect.")
    @click.option("--pane", default=None,
                  help="tmux pane to drive (default: $TMUX_PANE, the agent's own pane).")
    @click.option("--server", "server_match", default="voicemode", show_default=True,
                  help="Substring matched against /mcp server names.")
    @click.option("--dry-run", is_flag=True,
                  help="Report what would happen without sending any keystrokes.")
    def reconnect_command(timeout, pane, server_match, dry_run):
        """Reconnect the voicemode MCP server via the Claude Code /mcp menu.

        Runs the whole tmux `/mcp` reconnect dance in one call: opens the menu on
        this pane, finds the voicemode server by name, hits Reconnect if it's
        failed, waits until it connects, and prints the `ToolSearch` line to
        reload the converse schema. Intended for an agent to run in a single Bash
        call when voice drops (`-32000 Connection closed`).

        \b
        Exit codes:
          0   reconnected
          10  already connected (no-op)
          11  voicemode not found in the /mcp list
          12  timed out waiting to reconnect
          13  not inside a tmux pane
          1   unexpected screen / could not drive the menu
        """
        result = run_reconnect(
            pane=pane, server_match=server_match, timeout=timeout, dry_run=dry_run,
        )
        raise SystemExit(int(result.exit_code))

except ImportError:  # pragma: no cover - click is a core dependency
    reconnect_command = None
