---
name: voicemode-dj
description: Background music control for VoiceMode voice sessions using mpv
---

# VoiceMode DJ

Background music control during VoiceMode sessions via `voicemode dj` commands.

## Quick Reference

```bash
voicemode dj play <file|url>     # Start playback
voicemode dj stop                # Stop playback
voicemode dj mfp play <episode>  # Play MFP episode
voicemode dj status              # What's playing
voicemode dj next / prev         # Chapter navigation
voicemode dj volume [0-100]      # Get/set volume
voicemode dj find <query>        # Search library
```

## Documentation

- [Commands](../../docs/reference/dj/commands.md) - Full command reference
- [Music For Programming](../../docs/reference/dj/mfp.md) - MFP episode integration
- [Chapter Files](../../docs/reference/dj/chapters.md) - FFmpeg chapter format
- [Installation](../../docs/reference/dj/installation.md) - Setup requirements
- [IPC Reference](../../docs/reference/dj/ipc.md) - Low-level mpv control

## Programmatic Access

```python
from voice_mode import DJController, MfpService, MusicLibrary
```

## Configuration

`~/.voicemode/voicemode.env`:
```bash
VOICEMODE_DJ_VOLUME=50   # Default startup volume
```
