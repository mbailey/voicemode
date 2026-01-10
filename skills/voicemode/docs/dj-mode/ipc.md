# IPC Reference

DJ mode communicates with mpv via JSON IPC over a Unix socket.

## Socket Location

```
/tmp/voicemode-mpv.sock
```

## Sending Commands

Use socat to send JSON commands:

```bash
echo '{"command": [...]}' | socat - /tmp/voicemode-mpv.sock
```

## Common Commands

### Playback Control

```bash
# Pause
echo '{"command": ["set_property", "pause", true]}' | socat - /tmp/voicemode-mpv.sock

# Resume
echo '{"command": ["set_property", "pause", false]}' | socat - /tmp/voicemode-mpv.sock

# Stop
echo '{"command": ["quit"]}' | socat - /tmp/voicemode-mpv.sock

# Seek to position (seconds)
echo '{"command": ["seek", "300", "absolute"]}' | socat - /tmp/voicemode-mpv.sock
```

### Volume

```bash
# Get volume
echo '{"command": ["get_property", "volume"]}' | socat - /tmp/voicemode-mpv.sock

# Set volume (0-100)
echo '{"command": ["set_property", "volume", 50]}' | socat - /tmp/voicemode-mpv.sock
```

### Position and Duration

```bash
# Current position (seconds)
echo '{"command": ["get_property", "time-pos"]}' | socat - /tmp/voicemode-mpv.sock

# Total duration (seconds)
echo '{"command": ["get_property", "duration"]}' | socat - /tmp/voicemode-mpv.sock

# Percentage progress
echo '{"command": ["get_property", "percent-pos"]}' | socat - /tmp/voicemode-mpv.sock
```

### Chapters

```bash
# List all chapters
echo '{"command": ["get_property", "chapter-list"]}' | socat - /tmp/voicemode-mpv.sock

# Current chapter index
echo '{"command": ["get_property", "chapter"]}' | socat - /tmp/voicemode-mpv.sock

# Current chapter metadata
echo '{"command": ["get_property", "chapter-metadata"]}' | socat - /tmp/voicemode-mpv.sock

# Jump to specific chapter
echo '{"command": ["set_property", "chapter", 3]}' | socat - /tmp/voicemode-mpv.sock

# Next chapter
echo '{"command": ["add", "chapter", 1]}' | socat - /tmp/voicemode-mpv.sock

# Previous chapter
echo '{"command": ["add", "chapter", -1]}' | socat - /tmp/voicemode-mpv.sock
```

### Audio Devices

```bash
# List available devices
echo '{"command": ["get_property", "audio-device-list"]}' | socat - /tmp/voicemode-mpv.sock

# Get current device
echo '{"command": ["get_property", "audio-device"]}' | socat - /tmp/voicemode-mpv.sock

# Set device
echo '{"command": ["set_property", "audio-device", "coreaudio/AppleUSBAudioEngine:..."]}' | socat - /tmp/voicemode-mpv.sock
```

## Response Format

All commands return JSON:

```json
{
  "data": <value>,
  "request_id": 0,
  "error": "success"
}
```

On error:
```json
{
  "data": null,
  "request_id": 0,
  "error": "property not found"
}
```

## Using from Python

```python
import socket
import json

def mpv_command(cmd):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect('/tmp/voicemode-mpv.sock')
    sock.send(json.dumps({"command": cmd}).encode() + b'\n')
    response = sock.recv(4096)
    sock.close()
    return json.loads(response)

# Example: get current track
result = mpv_command(["get_property", "chapter-metadata"])
print(result["data"]["TITLE"])
```

## mpv IPC Documentation

For complete IPC reference, see:
- [mpv JSON IPC](https://mpv.io/manual/master/#json-ipc)
- [mpv Properties](https://mpv.io/manual/master/#properties)
- [mpv Commands](https://mpv.io/manual/master/#list-of-input-commands)
