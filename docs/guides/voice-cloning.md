# Voice Cloning

Clone any voice from a short audio sample and use it for text-to-speech.

## Quick Start

```bash
# 1. Install the clone TTS service (Apple Silicon only, ~3.4GB model download)
voicemode clone install

# 2. Add a voice from a reference audio clip (5-15 seconds of clear speech)
voicemode clone add myvoice ~/Downloads/voice-sample.wav -d "My custom voice"

# 3. Use it
sayas myvoice "Hello, this is my cloned voice speaking"
```

## Requirements

- **Apple Silicon Mac** (M1/M2/M3/M4) — uses MLX for inference
- **VoiceMode installed** — `pip install voicemode` or `uv pip install voicemode`
- ~4GB free memory for the Qwen3-TTS 1.7B model
- ~3.4GB disk for the model download

## Service Management

The clone service runs Qwen3-TTS via mlx-audio, exposing an OpenAI-compatible TTS endpoint.

```bash
# Install (downloads model, creates system service)
voicemode clone install

# Check status
voicemode clone status

# Uninstall (optionally remove the cached model)
voicemode clone uninstall
voicemode clone uninstall --remove-model
```

The service runs on port 8890 by default. Override with `--port`:

```bash
voicemode clone install --port 9000
```

## Voice Profiles

Voice profiles are stored in `~/.voicemode/voices.json`. Each profile maps a name to a reference audio clip and its transcript.

### Adding a Voice

```bash
# Auto-transcribes the audio using local Whisper
voicemode clone add fleabag ~/clips/fleabag.wav -d "Phoebe Waller-Bridge as Fleabag"

# Or provide the transcript manually
voicemode clone add fleabag ~/clips/fleabag.wav \
  -d "Phoebe Waller-Bridge as Fleabag" \
  --ref-text "Hair is everything. It's the difference between a good day and a bad day."
```

Tips for reference audio:
- **Duration**: 5-15 seconds works best
- **Format**: WAV preferred, but any format FFmpeg can read
- **Quality**: Clear speech, minimal background noise
- **Content**: Natural conversational speech, not reading

### Listing Voices

```bash
voicemode clone list
```

### Removing a Voice

```bash
# Remove profile and ref audio file
voicemode clone remove fleabag

# Remove profile but keep the audio file
voicemode clone remove fleabag --keep-audio
```

## Using sayas

`sayas` is the standalone CLI for generating speech with cloned voices:

```bash
# Basic usage
sayas fleabag "Hair is everything, darling"

# Save to file instead of playing
sayas fleabag "Hair is everything" -o output.mp3

# List available voices
sayas -l

# Preview the reference audio clip
sayas fleabag -p

# Print bash completion script
sayas --completion
```

### Bash Completion

```bash
# Add to your .bashrc
eval "$(sayas --completion)"

# Or save to a file
sayas --completion > ~/.bash_completion.d/sayas
source ~/.bash_completion.d/sayas
```

## VoiceMode Integration

When using VoiceMode's converse tool, specify a clone voice by name:

```
voice=fleabag
```

The converse tool automatically routes clone voices to the clone TTS service instead of the standard Kokoro/OpenAI providers.

## Configuration

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICEMODE_CLONE_PORT` | `8890` | Clone service port |
| `VOICEMODE_CLONE_MODEL` | `mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16` | TTS model |

## Architecture

```
~/.voicemode/
├── voices.json              # Voice profile registry
├── voices/                  # Reference audio files
│   ├── fleabag.wav
│   └── mike.wav
└── services/
    └── clone/               # mlx-audio installation
        ├── venv/            # Python venv with mlx-audio
        └── bin/
            └── start-clone-server.sh
```

The clone service exposes an OpenAI-compatible `/v1/audio/speech` endpoint with two extra fields for voice cloning:

```json
{
  "model": "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
  "input": "Text to speak",
  "ref_audio": "/path/to/reference.wav",
  "ref_text": "Transcript of the reference audio"
}
```
