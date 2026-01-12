# Music For Programming Integration

[Music For Programming](https://musicforprogramming.net) is a series of ambient/electronic mixes curated for deep work. DJ mode integrates this as its primary content source.

## Playing Episodes

```bash
# Play by episode number
mpv-dj mfp 49    # Episode 49 (Julien Mier)
mpv-dj mfp 51    # Episode 51 (Mücha)
```

The command:
1. Checks for local cached audio in `~/.voicemode/music-for-programming/`
2. If not cached, looks up the episode URL from the RSS feed via `mfp-rss-helper`
3. Streams from the URL (e.g., `https://datashat.net/music_for_programming_49-julien_mier.mp3`)
4. Loads chapter metadata for track-level navigation

## File Structure

All MFP files live in `~/.voicemode/music-for-programming/`:

```
~/.voicemode/music-for-programming/
├── rss.xml                                     # Cached RSS feed (auto-updated)
├── music_for_programming_49-julien_mier.mp3    # Audio (downloaded or cached)
├── music_for_programming_49-julien_mier.cue    # CUE sheet (for local playback)
├── music_for_programming_49-julien_mier.ffmeta # FFMETADATA chapters (for streaming)
├── music_for_programming_51-mücha.mp3
├── music_for_programming_51-mücha.cue
├── music_for_programming_51-mücha.ffmeta
└── ...
```

**Naming Convention:** Files are named to match the RSS MP3 filename exactly (minus extension), ensuring automatic pairing of audio with chapter metadata.

**File Types:**
- `rss.xml` - Cached RSS feed for episode URL lookups (see [RSS Caching](#rss-caching))
- `.mp3` - Audio file (downloaded by user or cached during streaming)
- `.cue` - CUE sheet with track timestamps (for local mpv playback)
- `.ffmeta` - FFMETADATA chapters (for HTTP streaming where CUE doesn't work)

**LLM Access:** You can read CUE files to search for tracks across episodes. Example: "Which episode has Boards of Canada?" - search the CUE files for artist names.

## Episode URLs

Music For Programming hosts audio at URLs that include the curator name:
```
https://datashat.net/music_for_programming_49-julien_mier.mp3
```

The episode number and curator name form the filename. Episodes are freely downloadable from the website.

Episode URLs are obtained dynamically from the MFP RSS feed using the `mfp-rss-helper` tool, which handles the lookup and caching automatically.

## RSS Caching

The `mfp-rss-helper` script fetches episode URLs from the official MFP RSS feed with smart caching for offline support.

### How It Works

1. **First run**: Fetches RSS feed from `musicforprogramming.net/rss.xml`
2. **Caches to**: `~/.voicemode/music-for-programming/rss.xml`
3. **Subsequent runs**: Tries fresh fetch, falls back to cache if offline
4. **Episode lookup**: Parses RSS to find correct URL for any episode number

### Offline Support

If you're offline but have a cached RSS feed, `mpv-dj mfp` will still work:
- Episode URL lookups use the cached `rss.xml`
- Already-downloaded audio files play normally
- Only fails if both network and cache are unavailable

### Helper Commands

```bash
# Get URL for an episode
mfp-rss-helper url 49              # Returns full URL for episode 49

# Get RSS-based filename (without extension)
mfp-rss-helper filename 49         # Returns: music_for_programming_49-julien_mier

# List all available episodes
mfp-rss-helper list                # Shows episode numbers and curators

# Force refresh the cache
mfp-rss-helper refresh             # Updates rss.xml from network
```

### Cache Location

```
~/.voicemode/music-for-programming/rss.xml
```

The cache is automatically created and updated. Delete it to force a fresh fetch on next use.

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

VoiceMode includes chapter files for select episodes in the package. These are automatically copied to your local directory when you first play an episode.

**Available chapters:**
- Episode 49, 51, 52, 70, 71, 74

**How it works:**
1. When you run `mpv-dj mfp 49` for the first time, the chapter file is copied from the package
2. The chapter file enables track-level navigation immediately
3. User modifications to chapter files are preserved during updates

### Syncing Chapter Files

Use the `sync-chapters` command to manage chapter files:

```bash
# Sync all chapter files from package
mpv-dj mfp sync-chapters

# Force overwrite (ignores user modifications)
mpv-dj mfp sync-chapters --force
```

**Sync behavior:**
- **New files**: Copied from package to local directory
- **Unchanged files**: Skipped (already up to date)
- **Updated files**: If you modified a chapter file, your version is backed up to `.user` before updating

Example output:
```
  Added: music_for_programming_49-julien_mier.ffmeta
  Unchanged: music_for_programming_51-mücha.ffmeta
  Updated: music_for_programming_74-ncw.ffmeta (user version saved as .user)
Chapter sync complete
```

### Contributing Chapter Files

Community contributions to improve chapter accuracy are welcome! To contribute:

1. **Fork the VoiceMode repository** on GitHub
2. **Create or improve chapter files** in `skills/voicemode/mfp/`
3. **Update the checksums** by regenerating `chapters.sha256`:
   ```bash
   cd skills/voicemode/mfp
   shasum -a 256 *.ffmeta > chapters.sha256
   ```
4. **Submit a Pull Request** with your changes

**Chapter file format:** See [chapters.md](chapters.md) for FFMETADATA format details.

**Quality guidelines:**
- Timestamps should be accurate to within a few seconds
- Track titles should match the official MFP tracklist
- Test playback with `mpv-dj mfp <episode>` and verify navigation works

## Listing Episodes

The `mfp list` command shows available episodes with their chapter and local file status.

### Basic Usage

```bash
# Show episodes with complete chapter files (CUE + FFmeta)
mpv-dj mfp list

# Show all episodes from RSS feed
mpv-dj mfp list --all

# Show episode URLs for downloading
mpv-dj mfp list --urls

# Show CUE/FFmeta file status separately
mpv-dj mfp list --verbose
```

### Output Formats

The list command automatically detects terminal vs pipe:
- **Terminal**: Human-readable columnized format
- **Pipe/redirect**: TSV (tab-separated values) for scripting

```bash
# Human format (in terminal)
mpv-dj mfp list
#  #  Curator               Ch  MP3
# 49  julien mier          yes  yes
# 51  mücha                yes   -

# TSV format (piped)
mpv-dj mfp list | head -3
# 49	julien mier	chapters	local
# 51	mücha	chapters	-
```

### TSV Output Format for LLMs

When piped, output is tab-separated for easy parsing by AI assistants:

| Column | Description | Values |
|--------|-------------|--------|
| 1 | Episode number | Integer (e.g., `49`) |
| 2 | Curator name | String (e.g., `julien mier`) |
| 3 | Chapter status | `chapters` or `-` |
| 4 | Local MP3 | `local` or `-` |
| 5 | URL (with --urls) | Full download URL |

**With `--verbose` flag**, column 3 splits into:
| Column | Description | Values |
|--------|-------------|--------|
| 3 | CUE file | `cue` or `-` |
| 4 | FFmeta file | `ffmeta` or `-` |
| 5 | Local MP3 | `local` or `-` |

**LLM Examples:**
```bash
# Find episodes with chapters ready to play
mpv-dj mfp list | awk -F'\t' '$3=="chapters" {print $1, $2}'

# Get download URL for episode 49
mpv-dj mfp list --all --urls | awk -F'\t' '$1==49 {print $5}'

# Count episodes with local MP3s
mpv-dj mfp list --all | awk -F'\t' '$4=="local"' | wc -l
```

### Column Indicators

| Indicator | Human Format | TSV Format | Meaning |
|-----------|--------------|------------|---------|
| Ch/chapters | `yes` / ` - ` | `chapters` / `-` | Both CUE and FFmeta files exist |
| CUE | `yes` / ` - ` | `cue` / `-` | CUE file exists (--verbose) |
| FFm | `yes` / ` - ` | `ffmeta` / `-` | FFmeta file exists (--verbose) |
| MP3 | `yes` / ` - ` | `local` / `-` | Local audio file downloaded |

**Note:** "Chapters" requires both CUE (for local playback) and FFmeta (for streaming) files. Use `--verbose` to see which files are missing.

## Episode Discovery

### Current
- Request episodes by number: `mpv-dj mfp 49`
- List episodes with chapters: `mpv-dj mfp list`
- List all episodes: `mpv-dj mfp list --all`
- Search tracks: `grep "Boards of Canada" ~/.voicemode/music-for-programming/*.cue`

### Planned
- **History tracking**: What episodes have been played
- **Favorites**: Mark episodes you enjoyed
- **Suggestions**: "Play something new" selects unplayed episodes

## Collaboration Opportunity

The chapter generation process could be shared with the Music For Programming curator (Datasette) to:
- Provide chapters for all ~90 episodes
- Enable richer track metadata
- Create a great partnership for promotion
