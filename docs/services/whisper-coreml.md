# Whisper CoreML Acceleration

Technical documentation for CoreML acceleration in VoiceMode's Whisper implementation.

## Overview

CoreML acceleration provides significant performance improvements for Whisper speech-to-text on Apple Silicon Macs, delivering 2-3x faster transcription speeds compared to Metal-only acceleration.

## Performance Comparison

| Acceleration Type | Processing Speed | Relative Performance | CPU Usage |
|------------------|------------------|---------------------|-----------|
| CPU Only         | ~1x (baseline)   | 100%                | High      |
| Metal (GPU)      | ~3-4x           | 300-400%            | Medium    |
| CoreML + Metal   | ~8-12x          | 800-1200%           | Low       |

*Example: Processing 7.6 seconds of audio in 0.2 seconds (38x real-time) with base.en model*

## Technical Architecture

### CoreML Integration

VoiceMode uses whisper.cpp with CoreML support through:

1. **Model Conversion**: GGML models are converted to CoreML format during installation
2. **Runtime Selection**: whisper.cpp automatically selects CoreML when available
3. **Fallback Support**: Falls back to Metal acceleration if CoreML fails

### Compilation Requirements

CoreML acceleration requires specific build-time dependencies:

- **Full Xcode Installation**: Command Line Tools alone insufficient
- **Core ML Tools**: For model conversion (coremltools Python package)
- **PyTorch**: Required for model conversion pipeline (~2.5GB download)

### Installation Process

1. **Dependency Check**: Verify Xcode and coremlc availability
2. **PyTorch Installation**: Download and install PyTorch via pip
3. **Model Download**: Fetch GGML model from Hugging Face
4. **CoreML Conversion**: Convert GGML → CoreML using coremltools
5. **Verification**: Test CoreML model loading and performance

## Current Implementation Status

### Why CoreML is Currently Disabled

As of the current installer, CoreML installation is commented out due to:

```bash
# Lines 841-842 and 871-872 in install script
# DISABLED: CoreML build issues - users getting errors at 3:30am
# setup_coreml_acceleration
```

### Issues Encountered

1. **Late-night Installation Failures**: Users reported errors during off-hours
2. **Xcode Detection Problems**: Inconsistent Xcode installation detection
3. **PyTorch Download Timeouts**: Large download size causing timeouts
4. **Dependency Conflicts**: Version conflicts between system and pip packages

## Re-enabling CoreML (Technical Guide)

### 1. Prerequisites Verification

```bash
# Check for full Xcode installation
if [[ -f "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/coremlc" ]]; then
    echo "✓ Full Xcode detected"
else
    echo "✗ Full Xcode required (not just Command Line Tools)"
fi

# Verify Xcode license acceptance
xcodebuild -checkFirstLaunchStatus
```

### 2. Model Installation Commands

#### CLI Method
```bash
# Install base model with CoreML conversion
voicemode whisper model install base.en --skip-core-ml=false --install-torch=true

# Force reinstallation with CoreML
voicemode whisper model install base.en --force-download --install-torch=true
```

#### MCP Tool Method
```python
whisper_model_install(
    model="base.en",
    force_download=True,
    skip_core_ml=False,
    install_torch=True,
    auto_confirm=True
)
```

### 3. Troubleshooting Common Issues

#### "CoreML not available" Error
- Verify Xcode installation path: `/Applications/Xcode.app/Contents/Developer`
- Check coremlc binary exists and is executable
- Ensure xcode-select points to full Xcode, not Command Line Tools

#### PyTorch Installation Failures
- Use system Python instead of conda/pyenv
- Clear pip cache: `pip cache purge`
- Install with specific index: `--extra-index-url https://download.pytorch.org/whl/cpu`

#### Model Conversion Failures
- Verify adequate disk space (>5GB free)
- Check /tmp directory permissions
- Monitor conversion logs for specific error messages

## File Locations

### Models Directory
```
~/.voicemode/services/whisper/models/
├── ggml-base.en.bin          # Original GGML model
├── ggml-base.en-encoder.mlmodel  # CoreML encoder
└── ggml-base.en-decoder.mlmodel  # CoreML decoder (if applicable)
```

### Configuration Files
- Service config: `~/.voicemode/services/whisper/config.json`
- Model preferences: `~/.voicemode/whisper-models.txt`
- Installation logs: `~/.voicemode/services/whisper/logs/`

## Performance Tuning

### Model Selection for CoreML

| Model Size | GGML Size | CoreML Size | Accuracy | Speed | Use Case |
|------------|-----------|-------------|----------|--------|----------|
| tiny.en    | 39MB      | ~150MB      | Good     | Fastest| Real-time |
| base.en    | 142MB     | ~400MB      | Better   | Fast   | Balanced |
| small.en   | 466MB     | ~1.2GB      | Best     | Good   | Accuracy |

### Runtime Optimization

```bash
# Set optimal thread count (usually CPU cores)
export WHISPER_CPP_THREADS=8

# Enable CoreML explicitly (if detection fails)
export WHISPER_COREML=1

# Set model path explicitly
export WHISPER_MODEL_PATH="~/.voicemode/services/whisper/models/ggml-base.en.bin"
```

## Development Notes

### Code Locations

- **MCP Tool**: `voice_mode/tools/services/whisper.py`
- **Model Management**: `voice_mode/tools/whisper_model_install.py`
- **Configuration**: `voice_mode/config.py`
- **Service Integration**: `voice_mode/providers.py`

### Future Improvements

1. **Better Error Handling**: More specific error messages for common failures
2. **Partial Installation**: Allow Metal-only fallback during CoreML failures
3. **Model Validation**: Verify CoreML model integrity after conversion
4. **Size Optimization**: Investigate quantization for smaller CoreML models
5. **Auto-retry Logic**: Automatic retry with fallback options

## Security Considerations

- CoreML models run in Apple's secure sandbox
- No additional network access required after installation
- Models stored in user directory with standard permissions
- No elevation required for CoreML runtime (unlike some CUDA setups)

## Monitoring and Logging

### Performance Metrics
```bash
# Check actual acceleration being used
voicemode whisper status

# View performance statistics
voicemode statistics

# Monitor real-time processing
tail -f ~/.voicemode/services/whisper/logs/performance.log
```

### Debug Information
```bash
# Enable debug logging
export VOICEMODE_DEBUG=true

# Test CoreML functionality
voicemode whisper model test base.en

# Benchmark different acceleration methods
voicemode whisper benchmark --models base.en --acceleration metal,coreml
```

This document should be updated as CoreML support evolves and installation issues are resolved.