# Audio Controller for Voice Mode

MPV-based audio playback controller integrated into Voice Mode.

## Features

- Audio file and stream playback
- Volume control with ducking for speech
- Chapter/cue point navigation
- Music for Programming episode streaming
- TTS playback integration
- Tool sound effects

## Configuration

Add to your Claude Desktop MCP configuration:

```json
{
  "mcpServers": {
    "audio-controller": {
      "type": "stdio",
      "command": "python",
      "args": [
        "-m",
        "voice_mode.mcp.audio_controller.audio_mcp_server"
      ]
    }
  }
}
```

Or use the integrated Voice Mode configuration with audio controller enabled:

```json
{
  "mcpServers": {
    "voicemode": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "voicemode"],
      "env": {
        "VOICEMODE_TOOLS": "converse,audio_controller"
      }
    }
  }
}
```

## Available MCP Tools

### Playback Control
- `play_audio` - Play file or URL
- `pause_audio` - Pause playback
- `resume_audio` - Resume playback  
- `stop_audio` - Stop playback

### Volume Control
- `set_volume` - Set volume (0-100)
- `duck_volume` - Lower volume for speech
- `restore_volume` - Restore normal volume

### Navigation
- `seek_audio` - Seek to position in seconds
- `seek_chapter` - Seek to named chapter
- `next_chapter` - Skip to next chapter
- `previous_chapter` - Go to previous chapter

### Special Features
- `play_music_for_programming` - Play MfP episode by number
- `play_tts` - Play TTS with auto ducking
- `play_tool_sound` - Play tool sound effect
- `load_chapters` - Load chapter markers
- `get_playback_state` - Get current state

## Requirements

- MPV media player installed
- Python 3.10+
- python-mpv-jsonipc package (automatically installed)

## Usage Examples

### Play background music
```
play_audio(source="https://musicforprogramming.net/sixty")
```

### Play Music for Programming episode
```
play_music_for_programming(episode=1)
```

### Volume ducking for TTS
```
play_tts(audio_file="/path/to/tts.mp3", duck=true)
```

### Chapter navigation
```
load_chapters(chapters=[
  {"title": "Intro", "time": 0},
  {"title": "Main", "time": 120}
])
seek_chapter(chapter="Main")
```