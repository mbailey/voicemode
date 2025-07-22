# Voice Mode Installation Tools

Voice Mode now includes MCP tools to automatically install and configure whisper.cpp and kokoro-fastapi, making it easier to set up free, private, open-source voice services.

## Overview

These tools handle:
- System detection (macOS/Linux)
- Dependency installation
- GPU support configuration
- Model downloads
- Service configuration

## Available Tools

### install_whisper_cpp

Installs [whisper.cpp](https://github.com/ggerganov/whisper.cpp) for speech-to-text (STT) functionality.

#### Features
- Automatic OS detection (macOS/Linux)
- GPU acceleration (Metal on macOS, CUDA on Linux)
- Model download management
- Build optimization
- Service configuration (launchd on macOS, systemd on Linux)
- Environment variable support for model selection

#### Usage

```python
# Basic installation with defaults
result = await install_whisper_cpp()

# Custom installation
result = await install_whisper_cpp(
    install_dir="~/my-whisper",
    model="large-v3",
    use_gpu=True,
    force_reinstall=False
)
```

#### Parameters
- `install_dir` (str, optional): Installation directory (default: `~/.voicemode/whisper.cpp`)
- `model` (str, optional): Whisper model to download (default: `large-v2`)
  - Available models: `tiny`, `tiny.en`, `base`, `base.en`, `small`, `small.en`, `medium`, `medium.en`, `large-v2`, `large-v3`
  - Note: large-v2 is default for best accuracy (requires ~3GB RAM)
- `use_gpu` (bool, optional): Enable GPU support (default: auto-detect)
- `force_reinstall` (bool, optional): Force reinstallation (default: false)

#### Return Value
```python
{
    "success": True,
    "install_path": "/Users/user/.voicemode/whisper.cpp",
    "model_path": "/Users/user/.voicemode/whisper.cpp/models/ggml-large-v2.bin",
    "gpu_enabled": True,
    "gpu_type": "metal",  # or "cuda" or "cpu"
    "performance_info": {
        "system": "Darwin",
        "gpu_acceleration": "metal",
        "model": "large-v2",
        "binary_path": "/Users/user/.voicemode/whisper.cpp/main",
        "server_port": 2022,
        "server_url": "http://localhost:2022"
    },
    "launchagent": "/Users/user/Library/LaunchAgents/com.voicemode.whisper-server.plist",  # macOS
    "systemd_service": "/home/user/.config/systemd/user/whisper-server.service",  # Linux
    "start_script": "/Users/user/.voicemode/whisper.cpp/start-whisper-server.sh"
}
```

### install_kokoro_fastapi

Installs [kokoro-fastapi](https://github.com/remsky/kokoro-fastapi) for text-to-speech (TTS) functionality.

#### Features
- Python environment management with UV
- Automatic model downloads
- Service configuration (launchd on macOS, systemd on Linux)
- Auto-start capability

#### Usage

```python
# Basic installation with defaults
result = await install_kokoro_fastapi()

# Custom installation
result = await install_kokoro_fastapi(
    install_dir="~/my-kokoro",
    models_dir="~/my-models",
    port=8881,
    auto_start=True,
    install_models=True,
    force_reinstall=False
)
```

#### Parameters
- `install_dir` (str, optional): Installation directory (default: `~/.voicemode/kokoro-fastapi`)
- `models_dir` (str, optional): Models directory (default: `~/.voicemode/kokoro-models`)
- `port` (int, optional): Service port (default: 8880)
- `auto_start` (bool, optional): Start service after installation (default: true)
- `install_models` (bool, optional): Download Kokoro models (default: true)
- `force_reinstall` (bool, optional): Force reinstallation (default: false)

#### Return Value
```python
{
    "success": True,
    "install_path": "/home/user/.voicemode/kokoro-fastapi",
    "service_url": "http://127.0.0.1:8880",
    "service_status": "managed_by_systemd",  # Linux
    "service_status": "managed_by_launchd",  # macOS
    "systemd_service": "/home/user/.config/systemd/user/kokoro-fastapi-8880.service",  # Linux
    "launchagent": "/Users/user/Library/LaunchAgents/com.voicemode.kokoro-8880.plist",  # macOS
    "start_script": "/home/user/.voicemode/kokoro-fastapi/start-cpu.sh",
    "message": "Kokoro-fastapi installed. Run: cd /home/user/.voicemode/kokoro-fastapi && ./start-cpu.sh"
}
```

## System Requirements

### whisper.cpp

#### macOS
- Xcode Command Line Tools
- Homebrew (for cmake)
- Metal support (built-in)

#### Linux
- Build essentials (gcc, g++, make)
- CMake
- CUDA toolkit (optional, for NVIDIA GPU support)

### kokoro-fastapi

#### All Systems
- Python 3.10+
- Git
- ~5GB disk space for models
- UV package manager (installed automatically if missing)

## Integration with Voice Mode

After installation, the services integrate automatically with Voice Mode:

1. **whisper.cpp**: 
   - Runs automatically on boot (port 2022)
   - OpenAI-compatible API endpoint
   - Model selection via `VOICEMODE_WHISPER_MODEL` environment variable
   - View installed models: `claude resource read whisper://models`

2. **kokoro-fastapi**: 
   - Automatically detected by Voice Mode's provider registry when running
   - 67 voices available
   - OpenAI-compatible API endpoint

## Examples

### Complete Setup

```python
# Install both services with defaults
whisper_result = await install_whisper_cpp()  # Uses large-v2 by default
kokoro_result = await install_kokoro_fastapi()

# Check installation status
if whisper_result["success"] and kokoro_result["success"]:
    print("Voice services installed successfully!")
    print(f"Whisper: {whisper_result['install_path']}")
    print(f"Whisper server: {whisper_result['performance_info']['server_url']}")
    print(f"Kokoro API: {kokoro_result['service_url']}")
```

### Upgrade Existing Installation

```python
# Force reinstall with larger model
result = await install_whisper_cpp(
    model="large-v3",
    force_reinstall=True
)
```

### Custom Configuration

```python
# Install kokoro-fastapi on different port
result = await install_kokoro_fastapi(
    port=9000,
    models_dir="/opt/models/kokoro"
)
```

## Troubleshooting

### Common Issues

1. **Missing Dependencies**
   - The tools will report missing dependencies with installation instructions
   - Follow the provided commands to install required packages

2. **Port Conflicts**
   - If port 8880 is in use, specify a different port for kokoro-fastapi
   - Check running services: `lsof -i :8880`

3. **GPU Not Detected**
   - On Linux, ensure NVIDIA drivers and CUDA are installed
   - Use `nvidia-smi` to verify GPU availability
   - Force CPU mode with `use_gpu=False` if needed

4. **Model Download Failures**
   - Check internet connection
   - Verify sufficient disk space
   - Try smaller models first (tiny, base)

### Manual Service Management

#### macOS (launchd)
```bash
# Whisper
launchctl load ~/Library/LaunchAgents/com.voicemode.whisper-server.plist
launchctl unload ~/Library/LaunchAgents/com.voicemode.whisper-server.plist

# Kokoro
launchctl load ~/Library/LaunchAgents/com.voicemode.kokoro.plist
launchctl unload ~/Library/LaunchAgents/com.voicemode.kokoro.plist
```

#### Linux (systemd)
```bash
# Whisper
systemctl --user start whisper-server
systemctl --user stop whisper-server
systemctl --user status whisper-server

# Kokoro
systemctl --user start kokoro-fastapi-8880
systemctl --user stop kokoro-fastapi-8880
systemctl --user status kokoro-fastapi-8880
```

#### Change Whisper Model
```bash
# Set environment variable before restarting
export VOICEMODE_WHISPER_MODEL=base.en  # or tiny, small, medium, large-v2, large-v3

# Restart service to apply change
# macOS
launchctl unload ~/Library/LaunchAgents/com.voicemode.whisper-server.plist
launchctl load ~/Library/LaunchAgents/com.voicemode.whisper-server.plist

# Linux
systemctl --user restart whisper-server
```

## Testing

Run the test suite to verify installation tools:

```bash
cd /path/to/voicemode
python -m pytest tests/test_installers.py -v

# Skip integration tests (no actual installation)
SKIP_INTEGRATION_TESTS=1 python -m pytest tests/test_installers.py -v
```

## Contributing

When adding new installation tools:

1. Create a new function in `voice_mode/tools/installers.py`
2. Use the `@mcp.tool()` decorator
3. Follow the existing pattern for error handling and return values
4. Add comprehensive tests in `tests/test_installers.py`
5. Update this documentation

## Security Notes

- All installations are performed in user space (no sudo required)
- Models are downloaded from official sources
- Services bind to localhost only by default
- No external network access without explicit configuration