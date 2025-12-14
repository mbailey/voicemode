"""Utility functions for telemetry opt-in prompts."""

import os
import re
import sys
from pathlib import Path
from typing import Dict, Optional


USER_CONFIG_PATH = Path.home() / ".voicemode" / "voicemode.env"
LEGACY_CONFIG_PATH = Path.home() / ".voicemode" / ".voicemode.env"


def should_prompt_for_telemetry() -> bool:
    """Check if we should prompt the user for telemetry consent.

    Returns True if:
    - VOICEMODE_TELEMETRY is set to 'ask' (default)
    - DO_NOT_TRACK is not set
    - We're in an interactive terminal (not MCP/pipe mode)
    - User hasn't already been prompted (checked via config file)

    Returns:
        True if user should be prompted, False otherwise
    """
    # Check if DO_NOT_TRACK is set (overrides everything)
    if os.getenv("DO_NOT_TRACK") is not None:
        return False

    # Check VOICEMODE_TELEMETRY setting
    voicemode_telemetry = os.getenv("VOICEMODE_TELEMETRY", "ask").lower()
    if voicemode_telemetry != "ask":
        # User has already made a choice (true or false)
        return False

    # Check if we're in interactive mode (not a pipe or MCP mode)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return False

    # Check if telemetry preference is already set in config file
    config_path = USER_CONFIG_PATH
    if not config_path.exists() and LEGACY_CONFIG_PATH.exists():
        config_path = LEGACY_CONFIG_PATH

    if config_path.exists():
        try:
            with open(config_path, 'r') as f:
                content = f.read()
                # Check if VOICEMODE_TELEMETRY is explicitly set in the file
                # (not just commented out)
                if re.search(r'^VOICEMODE_TELEMETRY=', content, re.MULTILINE):
                    # Already configured in file
                    return False
        except Exception:
            pass

    # All checks passed - user should be prompted
    return True


def prompt_for_telemetry_consent() -> Optional[bool]:
    """Prompt user for telemetry consent in interactive CLI mode.

    Shows a clear, concise prompt explaining what telemetry collects and
    asks the user to opt-in or opt-out.

    Returns:
        True if user opts in, False if user opts out, None if prompt fails
    """
    if not should_prompt_for_telemetry():
        return None

    try:
        # Clear screen and show prompt
        print("\n" + "=" * 70)
        print("VoiceMode Telemetry")
        print("=" * 70)
        print()
        print("VoiceMode would like to collect anonymous usage statistics")
        print("to help improve the tool.")
        print()
        print("What we collect:")
        print("  • Session counts and durations (binned for privacy)")
        print("  • Voice exchanges per session")
        print("  • TTS/STT provider usage (openai, kokoro, whisper)")
        print("  • Success/failure rates")
        print("  • Anonymized error types")
        print()
        print("What we DON'T collect:")
        print("  • Your conversations or voice recordings")
        print("  • Personal information or file paths")
        print("  • API keys or credentials")
        print("  • Anything that could identify you")
        print()
        print("Privacy protections:")
        print("  • All data is anonymized with a random UUID")
        print("  • Numbers are binned to prevent identification")
        print("  • You can opt-out anytime with DO_NOT_TRACK=1")
        print()
        print("=" * 70)

        # Get user response
        while True:
            response = input("\nEnable telemetry? [y/N]: ").strip().lower()

            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no', '']:
                # Default to no if user just presses enter
                return False
            else:
                print("Please enter 'y' for yes or 'n' for no (or press Enter for no)")

    except (EOFError, KeyboardInterrupt):
        # User interrupted prompt (Ctrl+C or Ctrl+D)
        print("\n\nTelemetry prompt cancelled - defaulting to disabled")
        return False
    except Exception as e:
        # Unexpected error - fail safely by not enabling telemetry
        print(f"\nError during telemetry prompt: {e}")
        print("Defaulting to telemetry disabled")
        return False


def parse_env_file(file_path: Path) -> Dict[str, str]:
    """Parse an environment file and return a dictionary of key-value pairs."""
    config = {}
    if not file_path.exists():
        return config

    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            # Parse KEY=VALUE format
            match = re.match(r'^([A-Z_]+)=(.*)$', line)
            if match:
                key, value = match.groups()
                # Remove quotes if present
                value = value.strip('"').strip("'")
                config[key] = value

    return config


