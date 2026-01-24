# DJ Mode

Background music control during VoiceMode sessions, powered by mpv with IPC.

## Quick Start

```bash
# Play Music For Programming (default content)
voicemode dj mfp play 49                   # Episode 49

# Play any audio with chapters
voicemode dj play file.mp3 --chapters file.txt   # Local file
voicemode dj play "https://..." --chapters f.txt # HTTP stream

# Control playback
voicemode dj status    # What's playing
voicemode dj next      # Skip to next track
voicemode dj volume 50 # Set volume (0-100)
voicemode dj stop      # Stop playback
```

## Commands

### Core Playback

| Command | Description |
|---------|-------------|
| `voicemode dj play <source> [--chapters <file>]` | Start playback |
| `voicemode dj status [--line]` | Show current track, position, volume |
| `voicemode dj pause` / `resume` | Pause or resume playback |
| `voicemode dj next` / `prev` | Navigate chapters |
| `voicemode dj volume [0-100]` | Get or set volume |
| `voicemode dj stop` | Stop playback |

### Music For Programming

| Command | Description |
|---------|-------------|
| `voicemode dj mfp list [--all]` | List episodes with chapters |
| `voicemode dj mfp play <episode>` | Play episode by number |
| `voicemode dj mfp sync [--force]` | Convert CUE files to FFmetadata |

### Music Library

| Command | Description |
|---------|-------------|
| `voicemode dj find <query>` | Search library by artist/album/title |
| `voicemode dj library scan [--path]` | Index music folder |
| `voicemode dj library stats` | Show library statistics |
| `voicemode dj history [--limit]` | Show play history |
| `voicemode dj favorite` | Toggle favorite on current track |

## Documentation

- [Music For Programming](mfp.md) - Primary content integration
- [Chapter Files](chapters.md) - FFmpeg format and CUE conversion
- [Installation](installation.md) - Setup mpv and dependencies
- [tmux Status Line](tmux-status.md) - Show current track in tmux
- [IPC Reference](ipc.md) - Raw socket commands

## Configuration

Set default startup volume in `~/.voicemode/voicemode.env`:

```bash
VOICEMODE_DJ_VOLUME=50   # Default: 50%
```

The DJ starts at 50% volume by default, which works well during voice conversations.

## Features

### Available Now

- HTTP streaming with chapter navigation
- CUE to FFmpeg chapters conversion
- Music For Programming episode playback
- RSS-based episode URL lookup with offline caching
- Volume, pause, skip, status commands
- Configurable default volume (VOICEMODE_DJ_VOLUME)
- IPC socket for programmatic control
- Play history tracking (last 100 sessions)
- Favorites system (save/list/remove tracks)
- [tmux status line integration](tmux-status.md) with color-coded warnings

### Planned

- **Smart Selection** - "Play something new" / "Play a favorite"
- **All MFP Episodes** - Chapter files for the full catalog
- **Local Caching** - Download episodes for offline playback

## History & Favorites

### Play History

Tracks played from the indexed music library are recorded:

```bash
voicemode dj history            # Show last 20 plays
voicemode dj history --limit 50 # Show last 50 plays
```

History is stored in the music library database (`~/.voicemode/dj/library.db`).

### Favorites

Toggle favorite status on the currently playing track:

```bash
voicemode dj favorite    # Toggle favorite on current track
voicemode dj find "*"    # Favorites marked with *
```

Note: History and favorites require tracks to be indexed in the music library.
Run `voicemode dj library scan` to index your music folder first.
