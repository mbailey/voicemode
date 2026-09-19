# Environment Variables Reference

Complete reference of all environment variables used by VoiceMode.

## Variable Precedence

Environment variables are processed in this order (highest to lowest priority):
1. Command-line environment (`OPENAI_API_KEY=xxx voicemode`)
2. MCP host configuration
3. Shell environment variables
4. Project `.voicemode.env` file
5. User `~/.voicemode/voicemode.env` file
6. Built-in defaults

## Core Configuration

### API Keys

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `OPENAI_API_KEY` | OpenAI API key for cloud TTS/STT | None | `sk-proj-...` |

## Voice Services

### Text-to-Speech (TTS)

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_TTS_BASE_URLS` | Comma-separated TTS service URLs | `http://127.0.0.1:8880/v1,https://api.openai.com/v1` | `http://localhost:8880/v1` |
| `VOICEMODE_VOICES` | Comma-separated voice preferences | `af_sky,alloy` | `nova,shimmer` |
| `VOICEMODE_TTS_VOICE` | Default TTS voice | First from VOICES | `nova` |
| `VOICEMODE_TTS_MODELS` | Comma-separated global TTS models (preference list) | `tts-1-hd,tts-1` | `gpt-4o-mini-tts,tts-1` |
| `VOICEMODE_TTS_MODELS_<PROVIDER>` | Per-provider TTS model override (see below) | Built-in per provider | `mlx-community/Kokoro-82M-bf16` |
| `VOICEMODE_TTS_MODEL` | Default TTS model | First from MODELS | `tts-1-hd` |
| `VOICEMODE_TTS_SPEED` | Speech speed (0.25-4.0) | `1.0` | `1.5` |

#### Per-provider TTS model resolution

When `VOICEMODE_TTS_BASE_URLS` lists providers that need **different** model
identifiers, VoiceMode picks the right model for each provider automatically as
it fails over the chain — no single global override forces one name onto all of
them. This makes the common Apple-Silicon chain
`kokoro-fastapi → mlx-audio → openai` work out of the box: kokoro-fastapi and
OpenAI receive `tts-1`, while mlx-audio (which loads Hugging Face repos on
demand) receives `mlx-community/Kokoro-82M-bf16`.

The dispatcher detects the provider it is about to call and resolves the model
in this order:

1. **Explicit caller model** (`converse(model=...)`) — sent as-is.
2. **`VOICEMODE_TTS_MODELS_<PROVIDER>`** — the suffix is the provider type,
   uppercased with `-` → `_`: `MLX_AUDIO`, `KOKORO`, `OPENAI`, `LOCAL`.
3. **First compatible entry of the global `VOICEMODE_TTS_MODELS`** — mlx-audio
   requires an HF repo id (contains `/`); kokoro/openai require a plain id.
4. **Built-in per-provider default** — mlx-audio → `mlx-community/Kokoro-82M-bf16`,
   everything else → `tts-1`.

```bash
# Explicit per-provider overrides (rarely needed — defaults already work)
VOICEMODE_TTS_MODELS_MLX_AUDIO=mlx-community/Kokoro-82M-bf16
VOICEMODE_TTS_MODELS_KOKORO=tts-1
VOICEMODE_TTS_MODELS_OPENAI=tts-1
```

If you previously worked around mixed-chain failover with a global
`VOICEMODE_TTS_MODELS=mlx-community/Kokoro-82M-bf16`, you can now delete it:
per-provider resolution makes every provider in the chain usable. Clone voices
are unaffected — they always use their profile's pinned model.

### Speech-to-Text (STT)

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_STT_BASE_URLS` | Comma-separated STT service URLs | `https://api.openai.com/v1` | `http://localhost:2022/v1` |
| `VOICEMODE_STT_MODEL` | STT model | `whisper-1` | `whisper-1` |
| `VOICEMODE_STT_PROMPT` | Vocabulary biasing for Whisper (names, terms) | None | `tmux, Tali, kubectl` |

### Whisper Configuration

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_WHISPER_MODEL` | Whisper model size | `large-v2` | `base.en` |
| `VOICEMODE_WHISPER_LANGUAGE` | Language code or 'auto' | `auto` | `en` |
| `VOICEMODE_WHISPER_PORT` | Whisper server port | `2022` | `2023` |
| `VOICEMODE_WHISPER_MODEL_PATH` | Path to Whisper models | `~/.voicemode/models/whisper` | `/models/whisper` |

### Kokoro Configuration

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_KOKORO_PORT` | Kokoro server port | `8880` | `8881` |
| `VOICEMODE_KOKORO_MODELS_DIR` | Kokoro models directory | `~/Models/kokoro` | `/models/kokoro` |
| `VOICEMODE_KOKORO_CACHE_DIR` | Kokoro cache directory | `~/.voicemode/cache/kokoro` | `/cache/kokoro` |
| `VOICEMODE_KOKORO_DEFAULT_VOICE` | Default Kokoro voice | `af_sky` | `am_adam` |

