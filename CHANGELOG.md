# Changelog

All notable changes to VoiceMode (formerly voice-mcp) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [7.2.0] - 2026-01-06

### Fixed

- **STT Timeout Increased to 60s** (VM-325)
  - Whisper sometimes takes longer than 30s for complex or longer audio
  - Increased default STT timeout from 30s to 60s to prevent transcription failures
  - A future release will make this configurable via `voicemode.env`

- **Test Isolation for LaunchAgents** (VM-310)
  - Tests no longer write plist files to real `~/Library/LaunchAgents` directory
  - Prevents test pollution of user's system configuration

### Changed

- **CLI Simplification** (VM-305, VM-306)
  - Removed deprecated `voicemode claude` command group (use Claude Code hooks instead)
  - Removed deprecated `voicemode audio` command group
  - Moved `transcribe` command to top-level: `voicemode transcribe` (was `voicemode audio transcribe`)

- **Plugin Structure**
  - Moved skill file to `skills/voicemode/SKILL.md` for better organization
  - Updated plugin packaging and configuration

### Added

- **Conversation History Search** (VM-279)
  - New SQLite FTS5-based search for conversation history
  - Enables fast full-text search across past voice conversations

- **Installer Testing Improvements** (VM-279)
  - Added `--gui` flag to test-installer.sh for GUI mode testing
  - Added `--test-mode` flag for automated testing scenarios

### Documentation

- **Plugin Skill Improvements** (VM-266)
  - Enhanced VoiceMode plugin skill with installation guidance
  - Better onboarding experience for new users

## [7.1.2] - 2025-12-27

### Added

- **Claude Code Skill Loading in Voice Conversations** (VM-286)
  - Added voice_skills_instructions to converse tool to ensure skills are checked during voice interactions
  - Voice requests arrive as tool results rather than user messages, causing skill triggers to be missed
  - New BLOCKING REQUIREMENT instructs Claude to check for relevant skills before acting on voice requests
  - Example: Saying "search for tasks" now properly triggers the taskmaster skill

## [7.1.1] - 2025-12-25

### Fixed

- **Whisper Thread Configuration**
  - Fixed Whisper decode failures on VMs with fewer than 8 CPU cores
  - Replace hardcoded 8 threads with dynamic CPU detection (sysctl on macOS, nproc on Linux)
  - Added `VOICEMODE_WHISPER_THREADS` environment variable for manual override
  - Added missing `--convert` flag to whisper-server startup for automatic audio format conversion

### Changed

- **Plugin Architecture** (VM-227)
  - Simplified plugin slash commands structure
  - Improved hooks.json format

### Documentation

- **Installer Testing Guide** (VM-276)
  - Added comprehensive guide for testing VoiceMode installer on Tart VMs
  - Fixed installer test script for local VM testing

## [7.1.0] - 2025-12-25

### Added

- **VoiceMode Plugin for Claude Code** (VM-227)
  - Install via: `/plugin marketplace add mbailey/voicemode` then `/plugin install voicemode`
  - Includes MCP server integration, slash commands, skill, and hooks
  - Commands: `/voicemode:install`, `/voicemode:converse`, `/voicemode:status`, `/voicemode:start`, `/voicemode:stop`
  - Self-contained hook receiver for soundfont support out of the box
  - No manual configuration needed - hooks work automatically

- **Non-Interactive Installer Mode** (VM-265)
  - Added `--yes` / `-y` flag for unattended installation
  - Added `--no-local-services` flag to skip Whisper/Kokoro installation
  - Added `--model` flag to specify Whisper model
  - Auto-detects non-interactive environment and warns if --yes not specified
  - Auto-installs Homebrew in non-interactive mode if needed
  - Enables Claude Code automation and CI/CD pipeline installation

- **Fast Hook Receiver with Enhanced Soundfont Support** (VM-258)
  - New voicemode-hook-receiver script for improved performance
  - Enhanced soundfont structure support
  - Optimized hook handling for faster responses

- **Audio Compression Improvements** (VM-240, VM-245)
  - Compress STT audio uploads to reduce bandwidth usage
  - Skip audio compression for local STT endpoints (no need for compression on localhost)
  - Configurable STT save format via `VOICEMODE_STT_SAVE_FORMAT` environment variable
  - Save full-quality WAV files while using compressed upload for remote endpoints

- **Detailed Timing Metrics** (VM-244)
  - Added detailed timing metrics for STT/TTS transcode operations
  - Configurable metrics output levels (minimal, summary, verbose)
  - Better visibility into performance characteristics

### Fixed

- **Multiline Environment Variable Corruption** (VM-268)
  - Fixed `voicemode whisper model` command corrupting multiline values in voicemode.env
  - Preserves VOICEMODE_PRONOUNCE and other multiline quoted variables correctly
  - Prevents whisper server from falling back to wrong model after config update

- **Benchmark Script** (VM-258)
  - Use stdin for `claude -p` in benchmark script
  - Improved benchmark reliability

- **Audio Quality Preservation** (VM-240)
  - Ensure full-quality WAV files are saved even when using compressed upload
  - Prevents quality loss in local audio archives

- **Homebrew Tools PATH**
  - Extended PATH in MCP server startup to include Homebrew bin directories
  - Fixes FFmpeg not found when running as MCP server

### Removed

- **Benchmark Script** - Removed claude-hooks/benchmark-hooks.sh (development testing only)

### Changed

- **Documentation** (VM-232)
  - Improved configuration guide clarity
  - Added Claude Code permissions section to configuration guide
  - Removed duplicate command reference (clarified /permissions is alias for /allowed-tools)

- **Code Quality**
  - Normalized indentation in hook receiver
  - Fixed log file path in hook receiver
  - Updated skill for batching announcements and Bash commands

- **CI/CD**
  - Added ffmpeg to test dependencies for better test coverage

## [7.0.1] - 2025-12-03

## [7.0.0] - 2025-11-27

### ⚠️ BREAKING CHANGE

- **Pronunciation System Replaced** (VM-183)
  - Old YAML-based pronunciation files are no longer loaded
  - Rules now defined via environment variables (VOICEMODE_PRONOUNCE)
  - New compact one-line format: `DIRECTION pattern replacement # description`
  - Default rules included for JSON, YAML, and API
  - **Migration**: Convert YAML rules to env var format in voicemode.env (or other files)

### Fixed

- **Kokoro Service PATH for uv Curl Installer** (VM-221)
  - Added `~/.local/bin` to Kokoro launchd plist PATH
  - Fixes Kokoro service startup when uv is installed via curl instead of Homebrew

- **TTS Speed Configuration**
  - Standardized TTS speed config to match codebase patterns
  - Added helpful error message when TTS speed from env var is invalid

### Refactored

- **Removed Unused Opuslib Code** (VM-185)
  - Removed opuslib code that logged confusing warnings on every run
  - Cleaner startup experience

## [6.2.0] - 2025-11-25

### Added

- **Python 3.14 Support** (VM-217)
  - VoiceMode now supports Python 3.14
  - LiveKit dependencies made optional to avoid compatibility issues
  - LiveKit functionality requires manual installation of livekit package

### ChangedS

- **Documentation Updates**
  - Getting started guide now uses `uvx voice-mode-install` for installation
  - Simplified installation instructions with uvx approach

### Fixed

- **ReadTheDocs Build System**
  - Restored `docs/gen_pages.py` to fix ReadTheDocs builds
  - Documentation builds now working correctly

- **Dependency Management**
  - Added aiohttp as core dependency for async HTTP operations
  - Prevents missing dependency errors during normal operation

- **LiveKit Optional Support**
  - `--help` flag now works on LiveKit commands without LiveKit installed
  - LiveKit tests automatically skipped when package not installed
  - Uses `pytest.importorskip` for proper test dependency handling

- **Test Reliability**
  - Skipped flaky TTS test to improve CI reliability

