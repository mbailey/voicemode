# Whisper.cpp Installation Tool Specification

## Overview
Create an MCP tool that automates the installation of whisper.cpp on macOS and Linux systems, with support for both CPU and GPU configurations.

## Tool Name
`install_whisper_cpp`

## Parameters
- `install_dir` (str, optional): Directory to install whisper.cpp (default: ~/whisper.cpp)
- `model` (str, optional): Whisper model to download (default: "base.en")
  - Options: tiny, tiny.en, base, base.en, small, small.en, medium, medium.en, large-v1, large-v2, large-v3
- `use_gpu` (bool, optional): Enable GPU support if available (default: auto-detect)
- `force_reinstall` (bool, optional): Force reinstallation even if already installed (default: false)

## Requirements Analysis

### macOS Requirements
- Xcode Command Line Tools
- Homebrew (for dependencies)
- Metal support (for GPU acceleration)

### Linux Requirements
- Build essentials (gcc, g++, make)
- CUDA toolkit (for NVIDIA GPU support)
- ROCm (for AMD GPU support)

## Implementation Steps

### 1. System Detection
- Detect operating system (macOS/Linux)
- Check for GPU availability and type
- Verify prerequisite tools are installed

### 2. Dependency Installation

#### macOS
```bash
# Install Xcode CLI tools if needed
xcode-select --install

# Install dependencies via Homebrew
brew install cmake
```

#### Linux
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y build-essential cmake

# Fedora/RHEL
sudo dnf install -y gcc gcc-c++ make cmake

# Check for CUDA
nvidia-smi # If available, build with CUDA support
```

### 3. Clone and Build whisper.cpp
```bash
# Clone repository
git clone https://github.com/ggerganov/whisper.cpp.git "$install_dir"
cd "$install_dir"

# Build based on platform and GPU
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS with Metal support
    make clean
    WHISPER_METAL=1 make -j
else
    # Linux
    if command -v nvidia-smi &> /dev/null; then
        # CUDA support
        make clean
        WHISPER_CUDA=1 make -j
    else
        # CPU only
        make clean
        make -j
    fi
fi
```

### 4. Download Model
```bash
# Download the specified model
cd "$install_dir"
./models/download-ggml-model.sh "$model"
```

### 5. Verify Installation
```bash
# Test whisper with a sample
./main -m "models/ggml-$model.bin" -f samples/jfk.wav
```

## Return Value
Dictionary containing:
- `success` (bool): Installation success status
- `install_path` (str): Path where whisper.cpp was installed
- `model_path` (str): Path to the downloaded model
- `gpu_enabled` (bool): Whether GPU support was enabled
- `performance_info` (dict): Build configuration and capabilities

## Error Handling
- Check for missing dependencies and provide installation commands
- Handle network errors during clone/download
- Verify sufficient disk space
- Provide rollback on failure

## Testing Requirements
1. Test on macOS with and without Metal
2. Test on Linux with and without CUDA
3. Test model download for various sizes
4. Test force reinstall functionality
5. Verify error handling for missing dependencies

## Integration with Voice Mode
- Update voice mode configuration to use installed whisper.cpp
- Provide helper function to get whisper.cpp path
- Update STT provider registry if needed