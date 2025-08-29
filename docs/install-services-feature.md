# Voice Mode Service Installation Feature

## Overview

The Voice Mode installer (`install`) now includes an integrated service installation feature that offers to install Whisper, Kokoro, and LiveKit services after the core Voice Mode setup is complete.

## Features

### User-Friendly Interface
- Clear introduction explaining the benefits of local services
- Three installation modes:
  - **Quick Mode (Y)**: Install all services with one confirmation
  - **Selective Mode (s)**: Choose which services to install
  - **Skip Mode (n)**: Skip service installation

### Service Descriptions
- **Whisper**: Fast local speech-to-text (no cloud required)
- **Kokoro**: Natural text-to-speech with multiple voices
- **LiveKit**: Real-time voice communication server

### Benefits Highlighted
- **Privacy**: All processing happens locally
- **Speed**: No network latency
- **Reliability**: Works offline

## Implementation Details

### Composable Design
- Uses existing `voice-mode` CLI commands
- No code duplication - leverages existing service installation tools
- Consistent behavior across install script and manual CLI usage

### Early Sudo Caching
- Requests administrator access early in the process
- Prevents repeated password prompts during service installation
- Gracefully handles cases where sudo is not available

### Cross-Platform Support
- Works on macOS (Intel and Apple Silicon)
- Works on Linux (Ubuntu, Fedora)
- Handles platform-specific service management (launchd/systemd)

### Error Handling
- Timeout protection (300 seconds per service)
- Graceful failure handling with helpful error messages
- Continues with remaining services if one fails
- Reports summary of successes/failures

## Usage

### Default Flow
```bash
curl -sSf https://getvoicemode.com/install | sh
```

Users will see:
```
🎤 Voice Mode Services

Voice Mode can install local services for the best experience:
  • Whisper - Fast local speech-to-text (no cloud required)
  • Kokoro - Natural text-to-speech with multiple voices
  • LiveKit - Real-time voice communication server

Benefits:
  • Privacy - All processing happens locally
  • Speed - No network latency
  • Reliability - Works offline

Install all recommended services? [Y/n/s]: 
```

### Testing

A comprehensive test suite is provided in `test_install_services.sh`:
```bash
./test_install_services.sh
```

The test suite covers:
- Voice-mode CLI detection
- Install all mode
- Selective installation
- Failure handling
- Full integration testing
- Platform-specific behavior
- Error handling and timeouts
- User input validation

## Technical Notes

### Service Installation Commands
The installer uses these commands internally:
```bash
voice-mode whisper install --auto-enable
voice-mode kokoro install --auto-enable
voice-mode livekit install --auto-enable
```

### Requirements
- Voice Mode must be successfully configured first
- Administrator access (sudo) for service management
- Sufficient disk space (~5GB for models)
- Internet connection for downloads

### Port Usage
- Whisper: 2022
- Kokoro: 8880
- LiveKit: 7880

The service tools handle port conflicts automatically.

## Future Enhancements

Potential improvements for future versions:
- Progress bars for long-running installations
- Disk space checking before installation
- Network connectivity verification
- Option to configure custom ports
- Uninstall option in the installer
