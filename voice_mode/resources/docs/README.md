# Voicemode Resource Structure Plan

> **Dated design record.** This is the plan that produced the
> `voicemode://docs/*` resources; it is kept for provenance, not as a parameter
> reference. The authoritative parameter documentation is
> [`parameters.md`](parameters.md) in this directory (served as
> `voicemode://docs/parameters`). The parameter sketches that used to sit inline
> below were a third hand-maintained copy of it and had drifted to names the tool
> no longer has — collapsed to pointers under VM-2099.

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

Key parameters: message (required) plus the optional listening, voice and
audio settings — each one described, with its default expressed as the config
key that owns it, in the voicemode-parameters resource.

For the full parameter list and advanced options, see voicemode-parameters resource.
```

*(The sketch above deliberately names no parameter defaults: this document is a
plan for the tool description, and every default it once spelled out was a copy
of [`parameters.md`](parameters.md) that stopped matching it.)*

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
