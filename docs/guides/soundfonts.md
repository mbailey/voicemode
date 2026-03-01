# Soundfonts

Audio feedback during Claude Code sessions. Sounds play when tools start and finish, giving you awareness of what Claude is doing without watching the screen.

## Prerequisites

Install Claude Code hooks:

```bash
voicemode claude hooks add
```

This registers VoiceMode's hook receiver with Claude Code. The receiver runs on each tool event and plays the appropriate sound.

## Quick Toggle

```bash
voicemode soundfonts off       # Disable (this session)
voicemode soundfonts on        # Re-enable
voicemode soundfonts status    # Show current state
```

For persistent changes that survive restarts:

```bash
voicemode soundfonts off --config   # Disable + update voicemode.env
voicemode soundfonts on --config    # Enable + update voicemode.env
```

## How It Works

Claude Code fires hook events (`PreToolUse`, `PostToolUse`, `PreCompact`) during operation. VoiceMode's hook receiver:

1. Checks if soundfonts are disabled (sentinel file or env var)
2. Looks up the right sound file based on the tool and event
3. Plays it asynchronously (non-blocking, won't slow down Claude)
4. Skips playback during active voice conversations

The hook receiver is a fast bash script (~20ms startup) that avoids Python overhead.

## Directory Structure

```
~/.voicemode/soundfonts/
  current -> voicemode          # Symlink to active soundfont pack
  voicemode/                    # Default soundfont pack
    fallback.mp3                # Global fallback sound
    PreToolUse/
      default.mp3               # Before tool execution
      task/subagent/
        baby-bear.mp3           # Small subagent spawned
        mama-bear.mp3           # Medium subagent
        papa-bear.mp3           # Large subagent
    PostToolUse/
      default.mp3               # After tool execution
      task/subagent/
        baby-bear.mp3
        mama-bear.mp3
        papa-bear.mp3
    PreCompact/
      default.mp3               # Before context compaction
    system-messages/
      ready-to-listen.mp3       # Voice recording started
      waiting-1-minute.mp3      # Idle timeout warning
      repeating.mp3             # Repeating last message
```

## Sound Lookup Order

When a tool event fires, the receiver searches for sounds from most specific to least specific:

| Priority | Path | When |
|----------|------|------|
| 1 | `{event}/mcp/{server}/{tool}/[01-99\|default].mp3` | MCP tool (e.g., voicemode converse) |
| 2 | `{event}/mcp/{server}/default.mp3` | Any tool from that MCP server |
| 3 | `{event}/mcp/default.mp3` | Any MCP tool |
| 4 | `{event}/{tool}/subagent/{subagent}.mp3` | Specific subagent type |
| 5 | `{event}/{tool}/[01-99\|default].mp3` | Specific tool |
| 6 | `{event}/default.mp3` | Any tool for that event |
| 7 | `fallback.mp3` | Nothing else matched |

Both `.mp3` and `.wav` formats are supported at every level.

### Numbered Variants

Place numbered files (`01.mp3`, `02.mp3`, ..., `99.mp3`) alongside `default.mp3` in any tool directory. The receiver randomly selects one, adding variety to repeated operations.

### Muting Specific Tools

Create a `MUTE.txt` file in any tool directory to suppress sounds for that tool:

```bash
# Silence the converse tool's PreToolUse sound
touch ~/.voicemode/soundfonts/current/PreToolUse/mcp/voicemode/converse/MUTE.txt
```

## Customizing Sounds

### Replace Individual Sounds

Drop replacement `.mp3` or `.wav` files into the appropriate directory:

```bash
# Custom sound for Bash tool completion
cp my-sound.mp3 ~/.voicemode/soundfonts/voicemode/PostToolUse/bash/default.mp3
```

### Create a Custom Soundfont Pack

1. Copy the default pack:

```bash
cp -r ~/.voicemode/soundfonts/voicemode ~/.voicemode/soundfonts/my-pack
```

2. Replace sounds in your new pack

3. Switch to it:

```bash
ln -sfn my-pack ~/.voicemode/soundfonts/current
```

## Disabling Soundfonts

Two mechanisms control soundfont playback:

| Mechanism | How to set | Scope |
|-----------|-----------|-------|
| Sentinel file | `voicemode soundfonts off` | Quick toggle |
| Environment variable | `VOICEMODE_SOUNDFONTS_ENABLED=false` in `~/.voicemode/voicemode.env` | Persistent config |

The sentinel file (`~/.voicemode/soundfonts-disabled`) is checked first as a fast-path circuit breaker. When absent, the environment variable decides. Default is enabled.

Use `voicemode soundfonts status` to see which mechanisms are active.

## Troubleshooting

### No sounds playing

1. Check hooks are installed: `voicemode claude hooks list`
2. Check soundfonts status: `voicemode soundfonts status`
3. Check the soundfont directory exists: `ls ~/.voicemode/soundfonts/current/`
4. Enable debug mode and run a Claude Code session:

```bash
export VOICEMODE_HOOK_DEBUG=1
```

Debug output goes to stderr and shows which sound file was selected (or why none was found).

### Sounds are too loud or quiet

Soundfont audio files are standard MP3/WAV. Adjust their volume with any audio editor, or use `ffmpeg`:

```bash
# Reduce volume by half
ffmpeg -i default.mp3 -filter:a "volume=0.5" default-quiet.mp3
mv default-quiet.mp3 default.mp3
```

### Hook receiver log

The receiver writes to `~/.voicemode/soundfonts/hook-receiver.log` (when not in debug mode). Check this for playback errors.
