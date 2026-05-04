# Impressions

**Speak in any voice.** Drop a short audio clip of someone speaking, give it a name, and VoiceMode does an *impression* — synthesising fresh speech in that voice via local Qwen3-TTS on top of mlx-audio.

> **Status:** Preview / experimental. Apple Silicon only. Opt-in: nothing happens until you install the `mlx-audio` service and add at least one voice.

## Why "impressions" and not "cloning"?

The mechanism is reference-clip TTS — the model imitates the timbre and cadence of a short sample. Calling that an *impression* matches what the model is actually doing (a comedian-style imitation), is more honest about quality limits, and reads naturally as a verb: *the model can do an impression of Fleabag*. Same technical path as the old "voice cloning" framing; better mental model.

## Requirements

- **Apple Silicon Mac** (M1/M2/M3/M4) — uses MLX for local inference.
- **VoiceMode installed** — `pip install voicemode` or `uv tool install voicemode`.
- **~3.4 GB free disk** for the Qwen3-TTS model (downloaded on first synthesis).
- **~4 GB free RAM** while synthesising.

If you're on Intel Mac, Linux, or Windows, the `mlx-audio` service won't install — Impressions are Apple-Silicon-only for now.

## Quick start

### 1. Install the mlx-audio service

```bash
voicemode service install mlx-audio
```

This sets up a local mlx-audio server (port 8890 by default), creates a launchd unit so it starts on login, and pre-stages the runtime. The Qwen3-TTS model itself isn't downloaded until you ask for synthesis the first time — expect a one-off ~3.4 GB pull on the first impression.

Verify:

```bash
voicemode service status mlx-audio
```

### 2. Add a voice

Voices live as **directories** under `~/.voicemode/voices/<name>/`. The minimal layout is one WAV file:

```
~/.voicemode/voices/
└── fleabag/
    └── default.wav        # 5-9 seconds of clean reference audio
```

Optionally, you can drop two extra files alongside `default.wav`:

```
~/.voicemode/voices/fleabag/
├── default.wav
├── description.txt        # one-line human description
└── persona.md             # structured character notes used to steer LLMs that speak in this voice
```

Multiple WAVs in the directory are fine — they're treated as a sample bin. Symlink whichever sample you want active to `default.wav`:

```bash
ln -sfn samantha-2024-loud.wav ~/.voicemode/voices/samantha/default.wav
```

