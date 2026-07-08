---
description: Uninstall VoiceMode -- services, MCP registration, config, and package
allowed-tools: Bash(voicemode:*), Bash(claude:*), Bash(uv:*)
---

# /voicemode:uninstall

Cleanly remove VoiceMode: services, MCP registration, config, and the package.

## Quick Uninstall (Non-Interactive)

```bash
voicemode uninstall -y
```

## What Gets Removed

| Component | Removed? |
|-----------|----------|
| Whisper, Kokoro, mlx-audio, voicemode ("serve") services | Yes |
| Claude Code MCP registration (`claude mcp remove voicemode`, tried at both user + local scope) | Yes |
| `~/.voicemode/voicemode.env` | Backed up to `voicemode.env.uninstalled`, **not** deleted |
| `voice-mode` package (`uv tool uninstall voice-mode`) | Yes -- removed LAST since it's the running binary |
| Voice clones (`~/.voicemode/voices/`, `voices.json`) | **Never** -- not even with `--remove-all-data` |
| Downloaded models (Whisper/Kokoro/mlx-audio) | Only with `--remove-models` or `--remove-all-data` |
| Logs, transcriptions, audio, conversations, cache | Only with `--remove-all-data` |

## Implementation

1. **Check how VoiceMode was installed** -- this determines whether an extra step is needed:
   ```bash
   claude plugin list   # lists "voicemode" if installed via the Claude Code plugin path
   ```

2. **Run the uninstall command:**
   ```bash
   # Interactive (prompts for confirmation)
   voicemode uninstall

   # Non-interactive
   voicemode uninstall -y

   # Also remove downloaded models
   voicemode uninstall -y --remove-models

   # Remove everything under ~/.voicemode/ except voice clones
   voicemode uninstall -y --remove-all-data
   ```

3. **Installed via the Claude Code plugin?** (Quick Start Option 1 --
   `claude plugin install voicemode@voicemode`). `claude mcp remove` cannot
   see or remove a plugin-managed MCP registration -- `voicemode uninstall`
   detects this and reports it in the residual-footprint report, but the
   plugin itself must be removed separately:
   ```bash
   claude plugin uninstall voicemode
   # and, if the marketplace was added only for this plugin:
   claude plugin marketplace remove mbailey/voicemode
   ```
   This is a first-class uninstall route, not an edge case -- the plugin
   install path (Quick Start Option 1) is the default one most users hit.

4. **Review the residual-footprint report** printed at the end of the
   command -- it states exactly what was removed and what was intentionally
   left behind (voice clones always; models/logs/audio/etc. unless the
   removal flags were given).

## Removing a Single Service

To uninstall just one service instead of everything:
```bash
voicemode service uninstall whisper
voicemode service uninstall kokoro
voicemode service uninstall mlx-audio
voicemode service uninstall voicemode   # the "serve" HTTP MCP server
```

## Flags

| Flag | Effect |
|------|--------|
| `-y`, `--yes` | Skip the confirmation prompt (non-interactive use) |
| `--remove-models` | Also delete downloaded Whisper/Kokoro/mlx-audio models |
| `--remove-all-data` | Also delete everything else under `~/.voicemode/` (logs, transcriptions, audio, conversations, cache, config backup) **except** voice clones (`voices/`, `voices.json`), which are never auto-deleted |

## After Uninstalling

Want VoiceMode back?
- Re-run `/voicemode:install`, OR
- Re-add the plugin: `claude plugin install voicemode@voicemode`

No need to manually disconnect MCP first -- the registration is already
removed.

## Complete Manual-Removal Reference

For every path VoiceMode and its installer write to disk -- including shared
tools (`uv`, Homebrew, rustup) that `voicemode uninstall` intentionally
leaves alone -- see [docs/reference/uninstall.md](../../docs/reference/uninstall.md).

For complete documentation, load the `voicemode` skill.
