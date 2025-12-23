"""Configuration management tools for voice-mode."""

import os
import re
from pathlib import Path
from typing import Dict, Optional, List
from voice_mode.server import mcp
from voice_mode.config import BASE_DIR, reload_configuration, find_voicemode_env_files
import logging

logger = logging.getLogger("voicemode")

# Configuration file path (user-level only for security)
USER_CONFIG_PATH = Path.home() / ".voicemode" / "voicemode.env"
# Legacy path for backwards compatibility
LEGACY_CONFIG_PATH = Path.home() / ".voicemode" / ".voicemode.env"


def parse_env_file(file_path: Path) -> Dict[str, str]:
    """Parse an environment file and return a dictionary of key-value pairs.

    Handles multiline quoted values like:
        VOICEMODE_PRONOUNCE="
        TTS \\bJSON\\b jason
        TTS \\bYAML\\b yammel
        "
    """
    config = {}
    if not file_path.exists():
        return config

    with open(file_path, 'r') as f:
        lines = f.readlines()

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip empty lines and comments
        if not line or line.startswith('#'):
            i += 1
            continue

        # Parse KEY=VALUE format
        match = re.match(r'^([A-Z_][A-Z0-9_]*)=(.*)$', line)
        if match:
            key, value = match.groups()

            # Handle multiline quoted values
            if value and value[0] in ('"', "'"):
                quote_char = value[0]
                # Check if the quote is closed on the same line
                if len(value) > 1 and value.endswith(quote_char):
                    # Single line quoted value - strip quotes
                    value = value[1:-1]
                else:
                    # Multiline quoted value - collect lines until closing quote
                    value_parts = [value[1:]]  # Start after opening quote
                    i += 1
                    while i < len(lines):
                        next_line = lines[i].rstrip('\n')
                        if next_line.rstrip().endswith(quote_char):
                            # Found closing quote - strip it and any trailing whitespace before it
                            closing_line = next_line.rstrip()
                            value_parts.append(closing_line[:-1])
                            break
                        else:
                            value_parts.append(next_line)
                        i += 1
                    value = '\n'.join(value_parts)

            config[key] = value

        i += 1

    return config


def _format_env_value(value: str) -> str:
    """Format a value for writing to an env file.

    Quotes values that contain newlines, spaces, or special characters.
    """
    if '\n' in value:
        # Multiline value - use double quotes
        return f'"{value}\n"'
    elif ' ' in value or '#' in value or '"' in value or "'" in value:
        # Value needs quoting - escape any existing quotes
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def write_env_file(file_path: Path, config: Dict[str, str], preserve_comments: bool = True):
    """Write configuration to an environment file.

    Handles three cases:
    1. Active config line (KEY=value) - replace with new value if key in config
    2. Commented config line (# KEY=value) - replace with active value if key in config
    3. Regular comments (# some text) - preserve as-is

    Properly handles multiline quoted values by skipping continuation lines.
    """
    # Read existing file to preserve comments and structure
    existing_lines = []
    existing_keys = set()
    # Track keys that were found as commented defaults (to avoid adding them again)
    commented_keys_replaced = set()

    # Pattern for commented-out config lines: # KEY=value or #KEY=value
    commented_config_pattern = re.compile(r'^#\s*([A-Z][A-Z0-9_]*)=')

    if file_path.exists() and preserve_comments:
        with open(file_path, 'r') as f:
            lines = f.readlines()

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if stripped and not stripped.startswith('#'):
                # Active config line
                match = re.match(r'^([A-Z_][A-Z0-9_]*)=(.*)$', stripped)
                if match:
                    key = match.group(1)
                    value_start = match.group(2)
                    existing_keys.add(key)

                    # Check if this is a multiline quoted value
                    is_multiline = False
                    if value_start and value_start[0] in ('"', "'"):
                        quote_char = value_start[0]
                        if not (len(value_start) > 1 and value_start.endswith(quote_char)):
                            # Multiline value - skip until closing quote
                            is_multiline = True
                            i += 1
                            while i < len(lines):
                                if lines[i].rstrip().endswith(quote_char):
                                    i += 1
                                    break
                                i += 1

                    if key in config:
                        # Replace with new value (properly formatted)
                        formatted_value = _format_env_value(config[key])
                        existing_lines.append(f"{key}={formatted_value}\n")
                    else:
                        # Keep existing line(s)
                        if is_multiline:
                            # Re-read the multiline value from original position
                            orig_i = i - 1
                            while orig_i >= 0:
                                test_line = lines[orig_i].strip()
                                if re.match(r'^([A-Z_][A-Z0-9_]*)=', test_line):
                                    break
                                orig_i -= 1
                            # Add all lines of the multiline value
                            while orig_i < i:
                                existing_lines.append(lines[orig_i])
                                orig_i += 1
                        else:
                            existing_lines.append(line)

                    if not is_multiline:
                        i += 1
                    continue
                else:
                    existing_lines.append(line)
            elif stripped.startswith('#'):
                # Check if this is a commented-out config line
                commented_match = commented_config_pattern.match(stripped)
                if commented_match:
                    key = commented_match.group(1)
                    if key in config:
                        # Replace commented default with active value
                        formatted_value = _format_env_value(config[key])
                        existing_lines.append(f"{key}={formatted_value}\n")
                        existing_keys.add(key)
                        commented_keys_replaced.add(key)
                    else:
                        # Keep the commented default as-is
                        existing_lines.append(line)
                else:
                    # Regular comment - preserve as-is
                    existing_lines.append(line)
            else:
                # Empty lines
                existing_lines.append(line)

            i += 1
    
    # Add new keys that weren't in the file
    new_keys = set(config.keys()) - existing_keys
    if new_keys and existing_lines:
        # Add a newline before new entries if file has content
        if existing_lines and not existing_lines[-1].strip() == '':
            existing_lines.append('\n')
        
        # Group new keys by category
        whisper_keys = sorted([k for k in new_keys if k.startswith('VOICEMODE_WHISPER_')])
        kokoro_keys = sorted([k for k in new_keys if k.startswith('VOICEMODE_KOKORO_')])
        other_keys = sorted([k for k in new_keys if not k.startswith('VOICEMODE_WHISPER_') and not k.startswith('VOICEMODE_KOKORO_')])
        
        if whisper_keys:
            existing_lines.append("# Whisper Configuration\n")
            for key in whisper_keys:
                formatted_value = _format_env_value(config[key])
                existing_lines.append(f"{key}={formatted_value}\n")
            existing_lines.append('\n')

        if kokoro_keys:
            existing_lines.append("# Kokoro Configuration\n")
            for key in kokoro_keys:
                formatted_value = _format_env_value(config[key])
                existing_lines.append(f"{key}={formatted_value}\n")
            existing_lines.append('\n')

        if other_keys:
            existing_lines.append("# Additional Configuration\n")
            for key in other_keys:
                formatted_value = _format_env_value(config[key])
                existing_lines.append(f"{key}={formatted_value}\n")

    # Write the file
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
        if existing_lines:
            f.writelines(existing_lines)
        else:
            for k, v in sorted(config.items()):
                formatted_value = _format_env_value(v)
                f.write(f"{k}={formatted_value}\n")
    
    # Set appropriate permissions (readable/writable by owner only)
    os.chmod(file_path, 0o600)