- **Linux systemd Service Template** (VM-212, fixes #113)
  - Refactored Linux installation to use template-based approach matching macOS
  - Updated systemd template from v1.0.0 to v1.1.0
  - Template now uses `{START_SCRIPT_PATH}` placeholder instead of direct binary invocation
  - Eliminates template drift by making template the source of truth
  - Linux installer now loads and processes template like macOS does
  - Consistent cross-platform service management architecture
  - Resolves issue where template file was outdated and unused

## [6.1.1] - 2025-11-11

### Fixed
- **TTS Fallback for System Messages** - Fixed play_system_audio TTS fallback behavior
  - Changed incorrect `initial_provider=None` parameter to `model="tts-1"`
  - Ensures TTS model is properly specified when falling back from audio files
  - Fixes issue where system messages could fail if audio files were missing
  - Affects wait/repeat commands and other system audio playback

### Added
- **Comprehensive Wait/Repeat Test Suite**
  - Added 291 lines of test coverage for wait and repeat functionality
  - Tests for play_system_audio with audio files and TTS fallback
  - Command detection tests for wait and repeat phrases
  - Integration tests for complete wait/repeat flows
  - Edge case coverage for error conditions

## [6.1.0] - 2025-11-10

### 🎉 Major Features

#### **Voice Control Commands - "Repeat" and "Wait"** (VM-199)
VoiceMode now understands natural voice commands during conversations:
- **"Repeat" Command**: Say phrases like "could you repeat that?" or "say that again" to replay the last message
- **"Wait" Command**: Say "wait a minute" or "hold on" to pause the conversation for 60 seconds
- **Instant Feedback**: Pre-recorded audio responses provide immediate confirmation (no TTS delay)
- **Natural Phrases**: Recognizes multiple variations: "repeat please", "one more time", "wait a sec", "give me a moment"
- **Smart Detection**: Strips punctuation and normalizes text for reliable phrase matching
- **Privacy-First**: System messages use local audio files - no cloud processing for these commands

### Added
- **Pre-Recorded System Audio Messages**
  - Bundled audio files for instant system feedback (no TTS latency)
  - "Repeating" - confirms replay request
  - "Waiting one minute" - acknowledges pause request
  - "Ready to listen" - signals end of wait period
  - Fallback to TTS if audio files unavailable
  - Audio stored in `voice_mode/data/soundfonts/default/system-messages/`

- **Claude Code Skill for VoiceMode** (VM-210)
  - New SKILL.md with comprehensive voice interaction instructions
  - Triggers on "voice mode" or "voicemode" mentions
  - Includes parallel operation guidelines for natural conversations
  - Documents all CLI commands and MCP tool usage

### Fixed
- **Concurrent Audio Playback** (VM-208)
  - Replaced blocking audio calls with queue-based NonBlockingAudioPlayer
  - Multiple VoiceMode instances can now play audio simultaneously
  - System audio mixer properly handles concurrent streams
  - Fixed chime audio normalization (int16 to float32 conversion)
  - Works seamlessly with Core Audio (macOS) and PulseAudio (Linux)

- **CI/CD Improvements**
  - Test installer workflow now restricted to master branch and version tags
  - Prevents confusing "failure" status on feature branches

### Changed
- **Unified Audio System**
  - All audio playback now uses NonBlockingAudioPlayer
  - Consistent audio handling for chimes, system messages, and replays
  - Better integration with system audio mixers

- **Communication Guidelines** (VM-210)
  - Parallel operations now default behavior (speak while acting)
  - Ask questions one at a time for clarity in voice interactions
  - Updated skill trigger phrases to include "voice mode"

### Refactored
- **Converse Tool Architecture** (VM-202)
  - Eliminated 120 lines of duplicate code between speak-only and conversation modes
  - Single unified flow with conditional STT execution
  - Maintains identical functionality with simpler codebase
  - Easier to maintain and extend with new features

### Developer
- Added `scripts/compare-voice-modes.sh` for testing voice services against cloud

## [6.0.5] - 2025-10-27

### Added
- **Makefile Target** - New `make run-installer` for quick logo preview
  - Runs installer from source with --dry-run
  - Shows logo and output without installing anything

### Fixed
- **Installer Logo Alignment** - Fixed box drawing character alignment
  - Removed emoji that caused terminal width inconsistencies
  - Adjusted spacing for perfect box alignment
  - Logo now renders correctly on all terminals

## [6.0.4] - 2025-10-27

### Added
- **Automated Installer Publishing** - voice-mode-install now publishes automatically on release
  - GitHub Actions workflow builds and publishes installer alongside main package
  - Both packages publish to PyPI when version tags are pushed
  - Supports both production and TestPyPI publishing

### Fixed
- **Installer Color** - Now uses proper Claude Code orange (ANSI color 208)
  - Changed to ANSI escape code `\033[38;5;208m` for proper orange color
  - Previous `bright_yellow` was not the correct Claude Code orange
  - Works on all 256-color terminals including xterm-256color
- **Installer Version Check** - Fixed "unable to check" latest version error
  - Changed from non-existent `uv pip index versions` command to PyPI JSON API
  - Version checking now works reliably with curl

## [6.0.3] - 2025-10-27

### Fixed
- **CLI Defaults** - Fixed CLI not respecting environment variable configuration (#75)
  - `voicemode converse` now uses DEFAULT_LISTEN_DURATION (120s) instead of hardcoded 30s
  - `voicemode converse` now uses MIN_RECORDING_DURATION from config for min-duration
  - CLI defaults now properly align with environment variable values
- **CLI Logging** - Restored INFO logging for converse command
  - `voicemode converse` now shows detailed progress output
  - Fixed regression caused by logger name standardization

## [6.0.2] - 2025-10-27

### Added
- **GitHub Star Notifications** - Receive notifications when someone stars the repository
  - Integration with ntfy.sh for push notifications
  - Automatic notification on new stargazers

### Changed
- **Logger Names** - Standardized logger names to use "voicemode" without hyphen
  - Consistent logging namespace across all modules
  - Improved log filtering and debugging experience

### Fixed
- **Converse Tool** - Simplified prompt and improved conversation continuation handling
  - Reduced prompt complexity for better LLM understanding
  - Better handling of conversation flow and context

## [6.0.1] - 2025-10-20

### Fixed

- **Installer: Architecture suffix handling** - Fixed dpkg package detection on ARM64 and other multi-arch systems
  - Package names with architecture suffixes (e.g., `python3-dev:arm64`) are now correctly detected as installed
  - Fixes false negatives where installed packages were reported as missing on ARM64 Ubuntu
  - Tested on Ubuntu ARM64 with `libasound2-dev:arm64` and `libportaudio2:arm64`

## [6.0.0] - 2025-10-16

### ⚠️ BREAKING CHANGES

- **Selective Tool Loading by Default** - Dramatically reduced token usage by loading only essential tools
  - Only `converse` and `service` tools loaded by default (2.6k tokens vs previous 26k tokens)
  - **90% reduction in MCP tool token usage** from ~26,000 to ~2,600 tokens
  - New configuration options for controlling tool loading:
    - `VOICEMODE_TOOLS_ENABLED` - Whitelist specific tools (e.g., "converse,service")
    - `VOICEMODE_TOOLS_DISABLED` - Blacklist specific tools (loads all except those listed)
  - Default: `VOICEMODE_TOOLS_ENABLED=converse,service` for minimal token footprint
  - Users who need additional tools can enable them via configuration

- **Converse Tool Parameter Renames** - Clarified listen duration parameter names
  - `listen_duration` → `listen_duration_max` (maximum recording duration)
  - `min_listen_duration` → `listen_duration_min` (minimum recording duration before silence detection)
  - Paired max/min suffixes make parameter relationship clearer

- **Audio Feedback Configuration Variable Renames** - Renamed for clarity
  - `VOICEMODE_PIP_LEADING_SILENCE` → `VOICEMODE_CHIME_LEADING_SILENCE`
  - `VOICEMODE_PIP_TRAILING_SILENCE` → `VOICEMODE_CHIME_TRAILING_SILENCE`
  - Users with custom configurations must update their environment variables

### Added

- **Comprehensive Configuration Template** - Expanded default voicemode.env template with 37 additional variables
  - Recording & VAD configuration (listen duration, silence detection, VAD aggressiveness)
  - Audio format configuration (global and per-operation format settings, bitrate controls)
  - Streaming configuration (chunk size, buffering, playback controls)
  - Event logging configuration (enable/disable, directory, rotation)
  - Pronunciation system configuration (enable, logging, privacy mode)
  - Think Out Loud mode (experimental multi-voice thinking feature)
  - Service management (auto-enable, LiveKit, frontend settings)
  - Advanced configuration (models directory, progress style, VAD debug)
  - All defaults verified to match actual code behavior

- **Tool Loading Configuration System**
  - Fine-grained control over which MCP tools are loaded
  - Whitelist mode (`VOICEMODE_TOOLS_ENABLED`) for explicit tool selection
  - Blacklist mode (`VOICEMODE_TOOLS_DISABLED`) for excluding specific tools
  - Configuration examples in default voicemode.env template
  - Documentation in tool loading architecture reference

### Changed

- Default configuration template now includes tool loading examples
- MCP tool loading optimized for Amazon Q and other token-constrained environments
- Updated documentation to reflect new default minimal tool set

### Fixed

- Converse tool description reduced to under 10,024 characters for Amazon Q compatibility (#84)
- Test suite updated to match Makefile output changes

## [5.1.9] - 2025-10-14

### Fixed
- **Whisper model size display** - Fixed incorrect size calculation in `voicemode whisper model --all`
  - Totals were showing millions of GB instead of reasonable values
  - Changed calculation to use MB values directly from registry
  - Fixes issue #81

## [5.1.8] - 2025-10-13

## [5.1.7] - 2025-10-13

## [5.1.6] - 2025-10-13

## [5.1.7] - 2025-10-13

## [5.1.6] - 2025-10-12

### Added
- **Release Management Script** - Automated script for version bumping and release preparation
- **Homebrew Auto-Installation** - Automatic detection and installation of Homebrew on macOS

### Fixed
- **dpkg False Positives** - Fixed false positive detections in dpkg checks
- **Tart VM Targets** - Added support for Tart VM testing targets

### Changed
- **Makefile Cleanup** - Reorganized and cleaned up Makefile structure

### Documentation
- **Code Reading Guide** - Added comprehensive guide for understanding voicemode converse command

## [5.1.5] - 2025-10-12

## [5.1.4] - 2025-10-12

### Added
- **voice-mode-install Package** - Standalone installer package for simplified VoiceMode setup
  - New PyPI package `voice-mode-install` provides `voice-mode-install` command
  - Handles system dependency detection and installation before main package
  - Cross-platform support for macOS, Ubuntu/Debian, and Fedora
  - Interactive prompts with smart defaults for dependency installation
  - Detects OS, distribution, and architecture automatically
  - Shows concise summary of missing system packages
  - Installs system dependencies using native package managers (brew/apt/dnf)
  - Automatically installs VoiceMode after dependencies are ready
  - Makefile targets for building, testing, and publishing installer package
  - Improved command existence checking using shutil.which

### Fixed
- **Installer Package Naming Consistency**
  - Fixed wheel filename pattern in Makefile from `voicemode_install` to `voice_mode_install`
  - Corrected package name from `voicemode-install` to `voice-mode-install` in all documentation
  - Updated README.md, CLI examples, and test scripts to use correct hyphenated name
  - PyPI package naming now consistent: `voice-mode-install` (package) → `voice_mode_install` (wheel) → `voicemode_install` (module)
  - Synchronized installer version (5.1.4) with voicemode for simpler version management

## [5.1.3] - 2025-10-12

### Fixed
- **Kokoro First-Time Installation Timeout**
  - Fixed systemd timeout error during first kokoro installation
  - Now starts kokoro manually before systemd to download models and dependencies
  - Waits for health check (max 3 minutes) before creating systemd service
  - Eliminates "timeout exceeded" errors on first install
  - Systemd service starts quickly on subsequent boots since everything is cached

## [5.1.2] - 2025-10-12

### Fixed
- **Kokoro Rust Dependency Detection**
  - Fixed `voicemode kokoro install` failing with "can't find Rust compiler" on Fedora
  - Marked Rust (cargo and rustc) as required dependencies for kokoro on Fedora
  - Previously marked as optional (ARM64 only), but sudachipy requires Rust on all architectures
  - Dependency chain: kokoro-fastapi → misaki[ja] → pyopenjtalk-plus → sudachipy
  - `voicemode deps --component kokoro` now correctly checks for Rust compiler

### Changed
- **Service Auto-Enable Default**
  - Changed `SERVICE_AUTO_ENABLE` default from `False` to `True`
  - Services now automatically enable and start after installation by default
  - Users can override with `VOICEMODE_SERVICE_AUTO_ENABLE=false` if desired
  - Improves out-of-box experience - services "just work" after installation

## [5.1.1] - 2025-10-12

### Added
- **Progress Indicator for Dependency Installation**
  - Animated braille spinner shows installation activity by default
  - New `--verbose/-v` flag for `voicemode deps` to show full package manager output
  - Friendly progress messages with emoji (📦, ✅, ❌)
  - Spinner runs in daemon thread for clean shutdown
  - Addresses user feedback about installation appearing to hang with no progress indication

### Fixed
- **Kokoro Service PATH Configuration**
  - Fixed hardcoded `/home/m/.local/bin` in systemd service file
  - Now uses dynamic user home directory expansion with `os.path.expanduser()`
  - Fixes "ModuleNotFoundError: No module named 'loguru'" and "Failed to spawn: uvicorn" errors
  - Affects any Linux user with username other than 'm'
  - Bug present since v2.16.0 (July 2025)

## [5.1.0] - 2025-10-12

### Added
- **Lazy-Loading System Dependency Management** - Complete dependency checking and installation system
  - Automatic detection and installation of system dependencies on-demand
  - Lazy dependency checking that happens when needed (core deps on converse, build deps on service install)
  - Single source of truth in `voice_mode/dependencies.yaml` for all platform dependencies
  - CLI command `voicemode deps` to check and install dependencies interactively
  - Non-interactive mode with `--yes` flag for automation
  - Component-specific checking with `--component` flag (whisper, kokoro, core)
  - Cross-platform support for Fedora, Ubuntu/Debian, and macOS
  - In-memory caching of dependency status for performance
  - WSL2-specific dependency handling (pulseaudio requirements)

### Fixed
- **ALSA Development Libraries Now Required for Core Installation**
  - Fixed installation failures on Linux due to missing ALSA headers
  - `simpleaudio` Python package requires ALSA development libraries to compile
  - Updated dependencies.yaml to mark as required:
    - Fedora: `alsa-lib-devel`
    - Ubuntu/Debian: `libasound2-dev`
  - Previously marked as optional, causing `uv tool install` failures
  - Affects all Linux platforms (native and WSL)
  - Tested on Fedora 42 ARM64

## [5.0.3] - 2025-10-05

### Fixed
- **Whisper Model Default** - Consolidated default Whisper model to single constant
  - Fixed inconsistency where CLI defaulted to `large-v2` while tool used `base`
  - All code now references `DEFAULT_WHISPER_MODEL = "base"` from config.py
  - DRY principle applied across CLI and tool implementations

## [5.0.2] - 2025-10-05

### Fixed
- **CLI Error Messages** - Display meaningful OpenAI error messages in CLI commands
  - Improved error reporting throughout CLI interface
  - Better user feedback when OpenAI API calls fail

## [5.0.1] - 2025-10-04

### Fixed
- **Version Command** - Fixed NameError caused by undefined `current_version` variable

## [5.0.0] - 2025-10-04

### Added
- **Pre-built Core ML Model Support** - Major improvement for Apple Silicon users
  - Downloads pre-built Core ML models from Hugging Face instead of building locally
  - Eliminates need for full Xcode installation (saves ~15GB disk space)
  - Significantly faster whisper model installation (minutes vs hours)
  - Automatic Core ML support detection and installation
  - Progress indicators for all model downloads

- **OpenAI Error Handling** - Clear, actionable error messages
  - Dedicated error parser for OpenAI API failures
  - User-friendly messages for quota exceeded, invalid API key, and rate limits
  - Helpful suggestions and fallback options displayed
  - Improved error reporting throughout TTS/STT pipeline

- **Whisper CLI Improvements**
  - Unified `whisper model` command as getter/setter for active model
  - Auto-restart whisper service when changing models
  - Better command organization with service groups
  - Enhanced progress bars and help text formatting
  - Default model download during whisper installation

### Changed
- **Version Display** - Now shows "VoiceMode" name and git status
- **CLI Structure** - Reorganized whisper commands for better UX
- **Installation** - Automatic Core ML support without manual configuration

### Fixed
- **WSL Detection** - Improved detection to handle WSLInterop-late
- **Error Messages** - Integration of OpenAIErrorParser for clear user feedback
- **CLI Help** - Removed redundant subcommands list from whisper service help
- **Progress Bars** - Improved formatting and reliability

### Removed
- **install_torch Parameter** - No longer needed with automatic Core ML support
- **Legacy Health Check Code** - Cleaned up leftover code from provider system refactoring

### Internal
- **Project Structure** - Cleaned up project root and reorganized files
- **Documentation** - Updated Core ML documentation with new download strategy

## [4.8.0] - 2025-10-03

### Added
- **CI Mode for Installer** - GitHub Actions integration for automated testing
  - New `--ci` flag for non-interactive installer operation
  - Automatic dependency installation and configuration
  - Status display showing installed dependencies with pass/fail indicators
  - Comprehensive system information collection for debugging

- **Enhanced Installer UX**
  - Detailed TTS error reporting with provider-specific failure information
  - Better error handling and user feedback throughout installation
  - Improved shell-specific source command display
  - Flexible working directory selection
  - Status checking for all dependencies before installation

### Fixed
- **Platform Compatibility**
  - Added Debian/Ubuntu support to installer alongside Fedora
  - Simplified Python version checking (UV manages Python installation)
  - Corrected echo escape sequence handling across different shells
  - Made pip optional since UV handles package management

### Documentation
- **Core ML Improvements**
  - Enhanced Core ML specification with pre-built model download strategy
  - Simplified voice selection guide by removing redundant examples
  - Clarified ~/claude directory usage (sandbox for testing, not projects)

## [4.7.1] - 2025-09-23

### Fixed
- **CLI Commands**
  - Fix broken whisper model install command import path after services refactoring

### Changed
- **Testing**
  - Move comprehensive help test from manual to automated testing for CI coverage

## [4.7.0] - 2025-09-22

### Fixed
- **Voice Interaction**
  - Distinguish STT connection errors from genuine "no speech detected" scenarios (#62)
  - Display detailed error messages showing attempted endpoints and specific failures
  - Fix misleading "[no speech detected]" messages when services are unavailable
  - Simplify STT function architecture from 3 layers to 2
  - Clean up "Unclosed client session" asyncio warning on startup

### Added
- **Testing**
  - Add comprehensive test coverage for STT error scenarios
  - Test connection failures, authentication errors, and fallback behavior

### Documentation
- Add troubleshooting guide index with diagnostic flowchart

## [4.6.0] - 2025-09-21

### Added
- **Streamlined Installation Experience**
  - Add OpenAI API key setup with browser integration for quick start
  - Add microphone detection before voice test
  - Improve confirmation prompts with smart defaults ([Y/n] for essential, [y/N] for optional)
  - Position OpenAI as recommended quick-start path (~3 minute setup)
  - Consolidate system dependency prompts into single confirmation

- **Documentation**
  - Add comprehensive tool loading architecture documentation
  - Improve README clarity and simplify getting started
  - Add reference documentation for internal systems

### Changed
- **Installation Flow**
  - Remove local services prompt from initial setup (moved to post-install docs)
  - Focus installation on getting users to Claude Code quickly
  - Update Claude Code configuration to use `uvx --refresh` for latest version
  - Use long flags in install script for better clarity

- **Code Organization**
  - Refactor services directory structure - flatten tools directory hierarchy
  - Move service tools up one level (services/whisper/install.py → whisper_install.py)
  - Simplify tool loading logic for uniform subdirectory handling
  - Move version utilities from tools to utils module

### Fixed
- **macOS Compatibility**
  - Fix bash completion "nosort: invalid option name" error on bash 3.2
  - Remove timeout command usage (not available on macOS by default)
  - Correct microphone device counting (filter input devices only)
  - Ensure voice test works with API keys from config files
  - Simplify voice test command for better compatibility

- **Tool Loading**
  - Handle sound_fonts subdirectory with underscore in name correctly
  - Fix installer tests after services directory restructuring

## [4.5.0] - 2025-09-18

### Added
- **Enhanced STT Logging**
  - Add comprehensive logging for speech-to-text operations
  - Log provider selection and fallback attempts
  - Include transcription details and provider info in logs

- **Configuration Management**
  - Add `voicemode config edit` command for easy configuration file editing
  - Support custom editor selection via --editor flag
  - Automatically open configuration file in default editor

- **Tool Environment Variables**
  - Replace VOICEMODE_TOOLS with VOICEMODE_TOOLS_ENABLED and VOICEMODE_TOOLS_DISABLED
  - Allow fine-grained control over tool availability
  - Support comma-separated lists for enabling/disabling specific tools

### Changed
- **Provider Selection Architecture**
  - Consolidate dual provider selection systems into single simple failover approach
  - Remove SIMPLE_FAILOVER configuration - simple failover is now the only mode
  - Simplify get_tts_config and get_stt_config to use direct configuration
  - Eliminate ~400 lines of unused provider registry selection logic
  - Provider registry now only stores endpoint info without complex selection

### Fixed
- Disable OpenAI client retries for local endpoints to avoid delays
- Fix logger name consistency (voicemode vs voice-mode) for STT logging
- Prevent test_installers from killing running voice services during tests
- Update tests to work with refactored provider system
- Resolve test failures related to new environment variables

## [4.4.0] - 2025-09-10

### Added
- **MCP Registry Support**
  - Add server.json configuration for MCP registry publication
  - Add mcp-name field to README for PyPI package validation
  - Integrate MCP registry publishing into CI/CD workflow
  - Support DNS-based namespace authentication (com.failmode/voicemode)
  - Update Makefile to sync server.json version during releases
  
- **Cloudflare Worker for voicemode.sh**
  - Serve install script via custom domain
  - Smart user-agent detection for CLI vs browser
  - Cached script delivery with fallback
  
- **Selective Tool Loading**
  - Reduce token usage by loading tools on demand
  - Implement smart tool filtering based on context
  - Add tool loading configuration options

- **Documentation Improvements**
  - Complete documentation reorganization
  - Add tutorials, guides, and reference sections
  - Improve getting-started guide with clear paths
  - Add universal installer as primary quick start
  - Archive outdated documentation

- **Three Bears Agent Support**
  - Add baby-bear, mama-bear, and papa-bear agent configurations
  - Integrate with sound fonts for agent-specific audio feedback

### Changed
- Consolidate PyPI and MCP Registry publishing workflows
- Update branch references from 'main' to 'master'
- Improve Cloudflare Worker error handling and caching
- Rename hook to hooks, stdin-receiver to receiver

### Fixed
- Fix broken documentation links after refactor
- Restore minimal claude command group for hook support
- Fix Claude settings.json path configuration

## [4.3.2] - 2025-09-03

### Fixed
- Add missing pyyaml dependency to pyproject.toml
- Remove macOS-only restriction from package
- Add Claude hooks configuration to repository settings

## [4.3.1] - 2025-09-03

### Fixed
- Minor bug fixes and improvements

## [4.3.0] - 2025-09-03

### Added
- Sound fonts with MP3 support and Three Bears sounds integration

## [4.2.0] - 2025-09-03

### Added
- **🧠 Think Out Loud Mode - AI Reasoning Made Audible**
  - Revolutionary feature that transforms AI's internal thinking into spoken performances
  - Extracts and voices Claude's reasoning blocks using multiple personas
  - Herman's Head / Inside Out style multi-voice performances for different reasoning types
  - Theditor agent that orchestrates thinking performances with distinct voices
  - Makes AI decision-making transparent and engaging through voice

- **🔊 Sound Fonts Integration - Audio Feedback for Every Action**
  - Play custom sounds for tool operations, errors, and completions
  - Filesystem-based sound font system with automatic discovery
  - Claude Code integration via receiver for hook-based audio
  - CLI command `play-sound` with theme, action, and sound selection
  - Enhances user experience with auditory feedback during operations
  - MP3 support added for 90% file size reduction over WAV
  - Recursive directory copying for complete sound font structure
  - Three Bears sound fonts for baby-bear, mama-bear, and papa-bear agents
  - Sound fonts disabled by default (VOICEMODE_SOUNDFONTS_ENABLED=false)

- **🎭 Claude Code Deep Integration**
  - Extract and analyze Claude's conversation logs in real-time
  - Access Claude's internal thinking blocks for transparency
  - CLI commands for message extraction with multiple output formats
  - Automatic context detection for Claude Code sessions
  - Foundation for advanced AI introspection features

### Changed
- **Enhanced Message Extraction**
  - Generic and flexible extraction supporting full conversations
  - Multiple output formats: full messages, text only, or thinking only
  - Better filtering by message type (user/assistant)
  - Improved integration with voice mode tools

### Removed
- **Redundant get_claude_thinking MCP tool**
  - Consolidated into more powerful get_claude_messages tool

### Documentation
- **Comprehensive Think Out Loud Documentation**
  - Agent specifications for theditor
  - Claude orchestration instructions
  - Voice persona mapping guide
  - Integration patterns and examples

## [4.1.0] - 2025-09-01

### Added
- **Pronunciation middleware for TTS/STT text processing**
  - Configurable pronunciation rules system that processes text before TTS and after STT
  - Regex-based text substitution rules with YAML configuration
  - Separate TTS and STT rule sets for bidirectional corrections
  - Privacy support - rules can be marked private to hide from LLM tool listings
  - Default rules for common patterns (3M, PoE, GbE, etc.)
  - Full CLI interface for managing pronunciation rules
  - MCP tool for LLM-based rule management with `pronounce` tool
  - Integrated into converse tool for automatic text processing
  - New configuration file: `voice_mode/data/default_pronunciation.yaml`

## [4.0.1] - 2025-09-01

### Removed
- Removed `whisperx` optional dependency to fix PyPI upload compatibility
  - The dependency was specified as a Git URL which is not allowed for PyPI packages
  - WhisperX functionality was recently added and not essential for core features

## [4.0.0] - 2025-08-31

### BREAKING CHANGES
- **Unified voice configuration system**
  - **BREAKING**: Replaced `.voices.txt` files with unified `.voicemode.env` configuration
  - Changed environment variable from `VOICEMODE_TTS_VOICES` to `VOICEMODE_VOICES` for simplicity
  - Implemented cascading configuration: env vars > project configs > global config  
  - Added directory tree walking for project-specific configuration discovery
  - Supports runtime configuration reloading via MCP tools
  - **Migration Required**: Users must migrate from `.voices.txt` to `.voicemode.env` with `VOICEMODE_VOICES=voice1,voice2` format

### Added

- **Comprehensive test coverage reporting system**
  - Integration with pytest-cov for coverage measurement
  - HTML coverage reports generated in htmlcov/ directory  
  - Coverage badges and metrics for monitoring code quality
  - Automated coverage reporting in CI/CD pipeline
  
- **Word-level timestamps for transcription**
  - Enhanced transcription output with word-level timing information
  - Support for SubRip (SRT) format output with precise word timestamps
  - New transcription CLI command for processing audio files
  - Comprehensive transcription backend supporting multiple formats
  - Word timing data available for improved accessibility and analysis

- **Enhanced voice selection guide**
  - Comprehensive documentation for voice selection across different providers
  - Clear migration instructions from old `.voices.txt` system
  
### Removed  
- **Legacy voice preference system**
  - Removed 578 lines of old `voice_preferences.py` system
  - Eliminated unreliable `.voices.txt` file parsing
  - Removed associated test files for deprecated voice preference system

## [3.34.3] - 2025-08-26

### Changed
- **Service management code cleanup**
  - Removed references to non-existent `start.sh` script in Kokoro service discovery
  - Improved Kokoro start script detection by checking for GPU/CPU specific scripts only
  - Cleaned up code paths for better maintainability

## [2.34.2] - 2025-08-26

## [2.34.1] - 2025-08-26

### Fixed
- **Whisper service enable command**
  - Fixed `voicemode whisper enable` using incorrect template variable names
  - Changed from WHISPER_BIN/MODEL_FILE to START_SCRIPT_PATH/INSTALL_DIR to match plist template
  - Correctly locates start-whisper-server.sh script in whisper install directory
  - Fixes KeyError 'START_SCRIPT_PATH' when enabling whisper service after installation

### Changed
- **Installer reliability**
  - Added `--force` flag to `uv tool install --upgrade` command
  - Ensures voicemode is fully reinstalled even if already present
  - Prevents stale installations when package structure changes
  - Improves update reliability when running install.sh multiple times

## [2.34.0] - 2025-08-26

### Changed
- **Installer improvements**
  - Refactored installer to use permanent `uv tool install --upgrade` instead of `uvx --refresh`
  - Added `uv tool update-shell` for automatic PATH configuration
  - Improved shell completion detection with smart fallbacks
  - Added Homebrew zsh completion directory support on macOS
  - Implemented XDG-compliant paths for bash completions
  - Removed fish shell support to simplify maintenance (bash/zsh only)
  - Zsh completions now correctly use underscore prefix (_voicemode)
  - MCP configuration now uses plain `voice-mode` command for better performance

### Fixed
- **Service file updates on reinstall**
  - Fixed whisper and kokoro installers to always update service files (plist/systemd) even when service is already installed
  - Ensures paths are properly expanded (no `~` symbols) in service files
  - Fixes issue where broken service files with unexpanded paths would remain broken after running install.sh
  - Service files now updated to latest templates on every install, ensuring users always get working configurations

## [2.33.4] - 2025-08-26

### Fixed
- **CoreML support restoration**
  - Re-enabled CoreML acceleration after fixing plist template path issues
  - Improved CoreML compilation flags handling in whisper installer

## [2.33.3] - 2025-08-26

### Changed
- Version bump for testing installer fixes

## [2.33.2] - 2025-08-26

### Fixed
- **Whisper service installation**
  - Corrected plist template path in whisper installer
  - Fixed CoreML support compilation flags (disabled then re-enabled after testing)
  - Removed duplicate inline plist fallback to prevent template divergence

## [2.33.1] - 2025-08-26

### Fixed
- **Whisper service LaunchAgent fixes**
  - Fixed LaunchAgent plist to call start-whisper-server.sh script instead of binary directly
  - Script provides dynamic model selection via VOICEMODE_WHISPER_MODEL environment variable
  - Added proper command-line arguments (--inference-path, --threads) missing from direct binary call
  - Resolved Signal 15 (SIGTERM) restart loop caused by missing parameters

### Changed
- **Service configuration templates**
  - Refactored Whisper installer to use plist template file instead of inline generation
  - Template approach improves maintainability and makes configuration easier to find
  - Removed duplicate inline plist fallback to prevent template/code divergence
  - Templates are packaged with distribution ensuring availability

## [2.33.0] - 2025-08-26

### Fixed
- **CoreML acceleration improvements**
  - Re-enabled CoreML acceleration in installer after fixing template loading issues
  - Fixed CoreML conversion with dedicated Python environment to avoid dependency conflicts
  - Improved CoreML setup to handle PyTorch dependency management properly
  - Disabled misleading CoreML prompt temporarily while fixing PyTorch installation

- **Whisper service improvements**
  - Implemented unified Whisper startup script for Mac and Linux
  - Fixed Whisper service to respect VOICEMODE_WHISPER_MODEL setting properly
  - Changed default Whisper model from large-v2 to base for faster initial setup

- **Installer script stability**
  - Fixed script exit after Whisper installation when CoreML setup CLI check fails
  - Properly handle check_voice_mode_cli failures in setup_coreml_acceleration
  - Installer now continues with Kokoro and LiveKit even if CoreML setup encounters issues
  - Fixed installer exit issue after Whisper when checking for voicemode CLI

- **Documentation corrections**
  - Removed mention of response_duration from converse prompt to avoid confusion

### Changed
- **Web documentation improvements**
  - Updated Quick Start to use `curl -O && bash install.sh` for proper interactive prompts
  - Clarified OpenAI API key is optional and serves as backup when local services unavailable
  - Added comprehensive list of what the installer automatically configures
  - Changed example to use `claude converse` instead of interactive prompt
  - Updated README to use `/voicemode:converse` for consistent voice usage

- **Configuration updates**
  - Added voicemode MCP to Claude Code configuration for easier integration

## [2.32.0] - 2025-08-25

### Added
- **Safe shell completions in installer**
  - Re-enabled shell completion setup with runtime command availability checks
  - Completions only activate if `voicemode` command is found in PATH
  - Prevents shell startup errors when command is not available
  - Supports bash, zsh, and fish shells with safe fallback behavior

- **Interactive PyTorch installation prompt for Whisper**
  - Added `--install-torch` flag to CLI for explicit PyTorch installation
  - Interactive prompt when Core ML acceleration requires PyTorch (~2.5GB)
  - Clear user choice between Core ML acceleration and standard Metal performance

### Changed
- **CLI consistency improvements**
  - Replaced all user-facing "voice-mode" references with "voicemode"
  - Updated shell completion environment variables from `_VOICE_MODE_COMPLETE` to `_VOICEMODE_COMPLETE`
  - Removed redundant `completion` command, keeping only the superior `completions` command
  - Simplified command help text and examples for consistency
  - Logger name remains "voice-mode" for backward compatibility

### Fixed
- **Installer script reliability**
  - Fixed false positive failure detection when Whisper shows "Make clean" warning
  - Improved service installation success detection
  - Fixed incorrect `whisper model-install` command (should be `whisper model install`)
  - Removed non-existent `--auto-confirm` flag from CoreML installation

- **Clean CLI output**
  - Replaced deprecated `proc.connections()` with `proc.net_connections()` to eliminate warnings
  - Suppressed httpx INFO logging in CLI commands for cleaner output
  - All warnings and debug info still available with `--debug` flag

## [2.30.0] - 2025-08-25

### Added
- **Intelligent update command**
  - Automatic detection of installation method (UV tool, UV pip, or standard pip)
  - Uses appropriate update strategy based on installation type
  - Seamless updates regardless of how Voice Mode was installed

## [2.29.0] - 2025-08-25

### Added
- **CoreML acceleration support for Whisper on Apple Silicon**
  - Added optional dependency group 'coreml' with PyTorch and CoreMLTools
  - Enhanced whisper_model_install tool with install_torch and auto_confirm parameters
  - Automatic detection of Apple Silicon Macs with CoreML acceleration offer
  - User-friendly confirmation prompts for large (~2.5GB) PyTorch download
  - Graceful fallback to Metal acceleration if CoreML requirements not met
  - Clear instructions for enabling CoreML later if initially skipped

- **Beautiful installer experience**
  - Added Voice Mode ASCII art in Claude Code orange color
  - Enhanced preamble with clear value proposition and privacy messaging
  - Early system detection with special recognition for Apple Silicon
  - Professional presentation with centered text and visual hierarchy

### Fixed
- **Improved converse tool documentation**
  - Simplified listen_duration parameter documentation
  - Removed confusing duration recommendations that led to unnecessary overrides
  - Clarified that silence detection handles timing well with sensible defaults
  - Reduces cognitive load and prevents token waste from explicit duration settings

## [2.28.3] - 2025-08-24

### Fixed
- **Parameter type handling for MCP tools**
  - Fixed vad_aggressiveness parameter to accept string values from LLMs
  - Fixed port parameters in kokoro_install and livekit_install
  - Fixed lines parameter in service management tool
  - All numeric parameters now properly convert strings to integers
  - Addresses systemic issue where Claude Code MCP client passes strings

- **Installer script uvx command corrections**
  - Fixed MCP configuration to use correct command `uvx voice-mode` (without --refresh)
  - Installer now always refreshes to latest version at start
  - Removed unnecessary --refresh flags from runtime commands
  - Updated user-facing command examples to show correct usage

## [2.28.2] - 2025-08-24

### Added
- **Configurable audio feedback pip delays**
  - Added VOICEMODE_PIP_LEADING_SILENCE and VOICEMODE_PIP_TRAILING_SILENCE environment variables
  - Allows customization of silence before and after audio feedback chimes
  - Configurable via converse tool parameters pip_leading_silence and pip_trailing_silence
  - Helps prevent audio cutoff on Bluetooth devices and other audio systems with delay

### Fixed
- **Audio feedback for Bluetooth devices**
  - Added silence buffer before chimes to prevent Bluetooth audio cutoff
  - Improved compatibility with devices that have audio activation delay
  - Better audio feedback experience across different output devices

## [2.28.1] - 2025-08-24

### Added
- **Standardized project naming as VoiceMode MCP**
  - Consistent branding across all documentation and code
  - Updated project descriptions and metadata
  - Renamed internal references from "voice-mode" to "VoiceMode MCP"
  - Maintains backward compatibility with existing installations

### Fixed
- **CoreML fallback for whisper.cpp on Apple Silicon**
  - Added proper error handling when CoreML models fail to load
  - Automatically falls back to CPU processing if CoreML initialization fails
  - Prevents whisper-server crashes on systems with CoreML issues
  - Improves reliability on various macOS configurations

## [2.28.0] - 2025-08-23

### Added
- **Comprehensive CLI help support**
  - Added `-h` and `--help` options to all CLI commands and subcommands
  - Consistent help functionality across all command groups (kokoro, whisper, livekit, config, etc.)
  - Help options available for both groups and individual commands
  - Improved user experience with quick access to command documentation

- **Core ML support for whisper.cpp installation**
  - Whisper install now uses CMake instead of Make for better control
  - Automatically enables Core ML support on Apple Silicon Macs
  - Provides ~3x faster encoding performance with Core ML acceleration
  - Core ML models automatically converted during installation
  - Falls back gracefully if Core ML conversion fails
  
- **Enhanced whisper status command**
  - Shows whisper.cpp version information
  - Displays Core ML support status (enabled/disabled)
  - Shows if Core ML model is active for current model
  - Reports GPU acceleration type (Metal/CUDA)
  - Helper utility in `whisper_version.py` for capability detection
  
- **Audio conversion optimization for local whisper**
  - Automatically detects truly local whisper (not SSH-forwarded)
  - Skips WAV to MP3 conversion for local whisper, sending WAV directly
  - Adds timing measurements for audio format conversion
  - Logs conversion time at INFO level for performance monitoring
  - Significantly reduces STT processing time for local deployments
  
- **Whisper model benchmark command**
  - New `whisper model benchmark` CLI command
  - Compares performance across multiple models
  - Shows load time, encode time, and total processing time
  - Calculates real-time factor for each model
  - Fixed timing output by removing --no-prints flag
  - Helps users choose optimal model for speed/accuracy tradeoffs
  - Provides personalized recommendations based on results

### Fixed
- **MCP server configuration**
  - Fixed .mcp.json to use `uv run voicemode` for local development
  - Removed hardcoded paths for better portability
  - Works correctly with project-local development version
  
- **Whisper model management**
  - Fixed model active command to properly update configuration
  - Fixed naming conflict in model install CLI command
  - Benchmark now correctly shows timing information
  - Core ML conversion errors are now properly reported and handled

## [2.27.0] - 2025-08-20

### Added
- **CLI version and update commands**
  - New `voice-mode version` command to display current version
  - New `voice-mode update` command to upgrade to latest version
  - Comprehensive bats tests for version and update functionality
  - Automatic version detection from package metadata
  
- **Shell completion support for CLI**
  - New `voice-mode completion` command group with bash, zsh, and fish subcommands
  - Automatic tab completion for all commands, options, and arguments
  - Install.sh automatically configures shell completions during setup
  - Native Click completion mechanism for dynamic suggestions
  
- **Parallel operations documentation**
  - Documented `wait_for_response=False` pattern in converse tool
  - Enables speaking while performing other operations simultaneously
  - Creates more natural conversations by eliminating dead air
  - Marked as RECOMMENDED pattern with clear usage examples
  
- **Comprehensive Whisper model management system**
  - New `whisper models` CLI command to list all available models with status
  - `whisper model active` command to get/set the active model  
  - `whisper model install` and `whisper model remove` commands
  - Model registry with complete size/hash metadata for all Whisper models
  - Color-coded output showing installed/available models (green=installed, yellow=selected)
  - Support for English-only models and all multilingual variants
  - Automatic Core ML conversion on Apple Silicon for improved performance
  - Shell completion support for all model management commands
  
- **MCP tools for model management**
  - `list_models` tool to list all available Whisper models with status
  - Enhanced `download_model` tool with registry validation
  - Force download option to re-download corrupted models
  - Skip Core ML option for testing
  - Parity between CLI and MCP interfaces
  
- **Infrastructure improvements**
  - Centralized model registry in `whisper/models.py` with all model metadata
  - Model categorization: tiny, base, small, medium, large, turbo
  - Size information for all models (39MB to 3.1GB)
  - SHA256 hashes for integrity verification
  - Shared download logic extracted to helpers module
  - Dynamic Click-based shell completions replacing static files
  - Comprehensive test suite for model management

### Changed
- **Configuration file naming**
  - Renamed `.voicemode.env` to `voicemode.env` (removed leading dot)
  - Added backwards compatibility to check for old filename
  - Shows deprecation warning when old filename is used
  - Updated all documentation to reference new filename
  - Updated systemd service templates
  
- Replaced static shell completions with Click-generated dynamic completions
- Shell completion files now generated from CLI structure
- Whisper model downloads now use centralized registry for validation
- Model status checks now verify both file existence and selection

### Fixed
- **macOS installation improvements**
  - Added coreutils dependency for timeout command support
  - Fixed duplicate launchctl load in service installers
  - Improved zsh PATH configuration by sourcing profile after UV/npm additions
  - Skip sudo prompts on macOS to prevent installation issues
  
- **Test suite fixes**
  - Fixed deprecation warning appearing in help output
  - Renamed deprecated `.voicemode.env` to `voicemode.env` to fix test failures
  
- Whisper model management now properly uses voicemode.env configuration file
- Test suite updated for all API changes and return value structures
- Resolved all CI test failures related to service status and diagnostics

### Removed
- Old static shell completion files  
- SERVICE_COMMANDS.md (replaced by integrated CLI commands)
- Shell aliases file (functionality moved to Click commands)

## [2.26.0] - 2025-08-18

### Added
- **CLI converse command** - Direct voice conversations from the command line
  - New `voice-mode converse` command for testing voice interactions
  - Supports all MCP tool options (voice, speed, audio format, etc.)
  - Continuous conversation mode with `--continuous` flag
  - Useful for testing TTS/STT services without MCP client
  - Full control over voice parameters and silence detection
  
### Changed
- **Gitignore update** - Added `*.prof` files to gitignore for profiling output

## [2.25.1] - 2025-08-18

### Fixed
- **WSL2 detection display** - Fixed incorrect WSL2 label on non-WSL systems
  - Parameter expansion bug was showing "(WSL2)" on all Linux systems
  - Now properly checks if IS_WSL equals "true" before adding WSL2 label
  - Fixes false positive on Fedora and other Linux distributions
  - Complements previous detection fix from 2025-08-17

## [git push origin -v2.25.0] - 2025-08-18

## [2.25.0] - 2025-08-18

### Fixed
- **uvx command refresh flag** - Add --refresh flag to all uvx commands in installer
  - Ensures latest version is always fetched when running voice-mode commands
  - Fixes issues with cached old versions being used
  - Applies to service installation, uninstallation, and status commands
- **Performance optimization** - Significantly improved help command performance
  - Lazy load heavy imports (numpy, scipy, webrtcvad) only when needed
  - Help command now runs 10x faster (from ~1.5s to ~0.15s)
  - Faster MCP server startup time for better user experience
- **Config path expansion** - Fixed tilde expansion for user home directories
  - Configuration paths now properly expand `~` to user home directory
  - Fixes issues with paths like `~/Models/kokoro` not being found
  - Added comprehensive tests for path expansion functionality
- **Frontend imports** - Corrected import statements to use single module
  - Fixed import errors in livekit frontend commands
  - All frontend commands now properly import from frontend module

## [2.24.0] - 2025-08-16

### Added
- **Enhanced Voice Activity Detection** - Improved silence detection behavior
  - VAD now waits indefinitely for speech before starting silence detection
  - No more timeouts when user hasn't started speaking yet
  - Silent recordings are not sent to STT, reducing API costs and preventing hallucinations
  - Returns "No speech detected" message instead of processing silence
  - Significantly improves user experience for voice interactions
- **VAD debugging mode** - Comprehensive debugging for Voice Activity Detection
  - New `VOICEMODE_VAD_DEBUG` environment variable enables detailed VAD logging
  - Shows real-time speech detection decisions, state transitions, and timing
  - Helps diagnose issues where recording stops before speech or cuts off early
  - Added test script `scripts/test-vad-enhancement.py` for VAD testing
  - Documented in `docs/vad-debugging.md` with common issues and solutions

## [2.23.0] - 2025-08-16

### Added
- **`skip_tts` parameter** - Dynamic control over text-to-speech in converse tool
  - Add optional `skip_tts` parameter to override global `VOICEMODE_SKIP_TTS` setting
  - When `True`: Skip TTS for faster text-only responses
  - When `False`: Always use TTS regardless of environment setting
  - When `None` (default): Follow `VOICEMODE_SKIP_TTS` environment variable
  - Enables LLM to intelligently choose between voice and text-only responses
- **`VOICEMODE_SKIP_TTS` environment variable** - Global TTS skip configuration
  - Set to `true` for permanent text-only mode (faster responses)
  - Can be overridden per-call with `skip_tts` parameter
  - Useful for rapid development iterations or when voice isn't needed

### Fixed
- **Service status detection** - Correctly identify SSH-forwarded vs locally running services
  - SSH processes listening on service ports are now recognized as port forwards
  - Status command now shows 🔄 for forwarded services vs ✅ for local services
  - Prevents confusion about where services are actually running

## [2.22.3] - 2025-08-16

### Fixed
- **Service auto-enable error** - Fix 'FunctionTool' object is not callable
  - Changed whisper and kokoro installers to use `enable_service` function instead of MCP tool
  - Services can now be properly auto-enabled after installation
- **Whisper build errors** - Remove obsolete make server command
  - whisper-server is now built as part of the main build target
  - Removed unnecessary build step that was causing errors
- **Build output verbosity** - Suppress cmake/make output unless debugging
  - Build output is now captured and only shown on errors
  - Use VOICEMODE_DEBUG=true to see full build output
  - Significantly cleaner installation experience

## [2.22.2] - 2025-08-16

### Fixed
- **CLI deprecation warnings** - Suppress known warnings for cleaner output
  - Hide audioop, pkg_resources, and psutil deprecation warnings by default
  - Warnings can be shown with `VOICEMODE_DEBUG=true` or `--debug` flag
  - Improves user experience when running CLI commands and MCP server
  - Applies to both direct CLI usage and MCP server invocations

## [2.22.1] - 2025-08-16

### Fixed
- **Package size reduction** - Exclude unnecessary files from wheel distribution
  - Exclude `__pycache__`, `node_modules`, `.next/cache` directories
  - Exclude test files, logs, and build artifacts
  - Remove overly broad shared-data section that included entire frontend
  - Significantly reduces installed package size
- **Install.sh service detection** - Fix service command availability check
  - Handle Python deprecation warnings that were causing false negatives
  - Check for actual help output content instead of just exit code
  - Services now install correctly when warnings are present
  - Add `--help` and `--debug` flags for better troubleshooting
  - Support `DEBUG=true` environment variable

## [2.22.0] - 2025-08-16

### Added
- **LiveKit service integration** - Complete support for LiveKit as a managed service
  - Install/uninstall LiveKit server with `voice-mode livekit install/uninstall`
  - Service management commands: `start/stop/status/restart/enable/disable/logs`
  - Frontend management for LiveKit Voice Assistant UI
  - Configurable host/port settings for frontend
  - SSL configuration examples and documentation
  - Production-ready frontend build support
  - Bash completions for all new commands
- **Service installation in install.sh** - Automated service setup during installation
  - Offers to install Whisper, Kokoro, and LiveKit services
  - Quick mode (Y) installs all services automatically
  - Selective mode (s) allows choosing individual services
  - Uses `uvx voice-mode` for robust operation on fresh systems
  - Cross-platform support for Linux and macOS
- **Install.sh automated testing** - Comprehensive test suite (temporarily skipped)
  - Unit tests for individual bash functions
  - Functional tests with environment mocking
  - Integration tests for complete installation flows
  - Foundation for future testing improvements
- **Documentation improvements**
  - YubiKey touch detector setup guide
  - LiveKit SSL configuration examples
  - Install.sh robustness analysis
  - Service installation feature documentation

### Fixed
- **LiveKit local development** - Added dummy API key support for local services
- **Frontend dependency handling** - Improved error messages and dependency resolution
- **Service enable command** - Resolved frontend service enable command issues
- **LiveKit WebSocket URL** - Hardcoded to wss://x1:8443 for reliable connections

### Changed
- **Whisper default port** - Updated from 2000 to 2022 in shell aliases
- **Install.sh robustness** - Always use `uvx voice-mode` for consistency
- **Test infrastructure** - Skip failing tests temporarily to maintain green CI

## [2.21.1] - 2025-08-13

- Late update to changelog for release 2.21.0

## [2.21.0] - 2025-08-13

### Added
- **CLI service commands** - New subcommands for managing Whisper and Kokoro services
  - `voice-mode service whisper start/stop/status/restart/enable/disable/logs`
  - `voice-mode service kokoro start/stop/status/restart/enable/disable/logs`
  - `voice-mode service whisper update-service-files` - Update systemd/launchd service files
  - `voice-mode service kokoro update-service-files` - Update systemd/launchd service files
  - Unified interface for controlling both STT and TTS services
  - Direct access to service management without needing MCP client
  - Consistent behavior across Linux (systemd) and macOS (launchd)

## [2.20.1] - 2025-08-11

### Fixed
- **Speed parameter validation error** - Fixed MCP validation error when passing speed parameter as string
  - Added type conversion from string to float for speed parameter
  - Now properly handles speed values passed by MCP clients (e.g., via uvx)
  - Added comprehensive validation and error messages for invalid speed values

## [2.20.0] - 2025-08-10

### Added
- **VAD aggressiveness control**
  - New `vad_aggressiveness` parameter in converse tool for controlling Voice Activity Detection sensitivity (0-3)
  - 0 = least aggressive filtering (more permissive), 3 = most aggressive (strict)
  - Allows adapting to different environments: quiet rooms (0-1) vs noisy environments (2-3)
  - Also configurable via VOICEMODE_VAD_AGGRESSIVENESS environment variable

### Changed
- **Improved VAD documentation**
  - Clarified that aggressiveness controls how strictly VAD filters out non-speech
  - Updated examples to better demonstrate appropriate use cases
  - Fixed configuration documentation that had backwards descriptions

## [2.19.0] - 2025-08-10

### Added
- **MCP prompt command: /release-notes**
  - New command to display recent changelog entries directly in Claude Code
  - Shows 5 most recent versions by default (configurable with parameter)
  - Parses and formats CHANGELOG.md for easy reading
  - Inspired by Claude Code's own /release-notes feature
  - Includes comprehensive test coverage

### Fixed
- Release notes prompt now handles empty string parameters correctly
- Command works properly with both source and installed packages
- Changelog is now accessible as an MCP resource when package is installed

### Changed
- Release notes output format now matches Claude Code's clean, minimal style
- Removed decorative headers and footers for cleaner terminal output
- Release notes displayed in chronological order (oldest first)

## [2.18.0] - 2025-08-10

### Added
- **TTS speed control**
  - New `speed` parameter in converse tool for controlling speech rate (0.25 to 4.0)
  - Currently supported by Kokoro TTS and any OpenAI-compatible services that support speed
  - Examples: 0.5 = half speed, 2.0 = double speed
  - Based on user request in issue #15

## [2.17.3] - 2025-08-07

### Fixed
- **STT audio saving with simple failover**
  - Fixed critical bug where STT audio files were not being saved when VOICEMODE_SIMPLE_FAILOVER=true
  - Simple failover now properly saves audio recordings before processing
  - Ensures consistent audio archival behavior across all failover modes

### Changed
- **Post-release improvements from 2.17.2**
  - Improved installer output formatting when Voice Mode is already configured
  - Fixed installer test that was failing due to complex mock setup
  - GitHub release notes now feature universal installer as primary installation method
  - Manual installation methods (pip, claude mcp) moved to subsection

## [2.17.2] - 2025-07-29

### Added
- **Universal installer script** for automatic setup
  - Single command installation: `curl -O https://getvoicemode.com/install.sh && bash install.sh`
  - Cross-platform support: Linux (Ubuntu/Fedora), macOS, and Windows WSL
  - Automatic dependency installation (Node.js, audio libraries, etc.)
  - Claude Code installation and Voice Mode MCP configuration
  - WSL2-specific audio setup and troubleshooting guidance
  - Symlink in project root for easy access: `./install.sh`
- **Centralized GPU detection utility**
  - Unified GPU detection across platforms (Metal, CUDA, ROCm)
  - Automatic selection of GPU vs CPU scripts for services
  - Intelligent fallback when specific scripts are missing
- **Service robustness improvements**
  - Systemd services now use `Restart=on-failure` instead of `Restart=always`
  - Added `RestartPreventExitStatus=127` to prevent restart loops when executables are missing
  - Services fail cleanly when installation directory is moved or deleted

### Changed
- **Installation improvements**
  - Installer now detects `ffmpeg` by command presence on Fedora (handles RPM Fusion installs)
  - Fixed installer exiting early due to `dnf check-update` exit codes
  - Automatic fallback for older Claude Code versions without `--scope` flag support
  - Better handling of existing Voice Mode configurations
- **Documentation updates**
  - README now emphasizes Claude Code and AI code editors as primary audience
  - Quick Start section leads with automatic installer
  - Clarified that OpenAI API key is optional (local services available)
  - Added clear explanation of free, open-source alternatives

### Fixed
- **Configuration directory creation**
  - Removed redundant `config/` directory creation (config stored in `voicemode.env`)
  - Fixed issue where services created unexpected directory structures
- **Claude Code compatibility**
  - Fixed `claude mcp list` and `claude mcp add` for versions without `--scope` support
  - Installer now works with all Claude Code versions

### Developer
- Added comprehensive tests for GPU detection and missing script scenarios
- Updated service file versions to 1.1.1 with improved systemd configuration

## [2.17.1] - 2025-07-29

## [2.17.0] - 2025-07-29

### 🎯 Major Voice Activity Detection Improvement
- **Dramatically improved silence detection accuracy** by fixing audio resampling bug
  - VAD was receiving corrupted audio due to improper downsampling from 24kHz to 16kHz
  - Now uses proper signal resampling instead of simple truncation
  - Results in significantly better speech/silence detection and fewer false positives
  - Background noise (fans, traffic) is now properly filtered out

### Added
- **Automatic configuration file loading**
  - Voice Mode now creates `~/.voicemode/voicemode.env` on first run
  - Template file includes all available settings with documentation
  - Environment variables always take precedence over file settings
  - Secure file permissions (0600) automatically set
- **Enhanced conversation logs with provider tracking (Schema v3)**
  - Added `provider_url` and `provider_type` fields to track which endpoint handled requests
  - Added detailed timing metrics: TTFA, generation time, playback time, transcription time
  - Moved conversation logs to `logs/conversations/` subdirectory for better organization
- **Year/month directory structure for audio files**
  - Audio files now saved in `audio/YYYY/MM/` structure to prevent flat directory issues
  - Automatic date extraction from filenames
  - Backward compatible with existing flat structure
- Development version detection with git info for better debugging
- Service file update capability for systemd/launchd services
- Complete service health check implementation
  - Services can report readiness status
  - Better failover decisions based on actual service health
- Enhanced service management with unified `service` tool
- Auto-installation of cmake dependency for whisper.cpp on macOS
- Simple failover mode for provider selection
  - New `VOICEMODE_SIMPLE_FAILOVER` environment variable (default: true)
  - Try each endpoint in order without health checks
  - Immediate failover on connection refused errors
  - No performance penalty as connection failures are instant

### Changed
- **Major project structure reorganization**
  - Moved external dependencies to `vendor/` directory (industry standard naming)
    - `bin/livekit-admin-mcp` → `vendor/livekit-admin-mcp/`
    - `livekit/` → `vendor/livekit-voice-assistant/`
  - Moved development docs to `docs/development/`
    - `DUAL_PACKAGE_NAMES.md`, `TESTING-CHECKLIST.md`
    - `insights/` → `docs/development/insights/`
  - Moved test files from root to `tests/` directory
  - Merged `config-examples/` into `docs/integrations/`
  - Removed directories moved to shadow repository: `assets/`, `notebooks/`, `npm-voicemode/`
  - Cleaned up root directory following Python best practices
  - Moved `testing/` to `docs/testing/` for manual testing procedures
  - Removed backup files (`.mcp.json-20250728`) and temporary files (`COMMIT-MESSAGE.txt`)
  - Removed outdated `.env.example` from root (superseded by auto-generated config)
- Renamed `conversation.py` to `converse.py` for consistency
- Reorganized service directory structure for better maintainability
- Consolidated service management prompts and documentation
- Separated MCP templates and data from resources
- **Improved configuration documentation**
  - Added comprehensive configuration reference guide
  - Documented auto-generation of `~/.voicemode/voicemode.env`
  - Clarified that environment variables take precedence over file settings
- **Configuration management now uses user-level config only**
  - Removed project-level `voicemode.env` support for security
  - All configuration stored in `~/.voicemode/voicemode.env`

### Fixed
- Fixed `wait_for_response=false` being ignored in converse tool
  - Added proper string-to-boolean conversion for MCP parameters
- Fixed critical TTS failover issue when Kokoro is stopped
  - Simple failover now maps Kokoro voices to OpenAI-compatible voices
  - af_sky → nova, af_alloy → alloy, etc.
  - Prevents "Failed to speak message" errors when primary TTS is unavailable
- Fixed provider failover issues when local services are stopped
  - Previously, stopping a service (like Kokoro) would cause "All TTS providers failed" errors
  - Now correctly fails over to next available endpoint (e.g., OpenAI)
- Removed unnecessary soundfile dependency from simple failover
- Fixed various import issues with TTS_VOICES and TTS_MODELS
- **Fixed whisper model download tool**
  - Now correctly checks `~/.voicemode/services/whisper/` installation path
  - Support for both new and legacy whisper installation locations
  - Fixed model type validation

## [2.16.0] - 2025-07-28 [YANKED]

### Added
- Version management for whisper.cpp and kokoro-fastapi services
  - Track installed versions and support upgrades
  - Install only tagged releases by default (not latest commits)
  - `version` parameter added to install tools
  - Version info displayed in service status
- Uninstall tools for whisper and kokoro services
  - Clean removal of services and optionally models/data
  - Automatic service stop before uninstall
- Migration helpers for old service naming conventions
  - Automatically migrate from old naming (e.g., whisper-server) to new (whisper)
  - Built into installers, no separate tool needed

### Changed
- Reorganized helper functions from tools/ to utils/
  - `voice_mode/tools/services/common.py` → `voice_mode/utils/services/common.py`
  - `voice_mode/tools/services/*/helpers.py` → `voice_mode/utils/services/*_helpers.py`
  - `voice_mode/tools/services/version_helpers.py` → `voice_mode/utils/version_helpers.py`
  - Helper functions are no longer exposed as MCP tools

### Fixed
- Fixed test failures caused by version management implementation
  - Fixed version parsing bug with mixed int/string comparisons
  - Updated test mocks to use correct import paths
  - Made subprocess mocks command-specific to avoid breaking git commands
- Fixed unified service test failures
  - Added missing subprocess.run and Path.exists mocks
  - Fixed incomplete Popen mock setup

## [2.15.0] - 2025-07-23

## [2.14.0] - 2025-07-20

### Added
- New `VOICEMODE_DEFAULT_LISTEN_DURATION` environment variable to customize default listening time (defaults to 120s)

### Changed
- Changed default listen_duration parameter from 45s to 120s for more natural conversations
- Updated recommended listen durations in converse tool documentation
  - Normal conversational responses: 20s → 30s
  - Open-ended questions: 30s → 60s
  - Detailed explanations: 100s → 120s (now the default)
  - Stories or long explanations: 300s (unchanged)
  - Provides more generous time for users giving longer responses
- **BREAKING**: Voice preference files renamed from `voices.txt` to `.voices.txt`
  - Now uses hidden files to avoid cluttering project directories
  - Affects both standalone files and those in `.voicemode` directories

### Fixed
- Improved error messages when OpenAI API key is missing to provide helpful guidance
  - Now explicitly mentions need to set OPENAI_API_KEY or use local services
  - Differentiates between missing API key and other connection failures

## [2.13.0] - 2025-07-14

### Added
- Unified CLI system with shared exchanges library
  - New `voicemode` command with multiple subcommands (`show`, `tell`, `diagnose`, etc.)
  - Centralized exchange processing library for consistent behavior across scripts
  - Modular command architecture for easy extension
- Enhanced exchange logging capabilities:
  - STT entries logged even when no speech is detected for better debugging
  - Real-time logging of both TTS and STT exchanges
  - Split timing metrics between STT and TTS for accurate performance attribution
  - Additional metadata in exchange logs for better analysis

### Changed
- Migrated all standalone scripts to use the unified CLI system
  - Scripts now accessible as subcommands of the main `voicemode` command
  - Consistent argument parsing and help documentation across all commands
  - Improved code reuse through shared libraries

### Fixed
- Fixed undefined `audio_path` variable in STT logging
- Fixed incorrect hardcoded audio format in STT logs (now uses actual format)

## [2.12.0] - 2025-07-06

### Fixed
- Fixed TypeError in `refresh_provider_registry` tool that prevented TTS service detection (#6)
  - Changed incorrect `url=` parameter to `base_url=` when creating EndpointInfo objects
  - Added unit tests to prevent regression

## [2.11.0] - 2025-07-06

### Added
- Password protection for LiveKit voice assistant frontend
  - Prevents unauthorized access to voice conversation interface
  - Configurable via `LIVEKIT_ACCESS_PASSWORD` environment variable
  - Includes `.env.local.example` template with secure defaults
  - Password validation on API endpoint before token generation
- Prominent language support guidance in conversation tool
  - Clear language-specific voice recommendations for 8 languages
  - Mandatory voice selection for non-English text
  - Warning about American accent when using default voices
  - Examples for Spanish, French, Italian, Portuguese, Chinese, Japanese, and Hindi

### Changed
- Updated convention paths from `.conventions/` to `docs/conventions/` in CLAUDE.md
- Enhanced language voice selection documentation with explicit requirements

### Documentation
- Added Spanish voice conversation example demonstrating language-specific voice selection
- Added blind community outreach contacts and resources for accessibility collaboration
- Updated LiveKit frontend README with password protection instructions

## [2.10.0] - 2025-07-06

### Added
- All 67 Kokoro TTS voices now available for local text-to-speech
  - Complete set of high-quality voices across multiple accents and languages
  - Voices include various English accents (American, British, Australian, Indian, Nigerian, Scottish)
  - Multiple voices per accent for variety (e.g., 9 American female, 13 American male voices)
  - Support for international English speakers
  - Automatically available when Kokoro TTS service is running
- Voice preference files support for project and user-level voice settings
  - Supports both standalone `voices.txt` and `.voicemode/voices.txt` files
  - Automatic discovery by walking up directory tree from current working directory
  - User-level fallback to `~/voices.txt` or `~/.voicemode/voices.txt`
  - Standalone files take precedence over .voicemode directory files
  - Simple text format with one voice name per line
  - Comments and empty lines supported
  - Preferences take priority over environment variables
- New `check_audio_dependencies` MCP tool for diagnosing audio system setup
  - Checks for required system packages on Linux/WSL
  - Verifies PulseAudio status
  - Provides platform-specific installation commands
  - Helpful for troubleshooting audio initialization errors
- Enhanced audio error handling with helpful diagnostics
  - Detects missing system packages and suggests installation commands
  - WSL-specific guidance for audio setup
  - Better error messages when audio recording fails

### Fixed
- Mock voice preferences in provider selection tests to prevent test pollution
- Skip conversation browser playback test when Flask is not installed

### Documentation
- Updated Roo Code integration guide with comprehensive MCP interface instructions
- Added visual guide to MCP settings and troubleshooting section
- Added comprehensive Voice Preferences section to configuration documentation
- Updated README with voice preference file examples
- Updated Ubuntu/Debian installation instructions to include all required audio packages (pulseaudio, libasound2-plugins)
- Added WSL2-specific note in README pointing to detailed troubleshooting guide

## [2.9.0] - 2025-07-03

### Added
- Version logging on server startup for better debugging and support

### Fixed
- Cleaned up debug output by removing duplicate print statements
- Suppressed known upstream deprecation warnings from dependencies:
  - pydub SyntaxWarnings for invalid escape sequences
  - audioop deprecation (already handled with audioop-lts for Python 3.13+)
  - pkg_resources deprecation in webrtcvad
- Converted debug print statements to proper logger calls

## [2.8.0] - 2025-07-03

### Changed
- Changed default `min_listen_duration` from 1.0 to 2.0 seconds to provide more time for users to think before responding

## [2.7.1] - 2025-07-03

### Changed
- Changed default `min_listen_duration` from 0.0 to 1.0 seconds to prevent premature cutoffs

## [2.7.1] - 2025-07-03

### Fixed
- Fixed failing test for stdio restoration on recording error
- Added Flask to project dependencies for conversation browser script

## [2.7.0] - 2025-07-03

### Added
- Minimum listen duration control for voice responses
  - New `min_listen_duration` parameter in `converse()` tool (default: 0.0)
  - Prevents silence detection from stopping recording before minimum duration
  - Useful for preventing premature cutoffs when users need thinking time
  - Works alongside existing `listen_duration` (max) parameter
  - Validates that min_listen_duration <= listen_duration
  - Examples:
    - Complex questions: 2-3 seconds minimum
    - Open-ended prompts: 3-5 seconds minimum
    - Quick responses: 0.5-1 second minimum

## [2.6.0] - 2025-06-30

### Changed
- Updated Discord link to new community server
- Increased default listen duration to 45 seconds for better user experience
- Fixed config import issue in conversation tool
- Improved FFmpeg detection for MCP mode

### Added
- Screencast preparation materials including title cards
- Initial screencast planning documentation

## [2.5.1] - 2025-06-28

## [2.5.0] - 2025-06-28

### Added
- Automatic silence detection for voice recording
  - Uses WebRTC VAD (Voice Activity Detection) to detect when user stops speaking
  - Automatically stops recording after configurable silence threshold (default: 1000ms)
  - Significantly reduces latency for short responses (e.g., "yes" now takes ~1s instead of 20s)
  - Configurable via environment variables:
    - `VOICEMODE_ENABLE_SILENCE_DETECTION` - Enable/disable feature (default: true)
    - `VOICEMODE_VAD_AGGRESSIVENESS` - VAD sensitivity 0-3 (default: 2)
    - `VOICEMODE_SILENCE_THRESHOLD_MS` - Silence duration before stopping (default: 1000)
    - `VOICEMODE_MIN_RECORDING_DURATION` - Minimum recording time (default: 0.5s)
  - Added `disable_vad` parameter to converse() for per-interaction control
  - Automatic fallback to fixed-duration recording if VAD unavailable or errors occur
  - Comprehensive test suite and manual testing tools
  - Full documentation in docs/silence-detection.md
- Voice-first provider selection algorithm
  - TTS providers are now selected based on voice availability rather than base URL order
  - Ensures Kokoro is automatically selected when af_sky voice is preferred
  - Added provider_type field to EndpointInfo for clearer provider identification
  - Improved model selection to respect provider capabilities
  - Comprehensive test coverage for voice-first selection logic
- Configurable initial silence grace period
  - New `VOICEMODE_INITIAL_SILENCE_GRACE_PERIOD` environment variable (default: 4.0s)
  - Prevents premature cutoff when users need time to think before speaking
  - Gives users more time to start speaking before VAD stops recording
- Trace-level debug logging
  - Enabled with `VOICEMODE_DEBUG=trace` environment variable
  - Includes httpx and openai library debug output
  - Writes to `~/.voicemode/logs/debug/voicemode_debug_YYYY-MM-DD.log`
  - Helps diagnose provider connection issues

### Fixed
- Fixed WebRTC VAD sample rate compatibility issue
  - VAD requires 8kHz, 16kHz, or 32kHz but voice_mode uses 24kHz
  - Implemented proper sample extraction for VAD processing
  - Silence detection now works correctly with 24kHz audio
- Added automatic STT (Speech-to-Text) failover mechanism
  - STT now automatically tries all configured endpoints when one fails
  - Matches the existing TTS failover behavior for consistency
  - Prevents complete STT failure when primary endpoint has connection issues
- Implemented optimistic endpoint initialization
  - All endpoints now assumed healthy at startup instead of pre-checked
  - Endpoints only marked unhealthy when they actually fail during use
  - Prevents false negatives from overly strict health checks
  - Added optimistic mode to refresh_provider_registry tool (default: True)
- Fixed EndpointInfo attribute naming bug
  - Renamed 'url' to 'base_url' for consistency across codebase
  - Fixed AttributeError that was preventing STT failover from working
- Fixed Kokoro TTS not being selected despite being available
  - Provider registry now initializes with known Kokoro voices
  - Enables automatic Kokoro selection when af_sky is preferred
- Prevented microphone indicator flickering on macOS
  - Changed from start/stop recording for each interaction to continuous stream
  - Microphone stays active during voice session preventing UI flicker
  - More responsive recording start times

### Changed
- Replaced all localhost URLs with 127.0.0.1 for better IPv6 compatibility
  - Prevents issues with SSH port forwarding on dual-stack systems
  - Affects TTS, STT, and LiveKit default URLs throughout codebase

### Removed
- Cleaned up temporary and development files
  - Removed unused debug scripts and test files
  - Removed obsolete documentation and analysis files

### Planned
- In-memory buffer for conversation timing metrics
  - Track full conversation lifecycle including Claude response times
  - Maintain recent interaction history without persistent storage
  - Enable better performance analysis and debugging
- Sentence-based TTS streaming
  - Send first sentence to TTS immediately while rest is being generated
  - Significant reduction in time to first audio (TTFA)
  - More responsive conversation experience

## [2.4.1] - 2025-06-25

## [2.4.0] - 2025-06-25

### Added
- Unified event logging system for tracking voice interaction events
  - JSONL format for easy parsing and analysis
  - Automatic daily log rotation
  - Thread-safe async file writing
  - Session-based event grouping
  - Configurable via `VOICEMODE_EVENT_LOG_ENABLED` and `VOICEMODE_EVENT_LOG_DIR`
- Event types tracked:
  - TTS events: request, start, first audio, playback start/end, errors
  - Recording events: start, end, saved
  - STT events: request, start, complete, no speech, errors
  - System events: session start/end, transport switches, provider switches
- Automatic timing metric calculation from event timestamps
- Integration with conversation flow for accurate performance tracking
- Provider management tools for voice-mode
  - `refresh_provider_registry` tool to manually update health checks
  - `get_provider_details` tool to inspect specific endpoints
  - Support for filtering by service type (tts/stt) or specific URL
- Automatic TTS failover support in conversation tools
  - Systematic failover through all configured endpoints
  - Failed endpoints marked as unhealthy for automatic exclusion
  - Better error tracking and debugging information

### Changed
- TTS provider selection algorithm now uses URL-priority based selection
  - Iterates through TTS_BASE_URLS in preference order
  - Supports both voice and model preference matching
  - More predictable provider selection behavior
- Default TTS configuration updated for local-first experience
  - Kokoro (127.0.0.1:8880) prioritized over OpenAI
  - Default voices: af_sky, alloy (available on both providers)
  - Model preference order: gpt-4o-mini-tts, tts-1-hd, tts-1
- Voice parameter selection guidelines added to CLAUDE.md
  - Encourages auto-selection over manual specification
  - Clear examples of when to specify parameters

### Fixed
- Negative response time calculation in conversation metrics
  - Response time now correctly measured from end of recording
  - Event-based timing provides more accurate measurements

### Removed
- VOICE_ALLOW_EMOTIONS environment variable (emotional TTS now automatic with gpt-4o-mini-tts)

## [2.3.0] - 2025-06-23

### Added
- Comprehensive uv/uvx documentation (`docs/uv.md`)
  - Installation and version management guide
  - Development setup instructions
  - Integration with Claude Desktop
- Documentation section in README with organized links to all guides
- WSL2 microphone troubleshooting guide and diagnostic script
- Test script for direct STT verification

### Fixed
- STT audio format now defaults to MP3 when base format is PCM, fixing OpenAI Whisper compatibility
  - OpenAI Whisper API doesn't support PCM format for uploads
  - Automatic fallback ensures STT continues to work with default configuration

### Changed
- Simplified audio feedback configuration to boolean AUDIO_FEEDBACK_ENABLED
- Removed voice feedback functionality, keeping only chime feedback
- Updated provider base URL specification to use comma-separated lists
- PCM remains the default format for TTS streaming (best performance)
- Standardized audio sample rate to 24kHz across codebase (was 44.1kHz)
  - Updated SAMPLE_RATE configuration constant
  - Replaced all hardcoded sample rate values with config constant
  - Aligned test mocks with new standard rate
  - Ensures consistency between OpenAI and Kokoro TTS providers

## [2.2.0] - 2025-06-22

### Added
- Configurable audio format support with PCM as the default for TTS streaming
- Environment variables for audio format configuration:
  - `VOICEMODE_AUDIO_FORMAT` - Primary format (default: pcm)
  - `VOICEMODE_TTS_AUDIO_FORMAT` - TTS-specific override (default: pcm)
  - `VOICEMODE_STT_AUDIO_FORMAT` - STT-specific override
- Support for multiple audio formats: pcm, mp3, wav, flac, aac, opus
- Format-specific quality settings:
  - `VOICEMODE_OPUS_BITRATE` (default: 32000)
  - `VOICEMODE_MP3_BITRATE` (default: 64k)
  - `VOICEMODE_AAC_BITRATE` (default: 64k)
- Automatic format validation based on provider capabilities
- Provider-aware format fallback logic
- Test suite for audio format configuration
- Streaming audio playback infrastructure:
  - `VOICEMODE_STREAMING_ENABLED` (default: true)
  - `VOICEMODE_STREAM_CHUNK_SIZE` (default: 4096)
  - `VOICEMODE_STREAM_BUFFER_MS` (default: 150)
  - `VOICEMODE_STREAM_MAX_BUFFER` (default: 2.0)
- TTFA (Time To First Audio) metric in timing output
- Per-request audio format override via `audio_format` parameter in conversation tools
- **Live Statistics Dashboard**: Comprehensive conversation performance tracking
  - Real-time performance metrics (TTFA, TTS generation, STT processing, total turnaround)
  - Session statistics (interaction counts, success rates, provider usage)
  - MCP tools: `voice_statistics`, `voice_statistics_summary`, `voice_statistics_recent`, `voice_statistics_reset`, `voice_statistics_export`
  - MCP resources: `voice://statistics/{type}`, `voice://statistics/summary/{format}`, `voice://statistics/export/{timestamp}`
  - Automatic integration with conversation tools - no manual tracking required
  - Thread-safe statistics collection across concurrent operations
  - Memory-efficient storage (maintains last 1000 interactions)

### Changed
- **BREAKING**: All `VOICE_MODE_` environment variables renamed to `VOICEMODE_`
  - `VOICE_MODE_DEBUG` → `VOICEMODE_DEBUG`
  - `VOICE_MODE_SAVE_AUDIO` → `VOICEMODE_SAVE_AUDIO`
  - `VOICE_MODE_AUDIO_FEEDBACK` → `VOICEMODE_AUDIO_FEEDBACK`
  - `VOICE_MODE_FEEDBACK_VOICE` → `VOICEMODE_FEEDBACK_VOICE`
  - `VOICE_MODE_FEEDBACK_MODEL` → `VOICEMODE_FEEDBACK_MODEL`
  - `VOICE_MODE_FEEDBACK_STYLE` → `VOICEMODE_FEEDBACK_STYLE`
  - `VOICE_MODE_PREFER_LOCAL` → `VOICEMODE_PREFER_LOCAL`
  - `VOICE_MODE_AUTO_START_KOKORO` → `VOICEMODE_AUTO_START_KOKORO`
- Also renamed non-prefixed variables to use `VOICEMODE_` prefix:
  - `VOICE_ALLOW_EMOTIONS` → `VOICEMODE_ALLOW_EMOTIONS`
  - `VOICE_EMOTION_AUTO_UPGRADE` → `VOICEMODE_EMOTION_AUTO_UPGRADE`
- Default audio format changed from MP3 to PCM for zero-latency TTS streaming
- Audio format is now validated against provider capabilities before use
- Dynamic audio loading based on format instead of hardcoded MP3
- Centralized all configuration in `voice_mcp/config.py` to eliminate duplication
- Logger names updated from "voice-mcp" to "voicemode"
- Debug directory paths updated:
  - `~/voice-mcp_recordings/` → `~/voicemode_recordings/`
  - `~/voice-mcp_audio/` → `~/voicemode_audio/`

### Benefits
- Zero-latency TTS streaming with PCM format
- Best real-time performance for voice conversations
- Universal compatibility with all audio systems
- Maintains backward compatibility with compressed formats
- Cleaner, consistent environment variable naming

### Known Issues
- OpenAI TTS with Opus format produces poor audio quality - NOT recommended for streaming
  - Use PCM (default) or MP3 for TTS instead
  - Opus still works well for STT uploads and file storage

## [2.1.3] - 2025-06-20

## [2.1.2] - 2025-06-20

## [2.1.1] - 2025-06-20

### Fixed
- Fixed `voice_status` tool error where `get_provider_display_status` was called with incorrect arguments
- Updated `.mcp.json` to use local package installation with `--refresh` flag

### Added
- Audio feedback chimes for recording start/stop (inspired by PR #1 from @jtuffin)
- New `VOICE_MODE_AUDIO_FEEDBACK` configuration with options: `chime` (default), `voice`, `both`, `none`
- Backward compatibility for boolean audio feedback values

### Changed
- Replaced all references from `voice-mcp` to `voice-mode` throughout documentation
- Updated MCP configuration examples to use `uvx` instead of outdated `./mcp-servers/` directory
- Removed hardcoded version from `server_new.py`
- Changed default listen duration to 15 seconds (from 10s/20s) in all voice conversation functions for better balance
- Audio feedback now defaults to chimes instead of voice for faster, less intrusive feedback

## [2.1.0] - 2025-06-20

## [2.0.3] - 2025-06-20

## [2.0.2] - 2025-06-20

## [2.0.1] - 2025-06-20

### Changed
- Consolidated package structure from three to two pyproject.toml files
- Removed unpublishable `voicemode` package configuration
- Made `voice-mode` the primary package (in pyproject.toml)
- Moved `voice-mcp` to secondary configuration (pyproject-voice-mcp.toml)

### Added
- Documentation for local development with uvx (`docs/local-development-uvx.md`)

## [2.0.0] - 2025-06-20

### 🎉 Major Project Rebrand: VoiceMCP → VoiceMode

We're excited to announce that **voice-mcp** has been rebranded to **VoiceMode**! 

This change reflects our vision for the project's future. While MCP (Model Context Protocol) describes the underlying technology, VoiceMode better captures what this tool actually delivers - a seamless voice interaction mode for AI assistants.

#### Why the Change?
- **Clarity**: VoiceMode immediately communicates the tool's purpose
- **Timelessness**: The name isn't tied to a specific protocol that may evolve
- **Simplicity**: Easier to remember and more intuitive for users

#### What's Changed?
- Primary command renamed from `voice-mcp` to `voicemode`
- GitHub repository moved to `mbailey/voicemode`
- Primary PyPI package is now `voice-mode` (hyphenated due to naming restrictions)
- Legacy `voice-mcp` package maintained for backward compatibility
- Documentation and branding updated throughout
- Simplified package structure to dual-package configuration

#### Backward Compatibility
- The `voice-mcp` command remains available for existing users
- Both `voice-mode` and `voice-mcp` packages available on PyPI
- All packages provide the `voicemode` command

### Changed
- Consolidated package configuration to two pyproject.toml files
- Made `voice-mode` the primary package with VoiceMode branding
- Updated package descriptions to reflect the rebrand

### Added
- Local development documentation for uvx usage

## [0.1.30] - 2025-06-19

### Added
- Audio feedback with whispered responses by default
- Configurable audio feedback style (whisper or shout) via VOICE_MODE_FEEDBACK_STYLE environment variable
- Support for overriding audio feedback settings per conversation

## [0.1.29] - 2025-06-17

### Changed
- Refactored MCP prompt names to use kebab-case convention (kokoro-start, kokoro-stop, kokoro-status, voice-status)
- Renamed Kokoro tool functions to follow consistent naming pattern (start_kokoro → kokoro_start, stop_kokoro → kokoro_stop)

## [0.1.28] - 2025-06-17

### Added
- MCP prompts for Kokoro TTS management:
  - `kokoro-start` - Start the local Kokoro TTS service
  - `kokoro-stop` - Stop the local Kokoro TTS service
  - `kokoro-status` - Check the status of Kokoro service
  - `voice-status` - Check comprehensive status of all voice services
- Instructions in CLAUDE.md for AI assistants on when to use Kokoro tools

## [0.1.27] - 2025-06-17

### Added
- Voice chat prompt/command (`/voice-mcp:converse`) for interactive voice conversations
- Automatic local provider preference with VOICE_MODE_PREFER_LOCAL environment variable
- Documentation improvements with better organization and cross-linking

### Changed
- Renamed voice_chat prompt to converse for clarity
- Simplified voice_chat prompt to take no arguments


## [0.1.26] - 2025-06-17

### Fixed
- Added missing voice_mode() function to cli.py for voice-mode command

## [0.1.25] - 2025-06-17

### Added
- Build tooling improvements for dual package maintenance

### Fixed
- Missing psutil dependency in voice-mode package

## [0.1.24] - 2025-06-17

### Fixed
- Improved signal handling for proper Ctrl-C shutdown
  - First Ctrl-C attempts graceful shutdown
  - Second Ctrl-C forces immediate exit

## [0.1.23] - 2025-06-17

### Added
- Provider registry system MVP for managing TTS/STT providers
  - Dynamic provider discovery and registration
  - Automatic availability checking
  - Feature-based provider filtering
- Dual package name support (voice-mcp and voice-mode)
  - Both commands now available in voice-mode package
  - Maintains backward compatibility
- Service management tools for Kokoro TTS:
  - `start_kokoro` - Start the Kokoro TTS service using uvx
  - `stop_kokoro` - Stop the running Kokoro service
  - `kokoro_status` - Check service status with CPU/memory usage
- Automatic cleanup of services on server shutdown
- psutil dependency for process monitoring
- `list_tts_voices` tool to list all available TTS voices by provider
  - Shows OpenAI standard and enhanced voices with characteristics
  - Lists Kokoro voices with descriptions
  - Includes usage examples and emotional speech guidance
  - Checks API/service availability for each provider

### Changed
- Default TTS voices updated: alloy for OpenAI, af_sky for Kokoro

## [0.1.22] - 2025-06-16

### Added
- Local STT/TTS configuration support in .mcp.json
- Split TTS metrics into generation and playback components for better performance insights
  - Tracks TTS generation time (API call) separately from playback time
  - Displays metrics as tts_gen, tts_play, and tts_total

### Changed
- Modified text_to_speech() to return (success, metrics) tuple
- Updated all tests to handle new TTS return format

## [0.1.21] - 2025-06-16

### Added
- VOICE_MODE_SAVE_AUDIO environment variable to save all TTS/STT audio files
- Audio files saved to ~/voice-mcp_audio/ with timestamps
- Improved voice selection documentation and guidance

### Changed
- Voice parameter changed from Literal to str for flexibility in voice selection


## [0.1.19] - 2025-06-15

### Added
- TTS provider selection parameter to converse function ("openai" or "kokoro")
- Auto-detection of TTS provider based on voice selection
- Support for multiple TTS endpoints with provider-specific clients

## [0.1.18] - 2025-06-15

### Changed
- Removed mcp-neovim-server from .mcp.json configuration

## [0.1.17] - 2025-06-15

### Changed
- Minor version bump (no functional changes)

## [0.1.16] - 2025-06-15

## [0.1.16] - 2025-06-15

### Added
- Voice parameter to converse function for dynamic TTS voice selection
- Support for Kokoro voices: af_sky, af_sarah, am_adam, af_nicole, am_michael
- Python 3.13 support with conditional audioop-lts dependency

### Fixed
- BrokenResourceError when concurrent voice operations interfere with MCP stdio communication
- Enhanced sounddevice stderr redirection workaround to prevent stdio corruption
- Added concurrency lock to serialize audio operations and prevent race conditions
- Protected stdio file descriptors during audio recording and playback operations
- Added anyio.BrokenResourceError to exception handling for MCP disconnections
- Configure pytest to exclude manual test scripts from CI builds

## [0.1.15] - 2025-06-14

### Fixed
- Removed load_dotenv call that was causing import error

## [0.1.14] - 2025-06-14

### Fixed
- Updated GitHub workflows for new project structure

## [0.1.13] - 2025-06-14

### Added
- Performance timing in voice responses showing TTS, recording, and STT durations
- Local STT/TTS documentation for Whisper.cpp and Kokoro
- CONTRIBUTING.md with development setup instructions
- CHANGELOG.md for tracking changes

### Changed
- Refactored from python-package subdirectory to top-level Python package
- Moved MCP server symlinks from mcp-servers/ to bin/ directory
- Updated wrapper script to properly resolve symlinks for venv detection
- Improved signal handlers to prevent premature exit
- Configure build to only include essential files in package

### Fixed
- Audio playback dimension mismatch when adding silence buffer
- MCP server connection persistence (was disconnecting after each request)
- Event loop cleanup errors on shutdown
- Wrapper script path resolution for symlinked execution
- Critical syntax errors in voice-mcp script

### Removed
- Unused python-dotenv dependency
- Temporary test files (test_audio.py, test_minimal_mcp.py)
- Redundant test dependencies in pyproject.toml
- All container/Docker support

## [0.1.12] - 2025-06-14

### Added
- Kokoro TTS support with configuration examples
- Export examples in .env.example for various setups
- Centralized version management and automatic PyPI publishing

### Changed
- Simplified project structure with top-level package

## [0.1.11] - 2025-06-13

### Added
- Initial voice-mcp implementation
- OpenAI-compatible STT/TTS support
- LiveKit integration for room-based voice communication
- MCP tool interface with converse, listen_for_speech, check_room_status, and check_audio_devices
- Debug mode with audio recording capabilities
- Support for multiple transport methods (local microphone and LiveKit)

## [0.1.0 - 0.1.10] - 2025-06-13

### Added
- Initial development and iteration of voice-mcp
- Basic MCP server structure
- OpenAI API integration for STT/TTS
- Audio recording and playback functionality
- Configuration via environment variables
