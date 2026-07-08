"""Unit tests for `voicemode service uninstall <name>` (VM-1874 D2/R15).

Fable/max adversarial review (reviews/2026-07-09T0224-impl-001/
fable-design-review.md, Issue 7) found the deprecation strings at
cli.py:1161 (and the top-level `voicemode uninstall` docstring) already
pointed users at `voicemode service uninstall <name>` -- a command that
did not exist. This adds the thin wrapper subcommands (whisper/kokoro/
mlx-audio via the existing `.fn` idiom, voicemode/"serve" via
`_teardown_serve_service`), resolving the dangling pointer.
"""

from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from voice_mode.cli import voice_mode_main_cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def base_dir(tmp_path):
    d = tmp_path / "voicemode_base"
    d.mkdir()
    return d


def _ok_result(**extra):
    result = {"success": True, "removed_items": [], "errors": []}
    result.update(extra)
    return result


def _make_tool_mock(**return_kwargs):
    mock = AsyncMock(return_value=_ok_result(**return_kwargs))
    mock.fn = mock
    return mock


class TestServiceUninstallRegistration:
    def test_uninstall_listed_in_service_group_help(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["service", "--help"])
        assert result.exit_code == 0
        assert "uninstall" in result.output

    def test_uninstall_help_lists_flags(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["service", "uninstall", "--help"])
        assert result.exit_code == 0
        assert "--remove-models" in result.output
        assert "--remove-all-data" in result.output
        assert "-y, --yes" in result.output

    def test_rejects_unknown_service(self, runner):
        result = runner.invoke(voice_mode_main_cli, ["service", "uninstall", "nope", "-y"])
        assert result.exit_code != 0  # click.Choice rejects it before the body runs


class TestServiceUninstallWhisperKokoroMlx:
    @pytest.mark.parametrize(
        "service_name,module_path",
        [
            ("whisper", "voice_mode.tools.whisper.uninstall.whisper_uninstall"),
            ("kokoro", "voice_mode.tools.kokoro.uninstall.kokoro_uninstall"),
            ("mlx-audio", "voice_mode.tools.mlx_audio.uninstall.mlx_audio_uninstall"),
        ],
    )
    def test_calls_the_matching_uninstall_fn(self, runner, service_name, module_path):
        mock_fn = _make_tool_mock()
        with patch(module_path, mock_fn):
            result = runner.invoke(
                voice_mode_main_cli, ["service", "uninstall", service_name, "-y"]
            )
        assert result.exit_code == 0, result.output
        mock_fn.assert_called_once_with(remove_models=False, remove_all_data=False)
        assert "uninstalled successfully" in result.output.lower()

    def test_forwards_flags(self, runner):
        mock_fn = _make_tool_mock()
        with patch("voice_mode.tools.kokoro.uninstall.kokoro_uninstall", mock_fn):
            result = runner.invoke(
                voice_mode_main_cli,
                ["service", "uninstall", "kokoro", "-y", "--remove-models", "--remove-all-data"],
            )
        assert result.exit_code == 0, result.output
        mock_fn.assert_called_once_with(remove_models=True, remove_all_data=True)

    def test_reports_errors_without_crashing(self, runner):
        mock_fn = _make_tool_mock(success=False, errors=["boom"])
        with patch("voice_mode.tools.whisper.uninstall.whisper_uninstall", mock_fn):
            result = runner.invoke(voice_mode_main_cli, ["service", "uninstall", "whisper", "-y"])
        assert result.exit_code == 0, result.output
        assert "boom" in result.output


class TestServiceUninstallVoicemode:
    """The 4th service ("voicemode"/"serve") has no `*_uninstall` tool fn --
    it goes through the shared `_teardown_serve_service` helper instead
    (same one `voicemode uninstall` R11 uses)."""

    def test_uninstalls_serve_via_stop_and_disable(self, runner, base_dir):
        mock_stop = AsyncMock(return_value="✅ VoiceMode stopped")
        mock_disable = AsyncMock(return_value="✅ VoiceMode service disabled and removed")

        with patch(
            "voice_mode.tools.service.stop_service", mock_stop
        ), patch(
            "voice_mode.tools.service.disable_service", mock_disable
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["service", "uninstall", "voicemode", "-y"])

        assert result.exit_code == 0, result.output
        mock_stop.assert_called_once_with("voicemode")
        mock_disable.assert_called_once_with("voicemode")
        assert "uninstalled successfully" in result.output.lower()

    def test_removes_serve_install_dir(self, runner, base_dir):
        serve_dir = base_dir / "services" / "voicemode"
        (serve_dir / "bin").mkdir(parents=True)
        (serve_dir / "bin" / "start-voicemode-serve.sh").write_text("#!/bin/sh\n")

        with patch(
            "voice_mode.tools.service.stop_service", AsyncMock(return_value="not running")
        ), patch(
            "voice_mode.tools.service.disable_service", AsyncMock(return_value="not installed")
        ), patch(
            "voice_mode.config.BASE_DIR", base_dir
        ):
            result = runner.invoke(voice_mode_main_cli, ["service", "uninstall", "voicemode", "-y"])

        assert result.exit_code == 0, result.output
        assert not serve_dir.exists()
