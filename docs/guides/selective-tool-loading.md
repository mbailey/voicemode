# Selective Tool Loading

VoiceMode supports selective tool loading to reduce token usage in Claude Code and other MCP clients.

> **Technical Details**: For information about how the tool loading system works internally, see the [Tool Loading Architecture](../reference/tool-loading-architecture.md) documentation.

## Why Use Selective Loading?

By default, VoiceMode loads only essential tools (`converse`, `service`), which consumes approximately 7,000 tokens in your Claude Code context. If you need additional tools, you can enable them selectively. Loading all tools (~40+ tools) would consume approximately 25,000 tokens.

## Loading Modes

VoiceMode supports two modes for controlling which tools are loaded:

### Whitelist Mode (Most Efficient)
Use `VOICEMODE_TOOLS_ENABLED` to load only specific tools. This is the most efficient mode for reducing token usage.

```bash
# Load only converse tool (saves ~20k tokens)
export VOICEMODE_TOOLS_ENABLED=converse

# Load converse and service tools (recommended minimum)
export VOICEMODE_TOOLS_ENABLED=converse,service

# Load multiple tools
export VOICEMODE_TOOLS_ENABLED=converse,service,statistics
```

### Blacklist Mode
Use `VOICEMODE_TOOLS_DISABLED` to load all tools except specific ones. Useful when you want most tools but need to exclude a few.

```bash
# Load all tools except pronunciation
export VOICEMODE_TOOLS_DISABLED=pronunciation_add,pronunciation_remove,pronunciation_list

# Load all tools except service installation
export VOICEMODE_TOOLS_DISABLED=whisper_install,kokoro_install,livekit_install
```

## Configuration Methods

### Method 1: Environment Variable
```bash
export VOICEMODE_TOOLS_ENABLED=converse,service
claude  # Start Claude Code
```

### Method 2: .voicemode.env File (Recommended)
Create or edit `~/.voicemode/voicemode.env`:
```bash
# Whitelist mode - only load specified tools (most efficient)
VOICEMODE_TOOLS_ENABLED=converse,service

# Or blacklist mode - load all except specified
# VOICEMODE_TOOLS_DISABLED=pronunciation_add,pronunciation_remove
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
        "VOICEMODE_TOOLS_ENABLED": "converse,service"
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
export VOICEMODE_TOOLS_ENABLED=converse
```

### Recommended Minimum
Voice conversation plus service management:
```bash
export VOICEMODE_TOOLS_ENABLED=converse,service
```

### Voice with Statistics
To track conversation metrics:
```bash
export VOICEMODE_TOOLS_ENABLED=converse,service,statistics
```

### Full Development Setup
For development and debugging:
```bash
export VOICEMODE_TOOLS_ENABLED=converse,service,statistics,configuration_management,providers
```

### All Tools
To load all available tools:
```bash
export VOICEMODE_TOOLS_DISABLED=""
# Or use blacklist to exclude specific tools only
```

### Default Behavior
If no configuration is set, VoiceMode loads essential tools only (`converse`, `service`).

## Token Savings

| Configuration | Approximate Token Usage | Compared to All Tools |
|--------------|------------------------|---------|
| `converse,service` (default) | ~7,000 tokens | Saves ~18,000 tokens |
| `converse` only | ~5,000 tokens | Saves ~20,000 tokens |
| `converse,service,statistics` | ~9,000 tokens | Saves ~16,000 tokens |
| Core tools (5 tools) | ~12,000 tokens | Saves ~13,000 tokens |
| All tools | ~25,000 tokens | - |

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
os.environ['VOICEMODE_TOOLS_ENABLED'] = 'converse,service'
from voice_mode import tools
# Check loaded modules
import sys
loaded = [m for m in sys.modules if 'voice_mode.tools' in m]
print(loaded)
```

## Best Practices

1. **Start Minimal**: Begin with `converse,service` for essential functionality
2. **Production Use**: Use whitelist mode (`VOICEMODE_TOOLS_ENABLED`) to conserve tokens
3. **Development**: Load all tools during development, or use blacklist mode to exclude a few
4. **Documentation**: Document which tools your workflow requires

## Integration with Claude Code

When using Claude Code, the token savings from selective loading gives you more room for:
- Larger codebases
- More conversation history
- Additional MCP servers
- Custom agents and tools

The default configuration (`converse,service`) provides optimal Claude Code performance with minimal token usage.

## Legacy Variable

> **Note**: The `VOICEMODE_TOOLS` variable is deprecated and will be removed in v5.0. Please migrate to `VOICEMODE_TOOLS_ENABLED` or `VOICEMODE_TOOLS_DISABLED`.