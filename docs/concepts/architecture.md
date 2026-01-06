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