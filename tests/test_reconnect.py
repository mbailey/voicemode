"""Tests for the voicemode `/mcp` self-reconnect command (VM-1727).

Two layers, matching the module's design:

* The **pure menu parser** is pinned against captured `/mcp` fixtures
  (`tests/fixtures/mcp_menu/`) -- failed, connected, deep-in-list,
  plugin-vs-stdio, not-present, connecting. This is where correctness lives.
* The **driver state machine** is exercised through a scripted `FakeRunner`
  (no live tmux / Claude Code): already-connected no-op, not-found, the
  failed -> reconnect -> connected happy path, fail-loud on an unexpected
  submenu / non-menu screen, and the timeout path.

The end-to-end choreography against a real menu is the `manual`-marked
integration test owned by VM-1727 verify-001, not here.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from voice_mode.reconnect import (
    ExitCode,
    ServerRow,
    detect_state,
    find_voicemode_row,
    looks_like_mcp_menu,
    marked_row,
    marked_row_name,
    parse_mcp_menu,
    reconnect,
    reload_line_for,
    submenu_reconnect_first,
)

FIXTURES = Path(__file__).parent / "fixtures" / "mcp_menu"


def load(name: str) -> str:
    return (FIXTURES / f"{name}.txt").read_text()


# ---------------------------------------------------------------------------
# Pure menu parser
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestParseMcpMenu:
    def test_failed_menu(self):
        rows = parse_mcp_menu(load("failed"))
        assert [r.name for r in rows] == ["taskmaster", "voicemode", "playwright"]
        vm = next(r for r in rows if r.name == "voicemode")
        assert vm.state == "failed"
        assert vm.index == 1          # one Down from the top
        assert vm.number == 2

    def test_connected_menu(self):
        rows = parse_mcp_menu(load("connected"))
        vm = next(r for r in rows if r.name == "voicemode")
        assert vm.state == "connected"
        assert vm.index == 0          # already at the top

    def test_deep_in_list(self):
        rows = parse_mcp_menu(load("deep_in_list"))
        assert len(rows) == 7
        vm = next(r for r in rows if r.name == "voicemode")
        assert vm.index == 5          # five Downs deep -- never trust a fixed count
        assert vm.number == 6
        assert vm.state == "failed"

    def test_plugin_and_stdio_both_listed(self):
        rows = parse_mcp_menu(load("plugin_vs_stdio"))
        names = [r.name for r in rows]
        assert "voicemode" in names
        assert "plugin:voicemode:voicemode" in names

    def test_not_present(self):
        rows = parse_mcp_menu(load("not_present"))
        assert all("voicemode" not in r.name for r in rows)

    def test_connecting_state(self):
        rows = parse_mcp_menu(load("connecting"))
        vm = next(r for r in rows if r.name == "voicemode")
        assert vm.state == "connecting"

    def test_headers_and_footers_skipped(self):
        # "Manage MCP servers" and "Esc to exit" must not be parsed as servers.
        rows = parse_mcp_menu(load("failed"))
        assert all("manage" not in r.name.lower() for r in rows)
        assert all(r.name.lower() != "esc" for r in rows)

    def test_unnumbered_menu_parsed_by_status_token(self):
        # Some CC versions render without numbers; rows are still found by their
        # status glyph, and indices stay sequential.
        text = (
            "Manage MCP servers\n"
            "❯ taskmaster        ✔ connected\n"
            "  voicemode         ✘ failed\n"
            "Esc to exit\n"
        )
        rows = parse_mcp_menu(text)
        assert [r.name for r in rows] == ["taskmaster", "voicemode"]
        assert rows[1].index == 1
        assert rows[1].state == "failed"

    def test_real_cc_2_1_186_menu_parsed_index_undercounts_cursor(self):
        # The real CC v2.1.186 menu (un-numbered) interleaves rows the parser
        # SKIPS -- a group label, `→ Show unused connectors`, and a disabled
        # built-in -- before voicemode. The parser still finds voicemode and its
        # failed state by text, BUT its parsed-row index (3) is NOT the number of
        # Downs the cursor needs (5). This divergence is the impl-002 defect, and
        # why navigation must be cursor-driven, not index-driven.
        rows = parse_mcp_menu(load("cc_2_1_186_unnumbered"))
        vm = find_voicemode_row(rows)
        assert vm is not None
        assert vm.name == "plugin:voicemode:voicemode"
        assert vm.state == "failed"
        assert vm.index == 3                       # parsed-row index
        # The skipped-but-navigable rows are absent from the parse...
        names = [r.name for r in rows]
        assert "computer-use" not in names         # `◯ disabled` -> skipped
        assert not any("show unused" in n.lower() for n in names)  # action row -> skipped


@pytest.mark.unit
class TestDetectState:
    @pytest.mark.parametrize("text,expected", [
        ("voicemode ✘ failed", "failed"),
        ("voicemode ✔ connected", "connected"),
        ("voicemode disconnected", "failed"),        # contains "connected" -> must still be failed
        ("voicemode ⠴ connecting…", "connecting"),
        ("voicemode needs authentication", "needs_auth"),
        ("voicemode ✓ ready", "connected"),
        ("voicemode something weird", "unknown"),
    ])
    def test_states(self, text, expected):
        assert detect_state(text) == expected


@pytest.mark.unit
class TestFindVoicemodeRow:
    def test_finds_failed_voicemode(self):
        rows = parse_mcp_menu(load("failed"))
        row = find_voicemode_row(rows)
        assert row is not None and row.name == "voicemode" and row.state == "failed"

    def test_prefers_failed_over_connected_when_multiple(self):
        # stdio voicemode is connected, plugin entry is failed -> act on the failed one.
        rows = parse_mcp_menu(load("plugin_vs_stdio"))
        row = find_voicemode_row(rows)
        assert row.name == "plugin:voicemode:voicemode"
        assert row.state == "failed"

    def test_returns_none_when_absent(self):
        rows = parse_mcp_menu(load("not_present"))
        assert find_voicemode_row(rows) is None

    def test_custom_server_match(self):
        rows = parse_mcp_menu(load("failed"))
        assert find_voicemode_row(rows, server_match="playwright").name == "playwright"


@pytest.mark.unit
class TestLooksLikeMenu:
    def test_true_for_real_menu(self):
        assert looks_like_mcp_menu(load("failed")) is True

    def test_false_for_prompt(self):
        assert looks_like_mcp_menu(load("not_a_menu")) is False


@pytest.mark.unit
class TestMarkedRow:
    """Cursor (selected-row) detection -- the basis of cursor-driven navigation."""

    def test_returns_selected_row_text(self):
        text = "  ❯ voicemode ✘ failed\n    taskmaster ✔ connected\n"
        assert marked_row(text).startswith("voicemode")

    def test_arrow_action_row_is_not_the_cursor(self):
        # `→ Show unused connectors` begins with → (a *content* marker, not the
        # ❯ cursor) and must NOT be read as the selected row -- the precise bug
        # that broke parsed-index navigation (VM-1727 impl-002).
        text = "    → Show unused connectors (1)\n  ❯ voicemode ✘ failed\n"
        assert marked_row(text).startswith("voicemode")

    def test_none_when_nothing_selected(self):
        assert marked_row("  taskmaster ✔ connected\n  voicemode ✘ failed\n") is None

    def test_name_of_selected_row(self):
        # The real menu opens with the cursor on the first server, not voicemode.
        assert marked_row_name(load("cc_2_1_186_unnumbered")) == "claude.ai"

    def test_name_strips_number_prefix(self):
        assert marked_row_name("❯ 6. voicemode ✘ failed\n") == "voicemode"


@pytest.mark.unit
class TestSubmenuReconnectFirst:
    def test_true_when_reconnect_selected(self):
        assert submenu_reconnect_first(load("submenu_failed")) is True

    def test_false_when_view_tools_first(self):
        # Connected server: item 1 is View tools -> must NOT blindly Enter.
        assert submenu_reconnect_first(load("submenu_connected")) is False


@pytest.mark.unit
class TestReloadLineFor:
    def test_plugin_name(self):
        line = reload_line_for("plugin:voicemode:voicemode")
        assert line == "ToolSearch select:mcp__plugin_voicemode_voicemode__converse"

    def test_stdio_name(self):
        assert reload_line_for("voicemode") == "ToolSearch select:mcp__voicemode__converse"

    def test_ambiguous_prints_both(self):
        line = reload_line_for(None)
        assert "mcp__plugin_voicemode_voicemode__converse" in line
        assert "mcp__voicemode__converse" in line


# ---------------------------------------------------------------------------
# Driver state machine (scripted FakeRunner)
# ---------------------------------------------------------------------------

class FakeRunner:
    """Scripted stand-in for :class:`TmuxRunner`.

    ``screens`` are returned by successive ``capture()`` calls; once exhausted
    the last screen repeats (so polling can run as long as it likes). ``sleep``
    advances a fake monotonic clock, so the timeout path is exercised without
    real waiting. Every ``send_keys`` call is recorded as a tuple for assertions.
    """

    def __init__(self, screens):
        self.screens = list(screens)
        self.sent = []
        self.clock = 0.0

    def send_keys(self, *keys):
        self.sent.append(tuple(keys))

    def capture(self):
        if len(self.screens) > 1:
            return self.screens.pop(0)
        return self.screens[0] if self.screens else ""

    def sleep(self, seconds):
        self.clock += seconds

    def now(self):
        return self.clock

    def downs(self):
        return sum(1 for c in self.sent if c == ("Down",))

    def enters(self):
        # Bare Enter presses (submenu-enter / Reconnect), not the ("/mcp","Enter") open.
        return sum(1 for c in self.sent if c == ("Enter",))


# Status fragments the CursorMenu renders for the target row.
_FAILED = "✘ failed"
_CONNECTED = "✔ connected · 3 tools"


class CursorMenu:
    """Cursor-aware fake of the ``/mcp`` menu: a ``❯`` that Down/Up move over rows.

    Where :class:`FakeRunner` replays fixed scripted screens, this *models* a
    live menu -- so cursor-driven navigation is exercised honestly: the rows the
    parser skips (group labels, action rows, disabled built-ins) still cost a
    ``Down`` here, which is the whole point of VM-1727 impl-002. A parsed-row
    index would under-count; the cursor is ground truth.

    ``layout`` is the body top-to-bottom as ``(kind, text)`` tuples:

    * ``"label"`` -- a non-navigable group header / decoration (rendered,
      never selectable; the cursor steps right over it).
    * ``"nav"``   -- a row the cursor can stop on; ``text`` is rendered as-is.
    * ``"target"`` -- the voicemode row the driver navigates to; ``text`` is the
      bare server name and the runner appends the live status. There must be
      exactly one. Its status flips ``failed -> connected`` after
      ``connect_after`` list captures following Reconnect (a large value models
      "never connects" -> timeout).

    ``submenu_ok`` controls the target's submenu: ``True`` shows *Reconnect*
    first (the failed case); ``False`` shows *View tools* first (drives the
    fail-loud guard).
    """

    def __init__(self, layout, *, header=("Manage MCP servers",),
                 footer=("Esc to exit",), submenu_ok=True, connect_after=1):
        self.layout = list(layout)
        self.header = list(header)
        self.footer = list(footer)
        self.submenu_ok = submenu_ok
        self.connect_after = connect_after

        navs = [i for i, (k, _) in enumerate(self.layout) if k in ("nav", "target")]
        self._nav_count = len(navs)
        targets = [n for n, i in enumerate(navs) if self.layout[i][0] == "target"]
        assert len(targets) == 1, "CursorMenu needs exactly one target row"
        self.target_pos = targets[0]
        self.target_name = self.layout[navs[self.target_pos]][1]

        self.cursor = 0
        self.opened = False
        self.in_submenu = False
        self.vm_state = "failed"
        self.reconnect_pressed = False
        self._polls = 0
        self.sent = []
        self.clock = 0.0

    # --- driver (TmuxRunner) protocol ---
    def send_keys(self, *keys):
        self.sent.append(tuple(keys))
        k = tuple(keys)
        if k == ("/mcp", "Enter"):
            self.opened, self.cursor, self.in_submenu = True, 0, False
        elif k == ("Down",) and not self.in_submenu:
            self.cursor = min(self.cursor + 1, self._nav_count - 1)
        elif k == ("Up",) and not self.in_submenu:
            self.cursor = max(self.cursor - 1, 0)
        elif k == ("Enter",):
            if not self.in_submenu and self.cursor == self.target_pos:
                self.in_submenu = True       # open the target's submenu
            elif self.in_submenu:
                self.reconnect_pressed = True  # hit Reconnect
        elif k == ("Escape",):
            self.in_submenu = False

    def capture(self):
        if not self.opened:
            return ""
        if self.in_submenu:
            return self._render_submenu()
        if self.reconnect_pressed:
            self._polls += 1
            if self._polls > self.connect_after:
                self.vm_state = "connected"
        return self._render_list()

    def sleep(self, seconds):
        self.clock += seconds

    def now(self):
        return self.clock

    # --- assertion helpers ---
    def downs(self):
        return sum(1 for c in self.sent if c == ("Down",))

    def enters(self):
        return sum(1 for c in self.sent if c == ("Enter",))

    # --- rendering ---
    def _render_list(self):
        lines = [f"  {h}" for h in self.header] + [""]
        nav_i = 0
        for kind, text in self.layout:
            if kind == "label":
                lines.append(f"    {text}")
                continue
            mark = "❯ " if nav_i == self.cursor else "  "
            if kind == "target":
                glyph = _CONNECTED if self.vm_state == "connected" else _FAILED
                body = f"{text} · {glyph}"
            else:
                body = text
            lines.append(f"  {mark}{body}")
            nav_i += 1
        lines += [""] + [f" {f}" for f in self.footer]
        return "\n".join(lines) + "\n"

    def _render_submenu(self):
        actions = ("❯ 1. Reconnect\n  2. View tools" if self.submenu_ok
                   else "❯ 1. View tools\n  2. Reconnect")
        return (f"  {self.target_name}\n\n  Status: ✘ failed\n\n"
                f"  {actions}\n\n  Esc to go back\n")


# The real CC v2.1.186 menu layout (defect report 2026-06-27T1210): two group
# labels, an action row, and a disabled built-in interleave the servers, so the
# parser puts voicemode at index 3 but the cursor needs 5 Downs to reach it.
REAL_LAYOUT = [
    ("label",  "claude.ai"),
    ("nav",    "claude.ai Google Calendar · ✔ connected · 8 tools"),
    ("nav",    "claude.ai Notion · ✔ connected · 18 tools"),
    ("nav",    "→ Show unused connectors (1)"),
    ("label",  "Built-in MCPs (always available)"),
    ("nav",    "computer-use · ◯ disabled"),
    ("nav",    "plugin:taskmaster:taskmaster · ✔ connected · 13 tools"),
    ("target", "plugin:voicemode:voicemode"),
]

# A tidy menu where voicemode is one row down (parsed index == cursor index).
SIMPLE_LAYOUT = [
    ("nav",    "taskmaster · ✔ connected"),
    ("target", "voicemode"),
    ("nav",    "playwright · ✔ connected"),
]


@pytest.fixture
def in_tmux():
    with patch.dict("os.environ", {"TMUX": "/tmp/tmux-501/default,1,0", "TMUX_PANE": "%5"}):
        yield


@pytest.mark.unit
class TestReconnectDriver:
    def test_not_in_tmux(self):
        with patch.dict("os.environ", {}, clear=True):
            result = reconnect(pane=None, runner=FakeRunner([""]))
        assert result.exit_code == ExitCode.NOT_IN_TMUX
        assert result.outcome == "not-in-tmux"

    def test_already_connected_is_noop(self, in_tmux):
        runner = FakeRunner([load("connected")])
        result = reconnect(pane="%5", runner=runner, settle=0)
        assert result.exit_code == ExitCode.ALREADY_CONNECTED
        assert result.outcome == "already-connected"
        # No navigation / submenu interaction when already connected.
        assert runner.downs() == 0
        assert runner.enters() == 0
        assert result.reload_line  # still tells the agent how to reload

    def test_not_found(self, in_tmux):
        runner = FakeRunner([load("not_present")])
        result = reconnect(pane="%5", runner=runner, settle=0)
        assert result.exit_code == ExitCode.NOT_FOUND
        assert runner.downs() == 0

    def test_menu_did_not_open_fails_loud(self, in_tmux):
        runner = FakeRunner([load("not_a_menu")])
        result = reconnect(pane="%5", runner=runner, settle=0)
        assert result.exit_code == ExitCode.ERROR
        # Must not have blindly navigated into an unknown screen.
        assert runner.downs() == 0
        assert runner.enters() == 0

    def test_failed_then_reconnects(self, in_tmux):
        # open -> navigate by cursor -> submenu reconnect-first -> poll -> connected
        runner = CursorMenu(SIMPLE_LAYOUT, connect_after=1)
        result = reconnect(pane="%5", runner=runner, settle=0, poll_interval=1)
        assert result.exit_code == ExitCode.RECONNECTED
        assert result.outcome == "reconnected"
        assert runner.downs() == 1            # voicemode is one row down
        assert runner.enters() == 2           # submenu-enter + Reconnect
        assert ("/mcp", "Enter") in runner.sent
        assert ("Escape",) in runner.sent     # menu closed / returned to list
        assert result.reload_line == "ToolSearch select:mcp__voicemode__converse"

    def test_real_menu_navigates_by_cursor_not_parsed_index(self, in_tmux):
        # THE impl-002 regression test. On the real CC v2.1.186 menu voicemode
        # is parsed-index 3, but the cursor needs 5 Downs (group label + action
        # row + disabled built-in sit before it). Cursor-driven nav must reach
        # and reconnect it -- the old count-from-parsed-index code sent 3 Downs,
        # landed on `computer-use`, and failed loud without ever reconnecting.
        runner = CursorMenu(REAL_LAYOUT, connect_after=1)
        result = reconnect(pane="%5", runner=runner, settle=0, poll_interval=1, timeout=30)
        assert result.exit_code == ExitCode.RECONNECTED
        assert runner.downs() == 5            # by cursor -- NOT the parsed index (3)
        assert runner.enters() == 2           # submenu-enter + Reconnect
        assert result.reload_line == "ToolSearch select:mcp__plugin_voicemode_voicemode__converse"

    def test_failed_at_top_needs_no_downs(self, in_tmux):
        # voicemode is already the selected row when the menu opens -> 0 Downs.
        layout = [("target", "voicemode"), ("nav", "taskmaster · ✔ connected")]
        runner = CursorMenu(layout, connect_after=1)
        result = reconnect(pane="%5", runner=runner, settle=0, poll_interval=1)
        assert result.exit_code == ExitCode.RECONNECTED
        assert runner.downs() == 0

    def test_unexpected_submenu_fails_loud(self, in_tmux):
        # Reconnect is NOT the first action -> abort without pressing it.
        runner = CursorMenu(SIMPLE_LAYOUT, submenu_ok=False)
        result = reconnect(pane="%5", runner=runner, settle=0)
        assert result.exit_code == ExitCode.ERROR
        assert runner.downs() == 1           # still navigated onto voicemode...
        assert runner.enters() == 1          # ...opened submenu, but Reconnect NOT pressed

    def test_cursor_never_lands_fails_loud(self, in_tmux):
        # voicemode is present + failed, but the cursor can never reach it (Down
        # wedged / capture glitch). Must fail loud -- never press Enter on the
        # wrong row -- rather than acting on whatever is selected.
        class StuckCursor(CursorMenu):
            def send_keys(self, *keys):           # swallow Down: cursor stuck at 0
                self.sent.append(tuple(keys))
                if tuple(keys) == ("/mcp", "Enter"):
                    self.opened = True

        runner = StuckCursor(SIMPLE_LAYOUT)
        result = reconnect(pane="%5", runner=runner, settle=0)
        assert result.exit_code == ExitCode.ERROR
        assert "cursor" in result.message.lower()
        assert runner.enters() == 0          # never opened a submenu / hit Reconnect

    def test_timeout_when_never_connects(self, in_tmux):
        runner = CursorMenu(SIMPLE_LAYOUT, connect_after=10 ** 6)  # never connects
        result = reconnect(pane="%5", runner=runner, settle=0, timeout=10, poll_interval=2)
        assert result.exit_code == ExitCode.TIMEOUT
        assert result.outcome == "timeout"

    def test_dry_run_sends_no_keys(self, in_tmux):
        runner = FakeRunner([load("failed")])
        result = reconnect(pane="%5", runner=runner, dry_run=True)
        assert result.exit_code == ExitCode.RECONNECTED
        assert result.outcome == "dry-run"
        assert runner.sent == []             # nothing driven


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestReconnectCLI:
    def test_registered_on_main_cli(self):
        from voice_mode.cli import voice_mode_main_cli
        assert "reconnect" in voice_mode_main_cli.commands

    def test_dry_run_exit_and_output(self):
        from click.testing import CliRunner
        from voice_mode.reconnect import reconnect_command

        with patch.dict("os.environ", {"TMUX": "1", "TMUX_PANE": "%5"}):
            result = CliRunner().invoke(reconnect_command, ["--dry-run"])
        assert result.exit_code == ExitCode.RECONNECTED
        assert "RESULT: dry-run" in result.output
        assert "ToolSearch select:" in result.output

    def test_not_in_tmux_exit_code(self):
        from click.testing import CliRunner
        from voice_mode.reconnect import reconnect_command

        with patch.dict("os.environ", {}, clear=True):
            result = CliRunner().invoke(reconnect_command, [])
        assert result.exit_code == ExitCode.NOT_IN_TMUX
        assert "RESULT: not-in-tmux" in result.output
