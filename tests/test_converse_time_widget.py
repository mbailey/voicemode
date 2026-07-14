"""Tests for the converse() wall-clock time widget (VM-1961, do-002).

Design: a single `_build_widgets_segment()` helper builds a trailing
` | Widgets: time HH:MM:SS` segment, applied at the one choke point --
the thin `converse()` wrapper -- so every return path from
`_converse_core` gets it uniformly. Off by default (`VOICEMODE_TIME_IN_RESPONSE`,
mirrored as `voice_mode.config.TIME_IN_RESPONSE`), with a per-call
`time_in_response` override on `converse()` mirroring the existing
`metrics_level` shape.

These tests mock `_converse_core` directly rather than driving the full
audio pipeline (as test_converse_control_return.py does for the
control-stop path) -- the widget is applied strictly after the core
returns, so this is a clean, fast, and structurally-accurate boundary:
it also proves by construction that the widget text can never reach the
TTS/synthesis path, since the core (which owns all TTS calls) never sees
`time_in_response` at all -- it is a wrapper-only parameter, forwarded to
nothing.
"""

import re
from unittest.mock import patch

import pytest


def _converse_fn():
    """The underlying coroutine behind the converse MCP tool (unwraps FastMCP)."""
    from voice_mode.tools.converse import converse
    return getattr(converse, "fn", converse)


_TIME_RE = re.compile(r"\d{2}:\d{2}:\d{2}")


# --------------------------------------------------------------------------
# Unit: _build_widgets_segment
# --------------------------------------------------------------------------

class TestBuildWidgetsSegment:
    def test_disabled_returns_empty_string(self):
        from voice_mode.tools.converse import _build_widgets_segment

        assert _build_widgets_segment(False) == ""

    def test_enabled_returns_time_segment(self):
        from voice_mode.tools.converse import _build_widgets_segment

        segment = _build_widgets_segment(True)
        assert segment.startswith(" | Widgets: time ")
        assert _TIME_RE.search(segment)

    def test_enabled_time_is_current_wall_clock(self):
        """The widget's time is accurate to within a few seconds of `now`."""
        import time as time_mod
        from datetime import datetime

        from voice_mode.tools.converse import _build_widgets_segment

        before = datetime.now()
        segment = _build_widgets_segment(True)
        after = datetime.now()

        match = _TIME_RE.search(segment)
        assert match, f"no HH:MM:SS found in {segment!r}"
        widget_time = match.group(0)

        # Compare against both boundary timestamps formatted the same way --
        # tolerant of a seconds-boundary tick during the call.
        assert widget_time in (
            before.strftime("%H:%M:%S"),
            after.strftime("%H:%M:%S"),
        )


# --------------------------------------------------------------------------
# Integration: converse() wrapper applies the widget uniformly
# --------------------------------------------------------------------------

async def _fake_core_ok(**_kwargs):
    return "Spoken successfully | Timing: play 0.3s"


async def _fake_core_error(**_kwargs):
    return "❌ Error: something went wrong"


