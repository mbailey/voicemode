"""Tests for auto-focus tmux pane feature (VM-922)."""

import subprocess
from unittest.mock import patch, call


class TestIsTmux:
    """Test the is_tmux() helper function."""

    def test_returns_true_when_tmux_env_set(self):
        with patch.dict("os.environ", {"TMUX": "/tmp/tmux-501/default,12345,0"}):
            from voice_mode.tools.converse import is_tmux
            assert is_tmux() is True

    def test_returns_false_when_tmux_env_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            from voice_mode.tools.converse import is_tmux
            assert is_tmux() is False

    def test_returns_false_when_tmux_env_empty(self):
        with patch.dict("os.environ", {"TMUX": ""}):
            from voice_mode.tools.converse import is_tmux
            assert is_tmux() is False


class TestFocusTmuxPane:
    """Test the focus_tmux_pane() function."""

    def test_runs_select_pane_and_select_window(self):
        with patch.dict("os.environ", {"TMUX_PANE": "%5"}):
            with patch("subprocess.run") as mock_run:
                from voice_mode.tools.converse import focus_tmux_pane
                focus_tmux_pane()

                assert mock_run.call_count == 2
                mock_run.assert_any_call(
                    ["tmux", "select-pane", "-t", "%5"], capture_output=True
                )
                mock_run.assert_any_call(
                    ["tmux", "select-window", "-t", "%5"], capture_output=True
                )

    def test_noop_when_tmux_pane_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch("subprocess.run") as mock_run:
                from voice_mode.tools.converse import focus_tmux_pane
                focus_tmux_pane()

                mock_run.assert_not_called()

    def test_noop_when_tmux_pane_empty(self):
        with patch.dict("os.environ", {"TMUX_PANE": ""}):
            with patch("subprocess.run") as mock_run:
                from voice_mode.tools.converse import focus_tmux_pane
                focus_tmux_pane()

                mock_run.assert_not_called()

    def test_silent_when_tmux_binary_not_found(self):
        with patch.dict("os.environ", {"TMUX_PANE": "%5"}):
            with patch(
                "subprocess.run",
                side_effect=FileNotFoundError("tmux not found"),
            ):
                from voice_mode.tools.converse import focus_tmux_pane
                # Should not raise
                focus_tmux_pane()


class TestAutoFocusPaneConfig:
    """Test the AUTO_FOCUS_PANE config option."""

    def test_default_is_false(self):
        import os
        os.environ.pop("VOICEMODE_AUTO_FOCUS_PANE", None)
        from voice_mode.config import env_bool
        assert env_bool("VOICEMODE_AUTO_FOCUS_PANE", False) is False

    def test_enabled_when_set_true(self):
        with patch.dict("os.environ", {"VOICEMODE_AUTO_FOCUS_PANE": "true"}):
            from voice_mode.config import env_bool
            assert env_bool("VOICEMODE_AUTO_FOCUS_PANE", False) is True

    def test_enabled_with_various_truthy_values(self):
        from voice_mode.config import env_bool
        for value in ("true", "1", "yes", "on", "TRUE", "True"):
            with patch.dict("os.environ", {"VOICEMODE_AUTO_FOCUS_PANE": value}):
                assert env_bool("VOICEMODE_AUTO_FOCUS_PANE", False) is True, (
                    f"Expected True for value '{value}'"
                )

    def test_disabled_with_falsy_values(self):
        from voice_mode.config import env_bool
        for value in ("false", "0", "no", "off", ""):
            with patch.dict("os.environ", {"VOICEMODE_AUTO_FOCUS_PANE": value}):
                assert env_bool("VOICEMODE_AUTO_FOCUS_PANE", False) is False, (
                    f"Expected False for value '{value}'"
                )
