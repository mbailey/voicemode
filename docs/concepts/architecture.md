# VoiceMode Architecture

Understanding how VoiceMode components work together to enable voice conversations.

## System Overview

VoiceMode is built as a Model Context Protocol (MCP) server that provides voice capabilities to AI assistants. It follows a modular architecture with clear separation between voice services, audio processing, and client interfaces.

```
┌─────────────────────────────────────────────┐
│             MCP Client (Claude)             │
└─────────────────┬───────────────────────────┘
                  │ MCP Protocol
┌─────────────────┴───────────────────────────┐
│           VoiceMode MCP Server              │
├──────────────────────────────────────────────┤
│              Core Components                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  Tools   │  │ Providers│  │  Config  │  │
│  └──────────┘  └──────────┘  └──────────┘  │
├──────────────────────────────────────────────┤
│            Voice Services                    │
│  ┌──────────────────┐  ┌──────────────────┐  │
│  │     Whisper      │  │      Kokoro      │  │
│  │      (STT)       │  │       (TTS)      │  │
│  └──────────────────┘  └──────────────────┘  │
└──────────────────────────────────────────────┘
```

## Core Components

### MCP Server

The FastMCP-based server (`server.py`) is the entry point that:
- Exposes tools, resources, and prompts via MCP protocol
- Handles stdio transport for communication
- Manages service lifecycle and health checks
- Auto-imports all tools from the tools directory

### Tools System

Tools are the primary interface for voice interactions:

**converse**: Main voice conversation tool
- Handles audio recording and playback
- Manages TTS/STT service selection
- Implements silence detection and VAD
- Uses local microphone for audio capture

**Service tools**: Installation and management
- `whisper_install`, `kokoro_install`
- Service start/stop/status operations
- Model and configuration management

### Provider System

The provider system (`providers.py`) implements service discovery and failover:

1. **Discovery**: Automatically finds running services
2. **Health Checks**: Validates service availability
3. **Failover**: Falls back to alternative services
4. **Load Balancing**: Distributes requests across providers

Provider selection priority:
1. User-specified URL (environment variable)
2. Local services (auto-discovered)
3. Cloud services (OpenAI)

### Configuration Layer

Multi-layered configuration system (`config.py`):

1. **Environment Variables**: Highest priority
2. **Project Config**: `.voicemode.env` in working directory
3. **User Config**: `~/.voicemode/voicemode.env`
4. **Defaults**: Built-in sensible defaults

## Voice Services

### Whisper (Speech-to-Text)

Local STT service using OpenAI's Whisper model:
- Runs on port 2022 by default
- Provides OpenAI-compatible API
- Supports multiple model sizes
- Hardware acceleration (Metal, CUDA)

### Kokoro (Text-to-Speech)

Local TTS service with natural voices:
- Runs on port 8880 by default
- OpenAI-compatible API
- Multiple languages and voices
- Efficient caching system

## Audio Pipeline

### Recording Flow

```
Microphone → Audio Capture → VAD → Silence Detection → STT Service → Text
```

1. **Audio Capture**: PyAudio for microphone input
2. **VAD**: WebRTC VAD filters non-speech
3. **Silence Detection**: Determines recording end
4. **STT Processing**: Converts audio to text

### Playback Flow

```
Text → TTS Service → Audio Stream → Format Conversion → Speaker
```

1. **TTS Generation**: Creates audio from text
2. **Streaming**: Chunks for real-time playback
3. **Format Conversion**: FFmpeg handles formats
4. **Playback**: PyAudio for speaker output

### Barge-In (TTS Interruption)

Barge-in enables natural conversation by allowing users to interrupt TTS playback:

```
TTS Playing ──┬── BargeInMonitor ──→ Voice Detected ──→ Interrupt Player
              │         │                                      │
              │   (VAD Analysis)                         (Stop Playback)
              │         │                                      │
              └─────────┴──── Captured Audio ──→ STT ──→ Response
```

**Components:**

1. **BargeInMonitor** (`barge_in.py`): Monitors microphone during TTS
   - Uses WebRTC VAD for speech detection
   - Captures audio buffer from voice onset
   - Fires interrupt callback when speech threshold met

2. **NonBlockingAudioPlayer**: Extended with interrupt support
   - `interrupt()` method stops playback immediately
   - `was_interrupted()` indicates barge-in occurred
   - Clean resource shutdown on interrupt

3. **Conversation Flow Integration**:
   - Monitor starts when TTS playback begins
   - On voice detection: TTS stops, captured audio flows to STT
   - Listening chime skipped (user already speaking)
   - Normal conversation continues with interrupted speech

