# VoiceMode - Complete Project Overview for Claude Code

This document provides a comprehensive overview of the VoiceMode project architecture, components, and voice conversation flow. It's designed to give Claude Code (and similar AI coding assistants) a complete understanding of how the system works.

## Table of Contents

- [Project Purpose](#project-purpose)
- [Architecture Overview](#architecture-overview)
- [Core Components](#core-components)
- [Voice Conversation Flow](#voice-conversation-flow)
- [Provider System](#provider-system)
- [Recording & Silence Detection](#recording--silence-detection)
- [Configuration System](#configuration-system)
- [Extension Points](#extension-points)
- [Key Files & Responsibilities](#key-files--responsibilities)

## Project Purpose

VoiceMode enables natural voice conversations with Claude Code and other AI assistants through the Model Context Protocol (MCP). It provides:

- **Natural voice interactions**: Users speak to Claude, Claude speaks back
- **Multiple service backends**: Cloud (OpenAI) or local (Whisper, Kokoro)
- **Low latency**: Real-time feel with streaming audio
- **Smart silence detection**: Automatically stops recording when user stops speaking
- **Privacy options**: Can run entirely locally without cloud services

**Primary Use Case**: Enable hands-free/eyes-free interaction with AI coding assistants when typing isn't practical (walking, cooking, screen fatigue, etc.)

## Architecture Overview

```
┌──────────────────────────────────────────────────┐
│         MCP Client (Claude Code/Desktop)         │
│              Uses MCP Protocol                   │
└─────────────────┬────────────────────────────────┘
                  │ stdio/MCP messages
┌─────────────────┴────────────────────────────────┐
│          VoiceMode MCP Server (server.py)        │
│  - FastMCP-based server                          │
│  - Auto-imports tools from voice_mode/tools/     │
│  - Manages service lifecycle                     │
└─────────────────┬────────────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
    ▼             ▼             ▼
┌─────────┐  ┌──────────┐  ┌─────────┐
│  Tools  │  │Providers │  │ Config  │
│ System  │  │Discovery │  │ System  │
└─────────┘  └──────────┘  └─────────┘
    │             │             │
    └─────────────┼─────────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
    ▼             ▼             ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│ Whisper  │ │  Kokoro  │ │  OpenAI  │
│  (STT)   │ │  (TTS)   │ │(STT/TTS) │
│  Local   │ │  Local   │ │  Cloud   │
└──────────┘ └──────────┘ └──────────┘
```

### Layer Breakdown

1. **MCP Client Layer**: Claude Code or other AI assistants
2. **Server Layer**: FastMCP server exposing tools via stdio
3. **Core Logic Layer**: Tools, providers, configuration
4. **Service Layer**: Voice processing services (STT/TTS)
5. **Audio Hardware**: Local microphone and speakers via PyAudio/sounddevice

## Core Components

### 1. MCP Server (`voice_mode/server.py`)

**Purpose**: Entry point for the VoiceMode MCP server

**Responsibilities**:
- Initialize FastMCP server with stdio transport
- Auto-import all tools from `voice_mode/tools/` directory
- Check for FFmpeg availability (required for audio processing)
- Set up logging infrastructure

**Key Features**:
- Dynamic tool loading (all Python modules in tools/ are auto-imported)
- Resources for documentation, statistics, configuration
- Prompts for common voice interaction patterns

### 2. Converse Tool (`voice_mode/tools/converse.py`)

**Purpose**: Primary interface for voice conversations

**Function Signature**:
```python
async def converse(
    message: str,                      # Text to speak to user
    wait_for_response: bool = True,    # Listen for response after speaking
    listen_duration_max: float = 120,  # Max listen time
    listen_duration_min: float = 2.0,  # Min time before silence detection
    voice: Optional[str] = None,       # TTS voice selection
    tts_provider: Optional[str] = None,# Provider preference
    disable_silence_detection: bool = False,
    # ... additional parameters
) -> str:
    """Speak message and optionally listen for response"""
```

**Conversation Flow**:
1. **TTS Phase**: Convert text to speech and play it
2. **Pause**: Brief 0.5s pause after TTS completes
3. **Signal Listening**: Play "listening" chime
4. **Recording Phase**: Capture audio from microphone
5. **Signal Complete**: Play "finished" chime
6. **STT Phase**: Convert audio to text
7. **Return**: Return transcribed text to Claude

**Key Features**:
- Failover between TTS/STT providers
- Optional DJ volume ducking during TTS playback
- Repeat phrase detection ("repeat that", "say that again")
- Wait phrase detection ("wait a minute", "give me a moment")
- Conch coordination to prevent multiple simultaneous conversations

### 3. Provider System (`voice_mode/providers.py`, `voice_mode/provider_discovery.py`)

**Purpose**: Discover and manage voice service endpoints

**Discovery Process**:
1. Check for user-specified endpoints (env vars)
2. Scan for local services on known ports
3. Health check each discovered endpoint
4. Build registry of available providers

**Provider Types**:
- **OpenAI**: Cloud-based STT/TTS (requires API key)
- **Whisper**: Local STT service (port 2022 default)
- **Kokoro**: Local TTS service (port 8880 default)

**Selection Priority**:
```
1. Explicit provider parameter (tts_provider="kokoro")
2. Environment variable override (VOICEMODE_TTS_URL)
3. Local services (if VOICEMODE_PREFER_LOCAL=true)
4. Cloud fallback (OpenAI)
```

**Failover Logic**:
- Try primary provider first
- On failure, automatically try next available provider
- Log all attempts and errors
- Return structured error if all providers fail

### 4. Configuration System (`voice_mode/config.py`)

**Purpose**: Multi-layered configuration with sensible defaults

**Configuration Precedence** (highest to lowest):
1. Environment variables
2. Project-level config (`.voicemode.env` in working directory)
3. User-level config (`~/.voicemode/voicemode.env`)
4. Built-in defaults

**Key Configuration Categories**:

**Audio Settings**:
- `SAMPLE_RATE`: Recording sample rate (24000 Hz default)
- `CHANNELS`: Audio channels (1 = mono)
- `AUDIO_FEEDBACK_ENABLED`: Enable chimes (true/false)
- `STT_AUDIO_FORMAT`: Format for STT audio (mp3, wav, etc.)

**Voice Service Settings**:
- `OPENAI_API_KEY`: OpenAI API key
- `VOICEMODE_TTS_URL`: Override TTS endpoint
- `VOICEMODE_STT_URL`: Override STT endpoint
- `VOICEMODE_PREFER_LOCAL`: Prefer local services over cloud

**Silence Detection**:
- `VOICEMODE_DISABLE_SILENCE_DETECTION`: Disable VAD (false default)
- `VOICEMODE_VAD_AGGRESSIVENESS`: 0-3, higher = more aggressive (2 default)
- `VOICEMODE_SILENCE_THRESHOLD_MS`: Silence duration to stop (1800ms default)
- `VOICEMODE_MIN_RECORDING_DURATION`: Minimum recording time (1.0s default)
- `VOICEMODE_INITIAL_SILENCE_GRACE_PERIOD`: Grace period before VAD starts (1.0s)

**TTS Settings**:
- `VOICEMODE_TTS_SPEED`: Playback speed 0.25-4.0 (1.0 default)
- `VOICEMODE_TTS_VOICES`: Voice preference list
- `VOICEMODE_SKIP_TTS`: Skip TTS for testing (false default)

**Logging/Debug**:
- `VOICEMODE_SAVE_AUDIO`: Save audio files (false default)
- `VOICEMODE_AUDIO_DIR`: Audio save location
- `VOICEMODE_DEBUG`: Enable debug logging
- `VOICEMODE_VAD_DEBUG`: Detailed VAD logging

### 5. Conch (`voice_mode/conch.py`)

**Purpose**: Lock file coordination to prevent multiple simultaneous conversations

**Why It Exists**: Without coordination, multiple voice requests could try to use the microphone simultaneously, causing conflicts.

**How It Works**:
- Lock file: `~/.voicemode/conch`
- Uses `fcntl.flock()` for atomic locking
- Contains: PID, agent name, acquisition timestamp
- Auto-expires stale locks (120s default)

**Usage in Converse**:
```python
conch = Conch(agent_name="converse")
if not conch.try_acquire():
    # Another agent has the conch
    holder = Conch.get_holder()
    if wait_for_conch:
        # Wait for conch to become available
        ...
    else:
        return "User is currently speaking with another agent"
```

**Parameters**:
- `wait_for_conch`: Wait for lock (false = return immediately)
- `CONCH_TIMEOUT`: Max wait time (30s default)
- `CONCH_CHECK_INTERVAL`: Polling interval (0.5s default)

### 6. Audio Recording (`voice_mode/tools/converse.py`)

**Recording Functions**:

**Simple Recording** (`record_audio`):
- Records for fixed duration
- No silence detection
- Fallback when VAD unavailable

**Smart Recording** (`record_audio_with_silence_detection`):
- Uses WebRTC VAD for silence detection
- Automatically stops when user stops speaking
- Respects minimum recording duration
- Grace period before VAD activates

**VAD Configuration**:
```python
vad = webrtcvad.Vad(aggressiveness)  # 0-3
# 0 = permissive (good for noisy environments)
# 1 = quality (balanced)
# 2 = low bitrate (default - good balance)
# 3 = very aggressive (may cut off speech)
```

### 7. Service Management Tools

**Installation Tools** (`voice_mode/tools/whisper/`, `voice_mode/tools/kokoro/`):
- `whisper_install`: Install Whisper.cpp service
- `kokoro_install`: Install Kokoro TTS service
- Platform-specific setup (launchd on macOS, systemd on Linux)
- Model downloads and configuration

**Service Control**:
- Start/stop services
- Status checks
- Model management

## Voice Conversation Flow

### Detailed Sequence Diagram

```
User/Claude                 Converse Tool              TTS Service    Microphone    STT Service
    |                            |                          |              |              |
    |--- converse("Hello") ----->|                          |              |              |
    |                            |                          |              |              |
    |                            |--[1] TRY ACQUIRE CONCH-->|              |              |
    |                            |                          |              |              |
    |                            |--[2] TTS REQUEST-------->|              |              |
    |                            |<----TTS AUDIO STREAM-----|              |              |
    |                            |                          |              |              |
    |                            |--[3] PLAY AUDIO--------->|              |              |
    |                            |   (via audio_player)     |              |              |
    |<---👂 User hears "Hello"---|                          |              |              |
    |                            |                          |              |              |
    |                            |--[4] SLEEP 0.5s--------->|              |              |
    |                            |                          |              |              |
    |                            |--[5] PLAY CHIME--------->|              |              |
    |<---🔔 "listening" chime----|   "listening"            |              |              |
    |                            |                          |              |              |
    |                            |--[6] START RECORDING-------------------->|              |
    |                            |                          |              |              |
    |---🎤 User speaks---------->|                          |              |              |
    |   "Fix the bug"            |                          |              |              |
    |                            |<---------[VAD DETECTS SPEECH]-----------|              |
    |                            |                          |              |              |
    |---🤐 User stops----------->|                          |              |              |
    |                            |<---------[VAD DETECTS SILENCE]----------|              |
    |                            |                          |              |              |
    |                            |--[7] STOP RECORDING----------------------|              |
    |                            |                          |              |              |
    |                            |--[8] PLAY CHIME--------->|              |              |
    |<---🔔 "finished" chime-----|   "finished"             |              |              |
    |                            |                          |              |              |
    |                            |--[9] STT REQUEST----------------------------->|        |
    |                            |   (audio data)           |              |     |        |
    |                            |<---TRANSCRIPTION------------------------------|        |
    |                            |   "Fix the bug"          |              |     |        |
    |                            |                          |              |              |
    |                            |--[10] RELEASE CONCH----->|              |              |
    |                            |                          |              |              |
    |<--"Fix the bug"------------|                          |              |              |
```

### Phase-by-Phase Breakdown

#### Phase 1: TTS (Text-to-Speech)
**Location**: `converse.py` lines 1332-1433

```python
# 1. Select TTS provider (failover logic)
tts_success, tts_metrics, tts_config = await text_to_speech_with_failover(
    message=message,
    voice=voice,
    initial_provider=tts_provider,
    speed=speed
)

# 2. Play audio through speakers
# (DJ volume ducking happens here if DJ is running)
```

**TTS Metrics Tracked**:
- `ttfa`: Time to first audio (latency)
- `generation`: TTS generation time
- `playback`: Audio playback duration
- `total`: Total TTS time

#### Phase 2: Pre-Recording Pause
**Location**: `converse.py` line 1476

```python
# Brief pause before listening
await asyncio.sleep(0.5)
```

**⚠️ CRITICAL TIMING POINT**: This is where a third-party integration could insert a delay or wait for external signal.

#### Phase 3: Signal Listening Start
**Location**: `converse.py` lines 1479-1486

```python
# Play "listening" feedback sound
await play_audio_feedback(
    "listening",
    openai_clients,
    chime_enabled,
    "whisper",
    chime_leading_silence=chime_leading_silence,
    chime_trailing_silence=chime_trailing_silence
)
```

**Purpose**: Audio cue to user that system is ready to record

#### Phase 4: Recording
**Location**: `converse.py` lines 1489-1499

```python
logger.info(f"🎤 Listening for {listen_duration_max} seconds...")

audio_data, speech_detected = await asyncio.get_event_loop().run_in_executor(
    None, 
    record_audio_with_silence_detection, 
    listen_duration_max, 
    disable_silence_detection, 
    listen_duration_min, 
    vad_aggressiveness
)
```

**Recording with VAD** (lines 789-1070):
1. Initialize WebRTC VAD
2. Start continuous audio stream
3. Process audio in chunks (10/20/30ms)
4. Check each chunk for speech vs silence
5. Track silence duration
6. Stop when: silence threshold exceeded (after min duration) OR max duration reached

#### Phase 5: Signal Recording Complete
**Location**: `converse.py` lines 1510-1517

```python
# Play "finished" feedback sound
await play_audio_feedback(
    "finished",
    openai_clients,
    chime_enabled,
    "whisper"
)
```

#### Phase 6: STT (Speech-to-Text)
**Location**: `converse.py` lines 1543-1608

```python
# Convert audio to text
stt_result = await speech_to_text(
    audio_data, 
    SAVE_AUDIO, 
    AUDIO_DIR if SAVE_AUDIO else None, 
    transport
)

# Extract transcription and provider info
response_text = stt_result.get("text")
stt_provider = stt_result.get("provider")
```

**STT Process**:
1. Convert numpy audio to WAV format
2. Convert WAV to configured format (MP3 default for bandwidth)
3. Send to STT service
4. Parse response
5. Log metrics (request time, file size, provider)

#### Phase 7: Special Handling

**Repeat Phrase Detection** (lines 1610-1704):
- Detects phrases like "repeat that", "say that again"
- Replays cached TTS audio
- Re-records user response

**Wait Phrase Detection** (lines 1706-1760):
- Detects phrases like "wait a minute", "hold on"
- Pauses for configured duration (60s default)
- Plays "ready to listen" chime
- Re-records user response

## Recording & Silence Detection

### WebRTC VAD Integration

**What is VAD**: Voice Activity Detection - identifies speech vs silence in audio

**Why WebRTC VAD**:
- Battle-tested (used in WebRTC for real-time communications)
- Low latency (processes 10-30ms chunks)
- Configurable aggressiveness
- Works offline

**How It Works**:

```python
vad = webrtcvad.Vad(aggressiveness)  # Initialize VAD

# Process audio in chunks
for chunk in audio_stream:
    is_speech = vad.is_speech(chunk, sample_rate)
    
    if is_speech:
        silence_duration = 0  # Reset silence counter
        speech_detected = True
    else:
        silence_duration += chunk_duration
        
        if silence_duration > SILENCE_THRESHOLD_MS:
            # User stopped speaking, stop recording
            break
```

**Configuration Parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `VAD_AGGRESSIVENESS` | 2 | 0-3, higher = more aggressive |
| `SILENCE_THRESHOLD_MS` | 1800 | Silence duration to stop (1.8s) |
| `MIN_RECORDING_DURATION` | 1.0 | Min time before VAD can stop |
| `INITIAL_SILENCE_GRACE_PERIOD` | 1.0 | Grace period before VAD starts |
| `VAD_CHUNK_DURATION_MS` | 30 | Chunk size (10, 20, or 30ms) |

**Why These Defaults**:
- 1.8s silence threshold: Natural pause between thoughts
- 1.0s minimum: Prevents premature cutoff
- 1.0s grace period: Allows time to start speaking
- 30ms chunks: Balance between latency and accuracy

### Recording Flow State Machine

```
START
  |
  v
[INITIALIZING]
  - Create VAD
  - Start audio stream
  |
  v
[GRACE PERIOD] ─────> (< INITIAL_SILENCE_GRACE_PERIOD)
  - Record but don't check VAD
  - Allows user to start speaking
  |
  v
[ACTIVE RECORDING]
  - Process audio chunks
  - Check VAD on each chunk
  |
  ├──> [SPEECH DETECTED]
  |      - Reset silence counter
  |      - Continue recording
  |      - Loop back to ACTIVE
  |
  └──> [SILENCE DETECTED]
         - Increment silence counter
         |
         ├──> (silence < MIN_RECORDING_DURATION)
         |      - Continue recording (haven't met minimum)
         |      - Loop back to ACTIVE
         |
         ├──> (silence < SILENCE_THRESHOLD_MS)
         |      - Continue recording (still waiting)
         |      - Loop back to ACTIVE
         |
         └──> (silence >= SILENCE_THRESHOLD_MS)
                - Stop recording
                |
                v
              [COMPLETE]
                - Return audio data
                - Return speech_detected flag
```

## Provider System

### Discovery Mechanism

**Auto-Discovery Process**:
1. Check environment variables for explicit URLs
2. Scan well-known ports for local services
3. Perform health checks on discovered services
4. Build registry with provider metadata

**Health Check**:
```python
async def check_health(base_url):
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(f"{base_url}/health")
            return response.status_code == 200
    except:
        return False
```

**Registry Structure**:
```python
{
    "tts": [
        {
            "name": "kokoro",
            "base_url": "http://127.0.0.1:8880",
            "type": "local",
            "health": "ok",
            "capabilities": ["streaming", "voices"]
        },
        {
            "name": "openai",
            "base_url": "https://api.openai.com/v1",
            "type": "cloud",
            "health": "ok"
        }
    ],
    "stt": [
        {
            "name": "whisper",
            "base_url": "http://127.0.0.1:2022",
            "type": "local",
            "health": "ok"
        }
    ]
}
```

### Failover Logic

**TTS Failover** (`text_to_speech_with_failover`):
```python
# Try providers in order
for provider in [initial_provider, *fallback_providers]:
    try:
        result = await text_to_speech(message, provider)
        return result  # Success
    except Exception as e:
        log_error(provider, e)
        continue  # Try next provider

# All failed
return error_with_attempted_endpoints()
```

**STT Failover** (similar pattern in `speech_to_text`):
- Try local Whisper first (if available)
- Fall back to OpenAI
- Return structured error if all fail

### OpenAI API Compatibility

**Why**: Enables transparent switching between services

**Implementation**:
- Local services expose OpenAI-compatible endpoints
- Same request/response format
- Same parameter names
- Same error codes

**Example - TTS Request**:
```python
# Works with both OpenAI and Kokoro
response = await client.post(
    f"{base_url}/v1/audio/speech",
    json={
        "model": "tts-1",
        "input": text,
        "voice": voice,
        "speed": speed
    }
)
```

## Configuration System

### Environment Variable Patterns

**Naming Convention**: `VOICEMODE_<CATEGORY>_<SETTING>`

**Categories**:
- `VOICEMODE_TTS_*`: Text-to-speech settings
- `VOICEMODE_STT_*`: Speech-to-text settings
- `VOICEMODE_VAD_*`: Voice activity detection
- `VOICEMODE_AUDIO_*`: Audio processing
- `VOICEMODE_DJ_*`: DJ integration settings

**Examples**:
```bash
# Voice service endpoints
export VOICEMODE_TTS_URL="http://localhost:8880"
export VOICEMODE_STT_URL="http://localhost:2022"

# Preferences
export VOICEMODE_PREFER_LOCAL=true
export VOICEMODE_TTS_SPEED=1.2

# Silence detection
export VOICEMODE_DISABLE_SILENCE_DETECTION=false
export VOICEMODE_VAD_AGGRESSIVENESS=2
export VOICEMODE_SILENCE_THRESHOLD_MS=1800

# Debugging
export VOICEMODE_DEBUG=true
export VOICEMODE_SAVE_AUDIO=true
export VOICEMODE_VAD_DEBUG=true
```

### Configuration Files

**Project Config**: `.voicemode.env` (in working directory)
```bash
# Project-specific voice preferences
VOICEMODE_TTS_VOICE=af_sarah
VOICEMODE_TTS_SPEED=1.1
VOICEMODE_PREFER_LOCAL=true
```

**User Config**: `~/.voicemode/voicemode.env`
```bash
# User-wide defaults
OPENAI_API_KEY=sk-...
VOICEMODE_AUDIO_FEEDBACK_ENABLED=true
VOICEMODE_VAD_AGGRESSIVENESS=2
```

**Loading Priority**:
1. Environment variables (highest)
2. Project `.voicemode.env`
3. User `~/.voicemode/voicemode.env`
4. Built-in defaults (lowest)

## Extension Points

### 1. Custom Voice Services

**Requirements**:
- Expose OpenAI-compatible API endpoints
- `/v1/audio/speech` for TTS
- `/v1/audio/transcriptions` for STT
- `/health` endpoint for discovery

**Example - Custom TTS Service**:
```python
@app.post("/v1/audio/speech")
async def custom_tts(request: TTSRequest):
    audio = generate_speech(request.input, request.voice)
    return StreamingResponse(audio, media_type="audio/mpeg")

@app.get("/health")
async def health():
    return {"status": "ok"}
```

**Integration**:
```bash
export VOICEMODE_TTS_URL="http://localhost:9000"
```

### 2. Third-Party Coordination (See THIRD_PARTY_INTEGRATION.md)

**Hook Points**:
- Pre-recording delay
- Recording start/stop control
- Audio feedback customization
- Provider selection

### 3. Custom Audio Feedback

**Current Implementation**:
- "listening" chime before recording
- "finished" chime after recording
- System messages (repeating, waiting, etc.)

**Customization**:
- Replace audio files in `voice_mode/data/audio/`
- Or use TTS for dynamic messages

**Files**:
- `chime_whisper_start.wav`: "listening" chime
- `chime_whisper_end.wav`: "finished" chime
- `repeating.wav`, `waiting-1-minute.wav`, etc.

### 4. Custom VAD Implementation

**Current**: WebRTC VAD (battle-tested, low latency)

**Alternative VAD Engines**:
- Silero VAD (neural network-based)
- pyannote.audio (speaker diarization)
- Custom energy-based VAD

**Integration Point**: Replace `record_audio_with_silence_detection` function

### 5. Logging and Monitoring

**Event Logging**: `~/.voicemode/logs/events/`
- Structured event log
- JSON format
- Timestamps, session IDs, metrics

**Conversation Logging**: `~/.voicemode/logs/conversations/`
- JSONL format
- TTS/STT exchanges
- Provider info, timings

**Custom Logging**:
```python
from voice_mode.utils import get_event_logger

logger = get_event_logger()
logger.log_event("CUSTOM_EVENT", {"data": "value"})
```

## Key Files & Responsibilities

### Server & Entry Points

| File | Purpose | Key Functions |
|------|---------|---------------|
| `voice_mode/server.py` | MCP server entry point | Server initialization, tool loading |
| `voice_mode/__main__.py` | CLI entry point | Command-line interface |
| `voice_mode/cli.py` | CLI commands | `voicemode` command implementation |

### Core Voice Logic

| File | Purpose | Key Functions |
|------|---------|---------------|
| `voice_mode/tools/converse.py` | Main conversation tool | `converse()`, recording, TTS/STT orchestration |
| `voice_mode/core.py` | Core voice operations | `text_to_speech()`, `speech_to_text()`, client management |
| `voice_mode/audio_player.py` | Audio playback | `NonBlockingAudioPlayer` for TTS playback |
| `voice_mode/streaming.py` | Streaming audio | Stream processing for real-time playback |

### Provider & Discovery

| File | Purpose | Key Functions |
|------|---------|---------------|
| `voice_mode/providers.py` | Provider definitions | Provider classes, base interfaces |
| `voice_mode/provider_discovery.py` | Service discovery | Registry, health checks, failover |
| `voice_mode/simple_failover.py` | Failover logic | Provider selection, error handling |

### Configuration & State

| File | Purpose | Key Functions |
|------|---------|---------------|
| `voice_mode/config.py` | Configuration system | Load config, defaults, validation |
| `voice_mode/conch.py` | Conversation lock | `Conch` class for coordination |
| `voice_mode/shared.py` | Shared state | Global state, locks |

### Service Management

| File | Purpose | Key Functions |
|------|---------|---------------|
| `voice_mode/tools/whisper/install.py` | Whisper installation | `whisper_install()` |
| `voice_mode/tools/kokoro/install.py` | Kokoro installation | `kokoro_install()` |
| `voice_mode/tools/service.py` | Service control | Start/stop/status operations |

### Utilities

| File | Purpose | Key Functions |
|------|---------|---------------|
| `voice_mode/utils.py` | General utilities | Event logging, helpers |
| `voice_mode/conversation_logger.py` | Conversation logging | JSONL logging for exchanges |
| `voice_mode/statistics_tracking.py` | Statistics | Track usage, performance metrics |
| `voice_mode/openai_error_parser.py` | Error handling | Parse OpenAI API errors |

### Resources & Documentation

| File | Purpose | Content |
|------|---------|---------|
| `voice_mode/resources/` | MCP resources | Docs, stats, config exposed to clients |
| `voice_mode/prompts/` | MCP prompts | Common patterns, examples |
| `voice_mode/templates/` | Templates | Service configs, etc. |

## Key Design Decisions

### 1. Why Local Microphone (not LiveKit)?

**Original Design**: Used LiveKit for audio transport
**Current Design**: Direct PyAudio/sounddevice microphone access

**Reasons**:
- Lower latency (no network round-trip)
- Simpler setup (no LiveKit server required)
- Better for local-first use case
- Still supports cloud services for STT/TTS

### 2. Why OpenAI API Compatibility?

**Benefits**:
- Transparent switching between services
- No vendor lock-in
- Easy to add new providers
- Standard interface for testing

### 3. Why WebRTC VAD?

**Alternatives Considered**:
- Energy-based (too simple, many false positives)
- Silero VAD (neural network, higher latency)
- No VAD (user must manually stop)

**WebRTC Wins**:
- Battle-tested in production systems
- Low latency (10-30ms chunks)
- Configurable aggressiveness
- Works offline
- No GPU required

### 4. Why FastMCP?

**Benefits**:
- Built for Python-based MCP servers
- Auto-discovery of tools
- Type hints and validation
- Resources and prompts support
- Active development

### 5. Why Separate TTS/STT Services?

**Architectural Benefits**:
- Scale independently
- Upgrade independently
- Different hardware requirements (GPU for STT)
- Mix cloud/local as needed
- Service specialization

## Common Workflows

### Starting a Voice Conversation

```python
# Simple conversation
await converse("Hello! What can I help you with?")
# Returns: User's spoken response as text

# Speak without listening
await converse("I'll work on that now.", wait_for_response=False)
# Returns: Success message

# Custom parameters
await converse(
    "Tell me about the bug",
    listen_duration_max=180,  # 3 minutes max
    voice="af_sarah",
    tts_provider="kokoro",
    disable_silence_detection=False
)
```

### Installing Local Services

```bash
# Install Whisper.cpp for STT
voicemode whisper install

# Install Kokoro for TTS
voicemode kokoro install

# Check service status
voicemode service status

# Start services (if not auto-started)
voicemode service start whisper
voicemode service start kokoro
```

### Debugging Voice Issues

```bash
# Enable debug logging
export VOICEMODE_DEBUG=true
export VOICEMODE_VAD_DEBUG=true

# Save audio for inspection
export VOICEMODE_SAVE_AUDIO=true

# Check logs
tail -f ~/.voicemode/logs/events/$(date +%Y-%m-%d).jsonl
tail -f ~/.voicemode/logs/conversations/$(date +%Y-%m-%d).jsonl

# Inspect saved audio
ls -lh ~/.voicemode/audio/$(date +%Y)/$(date +%m)/
```

### Custom Configuration

```bash
# Create project config
cat > .voicemode.env << EOF
VOICEMODE_PREFER_LOCAL=true
VOICEMODE_TTS_VOICE=af_sarah
VOICEMODE_TTS_SPEED=1.2
VOICEMODE_VAD_AGGRESSIVENESS=2
EOF

# Or use user config
voicemode config edit
```

## Testing & Development

### Running Tests

```bash
# Install dev dependencies
make dev-install

# Run all tests
make test

# Run specific test
uv run pytest tests/test_voice_mode.py -v

# Run with coverage
uv run pytest tests/ --cov=voice_mode
```

### Manual Testing

```bash
# Test voice conversation
voicemode test converse

# Test TTS only
voicemode test tts "Hello world"

# Test STT only
voicemode test stt

# Test provider discovery
voicemode providers list
```

### Development Workflow

```bash
# Clone and install
git clone https://github.com/mbailey/voicemode.git
cd voicemode

# Development install
make dev-install

# Make changes...

# Run tests
make test

# Build package
make build-package

# Test installation
make test-package
```

## Troubleshooting

### Common Issues

**"FFmpeg not found"**:
- VoiceMode requires FFmpeg for audio processing
- Install: `brew install ffmpeg` (macOS) or `apt install ffmpeg` (Linux)

**"No microphone detected"**:
- Check system permissions (macOS: Privacy & Security > Microphone)
- WSL2: Install pulseaudio packages
- Verify: `voicemode devices list`

**"OpenAI API error: 401 Unauthorized"**:
- Set `OPENAI_API_KEY` environment variable
- Or use local services (Whisper + Kokoro)

**"No speech detected"**:
- Check microphone levels
- Try lower VAD aggressiveness: `VOICEMODE_VAD_AGGRESSIVENESS=1`
- Try disabling silence detection temporarily
- Check for background noise

**"Recording cuts off too early"**:
- Increase silence threshold: `VOICEMODE_SILENCE_THRESHOLD_MS=2500`
- Increase minimum duration: `VOICEMODE_MIN_RECORDING_DURATION=2.0`
- Lower VAD aggressiveness: `VOICEMODE_VAD_AGGRESSIVENESS=1`

**"All TTS providers failed"**:
- Check if local services are running: `voicemode service status`
- Check OpenAI API key if using cloud
- Check network connectivity
- Review logs: `~/.voicemode/logs/events/`

## Performance Characteristics

### Latency Breakdown

**Typical Conversation Turn** (local services):
- TTS generation: 200-500ms
- TTS playback: 2-5s (depends on message length)
- Pause: 500ms
- Chime: 200ms
- Recording: 2-10s (depends on user speech + silence threshold)
- Chime: 200ms
- STT processing: 500-2000ms (depends on audio length)
- **Total**: ~6-19s

**Cloud Services** (OpenAI):
- TTS generation: 500-1500ms (network + generation)
- STT processing: 1000-3000ms (network + processing)
- **Total**: ~7-22s

### Resource Usage

**Memory**:
- Base: ~100MB
- Per conversation: +20-50MB (audio buffers)
- With local services: +500MB-2GB (model weights)

**CPU**:
- Recording/playback: 5-15% (audio processing)
- STT (local): 50-200% (depends on model size)
- TTS (local): 20-100%

**Disk**:
- Base installation: ~50MB
- Whisper models: 150MB-1.5GB (depends on size)
- Kokoro models: ~100MB
- Logs/audio: Grows over time (can be pruned)

## Security Considerations

### Audio Privacy

**Local Mode**:
- Audio never leaves the machine
- No cloud API calls
- Whisper + Kokoro run locally

**Cloud Mode**:
- Audio sent to OpenAI API
- Subject to OpenAI privacy policy
- Encrypted in transit (HTTPS)

### API Key Storage

**Best Practices**:
- Never commit API keys to git
- Use environment variables
- Use project/user config files (not world-readable)
- Rotate keys periodically

### Conch Lock Security

**Considerations**:
- Lock file readable by all users on system
- Contains PID and agent name (not sensitive)
- Stale lock auto-expires

## Future Enhancements

### Planned Features

1. **Streaming STT**: Real-time transcription during recording
2. **Voice Cloning**: Custom voice training for TTS
3. **Multi-Language**: Auto-detection and translation
4. **Speaker Diarization**: Multi-party conversations
5. **Noise Cancellation**: Improved recording quality
6. **Mobile Support**: iOS/Android clients

### Integration Opportunities

1. **Third-Party Signal Control**: (See THIRD_PARTY_INTEGRATION.md)
2. **Custom VAD Engines**: Plugin architecture for VAD
3. **Audio Effects**: EQ, compression, normalization
4. **Voice Commands**: Wake word detection
5. **Conversation Memory**: Context across sessions

## Resources

### Documentation

- **Main Docs**: https://voice-mode.readthedocs.io
- **GitHub**: https://github.com/mbailey/voicemode
- **PyPI**: https://pypi.org/project/voice-mode/

### Related Projects

- **FastMCP**: https://github.com/jlowin/fastmcp
- **Whisper.cpp**: https://github.com/ggerganov/whisper.cpp
- **Kokoro**: https://github.com/remsky/Kokoro-FastAPI
- **WebRTC VAD**: https://github.com/wiseman/py-webrtcvad

### Community

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Twitter**: @getvoicemode
- **YouTube**: @getvoicemode

---

**Document Version**: 1.0
**Last Updated**: 2026-01-17
**Maintainer**: Mike Bailey (mike@failmode.com)
