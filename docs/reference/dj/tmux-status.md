# DJ Mode: tmux Status Line Integration

Display the currently playing track in your tmux status bar.

## Overview

The `voicemode dj status --line` command outputs a compact, single-line format designed for tmux status bars. It includes:

- Track/chapter title (truncated to 40 chars)
- Current position
- Remaining time with color warnings
- Play/pause indicator (♪ or ⏸)

Example output:
```
Ulrich Schnauss - A Strangely Isolated.. 12:34 (-3:21) ♪
```

## Color Coding

The remaining time changes color as the track nears its end:

| Condition | Color |
|-----------|-------|
| > 30 seconds remaining | Default |
| 10-30 seconds remaining | Yellow |
| < 10 seconds remaining | Red (bold) |

This gives you a visual warning before the music stops.

## tmux Configuration

Add this to your `~/.tmux.conf`:

```bash
# DJ status in right status bar (updates every 5 seconds)
set -g status-right '#(voicemode dj status --line 2>/dev/null)'
set -g status-interval 5
```

### With Existing Status Right

If you already have content in your status-right, append the DJ status:

```bash
set -g status-right '#(voicemode dj status --line 2>/dev/null) | %H:%M'
```

### Conditional Display

Only show when music is playing (shows nothing when stopped):

```bash
set -g status-right '#(voicemode dj status --line 2>/dev/null)#(date +%%H:%%M)'
```

The command outputs nothing when no music is playing, so it won't leave blank space.

## Reload Configuration

After editing `~/.tmux.conf`, reload it:

```bash
tmux source-file ~/.tmux.conf
```

Or from within tmux, press `prefix` then `:` and type:
```
source-file ~/.tmux.conf
```

## Troubleshooting

### Status not updating

Decrease the interval for more frequent updates:

```bash
set -g status-interval 1   # Update every second
```

Note: More frequent updates increase CPU usage slightly.

### Command not found

Ensure `voicemode` is in your PATH. You may need to use the full path:

```bash
set -g status-right '#(~/.local/bin/voicemode dj status --line 2>/dev/null)'
```

Or if installed with uv:

```bash
set -g status-right '#(uv run voicemode dj status --line 2>/dev/null)'
```

### Colors not showing

Ensure your terminal supports 256 colors and tmux is configured for it:

```bash
set -g default-terminal "screen-256color"
```

## See Also

- [DJ Commands](commands.md) - Full command reference
- [Installation](installation.md) - Setup mpv and dependencies
