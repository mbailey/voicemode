# VoiceMode Converse Code Path Guide

## Overview
This guide traces the code path from running `voicemode converse` through all the relevant files.

## Code Path

### 1. Entry Point: Package Configuration
**File:** `pyproject.toml`
**Lines:** 100-102
```toml
[project.scripts]
voice-mode = "voice_mode.cli:voice_mode"
voicemode = "voice_mode.cli:voice_mode"
```
Both commands map to the `voice_mode()` function in the CLI module.

### 2. CLI Entry Function
**File:** `voice_mode/cli.py`
**Function:** `voice_mode()`
**Lines:** 74-76
```python
def voice_mode() -> None:
    """Entry point for voicemode command - starts the MCP server or runs subcommands."""
    voice_mode_main_cli()
```
This calls the main CLI group.

### 3. Main CLI Group
**File:** `voice_mode/cli.py`
**Function:** `voice_mode_main_cli()`
**Lines:** 40-72
This is a Click command group that handles all subcommands. Without a subcommand, it starts the MCP server. With subcommands, it routes to the appropriate handler.

### 4. Converse Subcommand
**File:** `voice_mode/cli.py`
**Decorator:** `@voice_mode_main_cli.command()`
**Function:** `converse()`
**Lines:** 1650-1815

Key parameters:
- `--message, -m`: Initial message to speak
- `--wait/--no-wait`: Whether to wait for response
- `--duration, -d`: Listen duration
- `--voice`: TTS voice to use
- `--tts-provider`: OpenAI or Kokoro
- `--continuous, -c`: Continuous conversation mode

The function creates an async wrapper (line 1690) that calls the actual tool implementation.

### 5. Converse Tool Implementation
**File:** `voice_mode/tools/converse.py`
**Decorator:** `@mcp.tool()`
**Function:** `converse()`
**Lines:** 1194-1195 (and beyond)

This is the main MCP tool that handles:
- Voice synthesis (TTS)
- Voice recognition (STT)
- Provider selection
- Audio playback and recording
- Conversation logging

Key imports:
- Line 61-70: Core functions from `voice_mode.core`
- Line 60: Provider registry from `voice_mode.provider_discovery`
- Line 28: Conversation logger

### 6. Core Audio Functions
**File:** `voice_mode/core.py`

Key functions:
- `get_openai_clients()` - Line 131: Initialize API clients
- `text_to_speech()` - Line 163: Convert text to audio
- `play_chime_start()` - Line 612: Play start chime
- `play_chime_end()` - Line 644: Play end chime
- `generate_chime()` - Line 528: Generate chime audio
- `cleanup()` - Line 676: Cleanup resources

### 7. Provider Discovery
**File:** `voice_mode/provider_discovery.py`

Discovers and manages TTS/STT providers:
- OpenAI API (cloud)
- Whisper.cpp (local STT)
- Kokoro (local TTS)
- LiveKit (real-time communication)

The provider registry is imported at line 60 of converse.py and used to select the best available provider.

### 8. Configuration
**File:** `voice_mode/config.py`

Loaded by converse.py (lines 29-58), provides:
- Audio settings (sample rate, channels)
- Service endpoints
- Debug flags
- Audio feedback settings
- Silence detection parameters

---

## Demonstration Script

### Setup
```bash
# Terminal control pattern: Use show tool with neovim panes
# After each step, use look tool to confirm the pane is showing correctly
```

### Step 1: Show Entry Point
```bash
# Show pyproject.toml focusing on scripts section
show pyproject.toml
look  # Confirm it's visible
# Highlight lines 100-102 in neovim
```

### Step 2: Show CLI Entry Functions
```bash
# Show the voice_mode() entry point
show voice_mode/cli.py:74-76
look  # Confirm visible

# Show the main CLI group
show voice_mode/cli.py:40-72
look  # Confirm visible
```

### Step 3: Show Converse Command
```bash
# Show the converse subcommand definition
show voice_mode/cli.py:1650-1700
look  # Confirm visible

# Search for the async wrapper
# Navigate to line 1690 to show how it calls the tool
```

### Step 4: Show Tool Implementation
```bash
# Open the converse tool file
show voice_mode/tools/converse.py:1194
look  # Confirm visible

# Show the key imports
show voice_mode/tools/converse.py:1-100
look  # Confirm visible
```

### Step 5: Show Core Functions
```bash
# Show the core module with TTS/STT functions
show voice_mode/core.py
look  # Confirm visible

# Highlight text_to_speech function
# Search for: /^async def text_to_speech
```

### Step 6: Show Provider Discovery
```bash
# Show provider discovery system
show voice_mode/provider_discovery.py
look  # Confirm visible
```

---

## Voice Demonstration Script

While showing each file, use voice to narrate:

```python
converse("Let's trace the voicemode converse command. First, the entry point is in pyproject.toml.", wait_for_response=False)
# Then show pyproject.toml

converse("When you run voicemode converse, it calls voice_mode function in cli.py", wait_for_response=False)
# Then show cli.py entry

converse("This routes to the converse subcommand, which is a Click command", wait_for_response=False)
# Then show converse function

converse("The CLI wraps the actual MCP tool, which is in tools/converse.py", wait_for_response=False)
# Then show tools/converse.py

converse("The tool uses core functions for text-to-speech and speech-to-text", wait_for_response=False)
# Then show core.py

converse("Provider discovery finds available TTS and STT services", wait_for_response=False)
# Then show provider_discovery.py
```

---

## Summary Flow

```
User runs: voicemode converse
    ↓
pyproject.toml (scripts) → voice_mode.cli:voice_mode
    ↓
cli.py:voice_mode() → voice_mode_main_cli()
    ↓
cli.py:converse() command (Click subcommand)
    ↓
tools/converse.py:converse() (MCP tool)
    ↓
Parallel operations:
- core.py:text_to_speech() → Speak the message
- Recording → Listen for response
- core.py:play_chime_start/end() → Audio feedback
- provider_discovery.py → Select TTS/STT providers
    ↓
Return transcribed response to user
```

## Key Concepts

1. **Click CLI Framework**: Handles command parsing and routing
2. **FastMCP Tools**: MCP tool decorator makes functions available to AI
3. **Provider Registry**: Dynamic discovery of local/cloud services
4. **Async/Await**: All voice operations are asynchronous
5. **Configuration**: Environment-based with sensible defaults
