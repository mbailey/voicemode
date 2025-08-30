# Voice Preferences with .voicemode.env

Voice Mode uses a unified `.voicemode.env` configuration system that allows you to set voice preferences and other configuration options per project or globally. This provides a consistent way to maintain voice settings and other configuration without environment variables.

## Configuration File Discovery

Voice Mode searches for configuration files in this order:

1. **Project-level** (walks up from current directory):
   - `.voicemode.env` (in project root)  
   - `.voicemode/voicemode.env` (in .voicemode directory)
2. **Global** (in user's home directory):
   - `~/.voicemode/voicemode.env` (primary global configuration)

The system uses cascading configuration where files found first take precedence, similar to how Claude Code handles CLAUDE.md files.

## File Format

The `.voicemode.env` file uses simple `KEY=value` format:

```bash
# Voice preferences for this project
VOICEMODE_VOICES=af_sky,nova,alloy
VOICEMODE_DEBUG=true
VOICEMODE_SAVE_AUDIO=false
```

- One setting per line: `KEY=value`
- Comments start with `#`
- Empty lines are ignored
- No quotes needed around values
- Comma-separated lists for multiple values

## Voice Configuration

Configure voice preferences using the `VOICEMODE_VOICES` setting:

```bash
# Preferred voices (comma-separated, tried in order)
VOICEMODE_VOICES=af_sky,nova,shimmer
```

Voice selection follows this priority:
1. **Environment variables** (highest priority)
2. **Project .voicemode.env files** (cascading from current directory up)  
3. **Global ~/.voicemode/voicemode.env**
4. **Built-in defaults** (lowest priority)

## Examples

### Project-Specific Voices
**`.voicemode.env` in project root:**
```bash
# Creative writing project - expressive voices
VOICEMODE_VOICES=shimmer,fable,nova
VOICEMODE_SAVE_TRANSCRIPTIONS=true
```

**`.voicemode/voicemode.env` in project's .voicemode directory:**
```bash
# Development project with Kokoro voice
VOICEMODE_VOICES=af_sky,am_adam
VOICEMODE_DEBUG=true
```

### Global User Preferences
**`~/.voicemode/voicemode.env`:**
```bash
# My default voice preferences
VOICEMODE_VOICES=af_sky,nova
VOICEMODE_SAVE_ALL=false
OPENAI_API_KEY=your-api-key-here
```

## Configuration Management

Use the MCP configuration tools for runtime management:

- `config_reload()` - Reload configuration from all files
- `show_config_files()` - View which files are being loaded
- `update_config()` - Update specific settings

## Migration from .voices.txt

The old `.voices.txt` system has been replaced. To migrate:

**Old `.voices.txt`:**
```
af_sky
nova
alloy
```

**New `.voicemode.env`:**
```bash
VOICEMODE_VOICES=af_sky,nova,alloy
```

This unified approach allows voice preferences alongside all other Voice Mode configuration in a single, consistent format.