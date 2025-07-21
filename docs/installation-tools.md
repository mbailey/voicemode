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
- `install_dir` (str, optional): Installation directory (default: `~/whisper.cpp`)
- `model` (str, optional): Whisper model to download (default: `base.en`)
  - Available models: `tiny`, `tiny.en`, `base`, `base.en`, `small`, `small.en`, `medium`, `medium.en`, `large-v1`, `large-v2`, `large-v3`
- `use_gpu` (bool, optional): Enable GPU support (default: auto-detect)
- `force_reinstall` (bool, optional): Force reinstallation (default: false)

#### Return Value
```python
{
    "success": True,
    "install_path": "/Users/user/whisper.cpp",
    "model_path": "/Users/user/whisper.cpp/models/ggml-base.en.bin",
    "gpu_enabled": True,
    "gpu_type": "metal",  # or "cuda" or "cpu"
    "performance_info": {
        "system": "Darwin",
        "gpu_acceleration": "metal",
        "model": "base.en",
        "binary_path": "/Users/user/whisper.cpp/main"
    }
}
```

### install_kokoro_fastapi

Installs [kokoro-fastapi](https://github.com/remsky/kokoro-fastapi) for text-to-speech (TTS) functionality.

#### Features
- Python environment management with UV
- Automatic model downloads
- Service configuration
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
- `install_dir` (str, optional): Installation directory (default: `~/kokoro-fastapi`)
- `models_dir` (str, optional): Models directory (default: `~/Models/kokoro`)
- `port` (int, optional): Service port (default: 8880)
- `auto_start` (bool, optional): Start service after installation (default: true)
- `install_models` (bool, optional): Download Kokoro models (default: true)
- `force_reinstall` (bool, optional): Force reinstallation (default: false)

#### Return Value
```python
{
    "success": True,
    "install_path": "/Users/user/kokoro-fastapi",
    "models_path": "/Users/user/Models/kokoro",
    "service_url": "http://127.0.0.1:8880",
    "service_status": "running",
    "start_command": "bash /Users/user/kokoro-fastapi/start.sh",
    "available_voices": ["af_sky", "af_sarah", "am_adam", ...],
    "config_path": "/Users/user/kokoro-fastapi/config.json"
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

1. **whisper.cpp**: Can be used as an STT provider by configuring the appropriate endpoint
2. **kokoro-fastapi**: Automatically detected by Voice Mode's provider registry when running

## Examples

### Complete Setup

```python
# Install both services
whisper_result = await install_whisper_cpp(model="base.en")
kokoro_result = await install_kokoro_fastapi()

# Check installation status
if whisper_result["success"] and kokoro_result["success"]:
    print("Voice services installed successfully!")
    print(f"Whisper: {whisper_result['install_path']}")
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

#### Start kokoro-fastapi manually:
```bash
cd ~/kokoro-fastapi
bash start.sh
```

#### Stop kokoro-fastapi:
```bash
# Find the process
ps aux | grep uvicorn
# Kill the process
kill <PID>
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