"""Tests for the soundfonts CLI commands.

Focus: ``_hooks_installed()`` hook-detection (VM-1338 / GH-313).

The original bug: ``_hooks_installed()`` read ``entry.get('command')`` at the
*matcher* level, but Claude Code nests the command one level deeper at
``hooks.<Event>[].hooks[].command``. The matcher-level entry has no ``command``
key, so the check always returned False even for correctly-installed hooks —
``voicemode soundfonts status`` reported "Hooks: not installed" right after a
successful ``voicemode claude hooks add``.

The fix reuses ``is_voicemode_hook()`` from ``claude.py`` (single source of
truth) for the nested traversal, and additionally treats an enabled
``voicemode@*`` plugin (recorded in the ``enabledPlugins`` map of the same
settings.json) as installed.
"""

import json
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from voice_mode.cli_commands.soundfonts import _hooks_installed, soundfonts


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def fake_home(tmp_path):
    """A fake home directory with an empty ``.claude`` dir.

    Returns the home Path; write ``<home>/.claude/settings.json`` per-test.
    """
    claude_dir = tmp_path / '.claude'
    claude_dir.mkdir()
    return tmp_path


def _write_settings(home, settings):
    """Write a settings dict to ``<home>/.claude/settings.json``."""
    (home / '.claude' / 'settings.json').write_text(json.dumps(settings, indent=2))


def _hooks_installed_with_home(home):
    """Call ``_hooks_installed()`` with ``Path.home()`` patched to ``home``."""
    with patch('voice_mode.cli_commands.soundfonts.Path.home', return_value=home):
        return _hooks_installed()


# Realistic Claude Code settings.json with VoiceMode hooks nested the way the
# `voicemode claude hooks add` command actually writes them. The command lives
# at hooks.<Event>[].hooks[].command — NOT at the matcher level. This exact
# structure is what the GH-313 bug missed.
NESTED_VOICEMODE_SETTINGS = {
    "hooks": {
        "PostToolUse": [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": "/Users/me/.voicemode/bin/voicemode-hook-receiver || true",
                    }
                ],
            }
        ],
        "Stop": [
            {
                "matcher": "*",
                "hooks": [
                    {
                        "type": "command",
                        "command": "/Users/me/.voicemode/bin/voicemode-hook-receiver || true",
                    }
                ],
            }
        ],
    }
}


class TestHooksInstalledSettingsJson:
    """Detection of hooks written into ~/.claude/settings.json."""

    def test_nested_voicemode_hook_detected(self, fake_home):
        """Fixture A (the GH-313 regression): realistic nested settings.json
        with a voicemode-hook-receiver command must be detected as installed.

        This is the case the old matcher-level check always missed.
        """
        _write_settings(fake_home, NESTED_VOICEMODE_SETTINGS)
        assert _hooks_installed_with_home(fake_home) is True

    def test_no_voicemode_hooks_and_no_plugins(self, fake_home):
        """Fixture B: settings.json with foreign hooks and no enabledPlugins
        must report not installed."""
        _write_settings(fake_home, {
            "hooks": {
                "PostToolUse": [
                    {
                        "matcher": "*",
                        "hooks": [
                            {"type": "command", "command": "/usr/bin/some-other-tool"}
                        ],
                    }
                ]
            }
        })
        assert _hooks_installed_with_home(fake_home) is False

    def test_matcher_level_command_is_not_mistaken_for_a_hook(self, fake_home):
        """A command string sitting at the matcher level (the place the old code
        wrongly looked) must NOT be detected — only the nested handler counts.

        Guards against a regression to the original buggy detection shape.
        """
        _write_settings(fake_home, {
            "hooks": {
                "PostToolUse": [
                    {"matcher": "*", "command": "voicemode-hook-receiver", "hooks": []}
                ]
            }
        })
        assert _hooks_installed_with_home(fake_home) is False

    def test_empty_settings(self, fake_home):
        """settings.json with no hooks key → not installed."""
        _write_settings(fake_home, {})
        assert _hooks_installed_with_home(fake_home) is False

    def test_no_settings_file(self, fake_home):
        """No settings.json at all → not installed (no crash)."""
        # fake_home/.claude exists but settings.json was never written
        assert _hooks_installed_with_home(fake_home) is False

    def test_malformed_settings_json(self, fake_home):
        """Malformed JSON → not installed (robustness, not a crash)."""
        (fake_home / '.claude' / 'settings.json').write_text("{ this is not json")
        assert _hooks_installed_with_home(fake_home) is False


