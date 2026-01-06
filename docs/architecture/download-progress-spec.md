# Download Progress Indicator Specification

## Overview

Standardize download progress indicators across VoiceMode CLI for consistent UX when downloading models, services, or other resources.

## Design Principles

1. **Informative**: Show progress, speed, time remaining
2. **Consistent**: Same style across all downloads
3. **Responsive**: Update smoothly without flickering
4. **Accessible**: Work in different terminal environments
5. **Graceful**: Handle unknown file sizes elegantly

## Progress Bar Options

### Option 1: Click Progress Bar (Recommended)
Using Click's built-in ProgressBar - integrates well with our CLI framework.

```
Downloading ggml-large-v3.bin (3.1 GB)
[████████████████████░░░░░░░░░░░░░░░░]  45% (1.4GB/3.1GB) • 12.5 MB/s • ETA: 02:16
```

**Pros:**
- Built into Click (no new dependencies)
- Automatic terminal width detection
- Handles ANSI colors well
- Can customize format easily

**Code example:**
```python
import click

with click.progressbar(
    length=total_size,
    label='Downloading ggml-large-v3.bin',
    show_eta=True,
    show_percent=True,
    show_pos=True,
    width=40,
    fill_char='█',
    empty_char='░'
) as bar:
    # Update during download
    bar.update(chunk_size)
```

### Option 2: Rich Progress Bar
Using the Rich library for beautiful terminal output.

```
Downloading Core ML model
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:00
ggml-large-v3-encoder.mlmodelc.zip
1.2 GB / 1.2 GB • 15.3 MB/s • ✓ Complete
```

**Pros:**
- Beautiful, modern appearance
- Multiple progress bars simultaneously
- Rich formatting options
- Spinners for indeterminate progress

**Cons:**
- Adds Rich as dependency (~500KB)

### Option 3: Custom Minimal Progress
Simple, dependency-free implementation.

```
Downloading: ggml-base.bin
[===========         ] 55% | 78.1 MB / 142 MB | 8.2 MB/s | ~8s remaining
```

**Code example:**
```python
def print_progress(downloaded, total, speed):
    percent = (downloaded / total) * 100
    bar_length = 20
    filled = int(bar_length * downloaded / total)
    bar = '=' * filled + ' ' * (bar_length - filled)

    print(f'\r[{bar}] {percent:.0f}% | {downloaded/1024/1024:.1f} MB / {total/1024/1024:.1f} MB | {speed/1024/1024:.1f} MB/s', end='', flush=True)
```

### Option 4: Spinner for Unknown Size
When Content-Length header is missing:

```
Downloading model ⠼ 45.2 MB downloaded (5.3 MB/s)
```

Spinner frames: `⠋ ⠙ ⠹ ⠸ ⠼ ⠴ ⠦ ⠧ ⠇ ⠏`

### Option 5: Block Progress
Visual blocks that fill up (good for accessibility):

```
Downloading ggml-small.bin (466 MB)
Progress: ▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░ 45%
Speed: 10.2 MB/s | Downloaded: 210 MB | Remaining: ~25s
```

### Option 6: Verbose Mode (Debug/CI)
For CI environments or debug mode:

```
[2024-10-01 13:45:23] Starting download: ggml-large-v3.bin
[2024-10-01 13:45:24] Progress: 5% (155 MB / 3100 MB) - 12.3 MB/s
[2024-10-01 13:45:25] Progress: 10% (310 MB / 3100 MB) - 13.1 MB/s
[2024-10-01 13:45:26] Progress: 15% (465 MB / 3100 MB) - 12.8 MB/s
```

## Implementation Strategy

### 1. Create Unified Download Function
```python
# voice_mode/utils/download.py
async def download_with_progress(
    url: str,
    destination: Path,
    description: str = None,
    style: str = "auto",  # auto, bar, spinner, blocks, verbose
    quiet: bool = False
) -> bool:
    """
    Download file with progress indicator.

    Args:
        url: URL to download from
        destination: Where to save the file
        description: Label for the progress bar
        style: Progress indicator style
        quiet: Suppress all output

    Returns:
        True if successful, False otherwise
    """
```

