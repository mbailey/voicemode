# Chapter Files

DJ mode uses FFmpeg metadata format for chapters, loaded via mpv's `--chapters-file` option.

## Why FFmpeg Format?

CUE files cannot reference HTTP URLs - mpv treats the `FILE` directive as a local path. The solution is:
- Stream audio from HTTP URL as the main source
- Load chapter metadata from a separate FFmpeg-format file

## FFmpeg Chapters Format

```
;FFMETADATA1

[CHAPTER]
TIMEBASE=1/1000
START=1744000
END=3311000
title=Track Name - Artist

[CHAPTER]
TIMEBASE=1/1000
START=3311000
END=4036000
title=Another Track - Another Artist
```

### Fields

| Field | Description |
|-------|-------------|
| `TIMEBASE=1/1000` | Timestamps are in milliseconds |
| `START` | Chapter start time in ms |
| `END` | Chapter end time in ms |
| `title` | Display name (title + artist) |

## Converting from CUE

Use the `cue-to-chapters` script:

```bash
# Basic conversion
cue-to-chapters input.cue > chapters.txt

# With explicit duration for last chapter (in milliseconds)
cue-to-chapters input.cue 8042343 > chapters.txt
```

### What Gets Converted

| CUE Field | FFmpeg Field |
|-----------|--------------|
| `INDEX 01 MM:SS:FF` | `START` (converted to ms) |
| `TITLE` | Combined into `title` |
| `PERFORMER` | Combined into `title` |

### CUE Time Format

CUE uses `MM:SS:FF` where:
- `MM` = minutes
- `SS` = seconds
- `FF` = frames (75 frames per second)

The converter handles this automatically.

## Chapter Storage

Music For Programming chapters are stored in `~/.voicemode/music-for-programming/`:

```
~/.voicemode/music-for-programming/
├── music_for_programming_49-julien_mier.ffmeta       # Episode 49
├── music_for_programming_51-mücha.ffmeta             # Episode 51
└── ...
```

**Naming Convention:** Chapter files are named to match the RSS MP3 filename exactly (with `.ffmeta` extension instead of `.mp3`). This ensures automatic pairing with audio files.

Use `mfp-rss-helper filename <episode>` to get the correct filename base for any episode.

## Creating Chapters from Scratch

For audio without existing CUE files:

1. **Get tracklist** - Find track listing from source
2. **Download reference tracks** - Get audio for each track
3. **Match timestamps** - Use audio fingerprinting (MFCC correlation)
4. **Generate FFmpeg format** - Create chapter file

Tools for step 3: librosa (Python), chromaprint/fpcalc

## IPC Chapter Commands

Query chapters via raw IPC:

```bash
# List all chapters
echo '{"command": ["get_property", "chapter-list"]}' | socat - /tmp/voicemode-mpv.sock

# Get current chapter metadata
echo '{"command": ["get_property", "chapter-metadata"]}' | socat - /tmp/voicemode-mpv.sock

# Get current chapter index
echo '{"command": ["get_property", "chapter"]}' | socat - /tmp/voicemode-mpv.sock

# Jump to chapter by index
echo '{"command": ["set_property", "chapter", 3]}' | socat - /tmp/voicemode-mpv.sock
```
