# ElevenLabs TTS and STT Setup

ElevenLabs is a cloud speech service with expressive, multilingual
text-to-speech and accurate speech-to-text. VoiceMode integrates with
ElevenLabs through its native REST API — no proxy required.

## Quick Start

1. Sign up at [elevenlabs.io](https://elevenlabs.io) and generate an API key
   from your [profile settings](https://elevenlabs.io/app/settings/api-keys).
   The free tier includes **10,000 characters per month** of TTS synthesis.

2. Find a voice ID. Go to the [Voice Library](https://elevenlabs.io/app/voice-library),
   click a voice, and copy the 20-character ID from the URL or voice detail panel
   (e.g. `21m00Tcm4TlvDq8ikWAM` for Rachel).

3. Add the following to `~/.voicemode/voicemode.env`:

   ```bash
   # ElevenLabs TTS and STT — single base URL for both
   VOICEMODE_TTS_BASE_URLS=https://api.elevenlabs.io/v1
   VOICEMODE_STT_BASE_URLS=https://api.elevenlabs.io/v1

   # API key
   ELEVENLABS_API_KEY=sk_...

   # Voice ID (20-character alphanumeric, from the ElevenLabs dashboard)
   VOICEMODE_ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
   ```

4. Restart your MCP client (or run `/mcp` → reconnect) so the new config is
   loaded.

## Why ElevenLabs

- **Multilingual in one model** — `eleven_flash_v2_5` (the default) supports 32
  languages in a single voice. No separate model per language.
- **Expressive** — naturalness and emotional range well above most local models.
- **Fast** — `eleven_flash_v2_5` has ~75ms median latency; `eleven_multilingual_v2`
  is slower but slightly higher quality.
- **Voice cloning** — paste any 20-char voice ID from the library or your own
  cloned voices into `VOICEMODE_ELEVENLABS_VOICE_ID`.

## TTS Models

| Model | Latency | Languages | Notes |
|---|---|---|---|
| `eleven_flash_v2_5` | ~75ms | 32 | Default — best for real-time use |
| `eleven_multilingual_v2` | ~300ms | 29 | Highest quality, long-form |
| `eleven_turbo_v2_5` | ~120ms | 32 | Balanced quality/latency |

Override the default model:
```bash
VOICEMODE_ELEVENLABS_MODEL=eleven_multilingual_v2
VOICEMODE_ELEVENLABS_FALLBACK_MODEL=eleven_flash_v2_5
```

## STT Models

| Model | Notes |
|---|---|
| `scribe_v1` | Default — 90+ languages, word-level timestamps |
| `scribe_v2` | Higher accuracy, same feature set |

Override:
```bash
VOICEMODE_ELEVENLABS_STT_MODEL=scribe_v2
```

## Live Translation Example

Configure VoiceMode to use ElevenLabs for both TTS and STT, then prompt your
LLM to act as a live interpreter:

```bash
# ~/.voicemode/voicemode.env
VOICEMODE_TTS_BASE_URLS=https://api.elevenlabs.io/v1
VOICEMODE_STT_BASE_URLS=https://api.elevenlabs.io/v1
ELEVENLABS_API_KEY=sk_...
VOICEMODE_ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM
```

In the system prompt for your AI:

> You are a live interpreter. When the user speaks in English, respond in
> Spanish. When they speak in Spanish, respond in English. Be concise.

The same voice will deliver both languages naturally.

## Configuration Reference

| Variable | Example | Description |
|---|---|---|
| `VOICEMODE_TTS_BASE_URLS` | `https://api.elevenlabs.io/v1` | Activates ElevenLabs TTS |
| `VOICEMODE_STT_BASE_URLS` | `https://api.elevenlabs.io/v1` | Activates ElevenLabs STT |
| `ELEVENLABS_API_KEY` | `sk_...` | ElevenLabs API key |
| `VOICEMODE_ELEVENLABS_VOICE_ID` | `21m00Tcm4TlvDq8ikWAM` | 20-char voice ID (required for TTS) |
| `VOICEMODE_ELEVENLABS_MODEL` | `eleven_flash_v2_5` | TTS model (default: `eleven_flash_v2_5`) |
| `VOICEMODE_ELEVENLABS_FALLBACK_MODEL` | `eleven_multilingual_v2` | TTS fallback model |
| `VOICEMODE_ELEVENLABS_STT_MODEL` | `scribe_v1` | STT model (default: `scribe_v1`) |

## Finding Voice IDs

Voice IDs are 20-character alphanumeric strings (e.g. `21m00Tcm4TlvDq8ikWAM`).
Find them in:
- The [Voice Library](https://elevenlabs.io/app/voice-library) — click a voice,
  copy the ID from the URL
- The [ElevenLabs API](https://elevenlabs.io/docs/api-reference/voices/get-all) —
  `GET /v1/voices` returns all voices with their IDs

A few well-known built-in IDs:

| Name | Voice ID |
|---|---|
| Rachel | `21m00Tcm4TlvDq8ikWAM` |
| Domi | `AZnzlk1XvdvUeBnXmlld` |
| Bella | `EXAVITQu4vr4xnSDxMaL` |
| Antoni | `ErXwobaYiN019PkySvjV` |
| Elli | `MF3mGyEYCl7XYWbV9V6O` |
| Josh | `TxGEqnHWrfWFTfGW9XjX` |
| Arnold | `VR6AewLTigWG4xSOukaG` |
| Adam | `pNInz6obpgDQGcFmaJgB` |
| Sam | `yoZ06aMxZJJ28mfd3POQ` |

## Speed Control

ElevenLabs accepts `voice_settings.speed` in the range **0.7–1.2**. VoiceMode
automatically clamps `VOICEMODE_TTS_SPEED` to this range if it exceeds it.

## Tier Notes

- `pcm_44100` output format requires a **Pro** tier subscription.
  The default (`mp3`) works on all tiers including free.
- The Voice Library is not available via the API to free tier users,
  but built-in voice IDs still work.

## Troubleshooting

**`ELEVENLABS_API_KEY is not set`** — Add `ELEVENLABS_API_KEY=sk_...` to
`~/.voicemode/voicemode.env`.

**`401 Unauthorized`** — The API key is set but invalid or expired. Regenerate
it in the ElevenLabs dashboard.

**`No ElevenLabs voice ID available`** — Set `VOICEMODE_ELEVENLABS_VOICE_ID`
to a 20-character voice ID from the ElevenLabs dashboard.

**`unsupported_model`** — You passed a model name that ElevenLabs doesn't
recognise. Valid TTS models: `eleven_flash_v2_5`, `eleven_multilingual_v2`,
`eleven_turbo_v2_5`. Valid STT models: `scribe_v1`, `scribe_v2`.

**High latency on first request** — `eleven_multilingual_v2` has higher
first-token latency. Switch to `VOICEMODE_ELEVENLABS_MODEL=eleven_flash_v2_5`
for real-time use.
