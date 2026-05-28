# Permissions — stop the per-project prompt

**Symptom:** Claude Code asks "Do you want to proceed?" the first time
`mcp__voicemode__converse` or `mcp__voicemode__service` is used in a project.

**Fix (one-time):** add VoiceMode's MCP tools to Claude Code's permission
allow-list. Three application paths below — pick whichever is easiest.

## Recommended snippet

```json
{
  "permissions": {
    "allow": [
      "mcp__voicemode__converse",
      "mcp__voicemode__service"
    ]
  }
}
```

| Tool                       | What it does                                              |
| -------------------------- | --------------------------------------------------------- |
| `mcp__voicemode__converse` | Voice conversations (speak via TTS, listen via STT)       |
| `mcp__voicemode__service`  | Start / stop / restart local Whisper and Kokoro services  |

Install/uninstall tools (`whisper_install`, `kokoro_install`, etc.) are
deliberately **not** on the recommended list — those download and compile
software and benefit from per-invocation approval.

## Three ways to apply it

### 1. `/permissions` UI (in Claude Code)

```
/permissions
```

Add `mcp__voicemode__converse` and `mcp__voicemode__service` to the allow
list. Persists to settings.json automatically.

### 2. Edit settings.json directly

```bash
$EDITOR ~/.claude/settings.json
```

Merge the snippet above into the existing `permissions.allow` array (or
add the whole `permissions` block if the file is empty).

### 3. Shell heredoc (fresh install)

```bash
mkdir -p ~/.claude
cat > ~/.claude/settings.json <<'EOF'
{
  "permissions": {
    "allow": [
      "mcp__voicemode__converse",
      "mcp__voicemode__service"
    ]
  }
}
EOF
```

Only safe if `~/.claude/settings.json` doesn't already exist — otherwise
this clobbers your other settings. Use option 1 or 2 if unsure.

## Where to put it: global vs project vs project-local

| File                            | Scope         | When to use                                                |
| ------------------------------- | ------------- | ---------------------------------------------------------- |
| `~/.claude/settings.json`       | All projects  | **Default.** Personal machine, one user — set once.        |
| `.claude/settings.json`         | This project  | Team setting — commits to git so the whole team gets it.   |
| `.claude/settings.local.json`   | This project  | Personal override on a team project — gitignored.          |

Merge order: global → project → project-local (last wins).

> The per-project prompt's "Yes, and don't ask again for plugin:voicemode:voicemode commands in /path/to/project" option also works — it writes to `.claude/settings.local.json`. But it only covers the one project you accepted it in. The snippet above, in `~/.claude/settings.json`, covers every project at once.

## See also

- **[Full permissions guide](../../../../docs/guides/permissions.md)** — three permission *levels* (voice-only, voice+service, all-tools-with-denies), troubleshooting, common JSON mistakes, security notes on what each tool can do.
- **[Claude Code permissions docs](https://docs.claude.com/en/docs/claude-code/settings#permissions)** — upstream reference for the `permissions` schema.
