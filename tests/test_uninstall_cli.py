"""Unit tests for the top-level `voicemode uninstall` command (VM-1874, gh #497).

Mocks the three underlying `*_uninstall` tool functions and the
`subprocess.run` calls (claude mcp remove, claude plugin list, uv tool
uninstall) -- mirrors tests/test_clone_cli.py's CliRunner pattern. No live
service teardown happens in these tests: tests/conftest.py's
`isolate_home_directory` (autouse) redirects `Path.home()` so even the real
`voice_mode.tools.service.stop_service` / `disable_service` calls this
command makes for the 4th ("serve") service can never reach a developer's
real `~/Library/LaunchAgents` or `~/.config/systemd/user`, and
`block_dangerous_commands` (autouse) turns `launchctl`/`systemctl` into
no-ops regardless.

Covers the R10-R16 rework (Fable/max adversarial review,
reviews/2026-07-09T0224-impl-001/fable-design-review.md) on top of the
original R1-R5/R9 slice: truthful --remove-all-data (voice clones are NEVER
auto-deleted), the 4th "serve" service teardown, Claude Code plugin
detection, dual-scope MCP removal, non-zero exit on errors, skip-package-
removal-after-errors, and BASE_DIR test isolation hardening.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from voice_mode.cli import voice_mode_main_cli


@pytest.fixture
def runner():
    """Create a Click CliRunner."""
    return CliRunner()


@pytest.fixture
def base_dir(tmp_path):
    """Isolated BASE_DIR for uninstall tests.

    Deliberately NOT `tmp_path` itself and NOT nested under
    `tmp_path / "home"` -- tests/conftest.py's `isolate_home_directory`
    (autouse) creates `tmp_path / "home"` with its own
    Library/LaunchAgents, systemd, and `.voicemode` scaffolding for HOME
    isolation. If a test patched `voice_mode.config.BASE_DIR` to bare
    `tmp_path`, that scaffolding would land *inside* the fake BASE_DIR and
    show up as a spurious "leftover" entry in the --remove-all-data sweep
    and residual-footprint report (this bit impl-001's first draft, whose
    tests didn't enumerate BASE_DIR children).

    R16 hardening (Fable review Issue 9): the `patch("voice_mode.config.
    BASE_DIR", base_dir)` pattern below only works because `voicemode_uninstall`
    imports BASE_DIR *inside* the command body (cli.py) rather than at
    module scope -- if a future refactor hoists that import, the patch
    silently stops applying and a destructive call would hit the
    developer's REAL ~/.voicemode. The `is_relative_to` assertion here is
    a canary: it fails loudly (AssertionError) instead of destroying real
    data, the moment this fixture's own invariant is violated.
    """
    d = tmp_path / "voicemode_base"
    d.mkdir()
    assert d.is_relative_to(tmp_path)
    return d


def _ok_result(**extra):
    result = {"success": True, "removed_items": [], "errors": []}
    result.update(extra)
    return result


def _make_tool_mock(**return_kwargs):
    """Build an AsyncMock shaped like an @mcp.tool-decorated function.

    The CLI calls `getattr(fn, 'fn', fn)(...)` -- on the real tool object
    `.fn` is the plain coroutine. AsyncMock auto-creates a *different*
    AsyncMock for `.fn`, which would silently detach the configured
    return value from the one actually invoked. Point `.fn` back at the
    mock itself so `getattr(..., 'fn', ...)` calls the mock we configured.
    """
    mock = AsyncMock(return_value=_ok_result(**return_kwargs))
    mock.fn = mock
    return mock


def _completed(returncode=0, stdout="", stderr=""):
    class _Result:
        pass

    r = _Result()
    r.returncode = returncode
    r.stdout = stdout
    r.stderr = stderr
    return r


def _wrap(async_fn):
    """Wrap a plain async function in an AsyncMock-like passthrough with .fn."""
    mock = AsyncMock(side_effect=async_fn)
    mock.fn = mock
    return mock


def _no_op_run_side_effect(extra=None):
    """A `subprocess.run` side_effect covering every call this command makes:
    claude mcp remove (both scopes), claude plugin list, uv tool uninstall.
    `extra` optionally overrides/extends handling per test.
    """
    extra = extra or {}

    def _side_effect(args, **kwargs):
        for matcher, result in extra.items():
            if list(args[: len(matcher)]) == list(matcher):
                return result(args) if callable(result) else result
        if args[:2] == ["claude", "mcp"]:
            return _completed(returncode=0)
        if args[:2] == ["claude", "plugin"]:
            return _completed(returncode=0, stdout="")
        if args[:2] == ["uv", "tool"]:
            return _completed(returncode=0)
        raise AssertionError(f"unexpected subprocess call: {args}")

    return _side_effect


class TestUninstallHelp:
    """--help surfaces the documented flags (success criteria)."""

    def test_uninstall_help_lists_flags(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["uninstall", "--help"])
        assert result.exit_code == 0
        assert "-y, --yes" in result.output
        assert "--remove-models" in result.output
        assert "--remove-all-data" in result.output

    def test_uninstall_in_main_help(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["--help"])
        assert result.exit_code == 0
        assert "uninstall" in result.output

    def test_remove_all_data_help_does_not_overpromise_voice_removal(self, runner):
        """R10: help text must not claim --remove-all-data removes voice
        data it doesn't touch (Fable review Issue 1)."""
        result = runner.invoke(voice_mode_main_cli, ["uninstall", "--help"])
        assert result.exit_code == 0
        assert "voice clones" in result.output.lower()
        assert "never" in result.output.lower() or "except" in result.output.lower()


class TestUninstallConfirmation:
    """Safe-by-default: confirm unless -y/--yes."""

    @patch("voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall")
    @patch("voice_mode.tools.kokoro.uninstall.kokoro_uninstall")
    @patch("voice_mode.tools.whisper.uninstall.whisper_uninstall")
    def test_declines_without_yes_aborts(self, mock_whisper, mock_kokoro, mock_mlx, runner):
        result = runner.invoke(voice_mode_main_cli, ["uninstall"], input="n\n")
        assert result.exit_code != 0
        mock_whisper.assert_not_called()
        mock_kokoro.assert_not_called()
        mock_mlx.assert_not_called()

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/uv")
    @patch("voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall")
    @patch("voice_mode.tools.kokoro.uninstall.kokoro_uninstall")
    @patch("voice_mode.tools.whisper.uninstall.whisper_uninstall")
    def test_yes_flag_bypasses_prompt(
        self, mock_whisper, mock_kokoro, mock_mlx, mock_which, mock_run, runner, base_dir
    ):
        mock_whisper.fn = mock_whisper
        mock_kokoro.fn = mock_kokoro
        mock_mlx.fn = mock_mlx
        mock_whisper.return_value = _ok_result()
        mock_kokoro.return_value = _ok_result()
        mock_mlx.return_value = _ok_result()
        mock_run.side_effect = _no_op_run_side_effect()

        with patch("voice_mode.config.BASE_DIR", base_dir):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        mock_whisper.assert_called_once()
        mock_kokoro.assert_called_once()
        mock_mlx.assert_called_once()


class TestUninstallOrchestration:
    """Ordering, flag forwarding, config/voices handling, error collection."""

    def test_order_services_then_serve_then_mcp_then_package(self, runner, base_dir):
        calls = []

        async def whisper_side_effect(**kwargs):
            calls.append("whisper")
            return _ok_result()

        async def kokoro_side_effect(**kwargs):
            calls.append("kokoro")
            return _ok_result()

        async def mlx_side_effect(**kwargs):
            calls.append("mlx-audio")
            return _ok_result()

        async def stop_serve_side_effect(name):
            return "not running"

        async def disable_serve_side_effect(name):
            calls.append("serve")
            return "✅ VoiceMode service disabled and removed"

        def run_side_effect(args, **kwargs):
            if args[:2] == ["claude", "mcp"]:
                calls.append("claude-mcp-remove")
                return _completed(returncode=0)
            if args[:2] == ["claude", "plugin"]:
                return _completed(returncode=0, stdout="")
            if args[:2] == ["uv", "tool"]:
                calls.append("uv-tool-uninstall")
                return _completed(returncode=0)
            raise AssertionError(f"unexpected subprocess call: {args}")

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall",
            new=_wrap(whisper_side_effect),
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall",
            new=_wrap(kokoro_side_effect),
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall",
            new=_wrap(mlx_side_effect),
        ), patch(
            "voice_mode.tools.service.stop_service",
            new=AsyncMock(side_effect=stop_serve_side_effect),
        ), patch(
            "voice_mode.tools.service.disable_service",
            new=AsyncMock(side_effect=disable_serve_side_effect),
        ), patch(
            "subprocess.run", side_effect=run_side_effect
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        # Services first (order among the three matches call sites), then
        # the 4th "serve" service (R11), then MCP removal at BOTH scopes
        # (R13), then the package uninstall LAST (R14).
        assert calls[:3] == ["whisper", "kokoro", "mlx-audio"]
        assert calls[3] == "serve"
        assert calls[4] == "claude-mcp-remove"
        assert calls[5] == "claude-mcp-remove"  # user scope, then local scope
        assert calls[-1] == "uv-tool-uninstall"

    def test_flag_forwarding(self, runner, base_dir):
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=_no_op_run_side_effect()
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(
                voice_mode_main_cli, ["uninstall", "-y", "--remove-models", "--remove-all-data"]
            )

        assert result.exit_code == 0, result.output
        for mock in (mock_whisper, mock_kokoro, mock_mlx):
            mock.assert_called_once_with(remove_models=True, remove_all_data=True)

    def test_voices_preserved_by_default(self, runner, base_dir):
        voices_dir = base_dir / "voices"
        voices_dir.mkdir()
        (voices_dir / "profile.wav").write_bytes(b"data")

        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=_no_op_run_side_effect()
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert voices_dir.exists()
        assert "voice clones" in result.output.lower()

    def test_voices_never_removed_even_with_remove_all_data(self, runner, base_dir):
        """R10 (Fable review Issue 1, D1): voice clones are NEVER auto-deleted,
        even with --remove-all-data -- the old (buggy) behavior removed them
        and the help text lied about it. This replaces the pre-rework test
        that asserted the opposite."""
        voices_dir = base_dir / "voices"
        voices_dir.mkdir()
        (voices_dir / "profile.wav").write_bytes(b"data")
        (base_dir / "voices.json").write_text("{}")

        # Other BASE_DIR data that --remove-all-data SHOULD sweep.
        (base_dir / "logs").mkdir()
        (base_dir / "logs" / "events.jsonl").write_text("{}")
        (base_dir / "audio").mkdir()
        (base_dir / "audio" / "recording.wav").write_bytes(b"data")

        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=_no_op_run_side_effect()
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y", "--remove-all-data"])

        assert result.exit_code == 0, result.output
        assert voices_dir.exists()
        assert (base_dir / "voices.json").exists()
        assert not (base_dir / "logs").exists()
        assert not (base_dir / "audio").exists()

    def test_config_backed_up_not_deleted(self, runner, base_dir):
        """R10 (Fable review Issue 11, D1): config commonly holds secrets --
        back it up (rename to .uninstalled) rather than hard-deleting it."""
        (base_dir / "voicemode.env").write_text("OPENAI_API_KEY=sk-secret\n")
        (base_dir / ".voicemode.env").write_text("FOO=bar\n")

        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=_no_op_run_side_effect()
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert not (base_dir / "voicemode.env").exists()
        assert not (base_dir / ".voicemode.env").exists()
        assert (base_dir / "voicemode.env.uninstalled").read_text() == "OPENAI_API_KEY=sk-secret\n"
        assert (base_dir / ".voicemode.env.uninstalled").read_text() == "FOO=bar\n"

    def test_mcp_not_registered_is_tolerated(self, runner, base_dir):
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        def run_side_effect(args, **kwargs):
            if args[:2] == ["claude", "mcp"]:
                return _completed(returncode=1, stderr="No MCP server found with name: voicemode")
            if args[:2] == ["claude", "plugin"]:
                return _completed(returncode=0, stdout="")
            return _completed(returncode=0)

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=run_side_effect
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert "Errors:" not in result.output

    def test_service_error_collected_run_continues_but_exits_nonzero(self, runner, base_dir):
        """R14 (Fable review Issue 5/6): errors are collected (not raised --
        the run continues through the remaining steps), but the command now
        exits non-zero, and package removal is skipped so the user can
        re-run `uninstall` to finish the job."""
        mock_whisper = AsyncMock(side_effect=RuntimeError("boom"))
        mock_whisper.fn = mock_whisper
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=_no_op_run_side_effect()
        ) as mock_run, patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        # Errors are collected, not raised -- the rest of the run proceeds
        # (kokoro/mlx-audio/MCP removal all still happen)...
        mock_kokoro.assert_called_once()
        mock_mlx.assert_called_once()
        assert "Errors:" in result.output
        assert "boom" in result.output
        # ...but the exit code signals failure to scripts/agents (R14)...
        assert result.exit_code == 1, result.output
        # ...and package self-removal is skipped, not amputating the re-run
        # path (R14) -- `uv tool uninstall` must not have been invoked.
        assert "skipping package removal" in result.output.lower()
        for call in mock_run.call_args_list:
            args = call.args[0] if call.args else call.kwargs.get("args")
            assert args[:2] != ["uv", "tool"]

    def test_uv_tool_uninstall_absent_is_tolerated(self, runner, base_dir):
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        def run_side_effect(args, **kwargs):
            if args[:2] == ["uv", "tool"]:
                return _completed(returncode=1, stderr="error: package `voice-mode` is not installed")
            if args[:2] == ["claude", "plugin"]:
                return _completed(returncode=0, stdout="")
            return _completed(returncode=0)

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=run_side_effect
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert "Errors:" not in result.output

    def test_no_uv_on_path_skips_package_removal(self, runner, base_dir):
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=_no_op_run_side_effect()
        ) as mock_run, patch(
            "shutil.which", return_value=None
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        # subprocess.run should never be called for `uv tool uninstall` (uv
        # absent from PATH).
        for call in mock_run.call_args_list:
            args = call.args[0] if call.args else call.kwargs.get("args")
            assert args[:2] != ["uv", "tool"]


class TestUninstallServeTeardown:
    """R11 (Fable review Issue 2): the 4th service, "serve" (the voicemode
    HTTP MCP server), must be torn down before package removal -- otherwise
    an enabled launchd/systemd unit relaunches a deleted binary at login."""

    def test_serve_service_stopped_and_disabled(self, runner, base_dir):
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()
        mock_stop = AsyncMock(return_value="✅ VoiceMode stopped")
        mock_disable = AsyncMock(return_value="✅ VoiceMode service disabled and removed")

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "voice_mode.tools.service.stop_service", mock_stop
        ), patch(
            "voice_mode.tools.service.disable_service", mock_disable
        ), patch(
            "subprocess.run", side_effect=_no_op_run_side_effect()
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        mock_stop.assert_called_once_with("voicemode")
        mock_disable.assert_called_once_with("voicemode")
        assert "voicemode (serve) service uninstalled" in result.output

    def test_serve_install_dir_removed(self, runner, base_dir):
        serve_dir = base_dir / "services" / "voicemode"
        (serve_dir / "bin").mkdir(parents=True)
        (serve_dir / "bin" / "start-voicemode-serve.sh").write_text("#!/bin/sh\n")

        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "voice_mode.tools.service.stop_service", AsyncMock(return_value="not running")
        ), patch(
            "voice_mode.tools.service.disable_service", AsyncMock(return_value="not installed")
        ), patch(
            "subprocess.run", side_effect=_no_op_run_side_effect()
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert not serve_dir.exists()

    def test_serve_teardown_error_collected_not_raised(self, runner, base_dir):
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "voice_mode.tools.service.stop_service", AsyncMock(side_effect=RuntimeError("launchctl exploded"))
        ), patch(
            "voice_mode.tools.service.disable_service", AsyncMock(return_value="not installed")
        ), patch(
            "subprocess.run", side_effect=_no_op_run_side_effect()
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        # Collected (command doesn't crash) but surfaces as a failure exit.
        assert result.exit_code == 1, result.output
        assert "launchctl exploded" in result.output
        mock_kokoro.assert_called_once()
        mock_mlx.assert_called_once()


class TestUninstallMcpBothScopes:
    """R13 (Fable review Issue 4): `claude mcp add` without --scope user
    registers at the default/local scope -- removal must try both."""

    def test_mcp_removed_from_both_scopes(self, runner, base_dir):
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()
        scope_calls = []

        def run_side_effect(args, **kwargs):
            if args[:2] == ["claude", "mcp"]:
                scope_calls.append(list(args))
                return _completed(returncode=0)
            if args[:2] == ["claude", "plugin"]:
                return _completed(returncode=0, stdout="")
            return _completed(returncode=0)

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=run_side_effect
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert ["claude", "mcp", "remove", "voicemode", "--scope", "user"] in scope_calls
        assert ["claude", "mcp", "remove", "voicemode"] in scope_calls
        assert "user scope" in result.output
        assert "local scope" in result.output

    def test_mcp_local_scope_removed_when_user_scope_not_found(self, runner, base_dir):
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        def run_side_effect(args, **kwargs):
            if args[:2] == ["claude", "mcp"] and "--scope" in args:
                return _completed(returncode=1, stderr="No MCP server found with name: voicemode")
            if args[:2] == ["claude", "mcp"]:
                return _completed(returncode=0)
            if args[:2] == ["claude", "plugin"]:
                return _completed(returncode=0, stdout="")
            return _completed(returncode=0)

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=run_side_effect
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert "Errors:" not in result.output
        assert "local scope" in result.output

    def test_mcp_both_scopes_erroring_is_collected_not_raised(self, runner, base_dir):
        """A real failure (not "not found") at BOTH scopes must be
        collected into `errors` (surfacing as a non-zero exit, R14) rather
        than crashing the command or being silently swallowed."""
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        def run_side_effect(args, **kwargs):
            if args[:2] == ["claude", "mcp"]:
                return _completed(returncode=1, stderr="internal error: config corrupt")
            if args[:2] == ["claude", "plugin"]:
                return _completed(returncode=0, stdout="")
            return _completed(returncode=0)

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=run_side_effect
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 1, result.output
        assert result.output.count("config corrupt") == 2  # both scopes' errors surfaced
        assert "skipping package removal" in result.output.lower()


class TestUninstallPluginDetection:
    """R12 (Fable review Issue 3): `claude mcp remove` cannot unregister a
    Claude Code PLUGIN install -- detect it and tell the user how."""

    def test_plugin_detected_prints_manual_instruction(self, runner, base_dir):
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        def run_side_effect(args, **kwargs):
            if args[:2] == ["claude", "plugin"]:
                return _completed(returncode=0, stdout="voicemode  1.2.3  enabled\n")
            return _completed(returncode=0)

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=run_side_effect
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert "claude plugin uninstall voicemode" in result.output

    def test_plugin_not_detected_no_mention(self, runner, base_dir):
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=_no_op_run_side_effect()
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert "claude plugin uninstall" not in result.output

    def test_claude_cli_missing_skips_plugin_detection_without_crash(self, runner, base_dir):
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        def run_side_effect(args, **kwargs):
            if args[:2] == ["claude", "mcp"] or args[:2] == ["claude", "plugin"]:
                raise FileNotFoundError("claude not found")
            return _completed(returncode=0)

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=run_side_effect
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert "'claude' CLI not found" in result.output
        assert "claude plugin uninstall" not in result.output


class TestUninstallRemoveAllDataSweep:
    """R10 (Fable review Issue 1, D1): --remove-all-data sweeps every
    BASE_DIR entry EXCEPT voices/ + voices.json."""

    def test_sweeps_every_data_kind_except_voice_clones(self, runner, base_dir):
        for name in ("logs", "audio", "transcriptions", "cache", "models", "services"):
            d = base_dir / name
            d.mkdir()
            (d / "file.txt").write_text("data")
        voices_dir = base_dir / "voices"
        voices_dir.mkdir()
        (voices_dir / "profile.wav").write_bytes(b"data")
        (base_dir / "voices.json").write_text("{}")

        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=_no_op_run_side_effect()
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y", "--remove-all-data"])

        assert result.exit_code == 0, result.output
        for name in ("logs", "audio", "transcriptions", "cache", "models", "services"):
            assert not (base_dir / name).exists(), f"{name} should have been swept"
        assert voices_dir.exists()
        assert (base_dir / "voices.json").exists()

    def test_base_dir_removed_when_nothing_but_sweep_targets_remain(self, runner, base_dir):
        (base_dir / "logs").mkdir()
        (base_dir / "logs" / "x.log").write_text("x")
        # No voices/ or voices.json in this scenario.

        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=_no_op_run_side_effect()
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y", "--remove-all-data"])

        assert result.exit_code == 0, result.output
        assert not base_dir.exists()

    def test_base_dir_preserved_when_voice_clones_remain(self, runner, base_dir):
        (base_dir / "voices").mkdir()
        (base_dir / "voices" / "profile.wav").write_bytes(b"data")

        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        with patch(
            "voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_whisper
        ), patch(
            "voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_kokoro
        ), patch(
            "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall", mock_mlx
        ), patch(
            "subprocess.run", side_effect=_no_op_run_side_effect()
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y", "--remove-all-data"])

        assert result.exit_code == 0, result.output
        assert base_dir.exists()
        assert (base_dir / "voices").exists()
