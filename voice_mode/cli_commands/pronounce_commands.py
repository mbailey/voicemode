"""CLI commands for managing pronunciation rules."""

import click
import yaml
import json
from pathlib import Path
from typing import Optional

from voice_mode.pronounce import get_manager


@click.group(name='pronounce')
def pronounce_group():
    """Manage pronunciation rules for TTS and STT."""
    pass


@pronounce_group.command(name='list')
@click.option('--direction', '-d', type=click.Choice(['tts', 'stt', 'all']), default='all',
              help='Filter by direction (tts/stt/all)')
@click.option('--enabled-only', '-e', is_flag=True, help='Show only enabled rules')
@click.option('--show-private', '-p', is_flag=True, help='Include private rules')
@click.option('--format', '-f', type=click.Choice(['table', 'yaml', 'json']), default='table',
              help='Output format')
def list_rules(direction: str, enabled_only: bool, show_private: bool, format: str):
    """List pronunciation rules."""
    manager = get_manager()
    
    # Get rules
    if direction == 'all':
        rules = manager.list_rules(include_private=show_private)
    else:
        rules = manager.list_rules(direction=direction, include_private=show_private)
    
    # Filter if needed
    if enabled_only:
        rules = [r for r in rules if r['enabled']]
    
    # Format output
    if format == 'table':
        if not rules:
            click.echo("No rules found.")
            return
        
        # Count private rules that were hidden
        all_rules = manager.list_rules(include_private=True)
        private_count = len(all_rules) - len(rules)
        
        # Simple table format without tabulate
        click.echo("\nPronunciation Rules:")
        click.echo("=" * 80)
        
        for rule in rules:
            status = '✓' if rule['enabled'] else '✗'
            click.echo(f"\n{status} [{rule['direction'].upper()}] {rule['name']} (order: {rule['order']})")
            click.echo(f"  Pattern:  {rule['pattern']}")
            click.echo(f"  Replace:  {rule['replacement']}")
            if rule['description']:
                click.echo(f"  Desc:     {rule['description']}")
        
        if private_count > 0 and not show_private:
            click.echo(f"\n({private_count} private rules hidden. Use --show-private to display)")
    
    elif format == 'yaml':
        import yaml
        click.echo(yaml.dump(rules, default_flow_style=False))
    
    elif format == 'json':
        import json
        click.echo(json.dumps(rules, indent=2))


@pronounce_group.command(name='test')
@click.argument('text')
@click.option('--direction', '-d', type=click.Choice(['tts', 'stt']), default='tts',
              help='Test direction (tts/stt)')
def test_rule(text: str, direction: str):
    """Test pronunciation rules on text."""
    manager = get_manager()
    result = manager.test_rule(text, direction)
    
    if text != result:
        click.echo(f"Original: {text}")
        click.echo(f"Modified: {result}")
        
        # Show which rules were applied if logging is enabled
        import os
        if os.environ.get('VOICEMODE_PRONUNCIATION_LOG_SUBSTITUTIONS', '').lower() == 'true':
            click.echo("\n(Check logs for applied rules)")
    else:
        click.echo(f"No changes: {text}")


@pronounce_group.command(name='add')
@click.option('--direction', '-d', type=click.Choice(['tts', 'stt']), required=True,
              help='Rule direction (tts/stt)')
@click.option('--pattern', '-p', required=True, help='Regex pattern to match')
@click.option('--replacement', '-r', required=True, help='Replacement text')
@click.option('--name', '-n', help='Rule name (auto-generated if not provided)')
@click.option('--description', help='Rule description')
@click.option('--order', type=int, default=100, help='Processing order (lower = earlier)')
@click.option('--disabled', is_flag=True, help='Create rule as disabled')
def add_rule(direction: str, pattern: str, replacement: str, name: Optional[str],
             description: str, order: int, disabled: bool):
    """Add a new pronunciation rule."""
    manager = get_manager()
    
    success = manager.add_rule(
        direction=direction,
        pattern=pattern,
        replacement=replacement,
        name=name,
        description=description or "",
        enabled=not disabled,
        order=order,
        private=False  # CLI-created rules are not private
    )
    
    if success:
        click.echo(f"✓ Rule added successfully")
    else:
        click.echo("✗ Failed to add rule (check pattern validity)", err=True)


@pronounce_group.command(name='remove')
@click.option('--direction', '-d', type=click.Choice(['tts', 'stt']), required=True,
              help='Rule direction (tts/stt)')
@click.argument('name')
def remove_rule(direction: str, name: str):
    """Remove a pronunciation rule by name."""
    manager = get_manager()
    
    success = manager.remove_rule(direction, name)
    
    if success:
        click.echo(f"✓ Rule '{name}' removed")
    else:
        click.echo(f"✗ Rule '{name}' not found", err=True)


@pronounce_group.command(name='enable')
@click.option('--direction', '-d', type=click.Choice(['tts', 'stt']), required=True,
              help='Rule direction (tts/stt)')
@click.argument('name')
def enable_rule(direction: str, name: str):
    """Enable a pronunciation rule."""
    manager = get_manager()
    
    success = manager.enable_rule(direction, name)
    
    if success:
        click.echo(f"✓ Rule '{name}' enabled")
    else:
        click.echo(f"✗ Failed to enable rule '{name}' (not found or private)", err=True)


@pronounce_group.command(name='disable')
@click.option('--direction', '-d', type=click.Choice(['tts', 'stt']), required=True,
              help='Rule direction (tts/stt)')
@click.argument('name')
def disable_rule(direction: str, name: str):
    """Disable a pronunciation rule."""
    manager = get_manager()
    
    success = manager.disable_rule(direction, name)
    
    if success:
        click.echo(f"✓ Rule '{name}' disabled")
    else:
        click.echo(f"✗ Failed to disable rule '{name}' (not found or private)", err=True)


@pronounce_group.command(name='reload')
def reload_rules():
    """Reload pronunciation rules from configuration files."""
    manager = get_manager()
    manager.reload_rules()
    click.echo("✓ Pronunciation rules reloaded")


@pronounce_group.command(name='edit')
@click.option('--system', is_flag=True, help='Edit system default rules (requires sudo)')
def edit_config(system: bool):
    """Open pronunciation config in editor."""
    import os
    import subprocess
    
    if system:
        # Edit system defaults
        config_path = Path(__file__).parent.parent / 'data' / 'default_pronunciation.yaml'
        if not config_path.exists():
            click.echo(f"System config not found: {config_path}", err=True)
            return
        # Might need sudo
        editor = os.environ.get('EDITOR', 'nano')
        subprocess.run(['sudo', editor, str(config_path)])
    else:
        # Edit user config
        config_path = Path.home() / '.voicemode' / 'config' / 'pronunciation.yaml'
        if not config_path.exists():
            # Create default config
            config_path.parent.mkdir(parents=True, exist_ok=True)
            default_config = {
                'version': 1,
                'tts_rules': [],
                'stt_rules': []
            }
            with open(config_path, 'w') as f:
                yaml.dump(default_config, f, default_flow_style=False)
        
        editor = os.environ.get('EDITOR', 'nano')
        subprocess.run([editor, str(config_path)])
    
    # Reload after editing
    manager = get_manager()
    manager.reload_rules()
    click.echo("✓ Configuration edited and reloaded")


# Register the command group
def register_commands(cli):
    """Register pronunciation commands with the main CLI."""
    cli.add_command(pronounce_group)