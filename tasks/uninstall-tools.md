# Service Uninstall Tools

## Overview

Added uninstall tools for both Whisper and Kokoro services to provide clean removal of installations.

## Implementation

### whisper_uninstall Tool

Located at: `voice_mode/tools/services/whisper/uninstall.py`

Features:
1. Stops any running Whisper service
2. Removes service configurations (launchd/systemd)
3. Removes the whisper.cpp installation
4. Optionally removes downloaded models
5. Optionally removes all Whisper-related data (logs, transcriptions)

Parameters:
- `remove_models` (bool): Remove downloaded Whisper models
- `remove_all_data` (bool): Remove all data including logs and transcriptions

### kokoro_uninstall Tool

Located at: `voice_mode/tools/services/kokoro/uninstall.py`

Features:
1. Stops any running Kokoro service
2. Removes service configurations (launchd/systemd)
3. Removes the kokoro-fastapi installation
4. Optionally removes downloaded Kokoro models
5. Optionally removes all Kokoro-related data (logs, cache, audio files)

Parameters:
- `remove_models` (bool): Remove downloaded Kokoro models
- `remove_all_data` (bool): Remove all data including logs and cache

## Usage Examples

```python
# Basic uninstall (keeps models and data)
whisper_uninstall()
kokoro_uninstall()

# Remove models too
whisper_uninstall(remove_models=True)
kokoro_uninstall(remove_models=True)

# Complete removal
whisper_uninstall(remove_models=True, remove_all_data=True)
kokoro_uninstall(remove_models=True, remove_all_data=True)
```

## Benefits

1. **Clean Removal**: Properly stops services and removes all components
2. **Flexible Options**: Keep models/data for reinstallation or remove everything
3. **Cross-Platform**: Works on both macOS (launchd) and Linux (systemd)
4. **Safe Operation**: Returns detailed status with list of removed items and any errors
5. **Backward Compatible**: Handles both old and new service naming conventions

## Return Format

Both tools return a dictionary with:
```python
{
    "success": bool,
    "message": str,
    "removed_items": list[str],
    "errors": list[str],
    "summary": {
        "items_removed": int,
        "errors_encountered": int
    }
}
```

## Documentation Updated

- Updated `docs/services/README.md` to include the new uninstall tools
- Added uninstallation section with usage examples