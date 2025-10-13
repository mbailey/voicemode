# Environment Variables Reference

Complete reference of all environment variables used by VoiceMode.

## Variable Precedence

Environment variables are processed in this order (highest to lowest priority):
1. Command-line environment (`OPENAI_API_KEY=xxx voice-mode`)
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
| `LIVEKIT_API_KEY` | LiveKit API key | `devkey` | `your-api-key` |
| `LIVEKIT_API_SECRET` | LiveKit API secret | `secret` | `your-secret` |

## Voice Services

### Text-to-Speech (TTS)

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_TTS_BASE_URLS` | Comma-separated TTS service URLs | `http://127.0.0.1:8880/v1,https://api.openai.com/v1` | `http://localhost:8880/v1` |
| `VOICEMODE_VOICES` | Comma-separated voice preferences | `af_sky,alloy` | `nova,shimmer` |
| `VOICEMODE_TTS_VOICE` | Default TTS voice | First from VOICES | `nova` |
| `VOICEMODE_TTS_MODELS` | Comma-separated TTS models | `tts-1-hd,tts-1` | `gpt-4o-mini-tts,tts-1` |
| `VOICEMODE_TTS_MODEL` | Default TTS model | First from MODELS | `tts-1-hd` |
| `VOICEMODE_TTS_SPEED` | Speech speed (0.25-4.0) | `1.0` | `1.5` |

### Speech-to-Text (STT)

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `VOICEMODE_STT_BASE_URLS` | Comma-separated STT service URLs | `https://api.openai.com/v1` | `http://localhost:2022/v1` |
| `VOICEMODE_STT_MODEL` | STT model | `whisper-1` | `whisper-1` |

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

### LiveKit Configuration

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `LIVEKIT_URL` | LiveKit WebSocket URL | `ws://127.0.0.1:7880` | `wss://livekit.example.com` |
| `LIVEKIT_PORT` | LiveKit server port | `7880` | `7881` |
| `VOICEMODE_LIVEKIT_ROOM_PREFIX` | Room name prefix | `voice-mode` | `my-app` |
| `VOICEMODE_LIVEKIT_AUTO_CREATE` | Auto-create rooms | `true` | `false` |

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
| `VOICEMODE_SAMPLE_RATE` | Sample rate in Hz | `24000` | `48000` |
| `VOICEMODE_OPUS_BITRATE` | Opus bitrate in bps | `32000` | `64000` |
| `VOICEMODE_MP3_BITRATE` | MP3 bitrate | `64k` | `128k` |
| `VOICEMODE_AAC_BITRATE` | AAC bitrate | `64k` | `96k` |

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
| `VOICEMODE_VAD_AGGRESSIVENESS` | VAD level (0-3) | `2` | `3` |
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
    "voice-mode": {
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
voice-mode config show --env
```

To test with specific variables:
```bash
VOICEMODE_DEBUG=true VOICEMODE_LOG_LEVEL=debug voice-mode converse
```