def write_env_file(file_path: Path, config: Dict[str, str], preserve_comments: bool = True):
    """Write configuration to an environment file.

    Handles three cases:
    1. Active config line (KEY=value) - replace with new value if key in config
    2. Commented config line (# KEY=value) - replace with active value if key in config
    3. Regular comments (# some text) - preserve as-is
    """
    # Read existing file to preserve comments and structure
    existing_lines = []
    existing_keys = set()

    # Pattern for commented-out config lines: # KEY=value or #KEY=value
    commented_config_pattern = re.compile(r'^#\s*([A-Z][A-Z0-9_]*)=')

    if file_path.exists() and preserve_comments:
        with open(file_path, 'r') as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    # Active config line
                    match = re.match(r'^([A-Z_]+)=', stripped)
                    if match:
                        key = match.group(1)
                        existing_keys.add(key)
                        if key in config:
                            # Replace with new value
                            existing_lines.append(f"{key}={config[key]}\n")
                        else:
                            # Keep existing line
                            existing_lines.append(line)
                    else:
                        existing_lines.append(line)
                elif stripped.startswith('#'):
                    # Check if this is a commented-out config line
                    commented_match = commented_config_pattern.match(stripped)
                    if commented_match:
                        key = commented_match.group(1)
                        if key in config:
                            # Replace commented default with active value
                            existing_lines.append(f"{key}={config[key]}\n")
                            existing_keys.add(key)
                        else:
                            # Keep the commented default as-is
                            existing_lines.append(line)
                    else:
                        # Regular comment - preserve as-is
                        existing_lines.append(line)
                else:
                    # Empty lines
                    existing_lines.append(line)

    # Add new keys that weren't in the file
    new_keys = set(config.keys()) - existing_keys
    if new_keys and existing_lines:
        # Add a newline before new entries if file has content
        if existing_lines and not existing_lines[-1].strip() == '':
            existing_lines.append('\n')

        # Add telemetry configuration section
        existing_lines.append("#############\n")
        existing_lines.append("# Telemetry Configuration\n")
        existing_lines.append("#############\n")
        existing_lines.append("\n")
        for key in sorted(new_keys):
            existing_lines.append(f"{key}={config[key]}\n")

    # Write the file
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        f.writelines(existing_lines if existing_lines else [f"{k}={v}\n" for k, v in sorted(config.items())])

    # Set appropriate permissions (readable/writable by owner only)
    os.chmod(file_path, 0o600)


def save_telemetry_preference(enabled: bool) -> bool:
    """Save user's telemetry preference to configuration file.

    Args:
        enabled: True to enable telemetry, False to disable

    Returns:
        True if saved successfully, False otherwise
    """
    config_path = USER_CONFIG_PATH
    if not config_path.exists() and LEGACY_CONFIG_PATH.exists():
        config_path = LEGACY_CONFIG_PATH

    try:
        # Read existing configuration
        config = parse_env_file(config_path)

        # Set VOICEMODE_TELEMETRY
        config["VOICEMODE_TELEMETRY"] = "true" if enabled else "false"

        # Write back to file
        write_env_file(config_path, config)

        return True

    except Exception as e:
        print(f"Warning: Failed to save telemetry preference: {e}")
        return False


def maybe_prompt_for_telemetry():
    """Check if telemetry prompt is needed and show it if appropriate.

    This is the main entry point for CLI commands to check and prompt
    for telemetry consent.

    If the user needs to be prompted, shows the prompt and saves their
    preference to the configuration file.
    """
    if not should_prompt_for_telemetry():
        return

    # Prompt user
    consent = prompt_for_telemetry_consent()

    if consent is None:
        # Prompt failed or was not shown
        return

    # Save preference
    if save_telemetry_preference(consent):
        if consent:
            print("\n✅ Telemetry enabled - Thank you!")
        else:
            print("\n✅ Telemetry disabled")

        print(f"Preference saved to: {USER_CONFIG_PATH}")
        print("You can change this anytime by editing the file or setting")
        print("VOICEMODE_TELEMETRY=true/false in your environment.\n")
    else:
        print("\n⚠️  Could not save preference to config file")
        print("You can manually set VOICEMODE_TELEMETRY=true/false")
        print(f"in {USER_CONFIG_PATH}\n")