## Soundfonts

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_SOUNDFONTS_ENABLED` | Enable/disable soundfont playback | `true` | `false` |
| `VOICEMODE_HOOK_DEBUG` | Enable debug output from hook receiver | unset | `1` |

`VOICEMODE_SOUNDFONTS_ENABLED` can be set in `~/.voicemode/voicemode.env` or the shell environment. The sentinel file (`~/.voicemode/soundfonts-disabled`, managed by `voicemode soundfonts on/off`) takes priority when present.

See the [Soundfonts Guide](../guides/soundfonts.md) for details.

## Audio Configuration

### Audio Formats

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_AUDIO_FORMAT` | Global audio format | `pcm` | `mp3` |
| `VOICEMODE_TTS_AUDIO_FORMAT` | TTS-specific format | `pcm` | `opus` |
| `VOICEMODE_STT_AUDIO_FORMAT` | STT-specific format | `mp3` | `wav` |

Supported formats: `pcm`, `opus`, `mp3`, `wav`, `flac`, `aac`

### Audio Quality

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_RECORDING_SAMPLE_RATE` | Microphone capture rate in Hz | `24000` | `48000` |
| `VOICEMODE_OPUS_BITRATE` | Opus bitrate in bps | `32000` | `64000` |
| `VOICEMODE_MP3_BITRATE` | MP3 bitrate | `64k` | `128k` |
| `VOICEMODE_AAC_BITRATE` | AAC bitrate | `64k` | `96k` |

`VOICEMODE_RECORDING_SAMPLE_RATE` controls only microphone recording, decoupled from
TTS/playback (fixed at 24kHz). If recordings sound corrupted, sped up, or slowed down,
set this to your microphone's native sample rate (commonly `44100` or `48000` for USB
mics) rather than leaving it at the TTS default. See
[issue #491](https://github.com/mbailey/voicemode/issues/491).

There is no `VOICEMODE_SAMPLE_RATE` variable — TTS playback rate is fixed and not
independently configurable.

### Audio Feedback

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_AUDIO_FEEDBACK` | Enable recording chimes | `true` | `false` |
| `VOICEMODE_FEEDBACK_STYLE` | Chime style | `whisper` | `shout` |
| `VOICEMODE_CHIME_PRE_DELAY` | Silence before chime (seconds) | `0.1` | `1.0` |
| `VOICEMODE_CHIME_POST_DELAY` | Silence after chime (seconds) | `0.2` | `0.5` |

## Voice Activity Detection

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_VAD_AGGRESSIVENESS` | VAD level (0-3) | `3` | `3` |
| `VOICEMODE_DISABLE_VAD` | Disable VAD | `false` | `true` |
| `VOICEMODE_DISABLE_SILENCE_DETECTION` | Disable silence detection | `false` | `true` |
| `VOICEMODE_SILENCE_THRESHOLD` | Silence duration (seconds) | `3.0` | `5.0` |
| `VOICEMODE_MIN_RECORDING_TIME` | Minimum recording (seconds) | `0.5` | `1.0` |
| `VOICEMODE_MAX_RECORDING_TIME` | Maximum recording (seconds) | `120.0` | `60.0` |

## File Storage

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_DATA_DIR` | Data directory | `~/.voicemode` | `/data/voicemode` |
| `VOICEMODE_LOG_DIR` | Log directory | `~/.voicemode/logs` | `/var/log/voicemode` |
| `VOICEMODE_CACHE_DIR` | Cache directory | `~/.voicemode/cache` | `/tmp/voicemode` |
| `VOICEMODE_SAVE_ALL` | Save all audio files | `false` | `true` |
| `VOICEMODE_SAVE_RECORDINGS` | Save input recordings | `false` | `true` |
| `VOICEMODE_SAVE_TTS` | Save TTS output | `false` | `true` |

