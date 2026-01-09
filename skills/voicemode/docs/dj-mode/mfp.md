# Music For Programming Integration

[Music For Programming](https://musicforprogramming.net) is a series of ambient/electronic mixes curated for deep work. DJ mode integrates this as its primary content source.

## Playing Episodes

```bash
# Play by episode number
mpv-dj mfp 76    # Episode 76 (Material Object)
mpv-dj mfp 75    # Episode 75
```

The command:
1. Streams from `https://datashat.net/music_for_programming_{episode}-*.mp3`
2. Loads chapter metadata from `~/.voicemode/chapters/mfp_{episode}.txt` (if available)

## Episode URLs

Music For Programming hosts audio at predictable URLs:
```
https://datashat.net/music_for_programming_76-material_object.mp3
```

The episode number and curator name form the filename.

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
4. Converting results to FFmpeg format

See [chapters.md](chapters.md) for the chapter file format.

### Chapter Distribution

Chapter files are stored in `~/.voicemode/chapters/`.

Future: Download chapters from VoiceMode CDN automatically.

## Episode Discovery

### Current
Episodes must be requested by number.

### Planned
- **History tracking**: What episodes have been played
- **Favorites**: Mark episodes you enjoyed
- **Suggestions**: "Play something new" selects unplayed episodes
- **Episode index**: List all available episodes

## Collaboration Opportunity

The chapter generation process could be shared with the Music For Programming curator (Datasette) to:
- Provide chapters for all ~90 episodes
- Enable richer track metadata
- Create a great partnership for promotion
