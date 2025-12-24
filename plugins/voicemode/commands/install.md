---
description: Install VoiceMode and its dependencies
allowed-tools: Bash(uvx:*), Bash(voicemode:*)
---

# /voicemode:install

Install VoiceMode and its dependencies.

## Implementation

### Step 1: Install VoiceMode Package

Run the installer with `--yes` flag (required for non-interactive environments like Claude Code):

```bash
uvx voice-mode-install --yes
```

This installs the VoiceMode package and CLI. It does NOT install local speech services.

### Step 2: Install Local Speech Services (Optional)

After the VoiceMode package is installed, optionally install local STT and TTS services.

**IMPORTANT**: These commands do NOT support a `--yes` flag - they are already non-interactive.

Install Whisper for local speech-to-text:
```bash
voicemode whisper service install
```

Install Kokoro for local text-to-speech:
```bash
voicemode kokoro install
```

Both installations can take several minutes as they download models.

### Step 3: Verify Installation

After installation completes:

1. Check service status:
   ```bash
   voicemode whisper service status
   voicemode kokoro service status
   ```

2. Start services if needed:
   ```bash
   voicemode whisper service start
   voicemode kokoro service start
   ```

## Notes

- The `voice-mode-install` script requires `--yes` flag in non-interactive mode
- The `voicemode whisper/kokoro install` commands are already non-interactive
- Local services require ~2-3GB disk space for models
- Installation requires network access for downloads
- Services will be configured to start automatically on login