@mcp.tool()
async def update_config(key: str, value: str) -> str:
    """Update a configuration value in the voicemode.env file.
    
    Args:
        key: The configuration key to update (e.g., 'VOICEMODE_VOICES')
        value: The new value for the configuration
    
    Returns:
        Confirmation message with the updated configuration
    """
    # Validate key format
    if not re.match(r'^[A-Z_]+$', key):
        return f"❌ Invalid key format: {key}. Keys must be uppercase with underscores only."
    
    # Use user config path, check for legacy if new doesn't exist
    config_path = USER_CONFIG_PATH
    if not config_path.exists() and LEGACY_CONFIG_PATH.exists():
        config_path = LEGACY_CONFIG_PATH
        logger.warning(f"Using deprecated .voicemode.env - please rename to voicemode.env")
    
    try:
        # Read existing configuration
        config = parse_env_file(config_path)
        
        # Store old value for reporting
        old_value = config.get(key, "[not set]")
        
        # Update the configuration
        config[key] = value
        
        # Write back to file
        write_env_file(config_path, config)
        
        # Report the change
        logger.info(f"Updated {key} in {config_path}")
        
        return f"""✅ Configuration updated successfully!

File: {config_path}
Key: {key}
Old Value: {old_value}
New Value: {value}

Note: You may need to restart services or reload the configuration for changes to take effect."""
        
    except Exception as e:
        logger.error(f"Failed to update configuration: {e}")
        return f"❌ Failed to update configuration: {str(e)}"