**Configuration:**
- `VOICEMODE_BARGE_IN=true` enables the feature
- `VOICEMODE_BARGE_IN_VAD` controls detection sensitivity (0-3)
- `VOICEMODE_BARGE_IN_MIN_MS` sets minimum speech duration threshold

**Performance Target:** <100ms from voice onset to TTS stop

### Barge-In Performance Characteristics

Measured performance characteristics from automated testing:

| Metric | Average | Max | Target |
|--------|---------|-----|--------|
| Interrupt callback latency | <5ms | <10ms | <50ms |
| Voice onset to TTS stop | <20ms | <50ms | <100ms |
| VAD check per chunk | <5ms | <20ms | - |
| Buffer append operation | <1ms | <10ms | - |
| Cross-thread interrupt latency | <20ms | <50ms | - |

**Latency Breakdown:**

The total latency from when the user starts speaking to when TTS stops consists of:

1. **VAD Processing** (~10-20ms): WebRTC VAD analyzes 20ms audio chunks
2. **Speech Threshold** (configurable, default 150ms): Minimum speech duration to confirm intentional interruption
3. **Callback Invocation** (<5ms): Signaling from monitor to player
4. **Player Stop** (<5ms): Stopping audio output stream

Note: The 150ms speech threshold is intentional to prevent false positives and is not considered system latency. Actual system latency (from confirmed speech detection to TTS stop) is typically under 50ms.

**CPU Overhead:**

- BargeInMonitor objects are lightweight (~1KB memory footprint)
- VAD checking runs at ~50+ checks per second without bottleneck
- Audio buffer operations are O(1) with lock protection
- Background thread has minimal impact during idle periods

**Memory Usage:**

- Audio buffer grows linearly with captured speech duration
- 5 seconds of captured audio at 24kHz, 16-bit: ~240KB
- Buffers are cleared on silence (when barge-in hasn't triggered)
- Memory is released when monitor is stopped

**Thread Safety:**

- All buffer operations protected by threading.Lock
- Events use threading.Event for signal coordination
- Callback invocation is thread-safe across monitoring and playback threads

## Service Architecture

### Service Lifecycle

1. **Installation**: Download binaries, create configs
2. **Registration**: systemd/launchd service files
3. **Startup**: Health checks, port binding
4. **Discovery**: Auto-detection by VoiceMode
5. **Monitoring**: Status checks, log rotation

### Service Communication

All services expose OpenAI-compatible APIs:
- Unified interface for TTS/STT
- Standard authentication (API keys)
- Consistent error handling
- Format negotiation

## Audio Transport

### Local Microphone

Direct microphone/speaker access using PyAudio:
- Low latency audio I/O
- No network overhead
- Privacy-focused (all processing local)
- WebRTC VAD for voice activity detection

## Security Model

### API Key Management

- Never stored in code
- Environment variable priority
- Secure MCP transport
- Optional local-only mode

### Audio Privacy

- Local processing option
- No cloud storage
- User-controlled recording

## Performance Optimization

### Caching Strategy

- Model caching (Whisper/Kokoro)
- Audio format caching
- Provider health caching
- Configuration caching

### Resource Management

- Lazy service loading
- Connection pooling
- Memory limits (systemd)
- CPU throttling

## Error Handling

### Graceful Degradation

1. Primary service fails
2. Attempt fallback service
3. Use cloud service if available
4. Return informative error

### Recovery Mechanisms

- Automatic service restart
- Connection retry logic
- Circuit breaker pattern
- Health check recovery

## Extension Points

### Adding New Tools

1. Create tool in `tools/` directory
2. Implement with FastMCP decorators
3. Auto-imported by server
4. Available via MCP

### Custom Providers

1. Implement provider interface
2. Add discovery logic
3. Register in provider system
4. Configure endpoints

### Service Integration

1. Create service installer
2. Add systemd/launchd templates
3. Implement health checks
4. Update CLI commands

## Deployment Patterns

### Development

- Local services
- Debug logging
- Hot reload
- Mock providers

### Production

- Service supervision
- Log rotation
- Health monitoring
- Failover configuration

### Containerized

- Docker compose setup
- Service orchestration
- Volume management
- Network isolation

## Future Architecture

### Planned Enhancements

- Plugin system for tools
- Webhook support
- Multi-language support
- GPU cluster support

### Scalability Path

- Distributed services
- Queue-based processing
- Caching layers
- Load balancing