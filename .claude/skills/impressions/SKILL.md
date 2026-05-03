---
name: impressions
description: Add and use custom voices for VoiceMode TTS via local mlx-audio. Use when the user wants to clone a voice, do an impression, add a reference clip, or use voice="<name>" in converse.
---

# Impressions

Make VoiceMode speak in any voice. The model takes a 5-9 second reference clip and synthesises fresh speech in that voice via local Qwen3-TTS on top of mlx-audio.

> **Status:** Preview / experimental. Apple Silicon only. Opt-in.

## When to use this skill

- User asks for "voice cloning", "do an impression", "speak as X", "add my voice"
- A `voice=` argument in `voicemode:converse` doesn't match a known Kokoro voice
- User wants to install or troubleshoot the `mlx-audio` service
- User asks how to configure a remote mlx-audio server

## Quick start

```bash
# 1. Install the local TTS service (one-time, Apple Silicon only)
voicemode service install mlx-audio

# 2. Add a voice -- a directory with one short clean WAV
mkdir -p ~/.voicemode/voices/fleabag
cp ~/Downloads/fleabag-clip.wav ~/.voicemode/voices/fleabag/default.wav

# 3. Use it
voicemode converse --voice fleabag
```

In the MCP `converse` tool, pass `voice="fleabag"` -- VoiceMode auto-routes any voice that matches a profile in `VOICEMODE_VOICES_DIR` to mlx-audio instead of Kokoro / OpenAI.

## Voice directory layout

Voices live as **directories**, not loose files, under `~/.voicemode/voices/<name>/`:

```
~/.voicemode/voices/fleabag/
├── default.wav        # required: 5-9 seconds of clean reference audio
├── description.txt    # optional: one-line human description
└── persona.md         # optional: structured character notes (see voice-lab)
```

Multiple WAVs are allowed; symlink whichever one is "active" to `default.wav`. A directory with multiple WAVs and no `default.wav` is treated as a sample bin and skipped.

## Picking a clip

5-9 seconds of clean conversational speech beats 30 seconds of noisy podcast audio. The model copies what it hears -- including hum, music beds, and laugh tracks. See [docs/finding-samples.md](docs/finding-samples.md) for ranking heuristics, an mlx-whisper word-timestamp ranker concept, and `ffmpeg loudnorm` recipes.

## Configuration

| Variable                         | Default                                       | Purpose                                              |
| -------------------------------- | --------------------------------------------- | ---------------------------------------------------- |
| `VOICEMODE_VOICES_DIR`           | `~/.voicemode/voices`                         | Where voice profiles live                            |
| `VOICEMODE_REMOTE_VOICES_DIR`    | *(unset)*                                     | Path on remote mlx-audio host (path translation)     |
| `VOICEMODE_MLX_AUDIO_BASE_URL`   | `http://127.0.0.1:8890/v1`                    | OpenAI-compatible mlx-audio endpoint                 |
| `VOICEMODE_IMPRESSIONS_MODEL`    | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16` | Hugging Face model ID                                |

### Deprecated aliases (one release only)

The unreleased 8.7.0 candidate used `VOICEMODE_CLONE_*` names. They're honoured in 8.7.x with a one-shot deprecation warning and **removed in 8.8.0**:

| Deprecated                 | Use instead                    |
| -------------------------- | ------------------------------ |
| `VOICEMODE_CLONE_BASE_URL` | `VOICEMODE_MLX_AUDIO_BASE_URL` |
| `VOICEMODE_CLONE_MODEL`    | `VOICEMODE_IMPRESSIONS_MODEL`  |
| `VOICEMODE_CLONE_PORT`     | `VOICEMODE_MLX_AUDIO_PORT`     |

If you see those in a user's `voicemode.env`, suggest updating them.

## Footguns

- **Kokoro name collisions** -- naming a voice `af_sky` (or any other Kokoro voice name) shadows the Kokoro voice. Pick distinctive names like `fleabag`, `mike-2026`, `bryan_morning`.
- **Apple Silicon only** -- no fallback for Intel Macs / Linux / Windows. Don't suggest installing mlx-audio on those platforms.
- **First synthesis is slow** -- ~3.4 GB model download on first call. Warn the user.

## Deep dives

- [docs/setup.md](docs/setup.md) -- install path, model quants table, remote mlx-audio config, troubleshooting.
- [docs/finding-samples.md](docs/finding-samples.md) -- clip ranking heuristic, ffmpeg loudnorm recipe, link to voice-lab.

## Related

- [Impressions guide](../../../docs/guides/impressions.md) -- user-facing prose version of this skill.
- [VoiceMode skill](../voicemode/SKILL.md) -- primary voice interaction skill.
- [voice-lab](https://github.com/mbailey/voice-lab) -- companion repo for curating reference clips and personas.
