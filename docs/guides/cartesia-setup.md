# Cartesia Text-to-Speech Setup

Cartesia is a low-latency cloud TTS service. VoiceMode supports it through a
dedicated provider that uses Cartesia's SSE streaming endpoint, so audio
starts playing within a few hundred milliseconds regardless of message
length.

## Quick Start

1. Sign up at [cartesia.ai](https://cartesia.ai) and grab an API key.
2. Pick a voice from [play.cartesia.ai/voices](https://play.cartesia.ai/voices)
   and copy its UUID.
3. Add the following to `~/.voicemode/voicemode.env`:

   ```bash
   # Add Cartesia first so it gets picked over OpenAI by default
   VOICEMODE_TTS_BASE_URLS=https://api.cartesia.ai,https://api.openai.com/v1

   # The voice id you copied above
   VOICEMODE_VOICES=<your-cartesia-voice-uuid>,onyx

   CARTESIA_API_KEY=sk_car_...
   VOICEMODE_CARTESIA_VOICE_ID=<your-cartesia-voice-uuid>
   VOICEMODE_CARTESIA_MODEL=sonic-3
   VOICEMODE_CARTESIA_FALLBACK_MODEL=sonic-2
   ```

4. Restart your MCP client (or run `/mcp` → reconnect) so the new config is
   loaded.

Any UUID-shaped entry in `VOICEMODE_VOICES` is treated as a Cartesia voice
id, so you can list multiple Cartesia voices and switch between them by
reordering the list.

## How It Works

VoiceMode auto-detects Cartesia from the `api.cartesia.ai` base URL and
routes requests through `voice_mode.cartesia_tts`:

- **Streaming path** (`stream`) — POSTs to `/tts/sse` and yields raw PCM
  `int16` chunks as they arrive. `streaming.stream_cartesia_pcm` plays each
  chunk via `sounddevice` the moment it lands.
- **Buffered fallback** (`synthesize`) — POSTs to `/tts/bytes` and returns a
  full WAV. Used if SSE fails or `VOICEMODE_STREAMING_ENABLED=false`.

If the configured model isn't recognised, both paths automatically retry
with `VOICEMODE_CARTESIA_FALLBACK_MODEL`.

## Configuration Reference

| Variable                            | Default   | Description                                                      |
| ----------------------------------- | --------- | ---------------------------------------------------------------- |
| `CARTESIA_API_KEY`                  | —         | API key (required).                                              |
| `VOICEMODE_CARTESIA_VOICE_ID`       | —         | Default voice id (required if no UUID is in `VOICEMODE_VOICES`). |
| `VOICEMODE_CARTESIA_MODEL`          | `sonic-3` | Primary model.                                                   |
| `VOICEMODE_CARTESIA_FALLBACK_MODEL` | `sonic-2` | Used if the primary model is rejected.                           |

## Pricing & Limits

Cartesia bills 1 credit per character of TTS output. The free tier includes
20K credits; the Pro tier is $4/month for 100K credits — typically 15–20
hours of voice-mode conversation depending on reply length.

See [cartesia.ai/pricing](https://cartesia.ai/pricing) for current tiers.

## Troubleshooting

**`CartesiaError: CARTESIA_API_KEY is not set`** — The variable isn't in
your shell environment or in `voicemode.env`. Confirm with
`voicemode config list | grep CARTESIA`.

**Audio cuts off mid-sentence** — Likely a network drop during the SSE
stream. Streaming silently ends; check `~/.voicemode/logs/events/` for the
`TTS_PLAYBACK_END` event and its `bytes_received` count vs. expected.

**Slower than expected first-audio time** — Verify streaming is engaged by
looking for `Starting Cartesia SSE streaming` in voicemode logs. If the log
line is missing, the buffered path is being used; check `STREAMING_ENABLED`.
