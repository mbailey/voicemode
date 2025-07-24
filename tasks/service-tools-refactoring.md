# Service Tools Refactoring Plan

## Overview
Refactor the service management tools to work with locally installed services instead of using uvx for Python packages. This includes renaming installer tools and updating the kokoro service management tools.

## Goals
1. Rename installer tools to follow consistent naming pattern
2. Update kokoro service tools to manage the locally installed kokoro-fastapi
3. Remove uvx-based service management code
4. Clean up any unused helper functions
5. Ensure consistency with whisper service management approach

## Current State Analysis

### Installer Tools (installers.py)
- `whisper_install` - Installs whisper.cpp locally
- `kokoro_install` - Installs kokoro-fastapi locally

### Service Management Tools (services.py)
- `kokoro_start` - Currently uses uvx to run Python package
- `kokoro_stop` - Stops uvx-managed process
- `kokoro_status` - Checks status of uvx-managed process

## Proposed Changes

### 1. Rename Installer Tools
- `whisper_install` (renamed from `install_whisper_cpp`)
- `kokoro_install` (renamed from `install_kokoro_fastapi`)

### 2. Add Whisper Service Management Tools
Create complete whisper service management:
- `whisper_start` - Start local whisper-server
- `whisper_stop` - Stop whisper-server process
- `whisper_status` - Check whisper-server status
- `whisper_enable` - Enable whisper service at startup (LaunchAgent/systemd)
- `whisper_disable` - Disable whisper service at startup

### 3. Refactor Kokoro Service Tools
Update to work with locally installed kokoro-fastapi:
- `kokoro_start` - Start the installed kokoro-fastapi service
- `kokoro_stop` - Stop the kokoro-fastapi process
- `kokoro_status` - Check kokoro-fastapi status
- `kokoro_enable` - Enable kokoro service at startup (LaunchAgent/systemd)
- `kokoro_disable` - Disable kokoro service at startup

### 4. Service Management Approach

#### macOS
- Use process management for both services
- Check for existing LaunchAgents
- Provide commands for launchctl management

#### Linux
- Use process management for both services
- Check for systemd services
- Provide systemctl commands

## Implementation Steps

### Phase 1: Rename Installer Tools ✅ COMPLETED
1. ✅ Update function names in installers.py
2. ✅ Update any references in documentation
3. ⏳ Test renamed tools

### Phase 2: Create Whisper Service Tools ✅ COMPLETED
1. ✅ Add `whisper_start` function
   - Find whisper-server binary
   - Start with appropriate arguments
   - Track process ID
2. ✅ Add `whisper_stop` function
   - Find and terminate whisper-server process
3. ✅ Add `whisper_status` function
   - Check if process is running
   - Show port status
   - Display resource usage
4. ✅ Add `whisper_enable` function
   - Create/update LaunchAgent plist (macOS)
   - Create/update systemd service (Linux)
   - Set to run at startup
5. ✅ Add `whisper_disable` function
   - Unload LaunchAgent (macOS)
   - Disable systemd service (Linux)

### Phase 3: Refactor Kokoro Service Tools ✅ COMPLETED
1. ✅ Update `kokoro_start`
   - Remove uvx usage
   - Find installed kokoro-fastapi
   - Start with appropriate arguments
2. ✅ Update `kokoro_stop`
   - Find and terminate kokoro process
3. ✅ Update `kokoro_status`
   - Check process status
   - Verify port availability
4. ✅ Add `kokoro_enable` function
   - Create/update LaunchAgent plist (macOS)
   - Create/update systemd service (Linux)
   - Set to run at startup
5. ✅ Add `kokoro_disable` function
   - Unload LaunchAgent (macOS)
   - Disable systemd service (Linux)

### Phase 4: Cleanup ✅ COMPLETED
1. ✅ Remove global `service_processes` dict (no longer used)
2. ✅ Remove uvx-specific code
3. ✅ Update error messages
4. ✅ Add consistent logging

## Service Discovery Strategy

### Finding Installed Binaries
1. Check common installation paths:
   - `~/.voicemode/whisper.cpp/whisper-server`
   - `~/.voicemode/kokoro-fastapi/start-*.sh`
   - System PATH locations

2. Use configuration to find services:
   - Check VOICEMODE_WHISPER_MODEL_PATH
   - Check VOICEMODE_KOKORO_MODELS_DIR

### Process Management
1. Use psutil to find existing processes by:
   - Process name
   - Port binding
   - Command line arguments

2. Track processes using:
   - PID files in ~/.voicemode/run/
   - Process discovery by port

## Testing Plan

1. Test installer tool renaming
2. Test starting/stopping services
3. Test status checking
4. Test with services already running
5. Test with services installed via LaunchAgent/systemd
6. Test error cases (missing installations, port conflicts)

## Enable/Disable Implementation Details

### macOS LaunchAgent Management
1. LaunchAgent files location: `~/Library/LaunchAgents/`
2. File names:
   - `com.voicemode.whisper.plist`
   - `com.voicemode.kokoro.plist`
3. Enable: `launchctl load -w <plist>`
4. Disable: `launchctl unload -w <plist>`

### Linux systemd Management
1. Service files location: `~/.config/systemd/user/`
2. File names:
   - `whisper.service`
   - `kokoro.service`
3. Enable: `systemctl --user enable <service>`
4. Disable: `systemctl --user disable <service>`

### Service File Generation
The enable functions should:
1. Check if service file exists
2. If not, generate from template with current configuration
3. Use paths from the installation directories
4. Include environment variables from configuration

## Tool Summary

### Final Tool Set (14 tools)
**Installers (2)**
- `whisper_install` - Install whisper.cpp
- `kokoro_install` - Install kokoro-fastapi

**Whisper Management (5)**
- `whisper_start` - Start whisper service
- `whisper_stop` - Stop whisper service
- `whisper_status` - Check whisper status
- `whisper_enable` - Enable at startup
- `whisper_disable` - Disable at startup

**Kokoro Management (5)**
- `kokoro_start` - Start kokoro service
- `kokoro_stop` - Stop kokoro service
- `kokoro_status` - Check kokoro status
- `kokoro_enable` - Enable at startup
- `kokoro_disable` - Disable at startup

## Success Criteria

- All tools follow consistent naming pattern
- Service management works for both whisper and kokoro
- No dependency on uvx for kokoro
- Clean, maintainable code
- Comprehensive error handling
- Works alongside LaunchAgent/systemd management
- Enable/disable functions properly manage startup services