"""Configuration management tools for voice-mode."""

import os
import re
from pathlib import Path
from typing import Dict, Optional, List
from voice_mode.server import mcp
from voice_mode.config import BASE_DIR
import logging

logger = logging.getLogger("voice-mode")

# Configuration file paths
USER_CONFIG_PATH = Path.home() / ".voicemode.env"
PROJECT_CONFIG_PATH = Path.cwd() / ".voicemode.env"


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
    """Write configuration to an environment file."""
    # Read existing file to preserve comments and structure
    existing_lines = []
    existing_keys = set()
    
    if file_path.exists() and preserve_comments:
        with open(file_path, 'r') as f:
            for line in f:
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
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
                else:
                    # Keep comments and empty lines
                    existing_lines.append(line)
    
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
                existing_lines.append(f"{key}={config[key]}\n")
            existing_lines.append('\n')
        
        if kokoro_keys:
            existing_lines.append("# Kokoro Configuration\n")
            for key in kokoro_keys:
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
async def update_config(key: str, value: str, scope: str = "user") -> str:
    """Update a configuration value in the voicemode.env file.
    
    Args:
        key: The configuration key to update (e.g., 'VOICEMODE_TTS_VOICES')
        value: The new value for the configuration
        scope: Where to save the config - 'user' (~/.voicemode.env) or 'project' (./.voicemode.env)
    
    Returns:
        Confirmation message with the updated configuration
    """
    # Validate key format
    if not re.match(r'^[A-Z_]+$', key):
        return f"❌ Invalid key format: {key}. Keys must be uppercase with underscores only."
    
    # Determine which config file to use
    config_path = USER_CONFIG_PATH if scope == "user" else PROJECT_CONFIG_PATH
    
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
            ("VOICEMODE_DEBUG", "Enable debug mode (true/false)"),
            ("VOICEMODE_SAVE_ALL", "Save all audio and transcriptions (true/false)"),
            ("VOICEMODE_SAVE_AUDIO", "Save audio files (true/false)"),
            ("VOICEMODE_SAVE_TRANSCRIPTIONS", "Save transcription files (true/false)"),
            ("VOICEMODE_AUDIO_FEEDBACK", "Enable audio feedback (true/false)"),
        ]),
        ("Provider Configuration", [
            ("VOICEMODE_TTS_BASE_URLS", "Comma-separated list of TTS endpoints"),
            ("VOICEMODE_STT_BASE_URLS", "Comma-separated list of STT endpoints"),
            ("VOICEMODE_TTS_VOICES", "Comma-separated list of preferred voices"),
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
    
    lines.append("💡 Usage: update_config(key='VOICEMODE_TTS_VOICES', value='af_sky,nova', scope='user')")
    
    return "\n".join(lines)