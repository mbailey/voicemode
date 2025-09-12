# Audio Controller MCP Server

MCP server providing audio playback control for Voice Mode using MPV.

## Features

- Play audio files and streams
- Volume control with ducking for speech
- Chapter/cue point navigation  
- Music for Programming episode streaming
- TTS playback integration
- Tool sound effects

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Make sure MPV is installed
brew install mpv  # macOS
sudo apt install mpv  # Linux
```

## Usage

### As MCP Server

Add to your MCP configuration:

```json
{
  "mcpServers": {
    "audio-controller": {
      "command": "python",
      "args": ["/path/to/audio_mcp_server.py"]
    }
  }
}
```

### Available Tools

- `play_audio` - Play file or URL
- `pause_audio` - Pause playback
- `resume_audio` - Resume playback
- `stop_audio` - Stop playback
- `set_volume` - Set volume (0-100)
- `duck_volume` - Lower volume for speech
- `restore_volume` - Restore normal volume
- `seek_audio` - Seek to position in seconds
- `seek_chapter` - Seek to named chapter
- `next_chapter` - Skip to next chapter
- `previous_chapter` - Go to previous chapter
- `get_playback_state` - Get current state
- `play_music_for_programming` - Play MfP episode
- `load_chapters` - Load chapter markers
- `play_tts` - Play TTS with auto ducking
- `play_tool_sound` - Play tool sound effect

### Standalone Testing

```python
from mpv_controller import MPVController

# Create controller
controller = MPVController()
controller.start()

# Play audio
controller.play("https://example.com/audio.mp3")
controller.set_volume(80)

# Play Music for Programming
controller.play_music_for_programming(1)
```

## Integration with Voice Mode

The MCP server integrates with Voice Mode to:
1. Play TTS outputs with automatic volume ducking
2. Provide background music during coding
3. Play sound effects for tool usage
4. Stream Music for Programming episodes

## Configuration

Future configuration options:
- Custom sound effect mappings
- Default volume levels
- Chapter file locations
- Cache directory for streams