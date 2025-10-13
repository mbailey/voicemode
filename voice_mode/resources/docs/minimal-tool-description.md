# Minimal Tool Description

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
• wait_for_response (bool, default: true): Listen for response after speaking
• listen_duration (number, default: 120): Max listen time in seconds
• min_listen_duration (number, default: 2.0): Min recording time before silence detection
• voice (string): TTS voice name (auto-selected unless specified)
• tts_provider ("openai"|"kokoro"): Provider selection (auto-selected unless specified)
• disable_silence_detection (bool, default: false): Disable auto-stop on silence
• vad_aggressiveness (0-3, default: 2): Voice detection strictness (0=permissive, 3=strict)
• speed (0.25-4.0): Speech rate (1.0=normal, 2.0=double speed)

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