class TestConverseWrapperWidgetToggle:
    @pytest.mark.asyncio
    async def test_default_off_output_unchanged(self):
        """Default (no env, no per-call override) -- output byte-identical to pre-widget."""
        with patch("voice_mode.tools.converse._converse_core", new=_fake_core_ok):
            with patch("voice_mode.tools.converse.TIME_IN_RESPONSE", False):
                result = await _converse_fn()(message="hi", wait_for_response=False)

        assert result == "Spoken successfully | Timing: play 0.3s"
        assert "Widgets:" not in result

    @pytest.mark.asyncio
    async def test_config_default_on_adds_widget(self):
        """VOICEMODE_TIME_IN_RESPONSE=true (config global on) -- widget appended."""
        with patch("voice_mode.tools.converse._converse_core", new=_fake_core_ok):
            with patch("voice_mode.tools.converse.TIME_IN_RESPONSE", True):
                result = await _converse_fn()(message="hi", wait_for_response=False)

        assert result.startswith("Spoken successfully | Timing: play 0.3s | Widgets: time ")
        assert _TIME_RE.search(result)

    @pytest.mark.asyncio
    async def test_per_call_true_overrides_config_off(self):
        with patch("voice_mode.tools.converse._converse_core", new=_fake_core_ok):
            with patch("voice_mode.tools.converse.TIME_IN_RESPONSE", False):
                result = await _converse_fn()(
                    message="hi", wait_for_response=False, time_in_response=True
                )

        assert "Widgets: time" in result
        assert _TIME_RE.search(result)

    @pytest.mark.asyncio
    async def test_per_call_false_overrides_config_on(self):
        with patch("voice_mode.tools.converse._converse_core", new=_fake_core_ok):
            with patch("voice_mode.tools.converse.TIME_IN_RESPONSE", True):
                result = await _converse_fn()(
                    message="hi", wait_for_response=False, time_in_response=False
                )

        assert result == "Spoken successfully | Timing: play 0.3s"
        assert "Widgets:" not in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize("truthy_str", ["true", "True", "1", "yes", "on"])
    async def test_per_call_string_true_coerced(self, truthy_str):
        with patch("voice_mode.tools.converse._converse_core", new=_fake_core_ok):
            with patch("voice_mode.tools.converse.TIME_IN_RESPONSE", False):
                result = await _converse_fn()(
                    message="hi", wait_for_response=False, time_in_response=truthy_str
                )

        assert "Widgets: time" in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize("falsy_str", ["false", "False", "0", "no", "off", "garbage"])
    async def test_per_call_string_false_coerced(self, falsy_str):
        with patch("voice_mode.tools.converse._converse_core", new=_fake_core_ok):
            with patch("voice_mode.tools.converse.TIME_IN_RESPONSE", True):
                result = await _converse_fn()(
                    message="hi", wait_for_response=False, time_in_response=falsy_str
                )

        assert "Widgets:" not in result

    @pytest.mark.asyncio
    async def test_error_path_returns_carry_widget_too(self):
        """Uniformity: error-path returns get the widget too when enabled (README notes #2)."""
        with patch("voice_mode.tools.converse._converse_core", new=_fake_core_error):
            with patch("voice_mode.tools.converse.TIME_IN_RESPONSE", True):
                result = await _converse_fn()(message="hi", wait_for_response=False)

        assert result.startswith("❌ Error: something went wrong | Widgets: time ")

    @pytest.mark.asyncio
    async def test_error_path_default_off_unaffected(self):
        with patch("voice_mode.tools.converse._converse_core", new=_fake_core_error):
            with patch("voice_mode.tools.converse.TIME_IN_RESPONSE", False):
                result = await _converse_fn()(message="hi", wait_for_response=False)

        assert result == "❌ Error: something went wrong"


# --------------------------------------------------------------------------
# Structural: the widget can never reach the TTS/synthesis path
# --------------------------------------------------------------------------

class TestWidgetNeverReachesTTS:
    @pytest.mark.asyncio
    async def test_time_in_response_not_forwarded_to_core(self):
        """The core never receives `time_in_response` -- it can't leak into TTS.

        `_converse_core` (which owns every text_to_speech_with_failover call)
        has no `time_in_response` parameter at all (see the signature-parity
        test), and the wrapper's forwarding call doesn't pass it either --
        the widget is appended to the wrapper's *return value* only, strictly
        after the core (and therefore all TTS synthesis) has already run.
        """
        captured_kwargs = {}

        async def _capture_core(**kwargs):
            captured_kwargs.update(kwargs)
            return "Spoken successfully | Timing: play 0.3s"

        with patch("voice_mode.tools.converse._converse_core", new=_capture_core):
            with patch("voice_mode.tools.converse.TIME_IN_RESPONSE", True):
                await _converse_fn()(
                    message="hi", wait_for_response=False, time_in_response=True
                )

        assert "time_in_response" not in captured_kwargs

    def test_core_has_no_time_in_response_parameter(self):
        import inspect
        from voice_mode.tools.converse import _converse_core

        assert "time_in_response" not in inspect.signature(_converse_core).parameters
