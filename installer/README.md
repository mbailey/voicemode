# voicemode-install

A standalone installer package for VoiceMode that handles system dependency detection and installation.

## Overview

`voicemode-install` simplifies the VoiceMode installation process by:

1. **Detecting your platform** - Identifies your OS, distribution, and architecture
2. **Checking dependencies** - Scans for required system packages
3. **Installing packages** - Uses your system's package manager (apt, dnf, brew)
4. **Installing VoiceMode** - Runs `uv tool install voice-mode`
5. **Hardware recommendations** - Suggests optimal configuration for your system
6. **Logging everything** - Saves installation logs for troubleshooting

## Quick Start

```bash
# Install and run
uvx voicemode-install

# Dry run (see what would be installed)
uvx voicemode-install --dry-run

# Install specific version
uvx voicemode-install --voice-mode-version=5.1.3

# Skip service installation
uvx voicemode-install --skip-services

# Non-interactive mode
uvx voicemode-install --non-interactive
```

## Prerequisites

- **uv** - Required to run the installer (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **Python 3.10+** - Usually pre-installed on modern systems
- **sudo access** - Needed to install system packages (Linux)

## Supported Platforms

- **macOS** - Intel and Apple Silicon (via Homebrew)
- **Ubuntu/Debian** - Using apt package manager
- **Fedora/RHEL** - Using dnf package manager

## Features

### Phase 1 (Included)

✅ **Dry-run Mode** - Preview what will be installed
✅ **Installation Logging** - Detailed logs saved to `~/.voicemode/install.log`
✅ **Shell Completion** - Auto-configures tab completion for bash/zsh
✅ **Health Check** - Verifies installation after completion
✅ **Version Pinning** - Install specific VoiceMode versions
✅ **Hardware Detection** - Recommends optimal setup for your system

### Phase 2 (Future)

⏱️ Config Validation - Check for conflicting settings
⏱️ Uninstall Support - Clean removal of VoiceMode

## How It Works

1. **Platform Detection** - Identifies OS, distribution, and architecture
2. **Dependency Checking** - Compares installed packages against `dependencies.yaml`
3. **Package Installation** - Uses platform-specific package managers:
   - macOS: `brew install`
   - Ubuntu/Debian: `sudo apt install`
   - Fedora: `sudo dnf install`
4. **VoiceMode Installation** - Runs `uv tool install voice-mode[==version]`
5. **Post-Install** - Configures shell completion and verifies installation

## Installation Logs

Logs are saved to `~/.voicemode/install.log` in JSONL format:

```json
{"timestamp": "2025-10-12T10:30:00", "type": "start", "message": "Installation started"}
{"timestamp": "2025-10-12T10:30:15", "type": "check", "message": "Checked core dependencies"}
{"timestamp": "2025-10-12T10:30:45", "type": "install", "message": "Successfully installed system packages"}
{"timestamp": "2025-10-12T10:31:30", "type": "complete", "message": "Installation completed"}
```

## Troubleshooting

### VoiceMode command not found after installation

Restart your shell or run:
```bash
source ~/.bashrc  # or ~/.zshrc for zsh
```

### Permission denied during package installation

The installer needs sudo access to install system packages. Run:
```bash
sudo -v  # Refresh sudo credentials
uvx voicemode-install
```

### Network errors during installation

- Check your internet connection
- Try again with: `uvx voicemode-install`
- Use `uvx --refresh voicemode-install` to get the latest installer

### Installation hangs or fails

1. Check the log file: `~/.voicemode/install.log`
2. Try a dry run: `uvx voicemode-install --dry-run`
3. Report issues with log file attached

## Development

### Building from Source

```bash
cd installer/
uv build
```

### Testing Locally

```bash
cd installer/
uv pip install -e .
voicemode-install --dry-run
```

### Project Structure

```
installer/
├── pyproject.toml          # Package definition
├── voicemode_install/
│   ├── __init__.py        # Version and exports
│   ├── cli.py             # Main CLI entry point
│   ├── system.py          # Platform detection
│   ├── checker.py         # Dependency checking
│   ├── installer.py       # Package installation
│   ├── hardware.py        # Hardware detection
│   ├── logger.py          # Installation logging
│   └── dependencies.yaml  # System dependencies
└── README.md
```

## Design Decisions

See `DECISIONS.md` in the task directory for detailed rationale behind:
- Version management strategy
- Dependency synchronization approach
- Error handling philosophy
- Platform coverage priorities
- Service installation scope

## Contributing

This installer is part of the [VoiceMode](https://github.com/mbailey/voicemode) project.

## License

MIT License - Same as VoiceMode
