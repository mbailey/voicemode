# VM-369 Technical Specification: Local MFP Chapter Distribution

## Overview

This specification defines the implementation approach for distributing Music For Programming (MFP) chapter files via the VoiceMode package.

## Problem Statement

Currently, when users run `mpv-dj mfp 49`:
1. mpv-dj looks for chapters at `~/.voicemode/music-for-programming/music_for_programming_49-julien_mier.ffmeta`
2. The file doesn't exist (no copy mechanism)
3. User sees "Note: No chapters file found"
4. Episode plays without chapter navigation

## Solution: On-Demand Copy with Sync Command

### Chosen Approach

Implement **on-demand copy** in mpv-dj plus a dedicated `sync-chapters` subcommand:

1. **On-demand**: When mpv-dj plays an episode, check if local chapter file exists. If not, copy from plugin directory.
2. **Sync command**: `mpv-dj mfp sync-chapters` to copy/update all chapter files with conflict handling.

### Why This Approach

| Option | Pros | Cons |
|--------|------|------|
| **Install hook** | Automatic | No hook mechanism in Claude Code plugins |
| **On-demand copy** ✓ | Works with existing system, no extra step | First play slightly slower |
| **CLI subcommand** | Explicit, user control | Extra step |

The hybrid approach gives us:
- Automatic copy on first play (seamless UX)
- Manual sync for updates and conflict resolution
- No new dependencies or mechanisms needed

## Component Design

### 1. Directory Structure

```
skills/voicemode/mfp/           # Package source (checked into git)
├── chapters.sha256             # Checksums for package-provided files
├── music_for_programming_49-julien_mier.ffmeta
├── music_for_programming_51-mücha.ffmeta
├── music_for_programming_52-inchindown.ffmeta
├── music_for_programming_70-things_disappear.ffmeta
├── music_for_programming_71-neon_genesis.ffmeta
├── music_for_programming_74-ncw.ffmeta
└── music_for_programming_76-material_object.ffmeta

~/.voicemode/music-for-programming/  # User directory (runtime)
├── .chapters.sha256                 # Cached checksums from last sync
├── music_for_programming_49-julien_mier.ffmeta
├── music_for_programming_49-julien_mier.ffmeta.user  # Backup if user modified
└── ...
```

### 2. Checksum File Format

`chapters.sha256` uses standard sha256sum format:
```
a1b2c3d4...  music_for_programming_49-julien_mier.ffmeta
e5f6g7h8...  music_for_programming_51-mücha.ffmeta
...
```

### 3. Chapter File Discovery

New function to find plugin directory:

```bash
# Find the plugin's mfp directory containing chapter files
find_plugin_mfp_dir() {
    local script_dir="$(dirname "$0")"

    # Relative path from bin/ to mfp/
    local mfp_dir="${script_dir}/../mfp"

    if [[ -d "$mfp_dir" ]]; then
        echo "$(cd "$mfp_dir" && pwd)"
        return 0
    fi

    return 1
}
```

### 4. On-Demand Copy Logic (cmd_mfp)

Update `cmd_mfp()` in mpv-dj:

```bash
cmd_mfp() {
    local episode="$1"
    # ... existing URL/filename lookup ...

    local chapters_file="${MFP_DIR}/${filename_base}.ffmeta"
    mkdir -p "$MFP_DIR"

    # On-demand copy if missing
    if [[ ! -f "$chapters_file" ]]; then
        local plugin_mfp_dir
        if plugin_mfp_dir=$(find_plugin_mfp_dir); then
            local source_file="${plugin_mfp_dir}/${filename_base}.ffmeta"
            if [[ -f "$source_file" ]]; then
                cp "$source_file" "$chapters_file"
                echo "Copied chapter file from package"
            fi
        fi
    fi

    # ... existing playback logic ...
}
```

### 5. Sync Command (cmd_mfp_sync_chapters)

New command: `mpv-dj mfp sync-chapters [--force]`

```bash
cmd_mfp_sync_chapters() {
    local force=false
    [[ "$1" == "--force" ]] && force=true

    local plugin_mfp_dir
    if ! plugin_mfp_dir=$(find_plugin_mfp_dir); then
        echo "Error: Could not find plugin mfp directory"
        exit 1
    fi

    mkdir -p "$MFP_DIR"

    local checksums_file="${plugin_mfp_dir}/chapters.sha256"
    local local_checksums="${MFP_DIR}/.chapters.sha256"

    # Process each ffmeta file in plugin directory
    for source_file in "$plugin_mfp_dir"/*.ffmeta; do
        [[ -f "$source_file" ]] || continue

        local filename=$(basename "$source_file")
        local dest_file="${MFP_DIR}/${filename}"

        sync_chapter_file "$source_file" "$dest_file" "$checksums_file" "$local_checksums" "$force"
    done

    # Update local checksums cache
    if [[ -f "$checksums_file" ]]; then
        cp "$checksums_file" "$local_checksums"
    fi

    echo "Chapter sync complete"
}
```

