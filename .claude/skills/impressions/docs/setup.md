# Impressions: Setup deep-dive

Beyond the quick start in [SKILL.md](../SKILL.md). Cover model choice, remote mlx-audio servers, and common install failure modes.

## Install path

```bash
voicemode service install mlx-audio
```

What this does:

1. `uv tool install mlx-audio>=0.4.3` (the bundled patch is gone as of VM-1126; pin floored).
2. Writes a launchd unit (`com.failmode.voicemode.mlx-audio.plist`) so the server starts on login.
3. Pre-stages the runtime but does **not** download the Qwen3-TTS model. That happens lazily on the first synthesis call.

Verify:

```bash
voicemode service status mlx-audio
voicemode service logs   mlx-audio --lines 100
```

## Model quants

The Qwen3-TTS family ships at multiple precisions on Hugging Face. Pick via `VOICEMODE_IMPRESSIONS_MODEL`:

| Quant  | HF model ID                                   | Disk    | RAM     | Speed   | Quality |
| ------ | --------------------------------------------- | ------- | ------- | ------- | ------- |
| 4-bit  | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-4bit` | ~1.0 GB | ~1.5 GB | fastest | OK      |
| 5-bit  | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-5bit` | ~1.3 GB | ~2.0 GB | fast    | good    |
| 6-bit  | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-6bit` | ~1.6 GB | ~2.4 GB | fast    | better  |
| bf16   | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16` | ~3.4 GB | ~4 GB   | normal  | best    |

Default is `bf16`. Drop to 6-bit on a 16 GB Mac that's tight on memory; drop to 4-bit only if you want to compare quality side-by-side.

```bash
# In ~/.voicemode/voicemode.env
VOICEMODE_IMPRESSIONS_MODEL=mlx-community/Qwen3-TTS-12Hz-1.7B-Base-6bit
```

## Remote mlx-audio (e.g. ms2)

When your Apple Silicon box isn't where Claude runs, point VoiceMode at a remote mlx-audio service over Tailscale or a local network. You set **two** env vars on the *client*: the base URL of the remote service, and the path-as-seen-by-the-server where voices live.

```bash
# ~/.voicemode/voicemode.env on the client (e.g. an Intel Mac driving ms2)
VOICEMODE_MLX_AUDIO_BASE_URL=http://ms2.your-tailnet.ts.net:8890/v1
VOICEMODE_REMOTE_VOICES_DIR=/Users/admin/.voicemode/voices  # path on ms2
```

VoiceMode rewrites `ref_audio` paths to start with `VOICEMODE_REMOTE_VOICES_DIR` before sending requests, so the remote mlx-audio process can find the WAV files on its own filesystem. The voices themselves must already exist on the remote box (rsync them, or mount the directory).

If you want HTTPS, expose the mlx-audio port via `tailscale serve --bg http://localhost:8890` on ms2 and point the client at `https://ms2.your-tailnet.ts.net/v1` instead.

## Troubleshooting

### "Connection refused" on first impression

The mlx-audio launchd unit hasn't started or has crashed.

```bash
voicemode service status mlx-audio          # Is it running?
voicemode service start  mlx-audio          # Start it
voicemode service logs   mlx-audio --lines 200
```

### "model not found" on first impression

The model is downloaded lazily on the first synthesis. Expect a 1-3 minute pause as ~3.4 GB streams from Hugging Face. If the call times out, just retry — the partial download resumes.

### Service installed but `voicemode converse --voice fleabag` falls back to Kokoro

The voice isn't being recognised as an impression profile. Check:

1. The directory exists at `$VOICEMODE_VOICES_DIR/fleabag/` (default `~/.voicemode/voices/fleabag/`).
2. There's a `default.wav` inside (file or symlink).
3. No name collision with a Kokoro voice — if you named it `af_sky`, Kokoro wins on case-insensitive match in some routing paths.

```bash
ls -la ~/.voicemode/voices/fleabag/
```

### Apple Silicon only

`voicemode service install mlx-audio` checks the host architecture. On Intel Macs / Linux / Windows it refuses to install — there is no fallback. Use the cloud TTS providers (OpenAI) instead, or run mlx-audio on a separate Apple Silicon box and point at it remotely.

### "VOICEMODE_CLONE_BASE_URL is deprecated" warning on startup

You have an old name in `~/.voicemode/voicemode.env`. Rename it:

| Deprecated                 | Replace with                   |
| -------------------------- | ------------------------------ |
| `VOICEMODE_CLONE_BASE_URL` | `VOICEMODE_MLX_AUDIO_BASE_URL` |
| `VOICEMODE_CLONE_MODEL`    | `VOICEMODE_IMPRESSIONS_MODEL`  |
| `VOICEMODE_CLONE_PORT`     | `VOICEMODE_MLX_AUDIO_PORT`     |

The old names work in 8.7.x but **stop working in 8.8.0**.

## See also

- [Impressions guide](../../../../docs/guides/impressions.md) — user-facing prose.
- [Finding good samples](finding-samples.md) — clip selection and processing.
