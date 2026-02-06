"""Tests for Claude Code hooks CLI commands."""

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from voice_mode.cli_commands.claude import (
    claude,
    get_available_hooks,
    install_hook_receiver,
    resolve_hook_command,
    is_voicemode_hook,
    merge_hooks,
    remove_hooks,
    HOOK_NAME_TO_EVENT,
)


@pytest.fixture
def runner():
    """Create a Click test runner."""
    return CliRunner()


@pytest.fixture
def temp_settings_dir(tmp_path, monkeypatch):
    """Set up temporary settings directory."""
    claude_dir = tmp_path / '.claude'
    claude_dir.mkdir()

    # Patch the SETTINGS_PATHS in the claude CLI module
    from voice_mode.cli_commands import claude as claude_mod
    monkeypatch.setattr(claude_mod, 'SETTINGS_PATHS', {
        'user': claude_dir / 'settings.json',
        'project': tmp_path / '.claude' / 'settings.json',
        'local': tmp_path / '.claude' / 'settings.local.json',
    })

    return claude_dir


@pytest.fixture
def mock_hook_def():
    """Sample hook definition."""
    return {
        "description": "Test hook",
        "hooks": {
            "PreToolUse": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": "${CLAUDE_PLUGIN_ROOT}/.claude/scripts/voicemode-hook-receiver || true"
                        }
                    ]
                }
            ]
        }
    }


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestMergeHooks:
    """Tests for merge_hooks function."""

    def test_merge_hooks_empty_settings(self, mock_hook_def):
        """Should merge into empty settings."""
        existing = {}
        command = 'voicemode-hook-receiver || true'

        result, added = merge_hooks(existing, mock_hook_def, command)

        assert 'hooks' in result
        assert 'PreToolUse' in result['hooks']
        assert len(result['hooks']['PreToolUse']) == 1
        assert result['hooks']['PreToolUse'][0]['hooks'][0]['command'] == command
        assert 'PreToolUse' in added

    def test_merge_hooks_existing_settings(self, mock_hook_def):
        """Should preserve existing non-VoiceMode content."""
        existing = {
            'some_other_setting': 'value',
            'hooks': {
                'OtherEvent': [
                    {'hooks': [{'type': 'command', 'command': 'other-command'}]}
                ]
            }
        }
        command = 'voicemode-hook-receiver || true'

        result, added = merge_hooks(existing, mock_hook_def, command)

        assert result['some_other_setting'] == 'value'
        assert 'OtherEvent' in result['hooks']
        assert 'PreToolUse' in result['hooks']
        assert 'PreToolUse' in added

    def test_merge_hooks_idempotent(self, mock_hook_def):
        """Should not duplicate if VoiceMode hook already present."""
        command = 'voicemode-hook-receiver || true'
        existing = {}

        # First merge
        result1, added1 = merge_hooks(existing, mock_hook_def, command)
        assert 'PreToolUse' in added1

        # Second merge - should detect existing
        result2, added2 = merge_hooks(result1, mock_hook_def, command)
        assert 'PreToolUse' not in added2
        assert len(result2['hooks']['PreToolUse']) == 1  # Still only one entry


class TestRemoveHooks:
    """Tests for remove_hooks function."""

    def test_remove_hooks_clean(self):
        """Should remove only VoiceMode hooks."""
        existing = {
            'hooks': {
                'PreToolUse': [
                    {
                        'hooks': [
                            {
                                'type': 'command',
                                'command': 'voicemode-hook-receiver || true'
                            }
                        ]
                    }
                ]
            }
        }

        result, removed = remove_hooks(existing)

        assert 'PreToolUse' in removed
        assert 'hooks' not in result  # Should clean up empty hooks object

    def test_remove_hooks_preserves_others(self):
        """Should not affect non-VoiceMode hooks."""
        existing = {
            'hooks': {
                'PreToolUse': [
                    {
                        'hooks': [
                            {
                                'type': 'command',
                                'command': 'other-command'
                            }
                        ]
                    },
                    {
                        'hooks': [
                            {
                                'type': 'command',
                                'command': 'voicemode-hook-receiver || true'
                            }
                        ]
                    }
                ]
            }
        }

        result, removed = remove_hooks(existing)

        assert 'PreToolUse' in removed
        assert 'PreToolUse' in result['hooks']
        assert len(result['hooks']['PreToolUse']) == 1
        assert result['hooks']['PreToolUse'][0]['hooks'][0]['command'] == 'other-command'

    def test_remove_hooks_cleanup_empty(self):
        """Should clean up empty arrays and objects."""
        existing = {
            'hooks': {
                'PreToolUse': [
                    {
                        'hooks': [
                            {
                                'type': 'command',
                                'command': 'voicemode-hook-receiver || true'
                            }
                        ]
                    }
                ],
                'PostToolUse': [
                    {
                        'hooks': [
                            {
                                'type': 'command',
                                'command': 'voicemode hook-receiver || true'
                            }
                        ]
                    }
                ]
            }
        }

        result, removed = remove_hooks(existing)

        assert 'PreToolUse' in removed
        assert 'PostToolUse' in removed
        assert 'hooks' not in result  # Should remove empty hooks object

    def test_remove_hooks_specific_event(self):
        """Should remove only specified event."""
        existing = {
            'hooks': {
                'PreToolUse': [
                    {
                        'hooks': [
                            {
                                'type': 'command',
                                'command': 'voicemode-hook-receiver || true'
                            }
                        ]
                    }
                ],
                'PostToolUse': [
                    {
                        'hooks': [
                            {
                                'type': 'command',
                                'command': 'voicemode-hook-receiver || true'
                            }
                        ]
                    }
                ]
            }
        }

        result, removed = remove_hooks(existing, ['PreToolUse'])

        assert 'PreToolUse' in removed
        assert 'PostToolUse' not in removed
        assert 'PreToolUse' not in result['hooks']
        assert 'PostToolUse' in result['hooks']


