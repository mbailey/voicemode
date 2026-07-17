# WSL2 Microphone Access Troubleshooting Guide

## Overview

The voice-mode MCP server uses the Python `sounddevice` library for audio recording, which relies on PortAudio for cross-platform audio I/O. WSL2 has known limitations with audio device access, particularly for microphone input.

## The Problem

WSL2 does not natively support audio devices. When running voice-mode in WSL2, you may encounter:

1. **No audio devices detected**:
   ```
   sounddevice.PortAudioError: Error querying device -1
   ```

2. **Empty device list**:
   ```python
   sd.query_devices()  # Returns nothing
   ```

3. **Recording failures**:
   ```
   Error: Could not record audio
   ```

## Root Causes

1. **WSL2 Architecture**: WSL2 runs in a lightweight VM and doesn't have direct access to Windows hardware devices
2. **Missing Audio Subsystem**: WSL2 doesn't include ALSA or PulseAudio by default
3. **No Native Audio Drivers**: WSL2 kernel doesn't include sound card drivers

## Solutions

### Solution 1: Windows Permissions + WSL2 Packages (Recommended for WSL 2.3.26.0+)

This solution has been confirmed working on recent WSL2 versions with WSLg support.

#### Prerequisites
- WSL version: 2.3.26.0 or higher
- WSLg enabled (comes with recent WSL2)
- Windows 10/11 with latest updates

#### Steps

1. **Enable Windows Microphone Permissions**:
   - Go to Windows Settings → Privacy & security → Microphone
   - Turn ON "Let desktop apps access your microphone"
   - Ensure your terminal app (Windows Terminal, etc.) has permission

2. **Install Required Packages in WSL2**:
   ```bash
   sudo apt update
   sudo apt install -y libasound2-plugins pulseaudio
   ```

3. **Start PulseAudio** (if not auto-started):
   ```bash
   pulseaudio --start
   ```

4. **Test Audio Devices**:
   ```bash
   # Test with pactl
   pactl info
   pactl list sources short
   
   # Test with Python
   python3 -c "import sounddevice as sd; print(sd.query_devices())"
   ```

5. **Set Default Audio Device** (if needed):
   ```bash
   # List devices
   python3 -m sounddevice
   
   # Set default input device (replace X with device number)
   export VOICEMODE_INPUT_DEVICE=X
   ```

### Solution 2: USB Microphone with USB/IP

For USB microphones, you can use USB/IP to share the device from Windows to WSL2.

#### Steps

1. **Install USB/IP on Windows**:
   - Download from [usbipd-win releases](https://github.com/dorssel/usbipd-win/releases)
   - Install the MSI package

2. **Install USB/IP in WSL2**:
   ```bash
   sudo apt install linux-tools-generic hwdata
   sudo update-alternatives --install /usr/local/bin/usbip usbip /usr/lib/linux-tools/*-generic/usbip 20
   ```

3. **Share USB Device**:
   ```powershell
   # In Windows PowerShell (as Administrator)
   usbipd list
   usbipd bind --busid <BUSID>
   usbipd attach --wsl --busid <BUSID>
   ```

4. **Verify in WSL2**:
   ```bash
   lsusb
   ```

### Solution 3: Network Audio Streaming

Use a network audio solution to stream audio from Windows to WSL2.

#### Option A: PulseAudio Server on Windows

1. **Install PulseAudio for Windows**:
   - Download from [PulseAudio Windows builds](https://www.freedesktop.org/wiki/Software/PulseAudio/Ports/Windows/Support/)
   - Extract to `C:\pulseaudio`

2. **Configure PulseAudio** (`C:\pulseaudio\etc\pulse\default.pa`):
   ```
   load-module module-native-protocol-tcp auth-ip-acl=127.0.0.1;172.16.0.0/12
   load-module module-waveout sink_name=output source_name=input
   ```

3. **Start PulseAudio on Windows**:
   ```cmd
   C:\pulseaudio\bin\pulseaudio.exe -D
   ```

4. **Configure WSL2 to use Windows PulseAudio**:
   ```bash
   # In WSL2
   export PULSE_SERVER=tcp:$(cat /etc/resolv.conf | grep nameserver | awk '{print $2}')
   ```

### Solution 4: LiveKit Transport (Recommended Alternative)

Instead of using local microphone access, use LiveKit for room-based audio:

1. **Set up LiveKit** (see [LiveKit setup guide](../livekit/README.md))

2. **Configure voice-mode**:
   ```bash
   export LIVEKIT_URL="wss://your-app.livekit.cloud"
   export LIVEKIT_API_KEY="your-api-key"
   export LIVEKIT_API_SECRET="your-api-secret"
   ```

3. **Use LiveKit transport**:
   ```python
   # Force LiveKit transport
   converse("Hello", transport="livekit")
   ```

## Debugging Steps

1. **Check WSL Version**:
   ```bash
   wsl --version
   ```

2. **Verify Audio Subsystem**:
   ```bash
   # Check if PulseAudio is running
   ps aux | grep pulse
   
   # Check ALSA
   aplay -l
   
   # Check sounddevice
   python3 -m sounddevice
   ```

3. **Enable Debug Mode**:
   ```bash
   export VOICEMODE_DEBUG=true
   python3 -m voice_mode
   ```

4. **Test Basic Audio**:
   ```python
   import sounddevice as sd
   import numpy as np
   
   # List devices
   print(sd.query_devices())
   
   # Try recording
   duration = 1  # seconds
   fs = 44100
   recording = sd.rec(int(duration * fs), samplerate=fs, channels=1)
   sd.wait()
   print(f"Recorded {len(recording)} samples")
   ```

## Known Limitations

1. **Audio Latency**: Network-based solutions (PulseAudio over TCP) introduce latency
2. **CPU Usage**: Audio streaming can increase CPU usage
3. **Reliability**: Network audio can be less reliable than native access
4. **WSL1 vs WSL2**: WSL1 has better device access but worse overall performance

## Recommendations

1. **For Development**: Use LiveKit transport to bypass local audio requirements
2. **For Testing**: Run voice-mode on native Linux or macOS for best results
3. **For Production**: Deploy to a proper Linux environment or use cloud-based STT/TTS

## Alternative Approaches

1. **Docker with Audio**: Run voice-mode in Docker with proper audio device mapping
2. **Remote Development**: Develop on WSL2 but run voice-mode on a remote Linux server
3. **Dual Boot**: Use native Linux for audio-intensive development

## Environment Variables for Troubleshooting

```bash
# Force specific audio device
export VOICEMODE_INPUT_DEVICE=0

# Increase audio buffer size
export VOICEMODE_AUDIO_BUFFER_SIZE=4096

# Use different microphone recording rate (decoupled from TTS playback)
export VOICEMODE_RECORDING_SAMPLE_RATE=16000

# Enable verbose audio debugging
export VOICEMODE_DEBUG=true
export VOICEMODE_AUDIO_DEBUG=true
```

## References

- [WSL2 Sound Support Issue #5816](https://github.com/microsoft/WSL/issues/5816)
- [Getting sound to work on WSL2](https://discourse.ubuntu.com/t/getting-sound-to-work-on-wsl2/11869)
- [WSL2 Audio Recording with Python sounddevice](https://stackoverflow.com/questions/77012897/how-to-record-audio-with-python-sounddevice-on-wsl)
- [PulseAudio on WSL2 Guide](https://www.linuxuprising.com/2021/03/how-to-get-sound-pulseaudio-to-work-on.html)