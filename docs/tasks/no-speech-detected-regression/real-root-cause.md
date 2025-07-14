# Real Root Cause: MCP Instance Mismatch

## The Actual Bug

The regression was caused by the refactoring that moved the MCP instance from `server.py` to `mcp_instance.py`:

1. **Before (working)**:
   - All files imported `mcp` from `voice_mode.server`
   - Single MCP instance used everywhere

2. **After (broken)**:
   - Most files changed to import from `voice_mode.mcp_instance`
   - But when running the MCP server, it might be creating a different instance
   - Tools registered with one instance but called from another

## Why This Breaks

When the MCP server runs:
1. It loads `server.py` which creates its own imports
2. The tools are registered with the MCP instance
3. But when the converse tool is called through the MCP protocol, it might be using a different context
4. This causes the audio recording to fail in some way that results in "No speech detected"

## Evidence

1. Direct tests work fine (recording + STT both work)
2. Only fails when called through MCP tool interface
3. The main change in the broken commit was moving imports from `server` to `mcp_instance`

## The Fix

Ensure all files consistently use the same MCP instance. The refactoring to separate `mcp_instance.py` needs to be done carefully to avoid instance mismatches.