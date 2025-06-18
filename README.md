# voice-mcp - Voice Mode for Claude Code

A Model Context Protocol (MCP) server that enables voice interactions with Claude and other LLMs. Requires only an OpenAI API key and microphone/speakers.

## 🖥️ Compatibility

**Runs on:** Linux • macOS • Windows (WSL) | **Python:** 3.10+ | **Tested:** Ubuntu 24.04 LTS, Fedora 42

## ✨ Features

- **🎙️ Voice conversations** with Claude - ask questions and hear responses
- **🔄 Multiple transports** - local microphone or LiveKit room-based communication  
- **🗣️ OpenAI-compatible** - works with any STT/TTS service (local or cloud)
- **⚡ Real-time** - low-latency voice interactions with automatic transport selection
- **🔧 MCP Integration** - seamless with Claude Desktop and other MCP clients

## 🎯 Simple Requirements

**All you need to get started:**

1. **🔑 OpenAI API Key** (or compatible service) - for speech-to-text and text-to-speech
2. **🎤 Computer with microphone and speakers** OR **☁️ LiveKit server** ([LiveKit Cloud](https://docs.livekit.io/home/cloud/) or [self-hosted](https://github.com/livekit/livekit))

## Quick Start

Setup for Claude Code:

```bash
export OPENAI_API_KEY=your-openai-key
claude mcp add voice-mcp uvx voice-mcp
claude
```

Try: *"Let's have a voice conversation"*

## 🎬 Demo

Watch voice-mcp in action:

[![voice-mcp Demo](https://img.youtube.com/vi/aXRNWvpnwVs/maxresdefault.jpg)](https://www.youtube.com/watch?v=aXRNWvpnwVs)

## Example Usage

Once configured, try these prompts with Claude:

- `"Let's have a voice conversation"`
- `"Ask me about my day using voice"`
- `"Tell me a joke"` (Claude will speak and wait for your response)
- `"Say goodbye"` (Claude will speak without waiting)

The new `converse` function makes voice interactions more natural - it automatically waits for your response by default.

## Claude Desktop Setup

Add to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

<details>
<summary>Using uvx (recommended)</summary>

```json
{
  "mcpServers": {
    "voice-mcp": {
      "command": "uvx",
      "args": ["voice-mcp"],
      "env": {
        "OPENAI_API_KEY": "your-openai-key"
      }
    }
  }
}
```

</details>

<details>
<summary>Using pip install</summary>

```json
{
  "mcpServers": {
    "voice-mcp": {
      "command": "voice-mcp",
      "env": {
        "OPENAI_API_KEY": "your-openai-key"
      }
    }
  }
}
```

</details>

## Tools

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `converse` | Have a voice conversation - speak and optionally listen | `message`, `wait_for_response` (default: true), `listen_duration` (default: 10s), `transport` (auto/local/livekit) |
| `listen_for_speech` | Listen for speech and convert to text | `duration` (default: 5s) |
| `check_room_status` | Check LiveKit room status and participants | None |
| `check_audio_devices` | List available audio input/output devices | None |
| `start_kokoro` | Start the Kokoro TTS service | `models_dir` (optional, defaults to ~/Models/kokoro) |
| `stop_kokoro` | Stop the Kokoro TTS service | None |
| `kokoro_status` | Check the status of Kokoro TTS service | None |

**Note:** The `converse` tool is the primary interface for voice interactions, combining speaking and listening in a natural flow.

## Configuration

**📖 See [docs/configuration.md](docs/configuration.md) for complete setup instructions for all MCP hosts**

**📁 Ready-to-use config files in [config-examples/](config-examples/)**

### Quick Setup

The only required configuration is your OpenAI API key:

```bash
export OPENAI_API_KEY="your-key"
```

### Optional Settings

```bash
# Custom STT/TTS services (OpenAI-compatible)
export STT_BASE_URL="http://localhost:2022/v1"  # Local Whisper
export TTS_BASE_URL="http://localhost:8880/v1"  # Local TTS
export TTS_VOICE="alloy"                        # Voice selection

# LiveKit (for room-based communication)
# See docs/livekit/ for setup guide
export LIVEKIT_URL="wss://your-app.livekit.cloud"
export LIVEKIT_API_KEY="your-api-key"
export LIVEKIT_API_SECRET="your-api-secret"

# Debug mode
export VOICE_MCP_DEBUG="true"

# Save all audio (TTS output and STT input)
export VOICE_MCP_SAVE_AUDIO="true"

# Microphone settings
export VOICE_MCP_MICROPHONE_CHIMES="true"  # Enable/disable recording chimes (default: true)
```

## Local STT/TTS Services

For privacy-focused or offline usage, voice-mcp supports local speech services:

- **[Whisper.cpp](docs/whisper.cpp.md)** - Local speech-to-text with OpenAI-compatible API
- **[Kokoro](docs/kokoro.md)** - Local text-to-speech with multiple voice options

These services provide the same API interface as OpenAI, allowing seamless switching between cloud and local processing.

### OpenAI API Compatibility Benefits

By strictly adhering to OpenAI's API standard, voice-mcp enables powerful deployment flexibility:

- **🔀 Transparent Routing**: Users can implement their own API proxies or gateways outside of voice-mcp to route requests to different providers based on custom logic (cost, latency, availability, etc.)
- **🎯 Model Selection**: Deploy routing layers that select optimal models per request without modifying voice-mcp configuration
- **💰 Cost Optimization**: Build intelligent routers that balance between expensive cloud APIs and free local models
- **🔧 No Lock-in**: Switch providers by simply changing the `BASE_URL` - no code changes required

Example: Simply set `OPENAI_BASE_URL` to point to your custom router:
```bash
export OPENAI_BASE_URL="https://router.example.com/v1"
export OPENAI_API_KEY="your-key"
# voice-mcp now uses your router for all OpenAI API calls
```

The OpenAI SDK handles this automatically - no voice-mcp configuration needed!

## Architecture

```
┌─────────────────────┐     ┌──────────────────┐     ┌─────────────────────┐
│   Claude/LLM        │     │  LiveKit Server  │     │  Voice Frontend     │
│   (MCP Client)      │◄────►│  (Optional)     │◄───►│  (Optional)         │
└─────────────────────┘     └──────────────────┘     └─────────────────────┘
         │                            │
         │                            │
         ▼                            ▼
┌─────────────────────┐     ┌──────────────────┐
│  Voice MCP Server   │     │   Audio Services │
│  • converse         │     │  • OpenAI APIs   │
│  • listen_for_speech│◄───►│  • Local Whisper │
│  • check_room_status│     │  • Local TTS     │
│  • check_audio_devices    └──────────────────┘
└─────────────────────┘
```

## Troubleshooting

### Common Issues

- **No microphone access**: Check system permissions for terminal/application
- **UV not found**: Install with `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **OpenAI API error**: Verify your `OPENAI_API_KEY` is set correctly
- **No audio output**: Check system audio settings and available devices

### Debug Mode

Enable detailed logging and audio file saving:

```bash
export VOICE_MCP_DEBUG=true
```

Debug audio files are saved to: `~/voice-mcp_recordings/`

### Audio Saving

To save all audio files (both TTS output and STT input):

```bash
export VOICE_MCP_SAVE_AUDIO=true
```

Audio files are saved to: `~/voice-mcp_audio/` with timestamps in the filename.

## License

MIT
