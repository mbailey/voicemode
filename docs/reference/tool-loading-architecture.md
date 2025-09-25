# Tool Loading Architecture

VoiceMode discovers all available tools from the filesystem, applies include/exclude filters based on configuration, then dynamically loads the filtered list at startup.

## Overview

VoiceMode's tool loading system provides automatic discovery and dynamic import of tools from the filesystem. This architecture enables:
- Zero-configuration tool registration
- Service-specific tool organization
- Selective loading for token optimization
- Seamless MCP protocol integration

## Directory Structure

```
voice_mode/tools/
├── __init__.py                  # Discovery and loading logic
├── {tool_name}.py               # Regular tools (e.g. converse.py, devices.py)
├── services/                    # Service-specific tools
│   ├── {service}/               # Service directory (e.g. whisper/, kokoro/)
│   │   ├── {tool}.py           # Service tool modules (e.g. install.py, uninstall.py)
│   │   └── helpers.py          # Shared utilities (excluded)
│   └── ...
├── sound_fonts/                 # Feature-specific subdirectories
└── transcription/
```

### Naming Conventions

- **Regular tools**: `{tool_name}.py` → loaded as `{tool_name}` (e.g. `converse.py` → `converse`)
- **Service tools**: `services/{service}/{tool}.py` → loaded as `{service}_{tool}` (e.g. `services/whisper/install.py` → `whisper_install`)
- **Excluded patterns**: `__init__.py`, `_*.py`, `*_helpers.py`, `types.py`

## Discovery Mechanism

### File System Scanning

The `get_all_available_tools()` function in `voice_mode/tools/__init__.py` discovers tools by:

1. Scanning the tools directory for Python files
2. Recursively scanning the services subdirectory
3. Applying exclusion patterns
4. Flattening the namespace for MCP exposure

```python
def get_all_available_tools() -> list[str]:
    """Discover all available tools from the filesystem."""
    tools = []

    # Find regular tools (*.py in tools/)
    for file in tools_dir.glob("*.py"):
        if should_include_tool(file):
            tools.append(file.stem)

    # Find service tools (services/*/*.py)
    services_dir = tools_dir / "services"
    for service_dir in services_dir.iterdir():
        if service_dir.is_dir():
            for file in service_dir.glob("*.py"):
                if should_include_tool(file):
                    tools.append(f"{service_dir.name}_{file.stem}")

    return sorted(tools)
```

### Tool Filtering

Tools are excluded if they match:
- `__init__.py` - Package initialization files
- `_*.py` - Private modules (underscore prefix)
- `*_helpers.py` - Utility modules
- `types.py` - Type definition modules

## Loading Process

### Environment Variable Processing

Three environment variables control tool loading:

1. **`VOICEMODE_TOOLS_ENABLED`** (whitelist mode)
   - Comma-separated list of tools to load
   - Only listed tools are loaded
   - Highest priority

2. **`VOICEMODE_TOOLS_DISABLED`** (blacklist mode)
   - Comma-separated list of tools to exclude
   - All tools except listed are loaded
   - Medium priority

3. **`VOICEMODE_TOOLS`** (legacy, deprecated)
   - Backwards compatibility
   - Will be removed in v5.0

### Dynamic Import Mechanism

The `load_tool()` function handles the actual import:

```python
def load_tool(tool_name: str) -> bool:
    """Load a single tool by name."""
    try:
        # First, try as a regular tool (even with underscores)
        tool_file = tools_dir / f"{tool_name}.py"
        if tool_file.exists():
            importlib.import_module(f".{tool_name}", package=__name__)
            return True

        # If not found and contains underscore, try service pattern
        if "_" in tool_name:
            parts = tool_name.split("_", 1)
            if len(parts) == 2:
                service_name, tool_file = parts
                module_path = f".services.{service_name}.{tool_file}"
                importlib.import_module(module_path, package=__name__)
                return True

        return False
    except ImportError as e:
        logger.error(f"Failed to import tool {tool_name}: {e}")
        return False
```

### Loading Order

1. Check for regular tool file first
2. If not found and name contains underscore, try service pattern
3. This prevents misinterpretation of tools like `configuration_management`

## Integration with FastMCP

### Server Initialization

In `voice_mode/server.py`:

```python
# Tools are auto-imported from the tools directory
import voice_mode.tools

# FastMCP server automatically discovers decorated tools
mcp = fastmcp.FastMCP(
    name="voicemode",
    version=__version__
)
```

