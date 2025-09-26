# Selective Tool Loading

VoiceMode supports selective tool loading to reduce token usage in Claude Code and other MCP clients.

> **Technical Details**: For information about how the tool loading system works internally, see the [Tool Loading Architecture](../reference/tool-loading-architecture.md) documentation.

## Why Use Selective Loading?

By default, VoiceMode loads all available tools (~40+ tools), which consumes approximately 25,000 tokens in your Claude Code context. If you only need voice conversation features, you can load just the `converse` tool and save ~20,000 tokens.

## How to Enable

Set the `VOICEMODE_TOOLS` environment variable to a comma-separated list of tools you want to load:

```bash
# Load only the converse tool (saves ~20k tokens)
export VOICEMODE_TOOLS=converse

# Load converse and statistics tools
export VOICEMODE_TOOLS=converse,statistics

# Load converse and configuration tools
export VOICEMODE_TOOLS=converse,configuration_management
```

## Configuration Methods

### Method 1: Environment Variable
```bash
export VOICEMODE_TOOLS=converse
claude  # Start Claude Code
```

### Method 2: .voicemode.env File
Create or edit `~/.voicemode/voicemode.env`:
```bash
VOICEMODE_TOOLS=converse
```

### Method 3: .mcp.json Configuration
Edit your `.mcp.json` file:
```json
{
  "mcpServers": {
    "voicemode": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "voicemode"],
      "env": {
        "VOICEMODE_TOOLS": "converse"
      }
    }
  }
}
```

## Available Tools

### Core Tools
- `converse` - Main voice conversation tool (includes TTS and STT)
- `statistics` - Voice conversation statistics and dashboard
- `configuration_management` - Configuration file management
- `providers` - Voice provider management
- `devices` - Audio device detection and management

### Service Management Tools
- `service` - Unified service management
- `whisper_install` - Whisper installation
- `kokoro_install` - Kokoro TTS installation
- `livekit_*` - LiveKit-related tools

### Utility Tools
- `claude_thinking` - Claude thinking mode tools
- `pronounce` - Pronunciation customization
- `dependencies` - Dependency checking
- `diagnostics` - System diagnostics
- `voice_registry` - Voice registry management

## Examples

### Minimal Setup (Voice Only)
For basic voice conversations with minimal token usage:
```bash
export VOICEMODE_TOOLS=converse
```

### Voice with Statistics
To track conversation metrics:
```bash
export VOICEMODE_TOOLS=converse,statistics
```

### Full Development Setup
For development and debugging:
```bash
export VOICEMODE_TOOLS=converse,statistics,configuration_management,providers,service
```

### All Tools (Default)
To load all tools (or unset the variable):
```bash
unset VOICEMODE_TOOLS
# or
export VOICEMODE_TOOLS=""
```

## Token Savings

| Configuration | Approximate Token Usage | Savings |
|--------------|------------------------|---------|
| All tools (default) | ~25,000 tokens | - |
| `converse` only | ~5,000 tokens | ~20,000 tokens |
| `converse,statistics` | ~8,000 tokens | ~17,000 tokens |
| Core tools (5 tools) | ~12,000 tokens | ~13,000 tokens |

## Troubleshooting

### Tools Not Loading
If a tool isn't loading when specified:
1. Check the tool name is spelled correctly
2. Check logs for warnings about missing tools
3. Ensure the tool file exists in `voice_mode/tools/`

### Unexpected Tools Loading
Some tools may load additional dependencies. For example:
- `converse` loads audio processing utilities
- Service tools may load helper modules

### Verifying Loaded Tools
Check which tools are loaded:
```python
import os
os.environ['VOICEMODE_TOOLS'] = 'converse'
from voice_mode import tools
# Check loaded modules
import sys
loaded = [m for m in sys.modules if 'voice_mode.tools' in m]
print(loaded)
```

## Best Practices

1. **Start Minimal**: Begin with just `converse` and add tools as needed
2. **Production Use**: Use selective loading in production to conserve tokens
3. **Development**: Load all tools during development for full functionality
4. **Documentation**: Document which tools your workflow requires

## Integration with Claude Code

When using Claude Code, the token savings from selective loading gives you more room for:
- Larger codebases
- More conversation history
- Additional MCP servers
- Custom agents and tools

Set `VOICEMODE_TOOLS=converse` in your `.mcp.json` for optimal Claude Code performance.