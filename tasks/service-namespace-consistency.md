# Service Namespace Consistency

## Problem

There's an inconsistency in service naming between different tools:

1. **Service tool** expects:
   - `com.voicemode.whisper.plist`
   - `com.voicemode.kokoro.plist`

2. **Installation tools** create:
   - `com.voicemode.whisper-server.plist` (whisper_install)
   - `com.voicemode.kokoro.plist` (kokoro_install - correct)

This causes issues where the service tool can't find services installed by the installation tools.

## Current State

### Service Tool (service.py)
- macOS: Looks for `com.voicemode.{service_name}.plist`
- Linux: Looks for `voicemode-{service_name}.service`

### Installation Tools
- **whisper_install**: Creates `com.voicemode.whisper-server.plist`
- **kokoro_install**: Creates `com.voicemode.kokoro.plist` ✓

## Proposed Solution

Standardize on the simpler naming convention used by the service tool:

### macOS (launchd)
- Whisper: `com.voicemode.whisper.plist`
- Kokoro: `com.voicemode.kokoro.plist`

### Linux (systemd)
- Whisper: `voicemode-whisper.service`
- Kokoro: `voicemode-kokoro.service`

## Required Changes

### 1. Update whisper_install.py
- Change plist name from `com.voicemode.whisper-server` to `com.voicemode.whisper`
- Update any references in the installation process

### 2. Update any existing templates
- Check if there are hardcoded references to `whisper-server` in templates

### 3. Migration handling
- Check for old naming and offer to migrate
- Or handle both names in service tool temporarily

## Benefits

1. **Consistency**: All services follow the same naming pattern
2. **Simplicity**: Service name matches the command name
3. **Predictability**: Easy to know what files to look for
4. **Compatibility**: Service tool works with all installed services

## Implementation Steps

1. ✅ Update whisper_install to use consistent naming
   - Changed plist name from `com.voicemode.whisper-server` to `com.voicemode.whisper`
   - Changed Linux service from `whisper-server.service` to `voicemode-whisper.service`
   - Updated log file paths to use consistent naming in logs directory
2. ✅ Templates already use correct naming
   - Templates in resources/launchd and resources/systemd are already correct
3. Add migration logic for existing installations (TODO)
4. Test all service operations with new naming (TODO)
5. Update documentation to reflect consistent naming (TODO)

## Changes Made

### whisper/install.py
- Line 271: `com.voicemode.whisper-server.plist` → `com.voicemode.whisper.plist`
- Line 279: `com.voicemode.whisper-server` → `com.voicemode.whisper`
- Line 291: Log path updated to `logs/whisper.out.log`
- Line 293: Log path updated to `logs/whisper.err.log`
- Line 352: `whisper-server.service` → `voicemode-whisper.service`
- Lines 365-366: Updated log paths for systemd