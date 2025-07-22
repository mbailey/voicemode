# Changelog

All notable changes to VoiceMode (formerly voice-mcp) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
