"""CLI commands for Claude Code integration.

Provides `voicemode claude hooks add/remove/list` commands
for managing VoiceMode hooks in Claude Code settings.
"""

import copy
import json
import os
import shutil
import sys
from importlib.resources import files
from pathlib import Path

import click


# Hook name to event name mapping
HOOK_NAME_TO_EVENT = {
    'pre-tool-use': 'PreToolUse',
    'post-tool-use': 'PostToolUse',
    'notification': 'Notification',
    'stop': 'Stop',
    'pre-compact': 'PreCompact',
    'permission-request': 'PermissionRequest',
}

# Settings file paths by scope
SETTINGS_PATHS = {
    'user': Path.home() / '.claude' / 'settings.json',
    'project': Path('.claude') / 'settings.json',
    'local': Path('.claude') / 'settings.local.json',
}


def get_available_hooks() -> dict:
    """Discover available hook files from package data.

    Returns dict mapping hook name to parsed JSON content.
    e.g. {'pre-tool-use': {...}, 'post-tool-use': {...}}
    """
    hooks_dir = files('voice_mode.data.hooks')
    available = {}
    for resource in hooks_dir.iterdir():
        if resource.name.endswith('.json'):
            name = resource.name.removesuffix('.json')
            content = json.loads(resource.read_text())
            available[name] = content
    return available


def get_installed_hook_names(scope: str) -> set[str]:
    """Return set of hook names (kebab-case) that are installed for the given scope.

    Reads the settings file and checks which hook events have VoiceMode
    hooks present, then maps event names back to hook names.
    """
    event_to_name = {v: k for k, v in HOOK_NAME_TO_EVENT.items()}
    try:
        settings = read_settings(scope)
    except Exception:
        return set()
    hooks_dict = settings.get('hooks', {})
    installed = set()
    for event, entries in hooks_dict.items():
        if any(is_voicemode_hook(e) for e in entries):
            if event in event_to_name:
                installed.add(event_to_name[event])
    return installed


def hook_name_add_completion(ctx, param, incomplete):
    """Shell completion for 'hooks add' - only suggest hooks NOT already installed."""
    scope = (ctx.params.get('scope') or 'user')
    available = get_available_hooks()
    installed = get_installed_hook_names(scope)
    return [name for name in sorted(available) if name not in installed and name.startswith(incomplete)]


def hook_name_remove_completion(ctx, param, incomplete):
    """Shell completion for 'hooks remove' - only suggest hooks that ARE installed."""
    scope = (ctx.params.get('scope') or 'user')
    installed = get_installed_hook_names(scope)
    return [name for name in sorted(installed) if name.startswith(incomplete)]


def install_hook_receiver() -> Path:
    """Install the bash hook-receiver script to ~/.voicemode/bin/.

    Copies the bundled voicemode-hook-receiver.sh from package data
    to ~/.voicemode/bin/voicemode-hook-receiver and makes it executable.

    Returns:
        Path to the installed script.
    """
    dest = Path.home() / '.voicemode' / 'bin' / 'voicemode-hook-receiver'
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Read bundled script from package data
    hooks_data = files('voice_mode.data.hooks')
    script_resource = hooks_data.joinpath('voicemode-hook-receiver.sh')
    script_content = script_resource.read_text()

    # Write and make executable
    dest.write_text(script_content)
    dest.chmod(0o755)

    return dest


def resolve_hook_command() -> str:
    """Determine the correct command for hook entries."""
    # Check PATH
    if shutil.which('voicemode-hook-receiver'):
        return 'voicemode-hook-receiver || true'
    # Check ~/.voicemode/bin/
    home_bin = Path.home() / '.voicemode' / 'bin' / 'voicemode-hook-receiver'
    if home_bin.exists() and os.access(home_bin, os.X_OK):
        return f'{home_bin} || true'
    # Not found - install it
    installed = install_hook_receiver()
    return f'{installed} || true'


def is_voicemode_hook(hook_entry: dict) -> bool:
    """Check if a hook entry belongs to VoiceMode."""
    for handler in hook_entry.get('hooks', []):
        cmd = handler.get('command', '')
        if 'voicemode-hook-receiver' in cmd or 'voicemode hook-receiver' in cmd:
            return True
    return False


def read_settings(scope: str) -> dict:
    """Read settings JSON file, returning empty dict if not found."""
    path = SETTINGS_PATHS[scope]
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def write_settings(scope: str, settings: dict) -> None:
    """Write settings JSON file, creating parent dirs if needed."""
    path = SETTINGS_PATHS[scope]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + '\n')


