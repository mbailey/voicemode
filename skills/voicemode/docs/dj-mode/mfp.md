# Music For Programming Integration

[Music For Programming](https://musicforprogramming.net) is a series of ambient/electronic mixes curated for deep work. DJ mode integrates this as its primary content source.

## Playing Episodes

```bash
# Play by episode number
mpv-dj mfp 76    # Episode 76 (Material Object)
mpv-dj mfp 49    # Episode 49 (Julien Mier)
```

The command:
1. Checks for local cached audio in `~/.voicemode/music-for-programming/`
2. If not cached, streams from `https://datashat.net/music_for_programming_{episode}-*.mp3`
3. Loads chapter metadata for track-level navigation

## File Structure

All MFP files live in `~/.voicemode/music-for-programming/`:

```
~/.voicemode/music-for-programming/
├── 049_Episode_49_Julien_Mier.mp3      # Audio (downloaded or cached)
├── 049_Episode_49_Julien_Mier.cue      # CUE sheet (for local playback)
├── 049_Episode_49_Julien_Mier.ffmeta   # FFMETADATA chapters (for streaming)
├── 076_Episode_76_Material_Object.mp3
├── 076_Episode_76_Material_Object.cue
├── 076_Episode_76_Material_Object.ffmeta
└── ...
```

**File Types:**
- `.mp3` - Audio file (downloaded by user or cached during streaming)
- `.cue` - CUE sheet with track timestamps (for local mpv playback)
- `.ffmeta` - FFMETADATA chapters (for HTTP streaming where CUE doesn't work)

**LLM Access:** You can read CUE files to search for tracks across episodes. Example: "Which episode has Boards of Canada?" - search the CUE files for artist names.

## Episode URLs

Music For Programming hosts audio at predictable URLs:
```
https://datashat.net/music_for_programming_76-material_object.mp3
```

The episode number and curator name form the filename. Episodes are freely downloadable from the website.

## Streaming vs Local

| Mode | When | Chapter File |
|------|------|--------------|
| **Streaming** | Audio not cached locally | `.ffmeta` (FFMETADATA format) |
| **Local** | Audio exists in music-for-programming/ | `.cue` (CUE sheet format) |

The mpv-dj tool automatically:
1. Checks for local audio file first
2. Falls back to HTTP streaming if not found
3. Uses appropriate chapter format for each mode

### Caching Streams

To save an episode while streaming (future feature):
```bash
mpv-dj mfp 49 --cache  # Stream and save to local directory
```

## Chapter Metadata

Chapters enable track-level navigation within episodes. Each chapter identifies:
- Track title
- Artist/performer
- Timestamp

With chapters loaded, you can:
- Ask "what's playing?" and get the actual track name
- Skip forward/backward by track (not arbitrary seek)
- See track information in `mpv-dj status`

### Creating Chapter Files

Chapter files are created by:
1. Getting the tracklist from musicforprogramming.net
2. Downloading reference tracks
3. Using MFCC fingerprinting to find timestamps
4. Converting results to CUE and FFMETADATA formats

See [chapters.md](chapters.md) for the chapter file format details.

### Chapter Distribution

VoiceMode includes chapter files for select episodes. These are copied to `~/.voicemode/music-for-programming/` on install.

Available chapters (Mike's favorites):
- Episode 44, 49, 51, 52, 66, 70, 71, 74, 76

More episodes can be added via community PRs.

## Episode Discovery

### Current
- Request episodes by number: `mpv-dj mfp 49`
- List available chapters: `ls ~/.voicemode/music-for-programming/*.cue`
- Search tracks: `grep "Boards of Canada" ~/.voicemode/music-for-programming/*.cue`

### Planned
- **History tracking**: What episodes have been played
- **Favorites**: Mark episodes you enjoyed
- **Suggestions**: "Play something new" selects unplayed episodes
- **Episode index**: Full catalog with curator names

## Collaboration Opportunity

The chapter generation process could be shared with the Music For Programming curator (Datasette) to:
- Provide chapters for all ~90 episodes
- Enable richer track metadata
- Create a great partnership for promotion
