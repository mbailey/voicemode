# Voicemode Resource Structure Plan

## Goal
Reduce the `mcp__voicemode__converse` tool description from ~4000 tokens to ~1000 tokens by moving detailed documentation into MCP resources that can be fetched on-demand.

## Current State
- Tool description: ~4000 tokens
- After initial reduction: ~1000 tokens
- Includes extensive examples, patterns, and parameter documentation

## Target State
- Tool description: ~200-300 tokens (minimal)
- Detailed docs: Separate MCP resources (~50-100 tokens per resource in listing)
- LLM fetches resources only when needed

## Proposed Tool Description

The minimal tool description should include:

```
Have an ongoing voice conversation - speak a message and optionally listen for response.

See MCP resources for detailed documentation:
- voicemode-quickstart: Basic usage examples
- voicemode-parameters: Detailed parameter explanations
- voicemode-languages: Non-English language support
- voicemode-patterns: Best practices and conversation patterns
- voicemode-troubleshooting: Audio, VAD, and connectivity issues

Key parameters:
- message (required): The message to speak
- wait_for_response: Listen for response after speaking (default: true)
- listen_duration: Max listen time in seconds (default: 120)
- voice: TTS voice name (auto-selected unless specified)
- tts_provider: openai or kokoro (auto-selected unless specified)
- disable_silence_detection: Disable auto-stop on silence (default: false)

For full parameter list and advanced options, see voicemode-parameters resource.
```

## Resource Structure

This directory mirrors the proposed MCP resource structure:

- `quickstart.md` - Basic usage and common patterns
- `parameters.md` - Complete parameter reference with descriptions
- `languages.md` - Non-English language support guide
- `patterns.md` - Advanced patterns (parallel operations, etc.)
- `troubleshooting.md` - Common issues and solutions

## Benefits

1. **Token Efficiency**: Only load documentation when needed
2. **Better Organization**: Separate concerns into logical chunks
3. **Easier Maintenance**: Update docs without changing tool definition
4. **Scalability**: Can add more resources without bloating tool context
5. **Smart Discovery**: Resource names in listing help LLM find what it needs

## Implementation Notes

- Resource names should be self-explanatory
- Resource URIs should follow pattern: `voicemode://docs/{resource-name}`
- Tool description should hint at resource availability
- LLM will see resource list in context and fetch as needed