A directory with multiple WAVs and *no* `default.wav` is skipped (it's a bin, not a voice). Add the symlink to opt it in.

### 3. Use the voice

In the converse MCP tool:

```python
voicemode:converse("Hair is everything, darling.", voice="fleabag")
```

From the CLI:

```bash
voicemode converse --voice fleabag
```

VoiceMode automatically routes any voice name that matches a profile in `VOICEMODE_VOICES_DIR` to the mlx-audio service instead of Kokoro / OpenAI.

## Picking a good reference clip

The model copies what it hears. Garbage in, garbage out.

- **5-9 seconds** beats 30 seconds. Long noisy clips are worse than short clean ones.
- **Clean speech only** — no music bed, no laugh track, no background hum.
- **Conversational delivery** — natural prosody outperforms read-aloud.
- **WAV preferred**, but anything FFmpeg can decode works.

For deeper guidance on ranking samples (mlx-whisper word-timestamp ranker, `ffmpeg loudnorm` recipes), see the [Impressions skill](../../.claude/skills/impressions/docs/finding-samples.md).

## Footguns

### Voice name collisions with Kokoro

Kokoro voices live in a flat namespace (`af_sky`, `am_michael`, `bf_emma`, …). If you create `~/.voicemode/voices/af_sky/`, **your impression profile shadows the Kokoro voice with the same name** — the next `voice="af_sky"` call routes to mlx-audio, not Kokoro. Pick distinctive names (`fleabag`, `mike-2026`, `bryan_morning`) to avoid surprises.

### Apple Silicon only

`mlx-audio` requires MLX, which is Apple-Silicon-only. There is no fallback path on Intel Macs, Linux, or Windows. If the service install fails on a non-supported platform, impressions are simply unavailable on that machine — Kokoro and OpenAI TTS continue to work as normal.

### First synthesis is slow

The Qwen3-TTS model (~3.4 GB) downloads on the first synthesis call. Plan for a 1-3 minute pause on the first impression after install. Subsequent calls are local and fast.

### `sayas` is removed

The standalone `sayas <voice> <text>` CLI from the 8.6.x line is **gone in 8.7.0**. Use `voicemode converse --voice <name> -m "text" --no-wait` instead -- it routes through the same mlx-audio backend and gets the rest of the converse pipeline (silence detection, audio formats, providers) for free. From the MCP tool, pass `voice="<name>"` to `voicemode:converse`.

## Configuration

| Variable                          | Default                                            | Description                                                                                            |
| --------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `VOICEMODE_VOICES_DIR`            | `~/.voicemode/voices`                              | Where impression voices live (one subdirectory per voice).                                             |
| `VOICEMODE_REMOTE_VOICES_DIR`     | *(unset)*                                          | If set, the path on the *remote* mlx-audio host where `VOICEMODE_VOICES_DIR` is mirrored. See below.   |
| `VOICEMODE_MLX_AUDIO_BASE_URL`    | `http://127.0.0.1:8890/v1`                         | OpenAI-compatible endpoint for the mlx-audio TTS service.                                              |
| `VOICEMODE_IMPRESSIONS_MODEL`     | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16`      | Hugging Face model ID. Other quants: `-4bit` (faster, lower quality), `-5bit`, `-6bit`, `-bf16` (best). |

### Deprecated env-var aliases (one release only)

The following names were used during the unreleased 8.7.0 candidate and are honoured for one release with a one-shot deprecation warning. **Replace them in your `~/.voicemode/voicemode.env`** — they will be removed in 8.8.0.

| Deprecated                  | Replace with                   |
| --------------------------- | ------------------------------ |
| `VOICEMODE_CLONE_BASE_URL`  | `VOICEMODE_MLX_AUDIO_BASE_URL` |
| `VOICEMODE_CLONE_MODEL`     | `VOICEMODE_IMPRESSIONS_MODEL`  |
| `VOICEMODE_CLONE_PORT`      | `VOICEMODE_MLX_AUDIO_PORT`     |

### Remote mlx-audio (e.g. running on a beefy ms2)

If your Apple Silicon box isn't where Claude runs, point VoiceMode at a remote mlx-audio service:

```bash
# In ~/.voicemode/voicemode.env on the client
VOICEMODE_MLX_AUDIO_BASE_URL=http://ms2.your-tailnet.ts.net:8890/v1
VOICEMODE_REMOTE_VOICES_DIR=/Users/admin/.voicemode/voices  # path on ms2
```

`VOICEMODE_REMOTE_VOICES_DIR` is the path-as-seen-by-the-server. The client rewrites `ref_audio` paths to that prefix before sending requests, so the remote mlx-audio process can find the WAV files on its own filesystem.

## Architecture

```
~/.voicemode/
└── voices/                         # VOICEMODE_VOICES_DIR
    ├── fleabag/
    │   ├── default.wav             # reference clip
    │   ├── description.txt         # optional
    │   └── persona.md              # optional
    └── samantha/
        ├── default.wav -> samantha-2024-loud.wav
        ├── samantha-2024-loud.wav
        └── samantha-2023-quiet.wav
```

mlx-audio exposes an OpenAI-compatible `/v1/audio/speech` endpoint with two extra fields used for the impression:

```json
{
  "model": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
  "input": "Text to speak",
  "ref_audio": "/path/to/voices/fleabag/default.wav",
  "ref_text": "(auto-transcribed via local Whisper, or provided explicitly)"
}
```

## See also

- [Impressions skill](../../.claude/skills/impressions/SKILL.md) — agent-facing reference for adding voices and troubleshooting on demand.
- [Setup deep-dive](../../.claude/skills/impressions/docs/setup.md) — model quants, remote mlx-audio config, install troubleshooting.
- [Finding good samples](../../.claude/skills/impressions/docs/finding-samples.md) — ranking heuristics, ffmpeg recipes, voice-lab tooling.
- [voice-lab](https://github.com/mbailey/voice-lab) — companion repo for curating reference clips and personas.
