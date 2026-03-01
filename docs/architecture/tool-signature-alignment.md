# Tool Signature Alignment: VoiceMode Local vs VoiceMode Connect

**Date**: 2026-02-16
**Source**: Voice conversation between Mike and Wimo
**Status**: Proposed

## Goal

Align the tool names and function signatures between VoiceMode (local MCP) and VoiceMode Connect (cloud MCP) so that:

1. A wake/call message to an agent can simply say "use `converse` to speak with Mike" and it works regardless of which MCP server handles the call
2. The agent doesn't need to know whether it's using local audio or remote WebSocket transport — same interface, different transport

## Current State

### VoiceMode Local (`voice_mode/tools/`)
Default tools exposed:
- `converse(message, wait_for_response, voice, ...)` — TTS + STT via local mic/speakers
- `service(service_name, action, lines)` — manage Whisper/Kokoro services

Additional tools:
- `register_wakeable(team_name, agent_name, agent_platform)` — register as wakeable via Connect
- Various admin tools (devices, providers, diagnostics, etc.)

### VoiceMode Connect (`mcp__claude_ai_voicemode-connect__*`)
- `converse(message, wait_for_response, voice, speed, ...)` — TTS + STT via remote web/mobile client
- `status(include_voices)` — list connected devices

## Proposed Direction

Review both `converse` signatures and align them so that:
- Core parameters match (message, wait_for_response, voice, speed)
- The wake/call message sent from the dashboard can just say "use converse to speak with [user]" without specifying which MCP server
- Either server can handle the call transparently
- Consider adding optional `device` parameter to local converse to route through WebSocket when a Connect device is available

## Questions to Resolve

1. Should local `converse` gain a `device` parameter that routes through Connect's WebSocket?
2. Or should the message just work with whichever `converse` tool the agent has available?
3. How do we handle the case where an agent has both local VoiceMode and VoiceMode Connect installed?
4. Should `status` be unified to show both local and remote devices?

## Context

This emerged from discussing how the dashboard "call" button should work. Instead of a special "wake" message type, the call button sends a regular message telling the agent to use `converse` to respond. If the tool signatures are aligned, the message works regardless of which MCP server the agent has.