@mcp.tool()
async def list_config_keys() -> str:
    """List all available configuration keys with their descriptions.
    
    Returns:
        A formatted list of all VOICEMODE_* configuration keys and their purposes
    """
    config_keys = [
        ("Core Configuration", [
            ("VOICEMODE_BASE_DIR", "Base directory for all voicemode data (default: ~/.voicemode)"),
            ("VOICEMODE_MODELS_DIR", "Directory for all models (default: $VOICEMODE_BASE_DIR/models)"),
            ("VOICEMODE_DEBUG", "Enable debug mode (true/false)"),
            ("VOICEMODE_SAVE_ALL", "Save all audio and transcriptions (true/false)"),
            ("VOICEMODE_SAVE_AUDIO", "Save audio files (true/false)"),
            ("VOICEMODE_SAVE_TRANSCRIPTIONS", "Save transcription files (true/false)"),
            ("VOICEMODE_AUDIO_FEEDBACK", "Enable audio feedback (true/false)"),
        ]),
        ("Provider Configuration", [
            ("VOICEMODE_TTS_BASE_URLS", "Comma-separated list of TTS endpoints"),
            ("VOICEMODE_STT_BASE_URLS", "Comma-separated list of STT endpoints"),
            ("VOICEMODE_VOICES", "Comma-separated list of preferred voices"),
            ("VOICEMODE_TTS_MODELS", "Comma-separated list of preferred models"),
            ("VOICEMODE_PREFER_LOCAL", "Prefer local providers over cloud (true/false)"),
            ("VOICEMODE_ALWAYS_TRY_LOCAL", "Always attempt local providers (true/false)"),
            ("VOICEMODE_AUTO_START_KOKORO", "Auto-start Kokoro service (true/false)"),
        ]),
        ("Whisper Configuration", [
            ("VOICEMODE_WHISPER_MODEL", "Whisper model to use (e.g., large-v2)"),
            ("VOICEMODE_WHISPER_PORT", "Whisper server port (default: 2022)"),
            ("VOICEMODE_WHISPER_LANGUAGE", "Language for transcription (default: auto)"),
            ("VOICEMODE_WHISPER_MODEL_PATH", "Path to Whisper models"),
        ]),
        ("Kokoro Configuration", [
            ("VOICEMODE_KOKORO_PORT", "Kokoro server port (default: 8880)"),
            ("VOICEMODE_KOKORO_MODELS_DIR", "Directory for Kokoro models"),
            ("VOICEMODE_KOKORO_CACHE_DIR", "Directory for Kokoro cache"),
            ("VOICEMODE_KOKORO_DEFAULT_VOICE", "Default Kokoro voice (e.g., af_sky)"),
        ]),
        ("API Keys", [
            ("OPENAI_API_KEY", "OpenAI API key for cloud TTS/STT"),
            ("LIVEKIT_URL", "LiveKit server URL (default: ws://127.0.0.1:7880)"),
            ("LIVEKIT_API_KEY", "LiveKit API key"),
            ("LIVEKIT_API_SECRET", "LiveKit API secret"),
        ]),
    ]
    
    lines = ["Available Configuration Keys", "=" * 50, ""]
    
    for category, keys in config_keys:
        lines.append(f"{category}:")
        lines.append("-" * len(category))
        for key, description in keys:
            lines.append(f"  {key}")
            lines.append(f"    {description}")
        lines.append("")
    
    lines.append("💡 Usage: update_config(key='VOICEMODE_VOICES', value='af_sky,nova')")
    
    return "\n".join(lines)


@mcp.tool()
async def config_reload() -> str:
    """Reload configuration from .voicemode.env files and clear all caches.
    
    This tool reloads configuration from:
    1. Global ~/.voicemode/voicemode.env file
    2. Project-specific .voicemode.env files (searched up directory tree)
    3. Environment variables (highest priority)
    
    Returns:
        Status message showing which files were loaded and any changes
    """
    try:
        # Get config files before reload
        old_files = find_voicemode_env_files()
        
        # Reload configuration 
        reload_configuration()
        
        # Get config files after reload
        new_files = find_voicemode_env_files()
        
        lines = ["✅ Configuration reloaded successfully!", ""]
        
        if new_files:
            lines.append("📁 Configuration files loaded (in order):")
            for i, config_file in enumerate(new_files, 1):
                lines.append(f"  {i}. {config_file}")
        else:
            lines.append("📁 No configuration files found - using defaults")
        
        lines.append("")
        lines.append("🔄 All caches have been cleared")
        lines.append("📊 Voice preferences and provider settings updated")
        
        logger.info(f"Configuration reloaded from {len(new_files)} files")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Failed to reload configuration: {e}")
        return f"❌ Failed to reload configuration: {str(e)}"


@mcp.tool()
async def show_config_files() -> str:
    """Show which .voicemode.env files are being used for configuration.
    
    This shows the current configuration file discovery and loading order:
    - Global configuration from ~/.voicemode/voicemode.env
    - Project-specific configuration (searched up directory tree)
    - Current working directory for context
    
    Returns:
        Formatted list of configuration files and their status
    """
    try:
        config_files = find_voicemode_env_files()
        
        lines = ["📋 Voice Mode Configuration Files", "=" * 40, ""]
        lines.append(f"🗂️  Current directory: {Path.cwd()}")
        lines.append("")
        
        if config_files:
            lines.append("📁 Configuration files (loading order):")
            lines.append("")
            
            for i, config_file in enumerate(config_files, 1):
                status = "✅ EXISTS" if config_file.exists() else "❌ MISSING"
                file_type = ""
                
                if config_file.name == "voicemode.env" and config_file.parent.name == ".voicemode":
                    if config_file.parent == Path.home() / ".voicemode":
                        file_type = " (Global)"
                    else:
                        file_type = " (Project - in .voicemode dir)"
                elif config_file.name == ".voicemode.env":
                    if config_file.parent == Path.cwd():
                        file_type = " (Project - current dir)"
                    else:
                        file_type = " (Project - parent dir)"
                
                lines.append(f"  {i}. {config_file}{file_type}")
                lines.append(f"     {status}")
                lines.append("")
        else:
            lines.append("❌ No configuration files found")
            lines.append("")
            lines.append("💡 Tip: Create ~/.voicemode/voicemode.env for global configuration")
            lines.append("💡 Tip: Create .voicemode.env in project directories for project-specific settings")
        
        lines.append("")
        lines.append("🔄 Use reload_config() to reload after making changes")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Failed to show config files: {e}")
        return f"❌ Failed to show config files: {str(e)}"
