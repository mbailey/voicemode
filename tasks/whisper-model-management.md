# Whisper Model Management Enhancement

## Overview
Create a new `download_model` tool for downloading Whisper models with Core ML support on Apple Silicon.

## Requirements

### Tool Name
- `download_model` (not `whisper_download_model` - keep it concise)

### Functionality
1. Download individual Whisper models
2. Download multiple models (accept list)
3. Download all available models (accept 'all' parameter)
4. Automatic Core ML conversion on Apple Silicon
5. Work on all platforms (macOS, Linux, Windows)
6. Respect environment variables for model location

### Environment Variables
- `VOICEMODE_WHISPER_MODEL_DIR`: Custom model directory (default: `~/.voicemode/whisper.cpp/models`)

### Implementation Details

#### Shared Model Download Logic
- Extract model download code from `whisper_install` into a shared helper function
- Both `whisper_install` and `download_model` should use this shared code
- `whisper_install` downloads the default model during installation
- `download_model` provides flexible model management after installation

#### Core ML Support
- On Apple Silicon Macs, automatically run Core ML conversion
- Use whisper.cpp's built-in Core ML conversion scripts
- This provides significant performance improvements on M1/M2/M3 chips

#### Available Models
Standard whisper.cpp models:
- tiny, tiny.en
- base, base.en  
- small, small.en
- medium, medium.en
- large-v1, large-v2, large-v3
- large-v3-turbo

### Tool Parameters
```python
@mcp.tool()
async def download_model(
    model: str | List[str] = "large-v2",  # Single model, list, or "all"
    force_download: bool = False,         # Re-download if exists
    skip_core_ml: bool = False           # Skip Core ML conversion
) -> str:
    """Download Whisper model(s) with optional Core ML conversion."""
```

### File Structure
```
voice_mode/tools/services/whisper/
├── download_model.py  # New tool
├── helpers.py         # Add shared download logic here
└── install.py         # Update to use shared logic
```

## Testing
- Test single model download
- Test multiple model download  
- Test "all" parameter
- Test Core ML conversion on macOS
- Test cross-platform compatibility
- Test environment variable usage

## Documentation Updates
- Update README with new tool
- Document Core ML benefits
- Add examples of tool usage