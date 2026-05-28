# Permissions — stop the per-project prompt

## Symptom

Claude Code prompts "Do you want to proceed?" the first time
`mcp__voicemode__converse` or `mcp__voicemode__service` is called in a
project.

## Fix

Add to Claude Code's `permissions.allow`:

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

Don't blanket-allow `mcp__voicemode__*` — install/uninstall tools
(`whisper_install`, `kokoro_install`, `whisper_model_install`) download
and compile software; per-invocation approval is correct for those.

## Where to put it

| File                          | Scope        | Pick when                                                       |
| ----------------------------- | ------------ | --------------------------------------------------------------- |
| `~/.claude/settings.json`     | USER         | Personal machine, one user — covers every project at once.      |
| `.claude/settings.json`       | Project      | Team setting — committed to git so everyone on the project gets it. |
| `.claude/settings.local.json` | Project (local) | Personal override on a team project — gitignored.            |

Merge order: USER → project → project-local (last wins).

## See also

- **[Full permissions guide](../../../../docs/guides/permissions.md)** — permission levels (voice-only, voice+service, all-with-denies), security notes on what each tool can do, common JSON mistakes.