### 2. Environment Detection
```python
def detect_progress_style():
    """Auto-detect best progress style based on environment."""
    if os.environ.get('CI'):
        return 'verbose'  # CI environment
    if not sys.stdout.isatty():
        return 'verbose'  # Not a terminal
    if os.environ.get('VOICEMODE_PROGRESS_STYLE'):
        return os.environ['VOICEMODE_PROGRESS_STYLE']
    return 'bar'  # Default to progress bar
```

### 3. Integration Points

**Whisper Models:**
```python
# voice_mode/utils/services/whisper_helpers.py
async def download_whisper_model(...):
    await download_with_progress(
        url=model_url,
        destination=model_path,
        description=f"Downloading {model_name}"
    )
```

**Core ML Models:**
```python
# voice_mode/utils/services/whisper_helpers.py
async def download_coreml_model(...):
    await download_with_progress(
        url=coreml_url,
        destination=coreml_zip,
        description=f"Downloading Core ML model for {model}"
    )
```

**Service Installations:**
```python
# When downloading Whisper.cpp releases, Kokoro, etc.
```

## User Configuration

### Environment Variables
```bash
# Progress bar style
export VOICEMODE_PROGRESS_STYLE=bar  # bar, spinner, blocks, verbose, quiet

# Colors
export VOICEMODE_PROGRESS_COLOR=true  # Enable/disable colors

# Update frequency
export VOICEMODE_PROGRESS_RATE=10  # Updates per second
```

### CLI Flags
```bash
# Global flags
voicemode --progress=verbose whisper model install large-v3
voicemode --quiet whisper model install base

# Command-specific
voicemode whisper model install large-v3 --no-progress
voicemode whisper model install large-v3 --progress-style=blocks
```

## Error Handling

### Network Interruption
```
Downloading ggml-large-v3.bin (3.1 GB)
[████████████░░░░░░░░░░░░░░░░░░░░░░]  35% (1.1GB/3.1GB)
❌ Download interrupted: Connection reset by peer
💡 Resume with: voicemode whisper model install large-v3 --resume
```

### Disk Space
```
Downloading ggml-large-v3.bin (3.1 GB)
[██████░░░░░░░░░░░░░░░░░░░░░░░░░░░░]  18% (558MB/3.1GB)
❌ Insufficient disk space (need 3.1 GB, have 2.1 GB available)
```

## Testing Considerations

1. **Terminal Widths**: Test with narrow (80 cols) and wide terminals
2. **Color Support**: Test with NO_COLOR environment variable
3. **CI Environment**: Test with CI=true
4. **Network Speeds**: Test progress updates with slow/fast connections
5. **File Sizes**: Test with small (KB), medium (MB), and large (GB) files

## Recommendation

**Use Click's ProgressBar (Option 1)** because:
- No new dependencies (already using Click)
- Good terminal compatibility
- Easy to customize
- Consistent with CLI framework
- Sufficient features for our needs

Fallback to spinner (Option 4) when file size is unknown.

## Example Implementation

```python
import click
import urllib.request
from pathlib import Path

def download_with_click_progress(url: str, dest: Path, label: str = None):
    """Download with Click progress bar."""

    response = urllib.request.urlopen(url)
    total_size = int(response.headers.get('Content-Length', 0))

    if not label:
        label = f"Downloading {dest.name}"

    if total_size == 0:
        # Unknown size - use spinner
        with click.progressbar(
            label=label,
            length=None,
            show_percent=False,
            show_pos=True
        ) as bar:
            downloaded = 0
            while chunk := response.read(8192):
                dest.write(chunk)
                downloaded += len(chunk)
                bar.update(len(chunk))
    else:
        # Known size - use progress bar
        with click.progressbar(
            length=total_size,
            label=label,
            show_eta=True,
            show_percent=True,
            width=40,
            fill_char='█',
            empty_char='░'
        ) as bar:
            with open(dest, 'wb') as f:
                while chunk := response.read(8192):
                    f.write(chunk)
                    bar.update(len(chunk))
```

## Next Steps

1. Implement download_with_progress utility function
2. Update whisper_helpers.py to use new function
3. Update CLI to show progress
4. Add --quiet and --verbose flags
5. Test across different environments
6. Document in user guide