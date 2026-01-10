# DJ Mode Installation

DJ mode requires mpv and socat to be installed.

## macOS

```bash
brew install mpv socat
```

## Ubuntu/Debian

```bash
sudo apt update
sudo apt install mpv socat
```

## Fedora

```bash
sudo dnf install mpv socat
```

## Arch Linux

```bash
sudo pacman -S mpv socat
```

## Verification

Check installation:

```bash
mpv --version
socat -V
```

## Scripts Location

The DJ mode scripts are in the VoiceMode skill:

```
skills/voicemode/bin/
├── mpv-dj           # Main DJ control script
└── cue-to-chapters  # CUE to FFmpeg converter
```

For the scripts to work, ensure they're in your PATH or call them with full path.

## Configuration

DJ mode uses:
- **Socket**: `/tmp/voicemode-mpv.sock` for IPC
- **Chapters**: `~/.voicemode/chapters/` for chapter files

Create the chapters directory:

```bash
mkdir -p ~/.voicemode/chapters
```

## Troubleshooting

### "mpv is not installed"

Install mpv using the commands above for your platform.

### "socat is not installed"

Install socat - required for IPC communication.

### "DJ is not running"

mpv must be started first with `mpv-dj play <source>`.

### No sound output

Check mpv's audio device:
```bash
mpv-dj raw '{"command": ["get_property", "audio-device-list"]}'
```

Switch audio output:
```bash
mpv-dj raw '{"command": ["set_property", "audio-device", "auto"]}'
```
