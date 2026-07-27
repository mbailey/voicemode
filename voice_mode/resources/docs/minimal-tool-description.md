# Minimal Tool Description

> **Dated design record.** Kept for provenance of the resource-based tool
> description, not as a parameter reference. The authoritative parameter
> documentation is [`parameters.md`](parameters.md) in this directory (served as
> `voicemode://docs/parameters`); the parameter list that used to be spelled out
> in the sketch below was a third hand-maintained copy of it, under names the
> tool no longer has — collapsed to a pointer under VM-2099, which is what this
> document argues for in the first place.

This is the proposed minimal description for the `mcp__voicemode__converse` tool.

**Target:** ~200-300 tokens (down from ~4000 tokens)

---

```
Have an ongoing voice conversation - speak a message and optionally listen for response.

🔌 ENDPOINT: STT/TTS services must expose OpenAI-compatible endpoints:
   /v1/audio/transcriptions and /v1/audio/speech

📚 DOCUMENTATION: See MCP resources for detailed information:
   - voicemode-quickstart: Basic usage and common examples
   - voicemode-parameters: Complete parameter reference
   - voicemode-languages: Non-English language support guide
   - voicemode-patterns: Best practices and conversation patterns
   - voicemode-troubleshooting: Audio, VAD, and connectivity issues

KEY PARAMETERS:
• message (required): The message to speak
• Everything else is optional — listening window, voice, provider, silence
  detection, speech rate. Each is described, with its default expressed as the
  config setting that owns it, in the voicemode-parameters resource. Defaults
  belong to the user's configuration; leave a parameter unset unless you have a
  present, articulable need for it.

PRIVACY: Microphone access required when wait_for_response=true.
         Audio processed via STT service, not stored.

For complete parameter list, advanced options, and detailed examples,
consult the MCP resources listed above.
```

---

## Token Savings

- **Original description:** ~4000 tokens
- **Current description:** ~1000 tokens
- **Proposed minimal:** ~200-300 tokens
- **Total savings:** ~3700 tokens (92.5% reduction)

## Resource Token Costs

When LLM sees resource listing in context:
- Each resource name/URI: ~10-20 tokens
- Total for 5 resources: ~50-100 tokens
- Only fetched when needed

## Net Savings

- Without fetching resources: ~3600 tokens saved
- Fetching 1 resource: ~3300 tokens saved (typical case)
- Fetching all 5 resources: ~1500 tokens saved (rare case)

Most interactions will save 3500+ tokens.
