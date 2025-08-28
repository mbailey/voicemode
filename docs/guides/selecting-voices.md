# Selecting Voices

Voice Mode supports multiple TTS providers with different voices. This guide helps you choose and configure voices for the best experience.

## Available Voices

### OpenAI Voices
- **alloy** - Balanced, neutral voice (default)
- **nova** - Warm, expressive female voice
- **shimmer** - Bright, energetic female voice
- **fable** - Calm, storytelling voice
- **echo** - Clear, professional voice
- **onyx** - Deep, authoritative male voice

### Kokoro Voices (Local TTS)
- **af_sky** - Natural female voice
- **af_sarah** - Alternative female voice
- **am_adam** - Natural male voice
- **af_nicole** - Additional female option
- **am_michael** - Additional male option

## Voice Selection Strategy

Voice Mode uses a **voice-first selection algorithm**:

1. **Try each preferred voice** in order from `VOICEMODE_VOICES`
2. **Find first healthy endpoint** that supports that voice
3. **Use that voice and endpoint** for TTS

This ensures you get your preferred voice when possible, regardless of which provider supports it.

## Configuring Voice Preferences

### Quick Setup
Add to your `.voicemode.env`:
```bash
# Try Kokoro first, fallback to OpenAI
VOICEMODE_VOICES=af_sky,nova,alloy
```

### Voice-First Examples

**Prefer expressive female voices:**
```bash
VOICEMODE_VOICES=shimmer,nova,af_sky
```

**Prefer male voices:**
```bash
VOICEMODE_VOICES=am_adam,onyx,echo
```

**Local-first setup:**
```bash
VOICEMODE_VOICES=af_sky,am_adam,nova
```

**Cloud-first setup:**
```bash
VOICEMODE_VOICES=nova,shimmer,af_sky
```

## Voice Selection Examples

### Creative Writing Project
**`.voicemode.env`:**
```bash
# Use expressive voices for storytelling
VOICEMODE_VOICES=fable,shimmer,af_sarah
```

### Professional Development
**`.voicemode.env`:**
```bash
# Clear, professional voices
VOICEMODE_VOICES=echo,alloy,am_adam
```

### Casual Conversation
**`.voicemode.env`:**
```bash
# Warm, natural voices
VOICEMODE_VOICES=nova,af_sky,shimmer
```

## Provider Considerations

### OpenAI (Cloud)
- **Pros**: Reliable, consistent quality, no setup
- **Cons**: Requires API key, costs money, internet dependent
- **Best for**: Quick setup, reliable fallback

### Kokoro (Local)
- **Pros**: Free, private, works offline
- **Cons**: Requires setup, resource intensive
- **Best for**: Privacy, cost control, offline use

## Configuration Hierarchy

Voice preferences follow this priority order:

1. **Environment variables** (`VOICEMODE_VOICES=voice1,voice2`)
2. **Project `.voicemode.env`** files (searched up directory tree)
3. **Global `~/.voicemode/voicemode.env`**
4. **Built-in defaults** (`alloy,nova,echo`)

## Testing Voice Selection

Use the voice registry tool to see what's available:
```bash
# View available voices and providers (MCP tool)
voice_registry()
```

You can also test specific voices:
```bash
# In your configuration
VOICEMODE_VOICES=af_sky
```

Then use the converse tool to test the voice selection.

## Troubleshooting

**Voice not working?**
1. Check `voice_registry()` to see if the voice is available
2. Verify the provider is healthy
3. Try a different voice as fallback

**Provider switching unexpectedly?**
- Voice-first selection will switch providers to get your preferred voice
- This is intentional behavior for the best voice experience
- Add multiple voices from the same provider if you want to stick to one provider

## Best Practices

1. **Always include fallbacks** - List multiple voices in case one isn't available
2. **Mix providers** - Include both local and cloud voices for flexibility  
3. **Test your setup** - Use `voice_registry()` to verify availability
4. **Project-specific voices** - Use different voices for different types of projects
5. **Consider context** - Professional voices for work, expressive for creative projects