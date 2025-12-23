---
description: Install VoiceMode and its dependencies
allowed-tools: Bash(uvx:*)
---

# /voicemode:install

Install VoiceMode and its dependencies.

## Usage

```
/voicemode:install
```

## Description

Runs the VoiceMode installer to set up local speech-to-text and text-to-speech services. The installer will:

1. Install the VoiceMode package
2. Install Whisper.cpp for local STT
3. Install Kokoro for local TTS
4. Configure services to start automatically
5. Test the installation

## Implementation

Run the VoiceMode installer using UV:

```bash
uvx voice-mode-install
```

The installer is interactive and will:
- Detect the operating system (macOS, Linux)
- Install required dependencies (FFmpeg, Python packages)
- Download and configure Whisper models
- Set up Kokoro TTS service
- Create systemd/launchd service files

## Alternative Installation

If UV is not available:

```bash
curl -sL https://voicemode.ai/install.sh | bash
```

## Post-Installation

After installation completes:

1. Start the services:
   ```
   /voicemode:start
   ```

2. Check they're running:
   ```
   /voicemode:status
   ```

3. Test voice conversation:
   ```
   /voicemode:converse Hello, can you hear me?
   ```

## Troubleshooting

If installation fails, check:
- Python 3.10+ is installed
- UV is available (`pip install uv` or `pipx install uv`)
- Sufficient disk space for models (~2GB)
- Network access for downloads

Load the voicemode skill for detailed troubleshooting guidance.
