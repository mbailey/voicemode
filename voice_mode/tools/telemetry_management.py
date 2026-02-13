"""Telemetry management tools for VoiceMode."""

import os
import re
from pathlib import Path
from typing import Dict

from voice_mode.server import mcp
from voice_mode.config import (
    logger,
    BASE_DIR,
    get_telemetry_status,
    is_telemetry_enabled,
)


# Configuration file path (user-level only for security)
USER_CONFIG_PATH = Path.home() / ".voicemode" / "voicemode.env"
# Legacy path for backwards compatibility
LEGACY_CONFIG_PATH = Path.home() / ".voicemode" / ".voicemode.env"


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

        # Group telemetry keys together
        telemetry_keys = sorted([k for k in new_keys if k.startswith('VOICEMODE_TELEMETRY')])
        other_keys = sorted([k for k in new_keys if not k.startswith('VOICEMODE_TELEMETRY')])

        if telemetry_keys:
            existing_lines.append("# Telemetry Configuration\n")
            for key in telemetry_keys:
                existing_lines.append(f"{key}={config[key]}\n")
            existing_lines.append('\n')

        if other_keys:
            existing_lines.append("# Additional Configuration\n")
            for key in other_keys:
                existing_lines.append(f"{key}={config[key]}\n")

    # Write the file
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        f.writelines(existing_lines if existing_lines else [f"{k}={v}\n" for k, v in sorted(config.items())])

    # Set appropriate permissions (readable/writable by owner only)
    os.chmod(file_path, 0o600)


@mcp.tool()
async def telemetry_set_preference(enabled: bool) -> str:
    """Set user's telemetry preference (opt-in or opt-out).

    This tool records the user's telemetry choice in the configuration file
    (~/.voicemode/voicemode.env) and reloads the configuration.

    Args:
        enabled: True to enable telemetry (opt-in), False to disable (opt-out)

    Returns:
        Confirmation message with the updated telemetry status

    Privacy note:
        - This tool only updates the local configuration file
        - No data is sent when opting out
        - When opting in, only anonymous usage stats are collected
        - Users can change their preference at any time
    """
    # Use user config path, check for legacy if new doesn't exist
    config_path = USER_CONFIG_PATH
    if not config_path.exists() and LEGACY_CONFIG_PATH.exists():
        config_path = LEGACY_CONFIG_PATH
        logger.warning(f"Using deprecated .voicemode.env - please rename to voicemode.env")

    # Check if DO_NOT_TRACK is set (overrides everything)
    if os.getenv("DO_NOT_TRACK") is not None:
        return """⚠️  Cannot change telemetry preference

DO_NOT_TRACK environment variable is set, which overrides all telemetry settings.
Telemetry is disabled and cannot be enabled while DO_NOT_TRACK is set.

To enable telemetry:
1. Unset the DO_NOT_TRACK environment variable
2. Use this tool again to set your preference

Note: DO_NOT_TRACK is a universal opt-out standard that disables telemetry
across many tools and services."""

    try:
        # Read existing configuration
        config = parse_env_file(config_path)

        # Set VOICEMODE_TELEMETRY
        new_value = "true" if enabled else "false"
        old_value = config.get("VOICEMODE_TELEMETRY", "ask")

        config["VOICEMODE_TELEMETRY"] = new_value

        # Write back to file
        write_env_file(config_path, config)

        # Log the change
        logger.info(f"Telemetry preference updated: {old_value} -> {new_value}")

        # Build response message
        lines = []
        if enabled:
            lines.append("✅ Telemetry enabled - Thank you!")
            lines.append("")
            lines.append("VoiceMode will now collect anonymous usage statistics to help")
            lines.append("improve the tool. This includes:")
            lines.append("  • Session counts and durations (binned)")
            lines.append("  • Voice exchanges per session")
            lines.append("  • TTS/STT provider usage")
            lines.append("  • Success/failure rates")
            lines.append("  • Anonymized error types")
            lines.append("")
            lines.append("Remember:")
            lines.append("  • No personal information is collected")
            lines.append("  • All data is anonymized")
            lines.append("  • You can opt-out anytime")
        else:
            lines.append("✅ Telemetry disabled")
            lines.append("")
            lines.append("VoiceMode will not collect any usage statistics.")
            lines.append("No data will be sent to any servers.")
            lines.append("")
            lines.append("You can enable telemetry later if you change your mind.")

        lines.append("")
        lines.append(f"Configuration saved to: {config_path}")
        lines.append(f"Previous setting: VOICEMODE_TELEMETRY={old_value}")
        lines.append(f"New setting: VOICEMODE_TELEMETRY={new_value}")
        lines.append("")
        lines.append("Note: Changes take effect immediately. The MCP server does not need")
        lines.append("to be restarted.")

        return "\n".join(lines)

    except Exception as e:
        logger.error(f"Failed to set telemetry preference: {e}")
        return f"❌ Failed to set telemetry preference: {str(e)}"


@mcp.tool()
async def telemetry_check_status() -> str:
    """Check current telemetry status and configuration.

    This tool provides a quick summary of the telemetry configuration without
    the detailed information shown in the telemetry status resource.

    Returns:
        Brief status message showing if telemetry is enabled and why
    """
    status = get_telemetry_status()

    lines = []
    lines.append("Telemetry Status")
    lines.append("=" * 40)
    lines.append("")

    # Status
    status_emoji = "✅" if status["enabled"] else "❌"
    lines.append(f"Status: {status_emoji} {'ENABLED' if status['enabled'] else 'DISABLED'}")
    lines.append(f"Reason: {status['reason']}")
    lines.append("")

    # Quick actions
    if status["voicemode_telemetry"] == "ask":
        lines.append("⚠️  User has not been prompted for telemetry consent")
        lines.append("")
        lines.append("Next steps:")
        lines.append("  1. Read voicemode://telemetry/opt-in-prompt for prompt text")
        lines.append("  2. Ask the user if they want to enable telemetry")
        lines.append("  3. Use telemetry_set_preference(enabled=true/false) to record choice")
    elif status["enabled"]:
        lines.append("Telemetry is active and collecting anonymous usage statistics.")
        lines.append("")
        lines.append("To disable:")
        lines.append("  • Use telemetry_set_preference(enabled=false)")
        lines.append("  • Or set DO_NOT_TRACK=1 environment variable")
    else:
        lines.append("Telemetry is disabled. No usage data is being collected.")
        lines.append("")
        lines.append("To enable:")
        if status["do_not_track"]:
            lines.append("  • Unset DO_NOT_TRACK environment variable")
            lines.append("  • Then use telemetry_set_preference(enabled=true)")
        else:
            lines.append("  • Use telemetry_set_preference(enabled=true)")

    lines.append("")
    lines.append("For more information:")
    lines.append("  • Read voicemode://telemetry/status resource")
    lines.append("  • See Privacy section in VoiceMode documentation")

    return "\n".join(lines)
