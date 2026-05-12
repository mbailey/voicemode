"""Tests for `voicemode converse` positional MESSAGE argument (VM-1268).

The converse subcommand accepts the message in two forms:

  voicemode converse "Hello"          # positional (preferred)
  voicemode converse -m "Hello"       # flag (kept for backward compat)

Rules:
  * Either form alone -> message resolves to the provided text.
  * Multi-word positional args join with spaces.
  * Neither form -> the default greeting is used.
  * Both forms together -> `click.UsageError`, non-zero exit.
  * Use `--` to pass a message that starts with a dash (standard POSIX escape).

These tests target the CLI parser, not the underlying TTS/STT pipeline, so we
mock the inner async `converse` call and the dependency check.
"""

from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from voice_mode.cli import voice_mode_main_cli


DEFAULT_GREETING = "Hello! How can I help you today?"


@pytest.fixture
def patched_converse():
    """Patch deps + converse tool so the CLI command runs to completion
    without needing audio devices, and yield the AsyncMock that captures
    the `message` kwarg the CLI would have spoken.
    """
    async_mock = AsyncMock(return_value="Voice response: ack | provider=test")

    # check_component_dependencies is imported inside the command body, so we
    # patch at the source module.
    with patch(
        "voice_mode.utils.dependencies.checker.check_component_dependencies",
        return_value={"core": True},
    ), patch("voice_mode.tools.converse.converse") as mock_converse_tool:
        # `converse_fn.fn` is the unwrapped coroutine inside FastMCP. The CLI
        # uses getattr(converse_fn, 'fn', converse_fn) so providing `.fn` is
        # the cleanest path.
        mock_converse_tool.fn = async_mock
        yield async_mock


def _spoken_message(async_mock):
    """Return the `message` kwarg of the last call to the patched converse."""
    assert async_mock.await_count >= 1, "converse was never awaited"
    return async_mock.await_args.kwargs["message"]


class TestConversePositionalMessage:
    """Parser behaviour for the new positional MESSAGE argument."""

    def test_positional_single_word(self, patched_converse):
        runner = CliRunner()
        result = runner.invoke(
            voice_mode_main_cli,
            ["converse", "Hello", "--skip-stt"],
        )
        assert result.exit_code == 0, result.output
        assert _spoken_message(patched_converse) == "Hello"

    def test_positional_quoted_phrase(self, patched_converse):
        runner = CliRunner()
        result = runner.invoke(
            voice_mode_main_cli,
            ["converse", "Hello there", "--skip-stt"],
        )
        assert result.exit_code == 0, result.output
        assert _spoken_message(patched_converse) == "Hello there"

    def test_positional_multi_word_joins_with_space(self, patched_converse):
        """`converse hello world` (unquoted) joins into 'hello world'."""
        runner = CliRunner()
        result = runner.invoke(
            voice_mode_main_cli,
            ["converse", "hello", "world", "--skip-stt"],
        )
        assert result.exit_code == 0, result.output
        assert _spoken_message(patched_converse) == "hello world"

    def test_no_args_uses_default_greeting(self, patched_converse):
        runner = CliRunner()
        result = runner.invoke(
            voice_mode_main_cli,
            ["converse", "--skip-stt"],
        )
        assert result.exit_code == 0, result.output
        assert _spoken_message(patched_converse) == DEFAULT_GREETING

    def test_flag_form_still_works(self, patched_converse):
        """Backward compat: `-m "foo"` keeps working unchanged."""
        runner = CliRunner()
        result = runner.invoke(
            voice_mode_main_cli,
            ["converse", "-m", "via flag", "--skip-stt"],
        )
        assert result.exit_code == 0, result.output
        assert _spoken_message(patched_converse) == "via flag"

    def test_both_positional_and_flag_errors(self, patched_converse):
        """Refuse ambiguity: error, don't silently pick one."""
        runner = CliRunner()
        result = runner.invoke(
            voice_mode_main_cli,
            ["converse", "positional", "-m", "via flag", "--skip-stt"],
        )
        assert result.exit_code != 0, result.output
        assert "both" in result.output.lower()
        # Crucially, the underlying converse must NOT have been called.
        assert patched_converse.await_count == 0

    def test_double_dash_escapes_dash_prefixed_message(self, patched_converse):
        """`-- "-c rocks"` passes a literal message starting with `-`."""
        runner = CliRunner()
        result = runner.invoke(
            voice_mode_main_cli,
            ["converse", "--skip-stt", "--", "-c is short for continuous"],
        )
        assert result.exit_code == 0, result.output
        # The message should be the literal dash-prefixed text...
        assert _spoken_message(patched_converse) == "-c is short for continuous"
        # ...and continuous mode must NOT have been activated by it.
        kwargs = patched_converse.await_args.kwargs
        # `continuous` is consumed by the CLI wrapper, not forwarded to the
        # tool, so we infer it stayed False from the fact that we entered the
        # single-call branch (one await, not the continuous loop).
        assert patched_converse.await_count == 1

    def test_interspersed_positional_before_option(self, patched_converse):
        """`converse "hi" --voice nova` resolves message='hi' and voice='nova'."""
        runner = CliRunner()
        result = runner.invoke(
            voice_mode_main_cli,
            ["converse", "hi", "--voice", "nova", "--skip-stt"],
        )
        assert result.exit_code == 0, result.output
        assert _spoken_message(patched_converse) == "hi"
        assert patched_converse.await_args.kwargs["voice"] == "nova"

    def test_interspersed_option_before_positional(self, patched_converse):
        """`converse --voice nova "hi"` works identically to the reverse order."""
        runner = CliRunner()
        result = runner.invoke(
            voice_mode_main_cli,
            ["converse", "--voice", "nova", "hi", "--skip-stt"],
        )
        assert result.exit_code == 0, result.output
        assert _spoken_message(patched_converse) == "hi"
        assert patched_converse.await_args.kwargs["voice"] == "nova"


class TestConverseHelpSurface:
    """The help output should show the positional form (no underlying call)."""

    def test_help_shows_positional_metavar(self):
        runner = CliRunner()
        result = runner.invoke(voice_mode_main_cli, ["converse", "-h"])
        assert result.exit_code == 0
        assert "[MESSAGE]" in result.output

    def test_help_lists_positional_example_first(self):
        runner = CliRunner()
        result = runner.invoke(voice_mode_main_cli, ["converse", "-h"])
        assert result.exit_code == 0
        # The positional example should appear before the `-m` example.
        positional_idx = result.output.find('converse "Hello there!"')
        flag_idx = result.output.find('converse -m "Hello there!"')
        assert positional_idx != -1, "positional example missing from help"
        assert flag_idx != -1, "flag example missing from help (backward-compat reference)"
        assert positional_idx < flag_idx, (
            "positional example should come before the -m example in help"
        )
