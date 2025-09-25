"""
Hook commands for Voice Mode - primarily for Claude Code integration.
"""

import click
import sys
import json
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any


@click.group()
@click.help_option('-h', '--help', help='Show this message and exit')
def hooks():
    """Manage Voice Mode hooks and event handlers."""
    pass


@hooks.command('receiver')
@click.option('--tool-name', help='Override tool name (for testing)')
@click.option('--action', type=click.Choice(['start', 'end']), help='Override action (for testing)')
@click.option('--subagent-type', help='Override subagent type (for testing)')
@click.option('--event', type=click.Choice(['PreToolUse', 'PostToolUse']), help='Override event (for testing)')
@click.option('--debug', is_flag=True, help='Enable debug output')
@click.option('--quiet', is_flag=True, help='Suppress all output (for production)')
def receiver(tool_name, action, subagent_type, event, debug, quiet):
    """Receive and process hook events from Claude Code via stdin.
    
    This command reads JSON from stdin when called by Claude Code hooks,
    or accepts command-line arguments for testing.
    
    The filesystem structure defines sound mappings:
    ~/.voicemode/soundfonts/current/PreToolUse/task/subagent/baby-bear.wav
    
    Examples:
        # Called by Claude Code (reads JSON from stdin)
        voicemode claude hooks receiver
        
        # Testing with defaults
        voicemode claude hooks receiver --debug
        
        # Testing with specific values
        voicemode claude hooks receiver --tool-name Task --action start --subagent-type mama-bear
    """
    from voice_mode.tools.sound_fonts.audio_player import Player
    
    # Try to read JSON from stdin if available
    hook_data = {}
    if not sys.stdin.isatty():
        try:
            hook_data = json.load(sys.stdin)
            if debug:
                print(f"[DEBUG] Received JSON: {json.dumps(hook_data, indent=2)}", file=sys.stderr)
            elif not quiet:
                # Show minimal info by default
                tool = hook_data.get('tool_name', 'Unknown')
                event_type = hook_data.get('hook_event_name', 'Unknown')
                if tool == 'Bash':
                    cmd = hook_data.get('tool_input', {}).get('command', '')[:50]
                    print(f"[HOOK] {event_type}: {tool} - {cmd}...", file=sys.stderr)
                else:
                    print(f"[HOOK] {event_type}: {tool}", file=sys.stderr)
        except Exception as e:
            if debug:
                print(f"[DEBUG] Failed to parse JSON from stdin: {e}", file=sys.stderr)
            # Silent fail for hooks
            sys.exit(0)
    else:
        # If no stdin and no args, show example
        if not tool_name and not action and not subagent_type and not event:
            print("Example JSON that Claude Code sends to this hook:", file=sys.stderr)
            example = {
                "session_id": "session_abc123",
                "transcript_path": "/path/to/transcript.md",
                "cwd": "/Users/admin/Code/project",
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {
                    "command": "git push origin main",
                    "description": "Push changes to remote",
                    "sandbox": True
                }
            }
            print(json.dumps(example, indent=2), file=sys.stderr)
            print("\nTest with: echo '<JSON>' | voicemode claude hooks receiver --debug", file=sys.stderr)
            sys.exit(0)
    
    # Extract values from JSON or use command-line overrides/defaults
    if not tool_name:
        tool_name = hook_data.get('tool_name', 'Task')
    
    if not event:
        event_name = hook_data.get('hook_event_name', 'PreToolUse')
    else:
        event_name = event
    
    # Map event to action if not specified
    if not action:
        if event_name == 'PreToolUse':
            action = 'start'
        elif event_name == 'PostToolUse':
            action = 'end'
        else:
            action = 'start'  # Default
    
    # Get subagent_type from tool_input if not specified
    if not subagent_type and tool_name == 'Task':
        tool_input = hook_data.get('tool_input', {})
        subagent_type = tool_input.get('subagent_type', 'baby-bear')
    elif not subagent_type:
        subagent_type = None

    # Check for pattern matches using configuration
    matched_sound = match_hook_pattern(hook_data, debug)

    if matched_sound and not quiet:
        if tool_name == 'Bash':
            command = hook_data.get('tool_input', {}).get('command', '')[:30]
            print(f"[HOOK] Pattern matched for: {command}... -> sound: {matched_sound}", file=sys.stderr)
        else:
            print(f"[HOOK] Pattern matched for {tool_name} -> sound: {matched_sound}", file=sys.stderr)

    if debug:
        print(f"[DEBUG] Processing: event={event_name}, tool={tool_name}, "
              f"action={action}, subagent={subagent_type}, matched_sound={matched_sound}", file=sys.stderr)
    
    # Check if sound fonts are enabled
    from voice_mode.config import SOUNDFONTS_ENABLED
    
    if not SOUNDFONTS_ENABLED:
        if debug:
            print(f"[DEBUG] Sound fonts are disabled (VOICEMODE_SOUNDFONTS_ENABLED=false)", file=sys.stderr)
    else:
        # Find sound file using filesystem conventions
        # Use matched sound from patterns if available
        if matched_sound:
            sound_file = find_configured_sound_file(matched_sound)
        else:
            sound_file = find_sound_file(event_name, tool_name, subagent_type)

        if sound_file:
            if debug:
                print(f"[DEBUG] Found sound file: {sound_file}", file=sys.stderr)
            
            # Play the sound
            player = Player()
            success = player.play(str(sound_file))
            
            if debug:
                if success:
                    print(f"[DEBUG] Sound played successfully", file=sys.stderr)
                else:
                    print(f"[DEBUG] Failed to play sound", file=sys.stderr)
        else:
            if debug:
                print(f"[DEBUG] No sound file found for this event", file=sys.stderr)
    
    # Always exit 0 to not disrupt Claude Code
    sys.exit(0)


