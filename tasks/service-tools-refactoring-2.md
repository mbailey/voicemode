# Service management refactoring - COMPLETED

## Summary

Successfully consolidated all service management tools into a unified approach:

### What was accomplished:

1. **Unified service tool** ✅
   - Created `service(service_name, action, lines)` tool that handles both whisper and kokoro
   - Actions: status, start, stop, restart, enable, disable, logs
   - Located at: `/voice_mode/tools/service.py`

2. **Service prompts created** ✅
   - `whisper` prompt - calls service tool with service_name='whisper'
   - `kokoro` prompt - calls service tool with service_name='kokoro'
   - Located at: `/voice_mode/prompts/services.py`

3. **Service files extracted** ✅
   - LaunchAgent plists and systemd unit files moved to `/voice_mode/resources/`
   - Added version tracking in `versions.json`
   - Templates use placeholders for dynamic values

4. **Configuration enhancements** ✅
   - Added `SERVICE_AUTO_ENABLE` config variable (defaults to False)
   - Install tools now support `auto_enable` parameter
   - Auto-enable behavior configurable via environment

5. **Cleanup completed** ✅
   - Removed individual service tool files (start/stop/status/enable/disable)
   - Updated install tools to support auto_enable
   - Created comprehensive test suite for unified service tool

### Key improvements:
- Single tool for all service operations
- Consistent interface across services
- Version tracking for service files
- Configurable auto-enable behavior
- Support for viewing logs
- Restart action added

### Original tasks:
- consolidate tools into one service tool ✅
- Create prompts ✅
- Provide access via cli ✅ (through MCP tools)
- plists should standalone files ✅
- systemd unit files should be their own files ✅
