# Voice Mode Configuration Reference

Voice Mode can be configured through environment variables to customize its behavior.

## Required Configuration

### OpenAI API Key

```bash
export OPENAI_API_KEY="your-api-key"
```

This is the only required configuration for basic functionality.

## Speech Services Configuration

### Speech-to-Text (STT)

| Variable | Default | Description |
|----------|---------|-------------|
| `STT_BASE_URL` | OpenAI API | Custom STT endpoint (OpenAI-compatible) |
| `STT_MODEL` | `"whisper-1"` | STT model to use |
| `STT_LANGUAGE` | auto-detect | Language code (e.g., "en", "es") |
| `VOICEMODE_STT_AUDIO_FORMAT` | `"mp3"` | Audio format for STT upload |
| `VOICEMODE_WHISPER_MODEL` | `"large-v2"` | Local Whisper model to use (tiny, base, small, medium, large-v2, large-v3) |

### Text-to-Speech (TTS)

| Variable | Default | Description |
|----------|---------|-------------|
| `TTS_BASE_URL` | OpenAI API | Custom TTS endpoint (OpenAI-compatible) |
| `TTS_MODEL` | `"tts-1"` | TTS model to use |
| `TTS_VOICE` | `"alloy"` | Default voice for TTS |
| `TTS_VOICES` | all available | Comma-separated list of allowed voices |
| `TTS_MODELS` | all available | Comma-separated list of allowed models |
| `VOICEMODE_TTS_AUDIO_FORMAT` | `"pcm"` | Audio format for TTS streaming |

### Audio Format Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICEMODE_AUDIO_FORMAT` | `"pcm"` | Default audio format for all operations |
| `VOICEMODE_TTS_AUDIO_FORMAT` | `"pcm"` | Override for TTS only |
| `VOICEMODE_STT_AUDIO_FORMAT` | `"mp3"` | Override for STT upload |
| `VOICEMODE_OPUS_BITRATE` | `"32000"` | Opus codec bitrate |
| `VOICEMODE_MP3_BITRATE` | `"64k"` | MP3 codec bitrate |

Supported formats: `pcm`, `mp3`, `wav`, `flac`, `aac`, `opus`

## LiveKit Configuration

For room-based voice communication:

| Variable | Default | Description |
|----------|---------|-------------|
| `LIVEKIT_URL` | none | LiveKit server URL (e.g., "wss://your-app.livekit.cloud") |
| `LIVEKIT_API_KEY` | none | LiveKit API key |
| `LIVEKIT_API_SECRET` | none | LiveKit API secret |

## Audio Feedback Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_MODE_AUDIO_FEEDBACK` | `"true"` | Enable/disable audio feedback sounds |
| `VOICE_MODE_FEEDBACK_STYLE` | `"whisper"` | Feedback style: "whisper" or "shout" |

## Feature Flags

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICE_ALLOW_EMOTIONS` | `"false"` | Enable emotional TTS (requires gpt-4o-mini-tts) |
| `VOICEMODE_DEBUG` | `"false"` | Enable debug logging |
| `VOICEMODE_SAVE_AUDIO` | `"false"` | Save all audio files |
| `VOICEMODE_DISABLE_SILENCE_DETECTION` | `"false"` | Disable automatic silence detection |

## Audio Recording Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICEMODE_SAMPLE_RATE` | `16000` | Audio sample rate in Hz |
| `VOICEMODE_CHANNELS` | `1` | Number of audio channels |
| `VOICEMODE_CHUNK_DURATION` | `0.03` | Audio chunk duration in seconds |

## Silence Detection Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICEMODE_VAD_MODE` | `3` | WebRTC VAD aggressiveness (0-3) |
| `VOICEMODE_SILENCE_THRESHOLD` | `0.01` | Audio level threshold for silence |
| `VOICEMODE_SILENCE_DURATION` | `0.7` | Seconds of silence before stopping |
| `VOICEMODE_MIN_SPEECH_DURATION` | `0.3` | Minimum speech duration in seconds |

## File Locations

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICEMODE_SAVE_DIR` | `~/voicemode_audio/` | Directory for saved audio files |
| `VOICEMODE_LOG_DIR` | `~/.voicemode/logs/` | Directory for log files |

## Provider Registry Configuration

Multiple provider URLs can be configured:

```bash
# Primary providers
export TTS_BASE_URL="http://127.0.0.1:8880/v1"
export STT_BASE_URL="http://127.0.0.1:2022/v1"

# Additional providers (comma-separated)
export TTS_BASE_URLS="http://127.0.0.1:8880/v1,https://api.openai.com/v1"
export STT_BASE_URLS="http://127.0.0.1:2022/v1,https://api.openai.com/v1"
```

The system will automatically failover to working providers.

## Example Configurations

### Local-Only Setup
```bash
export OPENAI_API_KEY="not-needed-for-local"
export STT_BASE_URL="http://127.0.0.1:2022/v1"
export TTS_BASE_URL="http://127.0.0.1:8880/v1"
```

### Local Whisper with Different Model
```bash
export OPENAI_API_KEY="not-needed-for-local"
export STT_BASE_URL="http://127.0.0.1:2022/v1"
export VOICEMODE_WHISPER_MODEL="base.en"  # Use smaller model for faster processing
```

### High-Quality Cloud Setup
```bash
export OPENAI_API_KEY="your-key"
export TTS_MODEL="tts-1-hd"
export TTS_VOICE="nova"
```

### Emotional TTS Setup
```bash
export OPENAI_API_KEY="your-key"
export VOICE_ALLOW_EMOTIONS="true"
export TTS_MODEL="gpt-4o-mini-tts"
```