def get_nested_value(data: Dict[str, Any], path: str) -> Any:
    """
    Get a value from nested dictionary using dot notation.

    Args:
        data: Dictionary to search in
        path: Dot-separated path (e.g., "tool_input.command")

    Returns:
        Value at path or None if not found
    """
    keys = path.split('.')
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


def load_hook_patterns() -> List[Dict[str, Any]]:
    """
    Load hook pattern configuration from environment or config file.

    Returns:
        List of pattern configurations
    """
    # Try to load from environment variable
    patterns_json = os.environ.get("VOICEMODE_HOOK_PATTERNS", "")

    if patterns_json:
        try:
            return json.loads(patterns_json)
        except json.JSONDecodeError:
            print(f"[ERROR] Invalid JSON in VOICEMODE_HOOK_PATTERNS", file=sys.stderr)
            return []

    # For now, return hardcoded YubiKey patterns as default
    # This will be replaced with config file loading later
    return [
        {
            "name": "yubikey_auth",
            "tool_name": "Bash",
            "hook_event_name": "PreToolUse",
            "match_field": "tool_input.command",
            "pattern": "^(git (push|pull|fetch)|ssh |scp |sftp |rsync )",
            "sound": "yubikey"
        }
    ]


def match_hook_pattern(hook_data: Dict[str, Any], debug: bool = False) -> Optional[str]:
    """
    Check if hook data matches any configured patterns.

    Args:
        hook_data: The hook data from Claude Code
        debug: Whether to print debug messages

    Returns:
        Sound name if pattern matches, None otherwise
    """
    patterns = load_hook_patterns()

    for pattern_config in patterns:
        # Check tool_name if specified
        if "tool_name" in pattern_config:
            if hook_data.get("tool_name") != pattern_config["tool_name"]:
                continue

        # Check hook_event_name if specified
        if "hook_event_name" in pattern_config:
            if hook_data.get("hook_event_name") != pattern_config["hook_event_name"]:
                continue

        # Check pattern against specified field
        if "match_field" in pattern_config and "pattern" in pattern_config:
            field_value = get_nested_value(hook_data, pattern_config["match_field"])
            if field_value and isinstance(field_value, str):
                try:
                    if re.match(pattern_config["pattern"], field_value):
                        if debug:
                            print(f"[DEBUG] Pattern '{pattern_config.get('name', 'unnamed')}' matched", file=sys.stderr)
                        return pattern_config.get("sound", "default")
                except re.error:
                    if debug:
                        print(f"[DEBUG] Invalid regex in pattern '{pattern_config.get('name', 'unnamed')}'", file=sys.stderr)

    return None


def find_configured_sound_file(sound_name: str) -> Optional[Path]:
    """
    Find a sound file by its configured name.

    Args:
        sound_name: Name of the sound (e.g., "yubikey", "error", "success")

    Returns:
        Path to sound file if found, None otherwise
    """
    base_path = Path.home() / '.voicemode' / 'soundfonts' / 'current'

    # Resolve symlink if it exists
    if base_path.is_symlink():
        base_path = base_path.resolve()

    if not base_path.exists():
        return None

    # Check for environment variable override for this specific sound
    custom_path = os.environ.get(f"VOICEMODE_HOOK_SOUND_{sound_name.upper()}", "")
    if custom_path and Path(custom_path).exists():
        return Path(custom_path)

    # Paths to try for the sound (most to least specific)
    paths_to_try = [
        base_path / f'{sound_name}.mp3',
        base_path / f'{sound_name}.wav',
        base_path / 'custom' / f'{sound_name}.mp3',
        base_path / 'custom' / f'{sound_name}.wav',
        # Special case for yubikey
        base_path / 'boop.mp3' if sound_name == 'yubikey' else None,
        # Fall back to default
        base_path / 'default.mp3',
    ]

    for path in paths_to_try:
        if path and path.exists():
            return path

    return None


