---
name: impressions
description: Adding a custom voice from a short reference clip with local mlx-audio on Apple Silicon; clip requirements, the transcript, configuration, remote servers, troubleshooting.
---
`voicemode clone add <name> <clip.wav>` makes a voice from three to nine seconds of clean speech plus its transcript; then `voice="<name>"`.

# Impressions: custom voices

Preview, opt-in, **Apple Silicon only** (no fallback on Intel, Linux or Windows: use OpenAI voices, or point at a remote Apple box). Qwen3-TTS on mlx-audio takes a short reference clip and speaks fresh text in that voice.

    voicemode service install mlx-audio       # once; a launchd unit. The model (~3.4 GB) downloads lazily on first use: minutes
    voicemode clone add fleabag ~/Downloads/fleabag.wav
    voicemode converse --voice fleabag        # or converse(voice="fleabag") over MCP

## The clip

- **3-9 seconds** (5-9 best) of one speaker, conversational, with no music bed, laugh track, cross-talk, hum or clipping. The model copies what it hears: a clean 6 s beats a noisy 30 s. Varied vowels and consonants generalise better than one repeated phrase.
- Any format in. `clone add` rejects bad lengths and normalises to mono 24 kHz 16-bit PCM with loudnorm I=-16 TP=-1.5 LRA=11, stored as `default.wav`. Trim: `ffmpeg -i in.wav -ss 0 -t 8 out.wav`. Cut from a long source: `ffmpeg -ss 00:01:23.4 -i src.wav -t 7 -c copy clip.wav`. Light hum: `-af arnndn=m=cb.rnnn`. Heavier noise: pick another clip; denoising kills the timbre.
- **Always pair the clip with its transcript.** Without one the model transcribes the clip itself, and any mis-hearing makes the synthesis stammer. `clone add` auto-transcribes into `voice.md`: check it and correct it. Over MCP, `ref_text` carries the transcript for a clip-path voice.

## On disk

`~/.voicemode/voices/<name>/default.wav` plus `voice.md` (front matter: name, source, duration_seconds, format, transcript). Extra WAVs may sit beside `default.wav`, with the active one symlinked to it; a directory with WAVs and no `default.wav` is a sample bin and is skipped. `voices.json` at the root is a legacy index that `clone add` still writes. Never name a voice after a Kokoro voice (`af_sky`): Kokoro wins.

## Configuration, in `~/.voicemode/voicemode.env`

| Variable | Default | Purpose |
|---|---|---|
| `VOICEMODE_VOICES_DIR` | `~/.voicemode/voices` | where profiles live |
| `VOICEMODE_MLX_AUDIO_BASE_URL` | `http://127.0.0.1:8890/v1` | the mlx-audio endpoint |
| `VOICEMODE_REMOTE_VOICES_DIR` | unset | the voices path as a remote server sees it |
| `VOICEMODE_IMPRESSIONS_MODEL` | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16` | `…-6bit` (~1.6 GB) on a tight 16 GB Mac; `…-4bit` smallest |

`VOICEMODE_CLONE_BASE_URL`, `_MODEL` and `_PORT` are deprecated aliases, removed in 8.8.0; suggest renaming them when seen. **Remote mlx-audio**: set the base URL to the Apple box (`http://ms2.your-tailnet.ts.net:8890/v1`, or `https://…/v1` behind `tailscale serve`) and `VOICEMODE_REMOTE_VOICES_DIR` to where the voices live there. The WAVs must exist on that box.

## Troubleshooting

- *Connection refused*: `voicemode service status mlx-audio`, then `start`, then `logs mlx-audio --lines 200`.
- *Model not found* on first use: the lazy download is still running; retry, it resumes.
- Falls back to Kokoro: the profile is not recognised. `ls ~/.voicemode/voices/<name>/` must show `default.wav`, and the name must not be a Kokoro name.
- Stammering: a missing or wrong transcript (above).

Curating many voices: the companion [voice-lab](https://github.com/mbailey/voice-lab) repo (a clip ranker over mlx-whisper word timestamps, batch processing, personas). User-facing prose: `docs/guides/impressions.md`.
