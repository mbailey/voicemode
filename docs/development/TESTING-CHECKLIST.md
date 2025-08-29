# Testing Checklist for Unified Service Management PR

## 🐧 Linux Testing

### Prerequisites
- [ ] Fresh Ubuntu/Debian system (or WSL2)
- [ ] Python 3.10+
- [ ] Git installed
- [ ] No existing voice-mode installation

### Installation Testing
1. **Clone and setup**
   ```bash
   git clone <repo>
   cd voicemode-config-refactor
   git checkout feature/unified-configuration
   uv venv
   source .venv/bin/activate
   uv pip install -e .
   ```

2. **Test Whisper installation**
   ```bash
   # Install Whisper
   /whisper_install
   
   # Verify installation
   /service whisper status
   
   # Test model download
   /download_model large-v2
   ```

3. **Test Kokoro installation**
   ```bash
   # Install Kokoro
   /kokoro_install
   
   # Verify installation
   /service kokoro status
   ```

### Service Management Testing
1. **Basic operations**
   ```bash
   # Status checks
   /service whisper status
   /service kokoro status
   
   # Stop/Start
   /service whisper stop
   /service whisper start
   
   # Restart
   /service kokoro restart
   
   # Logs
   /service whisper logs
   /service kokoro logs
   ```

2. **Systemd integration**
   ```bash
   # Enable services
   /service whisper enable
   /service kokoro enable
   
   # Check systemd status
   systemctl --user status voicemode-whisper
   systemctl --user status voicemode-kokoro
   
   # Reboot test
   sudo reboot
   # After reboot, verify services auto-started
   ```

3. **Voice functionality**
   ```bash
   # Test TTS
   /converse "Hello from Linux" wait_for_response=false
   
   # Test full conversation
   /converse "Testing voice on Linux"
   ```

### Uninstallation Testing
1. **Clean uninstall**
   ```bash
   # Uninstall with model preservation
   /whisper_uninstall
   /kokoro_uninstall
   
   # Verify services stopped
   /service whisper status  # Should show not installed
   /service kokoro status   # Should show not installed
   ```

2. **Full uninstall**
   ```bash
   # Reinstall first
   /whisper_install
   /kokoro_install
   
   # Full uninstall with data removal
   /whisper_uninstall remove_models=true remove_all_data=true
   /kokoro_uninstall remove_models=true remove_all_data=true
   
   # Verify complete removal
   ls ~/.voicemode/  # Should be minimal
   ```

## 🍎 macOS Testing (Fresh System)

### Prerequisites
- [ ] Fresh macOS system (or new user account)
- [ ] Xcode Command Line Tools: `xcode-select --install`
- [ ] No existing voice-mode installation

### Testing Environment Options

#### Option 1: Dedicated Test User (Recommended)
Create a separate user account for isolated testing:
```bash
# Create test user
sudo dscl . -create /Users/voicetest
sudo dscl . -create /Users/voicetest UserShell /bin/bash
sudo dscl . -create /Users/voicetest RealName "Voice Mode Test"
sudo dscl . -create /Users/voicetest UniqueID 1001
sudo dscl . -create /Users/voicetest PrimaryGroupID 20
sudo dscl . -create /Users/voicetest NFSHomeDirectory /Users/voicetest
sudo dscl . -passwd /Users/voicetest testpass123
sudo createhomedir -c -u voicetest

# Make admin for testing
sudo dscl . -append /Groups/admin GroupMembership voicetest

# Switch to test user
su - voicetest

# Install Homebrew fresh for this user
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install)"
```

#### Option 2: Standalone uv Installation
Skip Homebrew entirely and use standalone tools:
```bash
# Install uv without Homebrew
curl -LsSf https://astral.sh/uv/install | sh

# Note: This approach may require manual installation of system dependencies
```

### Installation Testing
1. **Initial setup**
   ```bash
   # Install uv (if using Homebrew)
   brew install uv
   # OR use standalone (if avoiding Homebrew)
   curl -LsSf https://astral.sh/uv/install | sh
   
   # Clone and setup
   git clone <repo>
   cd voicemode-config-refactor
   git checkout feature/unified-configuration
   uv venv
   source .venv/bin/activate
   uv pip install -e .
   ```

2. **Test Whisper installation**
   ```bash
   # Install Whisper (should detect Metal support)
   /whisper_install
   
   # Verify Metal acceleration
   /service whisper status  # Should show Metal support
   
   # Test CoreML model conversion
   /download_model large-v2
   ```

3. **Test Kokoro installation**
   ```bash
   # Install Kokoro (should use GPU acceleration)
   /kokoro_install
   
   # Verify installation
   /service kokoro status
   ```

### Service Management Testing
1. **Basic operations**
   ```bash
   # Same as Linux tests
   /service whisper status
   /service kokoro status
   # ... etc
   ```

2. **LaunchAgent integration**
   ```bash
   # Enable services
   /service whisper enable
   /service kokoro enable
   
   # Check launchd
   launchctl list | grep voicemode
   
   # Verify plists created
   ls ~/Library/LaunchAgents/com.voicemode.*
   
   # Logout/Login test
   # Log out and back in, verify services auto-started
   ```

3. **Audio device testing**
   ```bash
   # List devices
   /check_audio_devices
   
   # Test with different audio devices if available
   /converse "Testing on macOS"
   ```

### Performance Testing
1. **GPU acceleration**
   ```bash
   # Monitor GPU usage during transcription
   # In another terminal: sudo powermetrics --samplers gpu_power
   
   # Long transcription test
   /converse "Please transcribe this long message" listen_duration=30
   ```

2. **Resource usage**
   ```bash
   # Check memory usage
   /service whisper status  # Note memory
   /service kokoro status   # Note memory
   
   # Activity Monitor verification
   ```

### Edge Cases
1. **Network interruption**
   ```bash
   # Disable network
   # Test local services still work
   /converse "Testing offline mode"
   ```

2. **Service crashes**
   ```bash
   # Kill service manually
   pkill -9 whisper-server
   
   # Verify detection
   /service whisper status  # Should show not running
   
   # Restart
   /service whisper start
   ```

3. **Version updates**
   ```bash
   # Check for updates
   /version_info whisper
   /version_info kokoro
   
   # Test update process (if newer versions available)
   ```

## 📋 Cross-Platform Verification

### Configuration
- [ ] Environment variables work correctly
- [ ] Config files in correct locations
- [ ] Permissions set appropriately

### Logging
- [ ] Logs written to correct locations
- [ ] Log rotation works (if applicable)
- [ ] Debug mode provides useful output

### Error Handling
- [ ] Clear error messages for missing dependencies
- [ ] Graceful handling of permission issues
- [ ] Helpful suggestions for common problems

## 🎯 Success Criteria

- [ ] All services install without errors
- [ ] Services start/stop reliably
- [ ] Services persist across reboots
- [ ] Voice conversations work smoothly
- [ ] Uninstallation is clean and complete
- [ ] No regression in existing functionality
- [ ] Resource usage is reasonable
- [ ] Performance is acceptable

## 📝 Notes Section

Use this space to document any issues, observations, or platform-specific behaviors discovered during testing:

---

### Linux Notes:


### macOS Notes:


### General Observations: