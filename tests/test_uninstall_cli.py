"""Unit tests for the top-level `voicemode uninstall` command (VM-1874, gh #497).

Mocks the three underlying `*_uninstall` tool functions and the
`subprocess.run` calls (claude mcp remove, uv tool uninstall) -- mirrors
tests/test_clone_cli.py's CliRunner pattern. No live service teardown
happens in these tests.
"""

from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from voice_mode.cli import voice_mode_main_cli


@pytest.fixture
def runner():
    """Create a Click CliRunner."""
    return CliRunner()


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
        self, mock_whisper, mock_kokoro, mock_mlx, mock_which, mock_run, runner, tmp_path
    ):
        mock_whisper.fn = mock_whisper
        mock_kokoro.fn = mock_kokoro
        mock_mlx.fn = mock_mlx
        mock_whisper.return_value = _ok_result()
        mock_kokoro.return_value = _ok_result()
        mock_mlx.return_value = _ok_result()
        mock_run.return_value = _completed(returncode=0)

        with patch("voice_mode.config.BASE_DIR", tmp_path):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        mock_whisper.assert_called_once()
        mock_kokoro.assert_called_once()
        mock_mlx.assert_called_once()


class TestUninstallOrchestration:
    """Ordering, flag forwarding, config/voices handling, error collection."""

    def _patched(self):
        """Return a stack of the standard patches used by most tests."""
        return (
            patch("voice_mode.tools.whisper.uninstall.whisper_uninstall"),
            patch("voice_mode.tools.kokoro.uninstall.kokoro_uninstall"),
            patch("voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall"),
            patch("subprocess.run"),
            patch("shutil.which", return_value="/usr/bin/uv"),
        )

    def test_order_services_then_mcp_then_config_then_package(self, runner, tmp_path):
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

        def run_side_effect(args, **kwargs):
            if args[:2] == ["claude", "mcp"]:
                calls.append("claude-mcp-remove")
                return _completed(returncode=0)
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
            "subprocess.run", side_effect=run_side_effect
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", tmp_path
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        # Services first (order among the three matches call sites), then
        # MCP removal, then the package uninstall LAST.
        assert calls[:3] == ["whisper", "kokoro", "mlx-audio"]
        assert calls[3] == "claude-mcp-remove"
        assert calls[-1] == "uv-tool-uninstall"

    def test_flag_forwarding(self, runner, tmp_path):
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
            "subprocess.run", return_value=_completed(returncode=0)
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", tmp_path
        ):
            result = runner.invoke(
                voice_mode_main_cli, ["uninstall", "-y", "--remove-models", "--remove-all-data"]
            )

        assert result.exit_code == 0, result.output
        for mock in (mock_whisper, mock_kokoro, mock_mlx):
            mock.assert_called_once_with(remove_models=True, remove_all_data=True)

    def test_voices_preserved_by_default(self, runner, tmp_path):
        voices_dir = tmp_path / "voices"
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
            "subprocess.run", return_value=_completed(returncode=0)
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", tmp_path
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert voices_dir.exists()
        assert "voices" in result.output.lower()

    def test_voices_removed_with_remove_all_data(self, runner, tmp_path):
        voices_dir = tmp_path / "voices"
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
            "subprocess.run", return_value=_completed(returncode=0)
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", tmp_path
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y", "--remove-all-data"])

        assert result.exit_code == 0, result.output
        assert not voices_dir.exists()

    def test_config_files_removed(self, runner, tmp_path):
        (tmp_path / "voicemode.env").write_text("FOO=bar\n")
        (tmp_path / ".voicemode.env").write_text("FOO=bar\n")

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
            "subprocess.run", return_value=_completed(returncode=0)
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", tmp_path
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert not (tmp_path / "voicemode.env").exists()
        assert not (tmp_path / ".voicemode.env").exists()

    def test_mcp_not_registered_is_tolerated(self, runner, tmp_path):
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        def run_side_effect(args, **kwargs):
            if args[:2] == ["claude", "mcp"]:
                return _completed(returncode=1, stderr="No MCP server found with name: voicemode")
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
            "voice_mode.config.BASE_DIR", tmp_path
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert "Errors:" not in result.output

    def test_service_error_collected_and_run_continues(self, runner, tmp_path):
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
            "subprocess.run", return_value=_completed(returncode=0)
        ), patch(
            "shutil.which", return_value="/usr/bin/uv"
        ), patch(
            "voice_mode.config.BASE_DIR", tmp_path
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        # Errors are collected, not raised -- the rest of the run proceeds.
        assert result.exit_code == 0, result.output
        mock_kokoro.assert_called_once()
        mock_mlx.assert_called_once()
        assert "Errors:" in result.output
        assert "boom" in result.output

    def test_uv_tool_uninstall_absent_is_tolerated(self, runner, tmp_path):
        mock_whisper = _make_tool_mock()
        mock_kokoro = _make_tool_mock()
        mock_mlx = _make_tool_mock()

        def run_side_effect(args, **kwargs):
            if args[:2] == ["uv", "tool"]:
                return _completed(returncode=1, stderr="error: package `voice-mode` is not installed")
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
            "voice_mode.config.BASE_DIR", tmp_path
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        assert "Errors:" not in result.output

    def test_no_uv_on_path_skips_package_removal(self, runner, tmp_path):
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
            "subprocess.run", return_value=_completed(returncode=0)
        ) as mock_run, patch(
            "shutil.which", return_value=None
        ), patch(
            "voice_mode.config.BASE_DIR", tmp_path
        ):
            result = runner.invoke(voice_mode_main_cli, ["uninstall", "-y"])

        assert result.exit_code == 0, result.output
        # subprocess.run should only be called for `claude mcp remove`, not
        # for `uv tool uninstall` (uv absent from PATH).
        for call in mock_run.call_args_list:
            args = call.args[0] if call.args else call.kwargs.get("args")
            assert args[:2] != ["uv", "tool"]


def _wrap(async_fn):
    """Wrap a plain async function in an AsyncMock-like passthrough with .fn."""
    mock = AsyncMock(side_effect=async_fn)
    mock.fn = mock
    return mock