## Logging and Debugging

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_DEBUG` | Enable debug mode | `false` | `true` |
| `VOICEMODE_LOG_LEVEL` | Log level | `info` | `debug` |
| `VOICEMODE_EVENT_LOG` | Enable event logging | `false` | `true` |
| `VOICEMODE_CONVERSATION_LOG` | Log conversations | `false` | `true` |
| `VOICEMODE_SKIP_TTS` | Skip TTS for testing | `false` | `true` |

Log levels: `debug`, `info`, `warning`, `error`, `critical`

## Advanced Features

### Emotional TTS

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_ALLOW_EMOTIONS` | Enable emotional TTS | `false` | `true` |
| `VOICEMODE_EMOTION_AUTO_UPGRADE` | Auto-upgrade to emotional model | `false` | `true` |

### Service Preferences

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_PREFER_LOCAL` | Prefer local services | `true` | `false` |
| `VOICEMODE_AUTO_START_SERVICES` | Auto-start local services | `false` | `true` |

### Control Channel

See the [Control Channel reference](control-channel.md) for the command surface
(`voicemode control pause|resume|stop|skip-back`) and worked Stream Deck /
media-key / keyword examples.

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_CONTROL_CHANNEL_ENABLED` | Bind the control socket while speaking (pause/resume/stop/skip-back an utterance) | `false` | `true` |
| `VOICEMODE_CONTROL_SOCKET` | Path to the control Unix domain socket | `~/.voicemode/control.sock` | `/tmp/vm-control.sock` |
| `VOICEMODE_HISTORY_BUFFER_SIZE` | How many recent utterances `skip_back` can replay (history ring-buffer depth, ≥1) | `8` | `16` |

### Result Widgets

`converse()` results can carry small, non-spoken, agent-facing one-liners in a
trailing ` | Widgets: ...` segment — text-only, never passed to TTS. The wall-
clock time is the first widget (VM-1961); see the `time_in_response`
parameter in the [Converse Parameters reference](converse-parameters.md) for
the per-call override.

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_TIME_IN_RESPONSE` | Append the current local wall-clock time (`HH:MM:SS`) to every `converse()` result | `false` | `true` |

### Serve Command

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_SERVE_TRANSPORT` | MCP transport protocol (`streamable-http` or `sse`) | `sse` | `streamable-http` |
| `VOICEMODE_SERVE_ALLOW_LOCAL` | Allow localhost connections | `true` | `false` |
| `VOICEMODE_SERVE_ALLOW_ANTHROPIC` | Allow Anthropic IP ranges | `false` | `true` |
| `VOICEMODE_SERVE_ALLOW_TAILSCALE` | Allow Tailscale IP range (100.64.0.0/10) | `false` | `true` |
| `VOICEMODE_SERVE_ALLOWED_IPS` | Custom CIDR allowlist (comma-separated) | None | `192.168.1.0/24,10.0.0.0/8` |
| `VOICEMODE_SERVE_SECRET` | URL path secret segment | None | `my-secret-uuid` |
| `VOICEMODE_SERVE_TOKEN` | Bearer token for authentication | None | `my-secret-token` |

## Legacy Variables

These variables from older versions are still supported:

| Old Variable | New Variable | Notes |
|--------------|--------------|-------|
| `VOICE_MODE_DEBUG` | `VOICEMODE_DEBUG` | Deprecated |
| `VOICE_MODE_SAVE_AUDIO` | `VOICEMODE_SAVE_ALL` | Deprecated |
| `TTS_BASE_URL` | `VOICEMODE_TTS_BASE_URLS` | Still supported |
| `STT_BASE_URL` | `VOICEMODE_STT_BASE_URLS` | Still supported |
| `TTS_VOICE` | `VOICEMODE_TTS_VOICE` | Still supported |
| `TTS_MODEL` | `VOICEMODE_TTS_MODEL` | Still supported |

## Configuration Files

### User Configuration
Create `~/.voicemode/voicemode.env`:
```bash
export OPENAI_API_KEY="sk-..."
export VOICEMODE_VOICES="nova,shimmer"
export VOICEMODE_DEBUG=false
```

### Project Configuration
Create `.voicemode.env` in project root:
```bash
export VOICEMODE_VOICES="onyx"
export VOICEMODE_TTS_SPEED=0.9
```

## MCP Host Configuration

When used as an MCP server, environment variables can be set in the host configuration:

```json
{
  "mcpServers": {
    "voicemode": {
      "command": "uvx",
      "args": ["voice-mode"],
      "env": {
        "OPENAI_API_KEY": "sk-...",
        "VOICEMODE_DEBUG": "true"
      }
    }
  }
}
```

## Debugging Environment

To see all active environment variables:
```bash
voicemode config show --env
```

To test with specific variables:
```bash
VOICEMODE_DEBUG=true VOICEMODE_LOG_LEVEL=debug voicemode converse
```
