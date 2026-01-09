# DJ Mode

Background music control during VoiceMode sessions, powered by mpv with IPC.

## Quick Start

```bash
# Play Music For Programming (default content)
mpv-dj mfp 76                              # Episode 76

# Play any audio with chapters
mpv-dj play file.mp3 --chapters file.txt   # Local file
mpv-dj play "https://..." --chapters f.txt # HTTP stream

# Control playback
mpv-dj status    # What's playing
mpv-dj next      # Skip to next track
mpv-dj volume 50 # Set volume (0-100)
mpv-dj stop      # Stop playback
```

## Commands

| Command | Description |
|---------|-------------|
| `mpv-dj play <source> [--chapters <file>]` | Start playback |
| `mpv-dj mfp <episode>` | Play Music For Programming episode |
| `mpv-dj status` | Show current track, position, volume |
| `mpv-dj pause` / `resume` | Pause or resume playback |
| `mpv-dj next` / `prev` | Navigate chapters |
| `mpv-dj volume <0-100>` | Set volume |
| `mpv-dj stop` | Stop playback |
| `mpv-dj history [limit]` | Show play history |
| `mpv-dj favorite [add\|list\|remove]` | Manage favorites |
| `mpv-dj raw '<json>'` | Send raw IPC command |

## Documentation

- [Music For Programming](mfp.md) - Primary content integration
- [Chapter Files](chapters.md) - FFmpeg format and CUE conversion
- [Installation](installation.md) - Setup mpv and dependencies
- [IPC Reference](ipc.md) - Raw socket commands

## Features

### Available Now

- HTTP streaming with chapter navigation
- CUE to FFmpeg chapters conversion
- Music For Programming episode playback
- Volume, pause, skip, status commands
- IPC socket for programmatic control
- Play history tracking (last 100 sessions)
- Favorites system (save/list/remove tracks)

### Planned

- **Smart Selection** - "Play something new" / "Play a favorite"
- **All MFP Episodes** - Chapter files for the full catalog
- **Local Caching** - Download episodes for offline playback

## History & Favorites

### Play History

Every MFP episode played is recorded:

```bash
mpv-dj history       # Show last 10
mpv-dj history 20    # Show last 20
```

History stored in `~/.voicemode/dj/history.json` (last 100 entries).

### Favorites

Save tracks you like while playing:

```bash
mpv-dj favorite add         # Save current track
mpv-dj favorite list        # Show all favorites
mpv-dj favorite remove 1    # Remove by index
```

Favorites include track title, source, and timestamp position.
Data stored in `~/.voicemode/dj/favorites.json`.
