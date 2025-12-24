# VoiceMode Installer Testing Guide for Tart VMs

This guide covers testing the VoiceMode installer on fresh macOS VMs using Tart. It's designed for both automated testing (minions/agents) and manual verification.

## Table of Contents

- [Quick Start](#quick-start)
- [VM Setup Options](#vm-setup-options)
- [Base Image Selection](#base-image-selection)
- [Testing from Branch vs Published Package](#testing-from-branch-vs-published-package)
- [Test Scenarios](#test-scenarios)
- [Verification Steps](#verification-steps)
- [Troubleshooting](#troubleshooting)

## Quick Start

### Automated Testing (Headless)

```bash
# Clone fresh VM from macOS Tahoe (latest)
tart clone ghcr.io/cirruslabs/macos-tahoe-base:latest test-vm

# Start VM in headless mode
tart run test-vm --no-graphics &

# Wait for VM to boot and get IP
sleep 15
VM_IP=$(tart ip test-vm)

# Test published package (non-interactive)
ssh admin@$VM_IP "curl -LsSf https://astral.sh/uv/install.sh | sh && \
  export PATH=\"\$HOME/.local/bin:\$PATH\" && \
  uvx voice-mode-install --yes"

# Verify installation
ssh admin@$VM_IP "export PATH=\"\$HOME/.local/bin:\$PATH\" && voicemode --version"

# Clean up
tart stop test-vm
tart delete test-vm
```

## VM Setup Options

### Headless Mode (Recommended for Automation)

Best for automated testing and CI/CD pipelines. No GUI overhead.

```bash
# Start VM without graphics
tart run <vm-name> --no-graphics &

# Get VM IP address
VM_IP=$(tart ip <vm-name>)

# Connect via SSH
ssh admin@$VM_IP
```

### GUI Mode (For Interactive Debugging)

Useful when you need to see what's happening or debug installation issues.

```bash
# Start VM with GUI
tart run <vm-name>

# VM window will appear - log in as 'admin' (no password)
# Open Terminal.app in the VM
```

### SSH Connection

Tart VMs come with SSH enabled by default:

```bash
# Get VM IP
VM_IP=$(tart ip <vm-name>)

# Connect (default user: admin, no password required)
ssh admin@$VM_IP

# Or use tart exec (doesn't require IP)
tart exec <vm-name> -- bash -c "voicemode --version"
```

**SSH Tips:**
- Default credentials: user `admin`, no password
- SSH is available immediately after boot
- Use `tart ip <vm-name>` to get the VM's IP address
- Use `tart exec` for one-off commands without SSH

## Base Image Selection

### macOS Tahoe (26.x) - Recommended

Latest macOS version with best compatibility.

```bash
# Pull and clone
tart clone ghcr.io/cirruslabs/macos-tahoe-base:latest test-tahoe
tart run test-tahoe --no-graphics &
```

### macOS Sequoia (15.x)

```bash
tart clone ghcr.io/cirruslabs/macos-sequoia-base:latest test-sequoia
tart run test-sequoia --no-graphics &
```

### macOS Sonoma (14.x)

```bash
tart clone ghcr.io/cirruslabs/macos-sonoma-base:latest test-sonoma
tart run test-sonoma --no-graphics &
```

### Checking Available Images

```bash
# List locally available VMs
tart list

# Search for Cirrus Labs base images
# Visit: https://github.com/orgs/cirruslabs/packages?tab=packages&q=macos
```

## Testing from Branch vs Published Package

### Option 1: Test Published PyPI Package

Test the official release:

```bash
ssh admin@$VM_IP "
  # Install uv
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH=\"\$HOME/.local/bin:\$PATH\"

  # Install latest version from PyPI
  uvx voice-mode-install --yes
"
```

Test specific version:

```bash
ssh admin@$VM_IP "
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH=\"\$HOME/.local/bin:\$PATH\"

  # Install specific version
  uvx voice-mode-install==5.1.6 --yes
"
```

### Option 2: Test from Branch/Worktree

Test unreleased changes or feature branches:

```bash
ssh admin@$VM_IP "
  # Install uv
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH=\"\$HOME/.local/bin:\$PATH\"

  # Clone repository
  git clone https://github.com/mbailey/voicemode.git
  cd voicemode

  # Checkout specific branch
  git checkout feat/VM-265-add-non-interactive-mode-to-voice-mode-install

  # Install from source
  cd installer
  uv tool install --editable .

  # Run installer
  voice-mode-install --yes
"
```

### Option 3: Test Local Development Build

Test local changes before pushing:

```bash
# On host: Build wheel
cd /path/to/voicemode/installer
uv build

# Start simple HTTP server
python3 -m http.server 8000 &

# In VM: Download and install
ssh admin@$VM_IP "
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH=\"\$HOME/.local/bin:\$PATH\"

  # Download wheel from host (Tart host is at 192.168.64.1)
  curl -O http://192.168.64.1:8000/voice_mode_install-*.whl

  # Install wheel
  uv tool install ./voice_mode_install-*.whl

  # Run installer
  voice-mode-install --yes
"

# Clean up HTTP server
kill %1
```

### Option 4: Test Custom Package URL

Test from a specific URL:

```bash
ssh admin@$VM_IP "
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH=\"\$HOME/.local/bin:\$PATH\"

  # Install from URL
  uvx --from <package-url> voice-mode-install --yes
"
```

## Test Scenarios

### Scenario 1: Fresh Install (Non-Interactive)

Most common automated test case.

```bash
ssh admin@$VM_IP "
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH=\"\$HOME/.local/bin:\$PATH\"
  uvx voice-mode-install --yes
"
```

**Expected outcome:**
- Installs all system dependencies (FFmpeg, etc.)
- Installs VoiceMode via `uv tool install`
- Configures shell completion
- Installs and starts Whisper and Kokoro services
- Reports "Installation Complete!"

### Scenario 2: Install Without Services

Test installer without setting up services.

```bash
ssh admin@$VM_IP "
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH=\"\$HOME/.local/bin:\$PATH\"
  uvx voice-mode-install --yes --skip-services
"
```

**Expected outcome:**
- Installs system dependencies
- Installs VoiceMode command
- Skips Whisper and Kokoro service installation
- User can manually install services later

### Scenario 3: Install with Specific Model

Test installer with custom Whisper model.

```bash
ssh admin@$VM_IP "
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH=\"\$HOME/.local/bin:\$PATH\"
  uvx voice-mode-install --yes --model base
"
```

**Expected outcome:**
- Installs with specified Whisper model (base, small, medium, etc.)
- Model is configured in Whisper service

### Scenario 4: Dry Run

Test what would be installed without making changes.

```bash
ssh admin@$VM_IP "
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH=\"\$HOME/.local/bin:\$PATH\"
  uvx voice-mode-install --dry-run
"
```

**Expected outcome:**
- Shows platform detection
- Lists packages that would be installed
- Shows commands that would be run
- No actual changes made
- No sudo password required

### Scenario 5: Interactive Install

Test user-interactive mode (requires GUI or terminal).

```bash
# In GUI mode or with proper terminal
ssh -t admin@$VM_IP "
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH=\"\$HOME/.local/bin:\$PATH\"
  uvx voice-mode-install
"
```

**Expected outcome:**
- Prompts for confirmation before installing packages
- Asks about service installation
- Requests sudo password when needed
- Shows progress for each step

## Verification Steps

### 1. Check Installation

```bash
# Verify VoiceMode is installed
ssh admin@$VM_IP "export PATH=\"\$HOME/.local/bin:\$PATH\" && voicemode --version"

# Check for expected output (should show version number)
# Example: VoiceMode 5.1.6
```

### 2. Check Service Status

```bash
# Check Whisper service
ssh admin@$VM_IP "export PATH=\"\$HOME/.local/bin:\$PATH\" && voicemode whisper service status"

# Check Kokoro service
ssh admin@$VM_IP "export PATH=\"\$HOME/.local/bin:\$PATH\" && voicemode kokoro status"
```

**Expected output:**
- Services should be "running" or show process information
- If `--skip-services` was used, services won't be installed

### 3. Verify FFmpeg

```bash
# Check FFmpeg is available
ssh admin@$VM_IP "ffmpeg -version"

# Should show FFmpeg version and configuration
```

### 4. Check Dependencies

```bash
# Run VoiceMode dependency check
ssh admin@$VM_IP "export PATH=\"\$HOME/.local/bin:\$PATH\" && voicemode deps"
```

**Expected output:**
- All required dependencies marked as available
- No critical errors

### 5. Test Voice Conversation (Full Integration)

```bash
# Start MCP server and test voice
ssh admin@$VM_IP "export PATH=\"\$HOME/.local/bin:\$PATH\" && voicemode server stdio" <<EOF
{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
EOF
```

**Expected output:**
- Server starts without import errors
- Returns tool list including `converse` and `service`

### 6. Check Logs

```bash
# View installation log
ssh admin@$VM_IP "cat ~/.voicemode/install.log"

# Check for errors in service logs
ssh admin@$VM_IP "export PATH=\"\$HOME/.local/bin:\$PATH\" && voicemode whisper service logs" | tail -20
```

## Troubleshooting

### VM Won't Start

```bash
# Check VM exists
tart list

# Check if already running
tart list | grep running

# Try stopping and restarting
tart stop <vm-name>
tart run <vm-name> --no-graphics &
```

### Can't Get VM IP

```bash
# Wait for VM to fully boot
sleep 15

# Check VM is running
tart list | grep <vm-name>

# Get IP
tart ip <vm-name>

# If still no IP, try tart exec instead of SSH
tart exec <vm-name> -- bash -c "hostname -I"
```

### SSH Connection Refused

```bash
# VM may still be booting - wait longer
sleep 30
tart ip <vm-name>

# Check SSH is running in VM
tart exec <vm-name> -- bash -c "sudo systemsetup -getremotelogin"

# Use tart exec as alternative
tart exec <vm-name> -- bash
```

### uv Installation Fails

```bash
# Check internet connectivity
ssh admin@$VM_IP "curl -I https://astral.sh"

# Try manual installation
ssh admin@$VM_IP "curl -LsSf https://astral.sh/uv/install.sh -o /tmp/uv-install.sh"
ssh admin@$VM_IP "bash /tmp/uv-install.sh"
```

### voice-mode-install Not Found After Installation

```bash
# Check if uv installed correctly
ssh admin@$VM_IP "ls -la ~/.local/bin/"

# Verify PATH includes ~/.local/bin
ssh admin@$VM_IP "echo \$PATH"

# Explicitly add to PATH
ssh admin@$VM_IP "export PATH=\"\$HOME/.local/bin:\$PATH\" && voice-mode-install --version"
```

### Services Won't Start

```bash
# Check FFmpeg is available
ssh admin@$VM_IP "ffmpeg -version"

# View service logs
ssh admin@$VM_IP "export PATH=\"\$HOME/.local/bin:\$PATH\" && voicemode whisper service logs"

# Try manual start
ssh admin@$VM_IP "export PATH=\"\$HOME/.local/bin:\$PATH\" && voicemode whisper service start"
```

### Disk Space Issues

```bash
# Check available space
ssh admin@$VM_IP "df -h"

# Clean up if needed
ssh admin@$VM_IP "rm -rf ~/Library/Caches/*"
ssh admin@$VM_IP "brew cleanup" # If testing multiple times
```

## Automated Testing Script

For automated testing, use the comprehensive test script at [`scripts/test-installer.sh`](../../../../scripts/test-installer.sh):

```bash
# Run all test scenarios on a fresh VM
./scripts/test-installer.sh

# Test specific scenarios
./scripts/test-installer.sh --scenarios "install,dry-run"

# Test from a branch instead of PyPI
./scripts/test-installer.sh --branch feat/my-feature

# Keep VM running after tests for debugging
./scripts/test-installer.sh --keep-vm --verbose

# See all options
./scripts/test-installer.sh --help
```

**Available Options:**
- `--branch BRANCH` - Test from git branch instead of PyPI
- `--keep-vm` - Keep VM running after tests for debugging
- `--verbose` - Show detailed output from all commands
- `--scenarios LIST` - Comma-separated scenarios (install, skip-services, model, dry-run)
- `--base-image IMAGE` - Tart base image (default: ghcr.io/cirruslabs/macos-tahoe-base:latest)
- `--log-file FILE` - Write detailed output to log file

**Requirements:** `sshpass` must be installed (`brew install hudochenkov/sshpass/sshpass`)

## References

- [Tart Documentation](https://github.com/cirruslabs/tart)
- [VoiceMode Installer README](../../installer/README.md)
- [VoiceMode Testing Script](../../../../scripts/test-installer.sh)
- [Related Task: VM-262](https://github.com/mbailey/taskmaster-tasks/tree/master/projects/voicemode/VM-262_task_test-voicemode-plugin-on-fresh-macos-vm-using-tart)
- [Related Task: VM-265](https://github.com/mbailey/taskmaster-tasks/tree/master/projects/voicemode/VM-265_feat_add-non-interactive-mode-to-voice-mode-install-for-claude-code-automation)