class TestIsVoicemodeHook:
    """Tests for is_voicemode_hook function."""

    def test_is_voicemode_hook_with_receiver(self):
        """Should identify voicemode-hook-receiver command."""
        hook_entry = {
            'hooks': [
                {
                    'type': 'command',
                    'command': 'voicemode-hook-receiver || true'
                }
            ]
        }
        assert is_voicemode_hook(hook_entry) is True

    def test_is_voicemode_hook_with_cli(self):
        """Should identify voicemode hook-receiver command."""
        hook_entry = {
            'hooks': [
                {
                    'type': 'command',
                    'command': 'voicemode hook-receiver || true'
                }
            ]
        }
        assert is_voicemode_hook(hook_entry) is True

    def test_is_voicemode_hook_with_path(self):
        """Should identify voicemode-hook-receiver with path."""
        hook_entry = {
            'hooks': [
                {
                    'type': 'command',
                    'command': '/home/user/.voicemode/bin/voicemode-hook-receiver || true'
                }
            ]
        }
        assert is_voicemode_hook(hook_entry) is True

    def test_is_not_voicemode_hook(self):
        """Should not identify other commands."""
        hook_entry = {
            'hooks': [
                {
                    'type': 'command',
                    'command': 'some-other-command'
                }
            ]
        }
        assert is_voicemode_hook(hook_entry) is False

    def test_is_voicemode_hook_empty(self):
        """Should handle empty hook entry."""
        hook_entry = {'hooks': []}
        assert is_voicemode_hook(hook_entry) is False


class TestResolveHookCommand:
    """Tests for resolve_hook_command function."""

    def test_resolve_hook_command_in_path(self):
        """Should use bare command if in PATH."""
        with patch('shutil.which', return_value='/usr/local/bin/voicemode-hook-receiver'):
            result = resolve_hook_command()
            assert result == 'voicemode-hook-receiver || true'

    def test_resolve_hook_command_in_home_bin(self):
        """Should use home bin path if not in PATH but exists."""
        home_bin = Path.home() / '.voicemode' / 'bin' / 'voicemode-hook-receiver'

        with patch('shutil.which', return_value=None):
            with patch.object(Path, 'exists', return_value=True):
                with patch('os.access', return_value=True):
                    result = resolve_hook_command()
                    assert str(home_bin) in result
                    assert '|| true' in result

    def test_resolve_hook_command_installs_when_missing(self, tmp_path):
        """Should install hook receiver to ~/.voicemode/bin/ if not found."""
        fake_home = tmp_path / 'home'
        fake_home.mkdir(exist_ok=True)
        home_bin = fake_home / '.voicemode' / 'bin' / 'voicemode-hook-receiver'

        with patch('shutil.which', return_value=None):
            with patch('voice_mode.cli_commands.claude.Path.home', return_value=fake_home):
                result = resolve_hook_command()
                assert str(home_bin) in result
                assert '|| true' in result
                assert home_bin.exists()
                assert os.access(home_bin, os.X_OK)


class TestGetAvailableHooks:
    """Tests for get_available_hooks function."""

    def test_get_available_hooks(self):
        """Should discover hook files from package data."""
        hooks = get_available_hooks()

        # Should find at least the core hooks
        assert 'pre-tool-use' in hooks
        assert 'post-tool-use' in hooks
        assert 'notification' in hooks
        assert 'stop' in hooks
        assert 'pre-compact' in hooks

        # Each hook should have proper structure
        for name, hook_def in hooks.items():
            assert 'hooks' in hook_def
            assert isinstance(hook_def['hooks'], dict)


class TestHookNameMapping:
    """Tests for hook name to event mapping."""

    def test_hook_name_to_event_mapping(self):
        """Should map all hook names to valid events."""
        assert HOOK_NAME_TO_EVENT['pre-tool-use'] == 'PreToolUse'
        assert HOOK_NAME_TO_EVENT['post-tool-use'] == 'PostToolUse'
        assert HOOK_NAME_TO_EVENT['notification'] == 'Notification'
        assert HOOK_NAME_TO_EVENT['stop'] == 'Stop'
        assert HOOK_NAME_TO_EVENT['pre-compact'] == 'PreCompact'


# =============================================================================
# CLI Command Tests
# =============================================================================


class TestHooksAddCommand:
    """Tests for 'voicemode claude hooks add' command."""

    def test_add_all_hooks(self, runner, temp_settings_dir):
        """Should add all hooks to user settings."""
        with patch('voice_mode.cli_commands.claude.resolve_hook_command', return_value='voicemode-hook-receiver || true'):
            result = runner.invoke(claude, ['hooks', 'add'])

        assert result.exit_code == 0
        assert '+ PreToolUse' in result.output
        assert '+ PostToolUse' in result.output
        assert '+ Notification' in result.output
        assert '+ Stop' in result.output
        assert '+ PreCompact' in result.output
        assert 'Restart Claude Code' in result.output

        # Verify file was written
        settings_file = temp_settings_dir / 'settings.json'
        assert settings_file.exists()
        settings = json.loads(settings_file.read_text())
        assert 'hooks' in settings
        assert 'PreToolUse' in settings['hooks']

    def test_add_single_hook(self, runner, temp_settings_dir):
        """Should add only specified hook."""
        with patch('voice_mode.cli_commands.claude.resolve_hook_command', return_value='voicemode-hook-receiver || true'):
            result = runner.invoke(claude, ['hooks', 'add', 'pre-tool-use'])

        assert result.exit_code == 0
        assert '+ PreToolUse' in result.output

        settings_file = temp_settings_dir / 'settings.json'
        settings = json.loads(settings_file.read_text())
        assert 'PreToolUse' in settings['hooks']
        # Other hooks should not be present
        assert 'PostToolUse' not in settings['hooks']

    def test_add_hooks_idempotent(self, runner, temp_settings_dir):
        """Should not duplicate on repeated adds."""
        with patch('voice_mode.cli_commands.claude.resolve_hook_command', return_value='voicemode-hook-receiver || true'):
            # First add
            result1 = runner.invoke(claude, ['hooks', 'add', 'pre-tool-use'])
            assert result1.exit_code == 0
            assert '+ PreToolUse' in result1.output

            # Second add
            result2 = runner.invoke(claude, ['hooks', 'add', 'pre-tool-use'])
            assert result2.exit_code == 0
            assert 'already present' in result2.output

        settings_file = temp_settings_dir / 'settings.json'
        settings = json.loads(settings_file.read_text())
        # Should still be only one entry
        assert len(settings['hooks']['PreToolUse']) == 1

    def test_add_unknown_hook(self, runner, temp_settings_dir):
        """Should error on unknown hook name."""
        result = runner.invoke(claude, ['hooks', 'add', 'unknown-hook'])

        assert result.exit_code == 1
        assert 'Unknown hook: unknown-hook' in result.output

    def test_add_to_project_scope(self, runner, temp_settings_dir):
        """Should add to project settings with --scope."""
        with patch('voice_mode.cli_commands.claude.resolve_hook_command', return_value='voicemode-hook-receiver || true'):
            result = runner.invoke(claude, ['hooks', 'add', '-s', 'project'])

        assert result.exit_code == 0
        assert 'project settings' in result.output


