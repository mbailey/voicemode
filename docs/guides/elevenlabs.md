# ElevenLabs TTS and STT Setup

ElevenLabs is a cloud speech service with expressive, multilingual
text-to-speech and accurate speech-to-text. VoiceMode integrates with
ElevenLabs through its native REST API — no proxy required.

## Quick Start

1. Sign up at [elevenlabs.io](https://elevenlabs.io) and generate an API key
   from your [profile settings](https://elevenlabs.io/app/settings/api-keys).
   The free tier includes **10,000 characters per month** of TTS synthesis.

2. **Find a voice ID.** Voice availability depends on your account and tier —
   there is no universal default. Go to
   [My Voices](https://elevenlabs.io/app/voice-lab) in the ElevenLabs
   dashboard, click a voice, then click **More actions → Copy voice ID** to
   get the 20-character ID (e.g. `IKne3meq5aSn9XLyUdCD` for Charlie).

   > **Free tier note:** Not all voices are accessible via the API on free
   > accounts. If you get a `402 Payment Required` error, choose a different
   > voice. See [Free-tier voices](#free-tier-voices) below for a verified list.

3. Add the following to `~/.voicemode/voicemode.env`:

   ```bash
   # ElevenLabs TTS and STT — single base URL for both
   VOICEMODE_TTS_BASE_URLS=https://api.elevenlabs.io/v1
   VOICEMODE_STT_BASE_URLS=https://api.elevenlabs.io/v1

   # API key
   ELEVENLABS_API_KEY=sk_...

   # Voice ID — required, no default (voice availability is account-specific)
   VOICEMODE_ELEVENLABS_VOICE_ID=IKne3meq5aSn9XLyUdCD
   ```

4. Restart your MCP client (or run `/mcp` → reconnect) so the new config is
   loaded.

## Why ElevenLabs

- **Multilingual in one model** — `eleven_flash_v2_5` (the default) supports 32
  languages in a single voice. No separate model per language.
- **Expressive** — naturalness and emotional range well above most local models.
- **Fast** — `eleven_flash_v2_5` has ~75ms median latency; `eleven_multilingual_v2`
  is slower but slightly higher quality.
- **Voice cloning** — paste any 20-char voice ID from your ElevenLabs dashboard
  into `VOICEMODE_ELEVENLABS_VOICE_ID`.

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
VOICEMODE_ELEVENLABS_VOICE_ID=IKne3meq5aSn9XLyUdCD   # Charlie — replace with your voice
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
| `VOICEMODE_ELEVENLABS_VOICE_ID` | `IKne3meq5aSn9XLyUdCD` | **Required.** 20-char voice ID — no default, voice availability is account and tier-specific |
| `VOICEMODE_ELEVENLABS_MODEL` | `eleven_flash_v2_5` | TTS model (default: `eleven_flash_v2_5`) |
| `VOICEMODE_ELEVENLABS_FALLBACK_MODEL` | `eleven_multilingual_v2` | TTS fallback model |
| `VOICEMODE_ELEVENLABS_STT_MODEL` | `scribe_v1` | STT model (default: `scribe_v1`) |

## Finding Voice IDs

Voice IDs are 20-character alphanumeric strings. VoiceMode identifies ElevenLabs
voices by this shape — entries in `VOICEMODE_VOICES` that are 20-char alphanumeric
are routed to ElevenLabs; other formats (Kokoro `af_sky`, OpenAI `alloy`) route to
their respective providers.

To find your voice ID:
- Go to [My Voices](https://elevenlabs.io/app/voice-lab) in the ElevenLabs dashboard
- Click a voice → **More actions → Copy voice ID**
- Or call `GET /v1/voices` via the [ElevenLabs API](https://elevenlabs.io/docs/api-reference/voices/get-all)

## Free-tier voices

The following voices are confirmed accessible via the API on free accounts
(verified 2026-10-02). Voice availability may change — if a voice returns
`402 Payment Required`, choose another from this list.

| Name | Voice ID | Style |
|---|---|---|
| Alice | `Xb7hH8MSUJpSbSDYk0k2` | female, British, news |
| Bill | `pqHfZKP75CvOlQylNhV4` | male, American, narration |
| Brian | `nPczCjzI2devNBz1zQrb` | male, American, narration |
| Callum | `N2lVS1w4EtoT3dr4eOWO` | male, Transatlantic, characters |
| Charlie | `IKne3meq5aSn9XLyUdCD` | male, Australian, conversational |
| Chris | `iP95p4xoKVk53GoZ742B` | male, American, conversational |
| Daniel | `onwK4e9ZLuTAKqWW03F9` | male, British, news |
| Eric | `cjVigY5qzO86Huf0OWal` | male, American, conversational |
| George | `JBFqnCBsd6RMkjVDRZzb` | male, British, narration |
| Jessica | `cgSgspJ2msm6clMCkdW9` | female, American, conversational |
| Laura | `FGY2WhTYpPnrIDTdsKH5` | female, American, social media |
| Liam | `TX3LPaxmHKxFdv7VOQHJ` | male, American, narration |
| Lily | `pFZP5JQG7iQjIQuC4Bku` | female, British, narration |
| Matilda | `XrExE9yKIg1WjnnlVkGX` | female, American, narration |
| River | `SAz9YHcvj6GT2YYXdXww` | non-binary, American, social media |
| Roger | `CwhRBWXzGAHq8TQ4Fs17` | male, American, social media |
| Sarah | `EXAVITQu4vr4xnSDxMaL` | female, American, news |
| Will | `bIHbv24MWmeRgasZH58o` | male, American, social media |

## Speed Control

ElevenLabs accepts `voice_settings.speed` in the range **0.7–1.2**. VoiceMode
automatically clamps `VOICEMODE_TTS_SPEED` to this range if it exceeds it.

## Tier Notes

- `pcm_44100` output format requires a **Pro** tier subscription.
  The default (`mp3`) works on all tiers including free.
- Not all voices are available on all tiers — the free-tier list above is
  verified. Paid-plan-only voices (e.g. Aria, Charlotte, Rachel) return
  `402 Payment Required` on free accounts.

## Troubleshooting

**`ELEVENLABS_API_KEY is not set`** — Add `ELEVENLABS_API_KEY=sk_...` to
`~/.voicemode/voicemode.env`.

**`401 Unauthorized`** — The API key is set but invalid or expired. Regenerate
it in the ElevenLabs dashboard.

**`'af_sky' is not a valid ElevenLabs voice ID`** — `VOICEMODE_VOICES` contains
a Kokoro or OpenAI voice name. Set `VOICEMODE_ELEVENLABS_VOICE_ID` to a 20-char
ElevenLabs voice ID (see [Free-tier voices](#free-tier-voices) above).

**`402 Payment Required`** — The voice ID you set requires a paid ElevenLabs
plan. Choose a different voice from the free-tier list above.

**`unsupported_model`** — You passed a model name that ElevenLabs doesn't
recognise. Valid TTS models: `eleven_flash_v2_5`, `eleven_multilingual_v2`,
`eleven_turbo_v2_5`. Valid STT models: `scribe_v1`, `scribe_v2`.

**High latency on first request** — `eleven_multilingual_v2` has higher
first-token latency. Switch to `VOICEMODE_ELEVENLABS_MODEL=eleven_flash_v2_5`
for real-time use.