### 6. Conflict Resolution Logic

```bash
sync_chapter_file() {
    local source="$1"
    local dest="$2"
    local pkg_checksums="$3"
    local local_checksums="$4"
    local force="$5"

    local filename=$(basename "$source")

    # If destination doesn't exist, simple copy
    if [[ ! -f "$dest" ]]; then
        cp "$source" "$dest"
        echo "  Added: $filename"
        return
    fi

    # Calculate current checksums
    local source_sha=$(shasum -a 256 "$source" | cut -d' ' -f1)
    local dest_sha=$(shasum -a 256 "$dest" | cut -d' ' -f1)

    # If identical, skip
    if [[ "$source_sha" == "$dest_sha" ]]; then
        echo "  Unchanged: $filename"
        return
    fi

    # Get last known package checksum (from previous sync)
    local last_pkg_sha=""
    if [[ -f "$local_checksums" ]]; then
        last_pkg_sha=$(grep "$filename" "$local_checksums" 2>/dev/null | cut -d' ' -f1)
    fi

    # Determine if user modified the file
    local user_modified=false
    if [[ -n "$last_pkg_sha" && "$dest_sha" != "$last_pkg_sha" ]]; then
        user_modified=true
    fi

    if [[ "$user_modified" == true && "$force" != true ]]; then
        # User modified - backup and update
        cp "$dest" "${dest}.user"
        cp "$source" "$dest"
        echo "  Updated: $filename (user version saved as .user)"
    else
        # Not modified or force - overwrite
        cp "$source" "$dest"
        echo "  Updated: $filename"
    fi
}
```

## Implementation Steps

### Phase 1: Add Checksum File
1. Generate `chapters.sha256` from existing ffmeta files
2. Commit to `skills/voicemode/mfp/`

### Phase 2: Update mpv-dj
1. Add `find_plugin_mfp_dir()` function
2. Add on-demand copy logic to `cmd_mfp()`
3. Add `sync_chapter_file()` function
4. Add `cmd_mfp_sync_chapters()` command
5. Update command dispatch to handle `mfp sync-chapters`
6. Update help text

### Phase 3: Testing
1. Test fresh install scenario (no local files)
2. Test on-demand copy during play
3. Test sync-chapters command
4. Test conflict resolution (modified local file)
5. Test --force flag

## File Locations

| File | Purpose |
|------|---------|
| `skills/voicemode/bin/mpv-dj` | Main script to modify |
| `skills/voicemode/mfp/chapters.sha256` | New checksum file |
| `skills/voicemode/mfp/*.ffmeta` | Existing chapter files |

## Edge Cases

### 1. Plugin Directory Not Found
If `find_plugin_mfp_dir()` fails:
- On-demand copy: silently skip (play without chapters)
- Sync command: error with clear message

### 2. Special Characters in Filenames
Episode 51 has "mücha" with umlaut. Handle with:
- Use `LC_ALL=C` for checksum operations
- Quote all filenames in shell commands

### 3. Permissions Issues
If copy fails due to permissions:
- Print error message
- Continue playback without chapters (graceful degradation)

### 4. Missing Checksums File
If `chapters.sha256` doesn't exist:
- On-demand copy: still works (simple copy)
- Sync: treat all files as unmodified (simple overwrite)

## Success Criteria Mapping

| Acceptance Criteria | How Addressed |
|---------------------|---------------|
| mpv-dj mfp 49 works after fresh install | On-demand copy in cmd_mfp() |
| Chapter navigation for included episodes | All 7 ffmeta files in package |
| User modifications preserved on update | Conflict resolution with .user backup |
| PR process documented | Separate doc task (doc-001) |

## Notes

### Not In Scope for This Task
- CUE files (only FFMETA for streaming use case)
- Episodes 44 and 66 (no chapter files exist yet)
- Installer integration (using on-demand approach instead)

### Future Enhancements
- Add CUE file support if local playback demand emerges
- Generate missing episode chapters via audio-tools pipeline
- Consider periodic background sync
