# Kokoro FastAPI Installation Tool Specification

## Overview
Create an MCP tool that automates the installation and setup of remsky/kokoro-fastapi, a FastAPI server for Kokoro TTS (Text-to-Speech) service.

## Tool Name
`install_kokoro_fastapi`

## Parameters
- `install_dir` (str, optional): Directory to install kokoro-fastapi (default: ~/kokoro-fastapi)
- `models_dir` (str, optional): Directory for Kokoro models (default: ~/Models/kokoro)
- `port` (int, optional): Port to configure for the service (default: 8880)
- `auto_start` (bool, optional): Start the service after installation (default: true)
- `install_models` (bool, optional): Download Kokoro models (default: true)
- `force_reinstall` (bool, optional): Force reinstallation even if already installed (default: false)

## Requirements Analysis

### System Requirements
- Python 3.10+
- Git
- Sufficient disk space for models (~5GB)
- UV package manager (will install if missing)

### Python Dependencies
- FastAPI
- Kokoro TTS
- Other dependencies from requirements.txt

## Implementation Steps

### 1. Prerequisites Check
```python
# Check Python version
import sys
if sys.version_info < (3, 10):
    raise RuntimeError("Python 3.10+ required")

# Check for git
if not shutil.which("git"):
    raise RuntimeError("Git is required")

# Install UV if not present
if not shutil.which("uv"):
    subprocess.run(["curl -LsSf https://astral.sh/uv/install.sh | sh"], shell=True)
```

### 2. Clone Repository
```bash
# Clone kokoro-fastapi
git clone https://github.com/remsky/kokoro-fastapi.git "$install_dir"
cd "$install_dir"
```

### 3. Create Virtual Environment and Install Dependencies
```bash
# Use UV for faster installation
cd "$install_dir"
uv venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
uv pip install -r requirements.txt
```

### 4. Download Kokoro Models
```python
# Create models directory
os.makedirs(models_dir, exist_ok=True)

# Download models from HuggingFace
models = [
    "kokoro-v0_19.onnx",
    "kokoro-v0_19.onnx.json",
    # Additional model files as needed
]

for model in models:
    download_url = f"https://huggingface.co/remsky/kokoro/resolve/main/{model}"
    download_file(download_url, f"{models_dir}/{model}")
```

### 5. Configure Service
```python
# Create configuration file
config = {
    "host": "127.0.0.1",
    "port": port,
    "models_dir": models_dir,
    "log_level": "info"
}

with open(f"{install_dir}/config.json", "w") as f:
    json.dump(config, f, indent=2)
```

### 6. Create Systemd Service (Linux) or LaunchAgent (macOS)

#### Linux (systemd)
```ini
[Unit]
Description=Kokoro FastAPI TTS Service
After=network.target

[Service]
Type=simple
User=%s
WorkingDirectory=%s
Environment="PATH=%s"
ExecStart=%s/venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port %d
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

#### macOS (launchd)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.kokoro.fastapi</string>
    <key>ProgramArguments</key>
    <array>
        <string>%s/venv/bin/python</string>
        <string>-m</string>
        <string>uvicorn</string>
        <string>main:app</string>
        <string>--host</string>
        <string>127.0.0.1</string>
        <string>--port</string>
        <string>%d</string>
    </array>
    <key>WorkingDirectory</key>
    <string>%s</string>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
```

### 7. Verify Installation
```python
# Test the API endpoint
import requests
import time

if auto_start:
    # Wait for service to start
    time.sleep(2)
    
    # Check health endpoint
    response = requests.get(f"http://127.0.0.1:{port}/health")
    if response.status_code != 200:
        raise RuntimeError("Service health check failed")
    
    # Test TTS endpoint
    test_response = requests.post(
        f"http://127.0.0.1:{port}/v1/audio/speech",
        json={"text": "Hello world", "voice": "af_sky"}
    )
    if test_response.status_code != 200:
        raise RuntimeError("TTS test failed")
```

## Return Value
Dictionary containing:
- `success` (bool): Installation success status
- `install_path` (str): Path where kokoro-fastapi was installed
- `models_path` (str): Path to Kokoro models
- `service_url` (str): URL of the running service
- `service_status` (str): Status of the service (running/stopped)
- `available_voices` (list): List of available TTS voices

## Error Handling
- Check for port conflicts
- Handle model download failures with retry
- Verify disk space before downloading models
- Provide cleanup on installation failure
- Check for existing installations

## Testing Requirements
1. Test installation on macOS and Linux
2. Test with custom ports
3. Test model download and verification
4. Test service startup and API endpoints
5. Test force reinstall functionality
6. Verify systemd/launchd integration

## Integration with Voice Mode
- Update voice mode TTS provider configuration
- Register kokoro-fastapi as available TTS provider
- Update provider health checks
- Add to voice registry