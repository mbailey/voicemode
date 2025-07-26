# Version Management for Kokoro and Whisper

## Requirements

1. **Install only tagged releases** (not latest commit from main/master)
2. **List available versions** based on git repo tags
3. **Show installed version** in service status output
4. **Specify version during installation** with default to latest release
5. **Check if version already installed** and require --force flag to reinstall
6. **Support upgrades** by installing latest version

## Implementation Tasks

### 1. Version Discovery
- [ ] Create helper functions to fetch git tags from repositories
  - Kokoro: https://github.com/remsky/kokoro-fastapi
  - Whisper: https://github.com/ggerganov/whisper.cpp
- [ ] Parse and sort semantic versions properly
- [ ] Identify latest stable release (exclude pre-release tags)

### 2. Version Tracking
- [ ] Store installed version information
  - Option 1: Write version file during installation (e.g., `.version` in install dir)
  - Option 2: Use git describe or tags if installing via git clone
- [ ] Investigate built-in version reporting:
  - Check if whisper-server has --version flag
  - Check if kokoro-fastapi has version endpoint or similar

### 3. Update Install Tools
- [ ] Add `version` parameter to both install tools (default: "latest")
- [ ] Add `force` parameter to allow reinstallation
- [ ] Check current version before installing
- [ ] Clone/checkout specific tag instead of main branch
- [ ] Store version info after successful installation

### 4. Update Status Display
- [ ] Modify `status_service()` to include version information
- [ ] Try built-in version commands first
- [ ] Fall back to stored version info
- [ ] Show "unknown" if version can't be determined

### 5. Add Version Listing Tool
- [ ] Create `list_versions` tool for both services
- [ ] Show available versions from git tags
- [ ] Indicate which version is installed
- [ ] Mark latest stable release

## API Design

```python
# Install with specific version
whisper_install(version="v1.5.4")  # Install specific version
whisper_install(version="latest")  # Install latest release (default)
whisper_install(version="v1.5.4", force=True)  # Force reinstall

# List available versions
list_whisper_versions()
# Returns:
# Available versions for whisper.cpp:
# * v1.5.5 (latest)
# * v1.5.4 (installed)
# * v1.5.3
# ...

# Status shows version
service("whisper", "status")
# Returns:
# ✅ Whisper is running
#    PID: 1234
#    Port: 2022
#    Version: v1.5.4
#    ...
```

## Implementation Order

1. Start with version discovery helpers
2. Update install tools to use git tags
3. Add version tracking/storage
4. Update status display
5. Add list versions tools
6. Test full workflow

## Testing

- Install specific version
- Verify version in status
- Try to install same version (should skip unless --force)
- Upgrade to latest
- Downgrade to older version
- List available versions