### Tool Registration

Tools use FastMCP decorators for automatic registration:

```python
@mcp.tool
async def converse(message: str, wait_for_response: bool = True):
    """Voice conversation tool."""
    ...
```

No explicit registration needed - tools are discovered at import time.

## Service Tools Pattern

### Structure

Service tools are organized by service:

```
services/
├── whisper/
│   ├── install.py       # whisper_install
│   ├── uninstall.py     # whisper_uninstall
│   ├── model_active.py  # whisper_model_active
│   └── helpers.py       # Shared utilities (not loaded)
├── kokoro/
│   ├── install.py       # kokoro_install
│   └── uninstall.py     # kokoro_uninstall
└── livekit/
    ├── install.py       # livekit_install
    └── frontend.py      # livekit_frontend
```

### Naming Convention

Service tools follow the pattern `{service}_{action}`:
- `whisper_install` - Install Whisper service
- `kokoro_status` - Check Kokoro service status
- `livekit_frontend` - Manage LiveKit frontend

## Performance Considerations

### Token Usage

- Full tool loading: ~25,000 tokens in Claude Code context
- Selective loading (converse only): ~5,000 tokens
- 20,000 token savings with selective loading

### Memory Footprint

- Tools are imported on startup
- Lazy loading not currently implemented
- Import-time side effects should be avoided

## Error Handling

### Missing Tools

When a tool cannot be loaded:
1. Warning logged to stderr
2. Tool excluded from MCP exposure
3. Server continues with available tools

### Import Failures

```python
try:
    importlib.import_module(module_path, package=__name__)
except ImportError as e:
    logger.error(f"Failed to import tool {tool_name}: {e}")
    # Tool is skipped, not fatal
```

## Extension Guidelines

### Adding New Regular Tools

1. Create `voice_mode/tools/{tool_name}.py`
2. Implement tool function with FastMCP decorator
3. Tool automatically discovered on next server start

### Creating Service Tools

1. Create directory: `voice_mode/tools/services/{service}/`
2. Add tool modules: `install.py`, `uninstall.py`, etc.
3. Tools exposed as `{service}_{tool}`
4. Place shared code in `helpers.py` (excluded from loading)

## Best Practices

1. **Tool Organization**
   - Group related tools in service directories
   - Use clear, descriptive names
   - Keep tools focused on single responsibilities

2. **Dependencies**
   - Avoid heavy imports at module level
   - Use lazy imports where possible
   - Handle missing dependencies gracefully

3. **Documentation**
   - Include docstrings for MCP description
   - Document parameters clearly
   - Provide usage examples

## Implementation Details

### Key Files

- `voice_mode/tools/__init__.py` - Discovery and loading logic
- `voice_mode/server.py` - MCP server initialization
- Individual tool modules - Tool implementations

### Configuration Flow

1. Server startup
2. Environment variables checked
3. Tool list determined
4. Tools dynamically imported
5. FastMCP registers decorated functions
6. Server exposes tools via MCP protocol

## Debugging

### Verification

Check loaded tools:
```bash
# List all available tools
voicemode list-tools

# Check specific tool loading
VOICEMODE_DEBUG=1 voicemode
```

### Logging

Enable debug logging to see tool loading details:
```bash
export VOICEMODE_DEBUG=1
```

Log output shows:
- Tools discovered
- Tools being loaded
- Import failures
- Final loaded tool list

## Common Issues

### Tool Not Loading

1. Check file name matches expected pattern
2. Verify no syntax errors in tool module
3. Check tool not in exclusion patterns
4. Review debug logs for import errors

### Service Tool Conflicts

If a regular tool has an underscore in its name:
- It's checked as a regular tool first
- Only falls back to service pattern if not found
- This prevents misinterpretation

## Migration from VOICEMODE_TOOLS

The legacy `VOICEMODE_TOOLS` variable is deprecated:
- Still functional for backwards compatibility
- Will be removed in v5.0
- Migrate to `VOICEMODE_TOOLS_ENABLED` or `VOICEMODE_TOOLS_DISABLED`

Migration example:
```bash
# Old (deprecated)
export VOICEMODE_TOOLS=converse,statistics

# New (preferred)
export VOICEMODE_TOOLS_ENABLED=converse,statistics
```