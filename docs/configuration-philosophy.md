# Configuration Philosophy

## Overview

Voice Mode takes a pragmatic approach to configuration that balances MCP best practices with user convenience. While most MCP servers rely solely on host-provided environment variables, Voice Mode also reads from optional configuration files.

## Why Voice Mode Reads Configuration Files

### 1. **Already Managing the Directory**
Voice Mode creates and manages the `~/.voicemode/` directory for audio files, logs, and other data. Adding configuration management is a natural extension.

### 2. **User Convenience**
- Users can view and edit configuration in a familiar file format
- No need to modify multiple host configuration files across different tools
- Easier onboarding for new users

### 3. **Reasonable Defaults**
Voice Mode can create an initial configuration file with sensible defaults, making it easier for users to understand available options.

## Configuration Precedence

Voice Mode follows standard configuration precedence:

1. **Environment variables** (highest priority) - Always win
2. **Project config** (`voicemode.env` in current directory)
3. **User config** (`~/.voicemode/voicemode.env`)
4. **Built-in defaults** (lowest priority)

## Not Against MCP Specification

The MCP specification doesn't prohibit servers from reading configuration files. The key principles we maintain:

- **Host configuration is authoritative** - Environment variables always override file-based config
- **No surprises** - Configuration loading is predictable and documented
- **Backwards compatible** - Works perfectly without any config files

## Best of Both Worlds

This approach provides:
- **MCP compliance** - Hosts can fully control configuration via environment variables
- **Standalone usage** - Users can run voice-mode directly with file-based config
- **Service integration** - Systemd/launchd services can use the same config files

## Example Usage

```bash
# Host-provided (highest priority)
export VOICEMODE_TTS_VOICES="nova,alloy"

# Or in ~/.voicemode/voicemode.env
VOICEMODE_TTS_VOICES="af_sky,nova"
VOICEMODE_WHISPER_MODEL="base"

# Environment variables always win over file config
```