def _resolve_command_in_entries(entries: list, command: str) -> list:
    """Replace the command in hook entries with the resolved path."""
    resolved = copy.deepcopy(entries)
    for entry in resolved:
        for handler in entry.get('hooks', []):
            if handler.get('type') == 'command':
                handler['command'] = command
    return resolved


def merge_hooks(existing: dict, new_hooks: dict, command: str) -> tuple[dict, list[str]]:
    """Deep merge hooks into existing settings, preserving everything.

    Args:
        existing: Current settings dict
        new_hooks: Hook definitions from source JSON (with 'hooks' key)
        command: Resolved command path for hook entries

    Returns:
        Tuple of (updated settings, list of added event names)
    """
    result = copy.deepcopy(existing)
    added = []

    if 'hooks' not in result:
        result['hooks'] = {}

    hook_defs = new_hooks.get('hooks', {})
    for event, entries in hook_defs.items():
        # Replace command path from source file with resolved path
        resolved_entries = _resolve_command_in_entries(entries, command)

        if event not in result['hooks']:
            result['hooks'][event] = resolved_entries
            added.append(event)
        else:
            # Check if VoiceMode hook already present
            if not any(is_voicemode_hook(e) for e in result['hooks'][event]):
                result['hooks'][event].extend(resolved_entries)
                added.append(event)

    return result, added


def remove_hooks(existing: dict, event_names: list[str] | None = None) -> tuple[dict, list[str]]:
    """Remove VoiceMode hooks from settings.

    Args:
        existing: Current settings dict
        event_names: Specific events to remove, or None for all

    Returns:
        Tuple of (updated settings, list of removed event names)
    """
    result = copy.deepcopy(existing)
    removed = []

    if 'hooks' not in result:
        return result, removed

    events_to_check = event_names or list(result['hooks'].keys())

    for event in events_to_check:
        if event not in result['hooks']:
            continue
        original_count = len(result['hooks'][event])
        result['hooks'][event] = [
            e for e in result['hooks'][event] if not is_voicemode_hook(e)
        ]
        if len(result['hooks'][event]) < original_count:
            removed.append(event)
        # Clean up empty arrays
        if not result['hooks'][event]:
            del result['hooks'][event]

    # Clean up empty hooks object
    if not result.get('hooks'):
        result.pop('hooks', None)

    return result, removed


# ============================================================================
# Click Commands
# ============================================================================

@click.group(name='claude')
@click.help_option('-h', '--help', help='Show this message and exit')
def claude():
    """Claude Code integration commands."""
    pass


@claude.group(invoke_without_command=True)
@click.help_option('-h', '--help', help='Show this message and exit')
@click.pass_context
def hooks(ctx):
    """Manage Claude Code hooks for VoiceMode.

    Install, remove, and inspect VoiceMode hooks in Claude Code settings.
    Hooks enable audio feedback (soundfonts) during Claude Code sessions.
    """
    if ctx.invoked_subcommand is None:
        # Default: show hooks list
        ctx.invoke(hooks_list)


@hooks.command("add", epilog="""
Examples:
  voicemode claude hooks add                    # Add all hooks to user settings
  voicemode claude hooks add pre-tool-use       # Add only PreToolUse hook
  voicemode claude hooks add -s project         # Add to project settings
  voicemode claude hooks add --scope local      # Add to local settings
""")
@click.help_option('-h', '--help', help='Show this message and exit')
@click.argument('hook_name', required=False, default=None, shell_complete=hook_name_add_completion)
@click.option('-s', '--scope', type=click.Choice(['user', 'project', 'local']),
              default='user', show_default=True,
              help='Settings scope to install hooks into')
def hooks_add(hook_name, scope):
    """Add VoiceMode hooks to Claude Code settings.

    Without HOOK_NAME, adds all available hooks. With HOOK_NAME,
    adds only the specified hook event.
    """
    # Get available hooks
    available_hooks = get_available_hooks()

    # Determine which hooks to add
    if hook_name:
        if hook_name not in available_hooks:
            click.echo(f"Unknown hook: {hook_name}")
            click.echo(f"\nAvailable hooks: {', '.join(available_hooks.keys())}")
            sys.exit(1)
        hooks_to_add = {hook_name: available_hooks[hook_name]}
    else:
        hooks_to_add = available_hooks

    # Ensure hook receiver is installed, then resolve command path
    command = resolve_hook_command()

    # Read existing settings
    settings = read_settings(scope)

    # Track what was added
    all_added = []

    # Add each hook
    for name, hook_def in hooks_to_add.items():
        settings, added = merge_hooks(settings, hook_def, command)
        all_added.extend(added)

    # Write updated settings
    write_settings(scope, settings)

    # Print summary
    settings_path = SETTINGS_PATHS[scope]
    click.echo(f"Added VoiceMode hooks to {scope} settings ({settings_path}):")

    for name in hooks_to_add.keys():
        event = HOOK_NAME_TO_EVENT.get(name, name)
        if event in all_added:
            click.echo(f"  + {event}")
        else:
            click.echo(f"  - {event} (already present)")

    if all_added:
        click.echo()
        click.echo("Use --scope project for project-only installation.")
        click.echo("Restart Claude Code for hooks to take effect.")


