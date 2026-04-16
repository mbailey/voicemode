"""Tests for auto-focus tmux pane feature (VM-922)."""

from unittest.mock import patch, MagicMock


def _mk_run(display_session="worker", clients_on_session="", all_clients=""):
    """Build a subprocess.run side_effect that returns scripted results by argv.

    - select-pane / select-window: rc=0, no stdout needed
    - display-message: returns the session name
    - list-clients -t <session>: stdout lists clients already on that session
    - list-clients -F ...: stdout lists all clients with flags
    - switch-client: rc=0
    """
    def fake_run(argv, *_args, **_kwargs):
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        if not isinstance(argv, list) or len(argv) < 2 or argv[0] != "tmux":
            return result
        sub = argv[1]
        if sub == "display-message":
            result.stdout = display_session + "\n"
        elif sub == "list-clients":
            # "-t <session>" form includes "-t" at index 2
            if "-t" in argv:
                result.stdout = clients_on_session
            else:
                result.stdout = all_clients
        return result
    return fake_run


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

    def test_selects_pane_and_window(self):
        """select-pane and select-window always run when TMUX_PANE is set."""
        with patch.dict("os.environ", {"TMUX_PANE": "%5"}, clear=False):
            with patch("subprocess.run", side_effect=_mk_run(clients_on_session="/dev/ttys001\n")) as mock_run:
                from voice_mode.tools.converse import focus_tmux_pane
                focus_tmux_pane()

                mock_run.assert_any_call(
                    ["tmux", "select-pane", "-t", "%5"], capture_output=True
                )
                mock_run.assert_any_call(
                    ["tmux", "select-window", "-t", "%5"], capture_output=True
                )

    def test_skips_switch_client_when_session_already_visible(self):
        """If a client is already attached to the agent's session, don't steal focus."""
        with patch.dict("os.environ", {"TMUX_PANE": "%5"}, clear=False):
            with patch("subprocess.run", side_effect=_mk_run(
                display_session="worker",
                clients_on_session="/dev/ttys003\n",
            )) as mock_run:
                from voice_mode.tools.converse import focus_tmux_pane
                focus_tmux_pane()

                # No switch-client call should have happened
                for c in mock_run.call_args_list:
                    argv = c.args[0]
                    assert argv[:2] != ["tmux", "switch-client"], \
                        "switch-client should be skipped when session is already attached"

    def test_switches_focused_client_when_session_unattached(self):
        """If nothing is showing the agent's session, switch the focused client."""
        with patch.dict("os.environ", {"TMUX_PANE": "%5"}, clear=False):
            with patch("subprocess.run", side_effect=_mk_run(
                display_session="worker",
                clients_on_session="",
                all_clients="/dev/ttys000 (detached)\n/dev/ttys004 (focused)\n",
            )) as mock_run:
                from voice_mode.tools.converse import focus_tmux_pane
                focus_tmux_pane()

                mock_run.assert_any_call(
                    ["tmux", "switch-client", "-c", "/dev/ttys004", "-t", "worker"],
                    capture_output=True,
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

    def test_respects_focus_hold_sentinel(self):
        """When the focus-hold sentinel is active, focus is suppressed entirely."""
        with patch.dict("os.environ", {"TMUX_PANE": "%5"}, clear=False):
            with patch("voice_mode.tools.converse._is_focus_held", return_value=True):
                with patch("subprocess.run") as mock_run:
                    from voice_mode.tools.converse import focus_tmux_pane
                    focus_tmux_pane()

                    mock_run.assert_not_called()


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