class TestHooksRemoveCommand:
    """Tests for 'voicemode claude hooks remove' command."""

    def test_remove_all_hooks(self, runner, temp_settings_dir):
        """Should remove all VoiceMode hooks."""
        # First add hooks
        with patch('voice_mode.cli_commands.claude.resolve_hook_command', return_value='voicemode-hook-receiver || true'):
            runner.invoke(claude, ['hooks', 'add'])

        # Then remove
        result = runner.invoke(claude, ['hooks', 'remove'])

        assert result.exit_code == 0
        assert '+ PreToolUse (removed)' in result.output
        assert '+ PostToolUse (removed)' in result.output

        settings_file = temp_settings_dir / 'settings.json'
        settings = json.loads(settings_file.read_text())
        assert 'hooks' not in settings or not settings['hooks']

    def test_remove_single_hook(self, runner, temp_settings_dir):
        """Should remove only specified hook."""
        # Add hooks first
        with patch('voice_mode.cli_commands.claude.resolve_hook_command', return_value='voicemode-hook-receiver || true'):
            runner.invoke(claude, ['hooks', 'add'])

        # Remove one
        result = runner.invoke(claude, ['hooks', 'remove', 'pre-tool-use'])

        assert result.exit_code == 0
        assert '+ PreToolUse (removed)' in result.output

        settings_file = temp_settings_dir / 'settings.json'
        settings = json.loads(settings_file.read_text())
        assert 'PreToolUse' not in settings['hooks']
        assert 'PostToolUse' in settings['hooks']  # Others remain

    def test_remove_no_hooks_present(self, runner, temp_settings_dir):
        """Should handle no hooks gracefully."""
        result = runner.invoke(claude, ['hooks', 'remove'])

        assert result.exit_code == 0
        assert 'No hooks found' in result.output

    def test_remove_unknown_hook(self, runner, temp_settings_dir):
        """Should error on unknown hook name."""
        result = runner.invoke(claude, ['hooks', 'remove', 'unknown-hook'])

        assert result.exit_code == 1
        assert 'Unknown hook: unknown-hook' in result.output


class TestHooksListCommand:
    """Tests for 'voicemode claude hooks list' command."""

    def test_list_empty_hooks(self, runner, temp_settings_dir):
        """Should show not installed for all hooks."""
        result = runner.invoke(claude, ['hooks', 'list'])

        assert result.exit_code == 0
        assert 'not installed' in result.output
        assert 'PreToolUse' in result.output

    def test_list_installed_hooks(self, runner, temp_settings_dir):
        """Should show installed hooks."""
        # Add hooks first
        with patch('voice_mode.cli_commands.claude.resolve_hook_command', return_value='voicemode-hook-receiver || true'):
            runner.invoke(claude, ['hooks', 'add', 'pre-tool-use'])

        result = runner.invoke(claude, ['hooks', 'list'])

        assert result.exit_code == 0
        assert 'PreToolUse' in result.output
        assert '+ installed' in result.output

    def test_list_all_scopes(self, runner, temp_settings_dir):
        """Should show all scopes with --scope all."""
        result = runner.invoke(claude, ['hooks', 'list', '-s', 'all'])

        assert result.exit_code == 0
        assert 'User' in result.output
        assert 'Project' in result.output
        assert 'Local' in result.output

    def test_list_project_scope(self, runner, temp_settings_dir):
        """Should show project scope with --scope project."""
        result = runner.invoke(claude, ['hooks', 'list', '-s', 'project'])

        assert result.exit_code == 0
        assert 'Project' in result.output


class TestInstallHookReceiver:
    """Tests for install_hook_receiver function."""

    def test_install_creates_script(self, tmp_path):
        """Should install script to ~/.voicemode/bin/."""
        fake_home = tmp_path / 'home'
        fake_home.mkdir(exist_ok=True)

        with patch('voice_mode.cli_commands.claude.Path.home', return_value=fake_home):
            result = install_hook_receiver()

        expected = fake_home / '.voicemode' / 'bin' / 'voicemode-hook-receiver'
        assert result == expected
        assert expected.exists()
        assert os.access(expected, os.X_OK)

        # Verify it's a bash script
        content = expected.read_text()
        assert content.startswith('#!/usr/bin/env bash')
        assert 'voicemode-hook-receiver' in content

    def test_install_idempotent(self, tmp_path):
        """Should overwrite existing script without error."""
        fake_home = tmp_path / 'home'
        fake_home.mkdir(exist_ok=True)

        with patch('voice_mode.cli_commands.claude.Path.home', return_value=fake_home):
            install_hook_receiver()
            result = install_hook_receiver()

        assert result.exists()
        assert os.access(result, os.X_OK)


class TestHooksGroupDefault:
    """Tests for 'voicemode claude hooks' without subcommand."""

    def test_hooks_default_shows_list(self, runner, temp_settings_dir):
        """Should default to list command."""
        result = runner.invoke(claude, ['hooks'])

        assert result.exit_code == 0
        # Should show the list output
        assert 'PreToolUse' in result.output