@hooks.command("remove", epilog="""
Examples:
  voicemode claude hooks remove                 # Remove all VoiceMode hooks from user settings
  voicemode claude hooks remove pre-tool-use    # Remove only PreToolUse hook
  voicemode claude hooks remove -s project      # Remove from project settings
""")
@click.help_option('-h', '--help', help='Show this message and exit')
@click.argument('hook_name', required=False, default=None, shell_complete=hook_name_remove_completion)
@click.option('-s', '--scope', type=click.Choice(['user', 'project', 'local']),
              default='user', show_default=True,
              help='Settings scope to remove hooks from')
def hooks_remove(hook_name, scope):
    """Remove VoiceMode hooks from Claude Code settings.

    Without HOOK_NAME, removes all VoiceMode hooks. With HOOK_NAME,
    removes only the specified hook event.
    """
    # Validate hook name first (before reading settings)
    if hook_name:
        if hook_name not in HOOK_NAME_TO_EVENT:
            click.echo(f"Unknown hook: {hook_name}")
            click.echo(f"\nAvailable hooks: {', '.join(HOOK_NAME_TO_EVENT.keys())}")
            sys.exit(1)
        event_names = [HOOK_NAME_TO_EVENT[hook_name]]
    else:
        event_names = None

    # Read existing settings
    settings = read_settings(scope)

    if not settings.get('hooks'):
        click.echo(f"No hooks found in {scope} settings.")
        return

    # Remove hooks
    settings, removed = remove_hooks(settings, event_names)

    # Write updated settings
    write_settings(scope, settings)

    # Print summary
    settings_path = SETTINGS_PATHS[scope]
    click.echo(f"Removed VoiceMode hooks from {scope} settings ({settings_path}):")

    # Show all events we checked
    events_to_show = event_names if event_names else list(HOOK_NAME_TO_EVENT.values())
    for event in events_to_show:
        if event in removed:
            click.echo(f"  + {event} (removed)")
        else:
            click.echo(f"  - {event} (not found)")


@hooks.command("list", epilog="""
Examples:
  voicemode claude hooks list                   # Show hooks in user settings
  voicemode claude hooks list -s all            # Show hooks across all scopes
  voicemode claude hooks list -s project        # Show hooks in project settings
""")
@click.help_option('-h', '--help', help='Show this message and exit')
@click.option('-s', '--scope', type=click.Choice(['user', 'project', 'local', 'all']),
              default='user', show_default=True,
              help='Settings scope to inspect')
def hooks_list(scope):
    """Show VoiceMode hook status in Claude Code settings.

    Shows which VoiceMode hooks are installed and in which settings scope.
    """
    def check_scope(scope_name):
        """Check hooks for a single scope."""
        settings = read_settings(scope_name)
        hooks_dict = settings.get('hooks', {})

        results = {}
        for event in HOOK_NAME_TO_EVENT.values():
            if event not in hooks_dict:
                results[event] = False
            else:
                # Check if VoiceMode hook is present
                results[event] = any(is_voicemode_hook(e) for e in hooks_dict[event])

        return results

    if scope == 'all':
        # Show all scopes
        click.echo("VoiceMode Hooks Status:")
        click.echo()

        for scope_name in ['user', 'project', 'local']:
            settings_path = SETTINGS_PATHS[scope_name]
            click.echo(f"{scope_name.capitalize()} ({settings_path}):")

            results = check_scope(scope_name)
            any_installed = any(results.values())

            if not any_installed:
                click.echo("  (no VoiceMode hooks)")
            else:
                for event, installed in results.items():
                    if installed:
                        click.echo(f"  {event:14} + installed")

            click.echo()
    else:
        # Show single scope
        settings_path = SETTINGS_PATHS[scope]
        click.echo(f"VoiceMode Hooks - {scope.capitalize()} ({settings_path}):")

        results = check_scope(scope)
        for event, installed in results.items():
            status = "+ installed" if installed else "  not installed"
            click.echo(f"  {event:14} {status}")