def find_yubikey_sound_file() -> Optional[Path]:
    """
    Find YubiKey authentication sound file.

    Looks for yubikey-specific sounds in order:
    1. yubikey.mp3 or yubikey.wav in soundfonts root
    2. PreToolUse/bash/yubikey.{mp3,wav}
    3. PreToolUse/yubikey.{mp3,wav}
    4. Falls back to a distinctive default

    Returns:
        Path to sound file if found, None otherwise
    """
    base_path = Path.home() / '.voicemode' / 'soundfonts' / 'current'

    # Resolve symlink if it exists
    if base_path.is_symlink():
        base_path = base_path.resolve()

    if not base_path.exists():
        return None

    # Paths to try for YubiKey sound (most to least specific)
    paths_to_try = [
        base_path / 'yubikey.mp3',
        base_path / 'yubikey.wav',
        base_path / 'PreToolUse' / 'bash' / 'yubikey.mp3',
        base_path / 'PreToolUse' / 'bash' / 'yubikey.wav',
        base_path / 'PreToolUse' / 'yubikey.mp3',
        base_path / 'PreToolUse' / 'yubikey.wav',
        # Fall back to a distinctive sound if no yubikey-specific sound exists
        base_path / 'alert.mp3',
        base_path / 'alert.wav',
        base_path / 'fallback.mp3',
    ]

    for path in paths_to_try:
        if path.exists():
            return path

    return None


def find_sound_file(event: str, tool: str, subagent: Optional[str] = None) -> Optional[Path]:
    """
    Find sound file using filesystem conventions.
    
    Tries paths in order (mp3 preferred over wav for size):
    1. Most specific: {event}/{tool}/subagent/{subagent}.{mp3,wav} (Task tool only)
    2. Tool default: {event}/{tool}/default.{mp3,wav}
    3. Event default: {event}/default.{mp3,wav}
    4. Global fallback: fallback.{mp3,wav}
    
    Args:
        event: Event name (PreToolUse, PostToolUse)
        tool: Tool name (lowercase)
        subagent: Optional subagent type (lowercase)
        
    Returns:
        Path to sound file if found, None otherwise
    """
    # Get base path (follow symlink if exists)
    base_path = Path.home() / '.voicemode' / 'soundfonts' / 'current'
    
    # Resolve symlink if it exists
    if base_path.is_symlink():
        base_path = base_path.resolve()
    
    if not base_path.exists():
        return None
    
    # Normalize names to lowercase for filesystem
    event = event.lower() if event else 'pretooluse'
    tool = tool.lower() if tool else 'default'
    subagent = subagent.lower() if subagent else None
    
    # Map event names to directory names
    event_map = {
        'pretooluse': 'PreToolUse',
        'posttooluse': 'PostToolUse',
        'start': 'PreToolUse',
        'end': 'PostToolUse'
    }
    event_dir = event_map.get(event, event)
    
    # Build list of paths to try (most specific to least specific)
    paths_to_try = []
    
    # 1. Most specific: subagent sound (Task tool only)
    if tool == 'task' and subagent:
        # Try mp3 first (smaller), then wav
        paths_to_try.append(base_path / event_dir / tool / 'subagent' / f'{subagent}.mp3')
        paths_to_try.append(base_path / event_dir / tool / 'subagent' / f'{subagent}.wav')
    
    # 2. Tool-specific default
    paths_to_try.append(base_path / event_dir / tool / 'default.mp3')
    paths_to_try.append(base_path / event_dir / tool / 'default.wav')
    
    # 3. Event-level default
    paths_to_try.append(base_path / event_dir / 'default.mp3')
    paths_to_try.append(base_path / event_dir / 'default.wav')
    
    # 4. Global fallback
    paths_to_try.append(base_path / 'fallback.mp3')
    paths_to_try.append(base_path / 'fallback.wav')
    
    # Find first existing file
    for path in paths_to_try:
        if path.exists():
            return path
    
    return None


# Keep the old stdin-receiver command for backwards compatibility (deprecated)
@hooks.command('stdin-receiver', hidden=True)
@click.argument('tool_name')
@click.argument('action', type=click.Choice(['start', 'end', 'complete']))
@click.argument('subagent_type', required=False)
@click.option('--debug', is_flag=True, help='Enable debug output')
def stdin_receiver_deprecated(tool_name, action, subagent_type, event, debug):
    """[DEPRECATED] Use receiver instead."""
    # Call the new receiver command
    ctx = click.get_current_context()
    ctx.invoke(receiver, 
               tool_name=tool_name,
               action=action,
               subagent_type=subagent_type,
               event=event,
               debug=debug)