class TestHooksInstalledPlugin:
    """Detection of plugin-provided hooks via the enabledPlugins map."""

    def test_enabled_voicemode_plugin_detected(self, fake_home):
        """Fixture C: no nested hooks, but an enabled voicemode@skillbox plugin
        → installed (plugin install mode)."""
        _write_settings(fake_home, {"enabledPlugins": {"voicemode@skillbox": True}})
        assert _hooks_installed_with_home(fake_home) is True

    def test_disabled_voicemode_plugin_not_detected(self, fake_home):
        """Fixture D: enabledPlugins has voicemode@skillbox set to false
        → not installed."""
        _write_settings(fake_home, {"enabledPlugins": {"voicemode@skillbox": False}})
        assert _hooks_installed_with_home(fake_home) is False

    def test_plugin_match_is_marketplace_agnostic(self, fake_home):
        """Matching is on the 'voicemode@' prefix, not a hardcoded marketplace,
        so voicemode from any marketplace counts."""
        _write_settings(fake_home, {"enabledPlugins": {"voicemode@othermarket": True}})
        assert _hooks_installed_with_home(fake_home) is True

    def test_other_plugin_not_mistaken_for_voicemode(self, fake_home):
        """An unrelated enabled plugin must NOT count as VoiceMode hooks."""
        _write_settings(fake_home, {"enabledPlugins": {"someother@skillbox": True}})
        assert _hooks_installed_with_home(fake_home) is False

    def test_prefix_match_is_precise(self, fake_home):
        """A plugin whose name merely contains 'voicemode' but does not start
        with the 'voicemode@' prefix must not match."""
        _write_settings(fake_home, {
            "enabledPlugins": {
                "notvoicemode@skillbox": True,
                "voicemode-extras@skillbox": True,
            }
        })
        assert _hooks_installed_with_home(fake_home) is False

    def test_settings_hook_takes_precedence_when_both_present(self, fake_home):
        """Both a nested settings.json hook AND an enabled plugin → installed."""
        settings = dict(NESTED_VOICEMODE_SETTINGS)
        settings["enabledPlugins"] = {"voicemode@skillbox": True}
        _write_settings(fake_home, settings)
        assert _hooks_installed_with_home(fake_home) is True


class TestSoundfontsStatusReportsInstalled:
    """End-to-end: `voicemode soundfonts status` reports installed correctly."""

    def test_status_reports_hooks_installed_with_nested_settings(self, runner, fake_home):
        """After `voicemode claude hooks add` (nested settings.json), the status
        command must print 'Hooks: installed', not 'Hooks: not installed'."""
        _write_settings(fake_home, NESTED_VOICEMODE_SETTINGS)
        with patch('voice_mode.cli_commands.soundfonts.Path.home', return_value=fake_home):
            result = runner.invoke(soundfonts, ['status'])
        assert result.exit_code == 0
        assert 'Hooks: installed' in result.output
        assert 'Hooks: not installed' not in result.output

    def test_status_reports_hooks_installed_with_plugin(self, runner, fake_home):
        """Plugin install mode: status reports installed from enabledPlugins."""
        _write_settings(fake_home, {"enabledPlugins": {"voicemode@skillbox": True}})
        with patch('voice_mode.cli_commands.soundfonts.Path.home', return_value=fake_home):
            result = runner.invoke(soundfonts, ['status'])
        assert result.exit_code == 0
        assert 'Hooks: installed' in result.output

    def test_status_reports_not_installed_when_absent(self, runner, fake_home):
        """No VoiceMode hooks anywhere → status nags to install them."""
        _write_settings(fake_home, {})
        with patch('voice_mode.cli_commands.soundfonts.Path.home', return_value=fake_home):
            result = runner.invoke(soundfonts, ['status'])
        assert result.exit_code == 0
        assert 'Hooks: not installed' in result.output
        assert 'voicemode claude hooks add' in result.output
