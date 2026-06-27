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
        # open -> failed list ; enter submenu -> reconnect first ; poll -> connected
        runner = FakeRunner([
            load("failed"),          # initial list capture
            load("submenu_failed"),  # submenu check
            load("failed"),          # poll #1 still failed
            load("connected"),       # poll #2 connected
        ])
        result = reconnect(pane="%5", runner=runner, settle=0, poll_interval=1)
        assert result.exit_code == ExitCode.RECONNECTED
        assert result.outcome == "reconnected"
        assert runner.downs() == 1            # voicemode is one row down in failed.txt
        assert runner.enters() == 2           # submenu-enter + Reconnect
        assert ("/mcp", "Enter") in runner.sent
        assert ("Escape",) in runner.sent     # menu closed / returned to list
        assert result.reload_line == "ToolSearch select:mcp__voicemode__converse"

    def test_failed_deep_sends_correct_down_count(self, in_tmux):
        runner = FakeRunner([
            load("deep_in_list"),
            load("submenu_failed"),
            load("connected"),
        ])
        result = reconnect(pane="%5", runner=runner, settle=0, poll_interval=1)
        assert result.exit_code == ExitCode.RECONNECTED
        assert runner.downs() == 5            # text-located, five rows deep

    def test_unexpected_submenu_fails_loud(self, in_tmux):
        # Reconnect is NOT the first action -> abort without pressing it.
        runner = FakeRunner([
            load("failed"),
            load("submenu_connected"),   # View tools is first
        ])
        result = reconnect(pane="%5", runner=runner, settle=0)
        assert result.exit_code == ExitCode.ERROR
        assert runner.enters() == 1          # only the submenu-enter; Reconnect NOT pressed

    def test_timeout_when_never_connects(self, in_tmux):
        runner = FakeRunner([
            load("failed"),          # initial list
            load("submenu_failed"),  # submenu
            load("failed"),          # every poll stays failed (repeats forever)
        ])
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
