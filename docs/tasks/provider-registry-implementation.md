# Provider Registry Implementation Notes

## What We Built (MVP)

### 1. Provider Registry Module (`voice_mcp/providers.py`)
- Basic provider metadata storage
- Provider availability checking
- Provider selection logic with preferences
- Display formatting for status

### 2. Provider Structure
```python
{
    "id": "kokoro",
    "name": "Kokoro TTS",
    "type": "tts",  # or "stt"
    "base_url": "http://localhost:8880/v1",
    "local": True,
    "auto_start": True,
    "features": ["local", "free", "fast"],
    "default_voice": "af_sky",
    "voices": ["af_sky", "af_sarah", ...],
    "models": ["tts-1"]
}
```

### 3. Key Functions
- `is_provider_available()` - Health check with fallback strategies
- `get_tts_provider()` - Select best TTS provider based on requirements
- `get_stt_provider()` - Select best STT provider
- `get_provider_by_voice()` - Auto-detect provider from voice name

### 4. Integration Points
- Updated `get_tts_config()` to use provider registry
- Enhanced `voice_status()` to show provider information
- Maintained backward compatibility with env vars

## Design Decisions

1. **Minimal MVP**: Started with basic metadata, not full cost/latency tracking
2. **OpenAI Compatibility**: All providers use OpenAI-compatible endpoints
3. **Fallback Logic**: Try multiple endpoints for health checks
4. **Local First**: Default preference for local providers

## Next Steps

1. Add cost metadata and tracking
2. Implement provider preference system
3. Add more providers (Groq, Deepgram, etc.)
4. Build provider switching UI/commands
5. Add latency measurements

## Lessons Learned

- Health check endpoints vary between services
- OpenAI compatibility simplifies integration
- Provider registry enables future enhancements without breaking changes