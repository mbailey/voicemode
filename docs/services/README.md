# Voice Mode Services

Voice Mode uses local services for speech-to-text (STT) and text-to-speech (TTS) functionality, with cloud fallback options.

## Available Services

- **[Kokoro](kokoro.md)**: High-quality local text-to-speech service with multiple voices and languages
- **[Whisper](whisper.md)**: Fast and accurate local speech-to-text service using OpenAI's Whisper models

## Service Management

Voice Mode provides comprehensive service management through tools, prompts, and resources.

### Tools

- [`service`](../../voice_mode/tools/service.py): Unified service management for start, stop, status, restart, enable, disable, and logs
- [`kokoro_install`](../../voice_mode/tools/services/kokoro/install.py): Automated installation and setup of Kokoro TTS service
- [`kokoro_uninstall`](../../voice_mode/tools/services/kokoro/uninstall.py): Clean uninstallation of Kokoro TTS service with optional data removal
- [`whisper_install`](../../voice_mode/tools/services/whisper/install.py): Automated installation and setup of Whisper STT service
- [`whisper_uninstall`](../../voice_mode/tools/services/whisper/uninstall.py): Clean uninstallation of Whisper STT service with optional data removal
- [`download_model`](../../voice_mode/tools/services/whisper/download_model.py): Download and convert Whisper models with Core ML support

### Prompts

- [`whisper`](../../voice_mode/prompts/services.py): Quick access to Whisper service management commands
- [`kokoro`](../../voice_mode/prompts/services.py): Quick access to Kokoro service management commands
- [`voice-status`](../../voice_mode/prompts/status.py): Check the status of all voice services and providers

### Resources

#### LaunchD (macOS)
- [`com.voicemode.kokoro.plist`](../../voice_mode/resources/launchd/com.voicemode.kokoro.plist): macOS service definition for Kokoro auto-start
- [`com.voicemode.whisper.plist`](../../voice_mode/resources/launchd/com.voicemode.whisper.plist): macOS service definition for Whisper auto-start

#### Systemd (Linux)
- [`voicemode-kokoro.service`](../../voice_mode/resources/systemd/voicemode-kokoro.service): Linux service definition for Kokoro auto-start
- [`voicemode-whisper.service`](../../voice_mode/resources/systemd/voicemode-whisper.service): Linux service definition for Whisper auto-start

#### Version Management
- [`versions.json`](../../voice_mode/resources/versions.json): Service file version tracking for update management

## Service Commands

### Basic Operations
- `service("kokoro", "status")` - Check if Kokoro is running
- `service("whisper", "start")` - Start Whisper service
- `service("kokoro", "stop")` - Stop Kokoro service
- `service("whisper", "restart")` - Restart Whisper service

### Boot Management
- `service("kokoro", "enable")` - Configure Kokoro to start at boot/login
- `service("whisper", "disable")` - Remove Whisper from boot/login startup

### Debugging
- `service("kokoro", "logs", 100)` - View last 100 lines of Kokoro logs
- `service("whisper", "logs")` - View recent Whisper logs (default 50 lines)

## Installation

Services can be installed automatically:

```python
# Install Kokoro TTS
kokoro_install()

# Install Whisper STT
whisper_install()

# Download Whisper models
download_model("large-v2")
```

## Uninstallation

Services can be cleanly uninstalled:

```python
# Uninstall Kokoro (keep models and data)
kokoro_uninstall()

# Uninstall Kokoro and remove models
kokoro_uninstall(remove_models=True)

# Uninstall Kokoro completely (remove everything)
kokoro_uninstall(remove_models=True, remove_all_data=True)

# Same options available for Whisper
whisper_uninstall()
whisper_uninstall(remove_models=True)
whisper_uninstall(remove_models=True, remove_all_data=True)
```

## Configuration

Services are configured through environment variables:

- `VOICEMODE_KOKORO_PORT` - Kokoro service port (default: 8880)
- `VOICEMODE_WHISPER_PORT` - Whisper service port (default: 2022)
- `VOICEMODE_SERVICE_AUTO_ENABLE` - Auto-enable services after installation (default: false)

See the individual service documentation for more configuration options.