"""Voice command prompts for guided interactions."""

from voice_mode.mcp_instance import mcp


@mcp.prompt()
async def voice_setup() -> str:
    """Guide for setting up voice services"""
    return """To set up voice services for voice-mode:

1. **Environment Variables**:
   - OPENAI_API_KEY: Your OpenAI API key (only required if using OpenAI services)
   
2. **Optional Configuration**:
   - TTS_VOICE: Default voice (e.g., 'nova', 'alloy', 'af_sky')
   - TTS_MODEL: TTS model (e.g., 'tts-1', 'tts-1-hd', 'gpt-4o-mini-tts')
   - STT_MODEL: STT model (default: 'whisper-1')
   - VOICE_MODE_PREFER_LOCAL: Use local services when available (default: true)
   - VOICE_MODE_AUTO_START_KOKORO: Auto-start Kokoro TTS (default: false)

3. **Local Services** (optional):
   - Kokoro TTS: Run `kokoro_start()` for local TTS
   - LiveKit: Set LIVEKIT_URL for room-based voice chat

4. **Quick Test**:
   ```
   # Test basic TTS
   converse("Hello! Can you hear me?", wait_for_response=False)
   
   # Test conversation
   converse("What's your name?")
   ```
"""


@mcp.prompt()
async def emotional_speech_guide() -> str:
    """Guide for using emotional speech features"""
    return """To use emotional speech with voice-mode:

**Requirements**:
- Use OpenAI API (emotional speech requires OpenAI's gpt-4o-mini-tts model)

**Usage Examples**:

```python
# Excitement
converse("We did it! This is amazing!", 
         tts_model="gpt-4o-mini-tts",
         tts_instructions="Sound extremely excited and celebratory")

# Sadness
converse("I'm sorry for your loss", 
         tts_model="gpt-4o-mini-tts",
         tts_instructions="Sound gentle and sympathetic")

# Urgency
converse("Watch out! Be careful!", 
         tts_model="gpt-4o-mini-tts",
         tts_instructions="Sound urgent and concerned")

# Humor
converse("That's the funniest thing I've heard all day!", 
         tts_model="gpt-4o-mini-tts",
         tts_instructions="Sound amused and playful")

# Whispering
converse("This is a secret", 
         tts_model="gpt-4o-mini-tts",
         tts_instructions="Whisper very quietly")
```

**Tips**:
- Be specific with emotional instructions
- Combine emotions with speaking style (e.g., "Sound excited but speak slowly")
- Cost: ~$0.02/minute for emotional speech
- Automatically uses gpt-4o-mini-tts when emotional instructions are provided
"""


@mcp.prompt()
async def language_voice_guide() -> str:
    """Guide for selecting appropriate voices for different languages"""
    return """To speak in different languages with voice-mode:

**Language-Specific Voice Selection**:

When speaking non-English languages, select an appropriate voice for natural pronunciation:

**Spanish** (Kokoro only):
- ef_dora: Spanish female voice - Clear and expressive
- em_alex: Spanish male voice - Natural pronunciation
- em_santa: Spanish male voice - Santa character

Example:
```python
converse("¡Hola! ¿Cómo estás?", voice="ef_dora", tts_provider="kokoro")
```

**French** (Kokoro only):
- ff_siwis: French female voice

**Italian** (Kokoro only):
- if_sara: Italian female voice
- im_nicola: Italian male voice

**Portuguese** (Kokoro only):
- pf_dora: Portuguese female voice
- pm_alex: Portuguese male voice
- pm_santa: Portuguese male voice

**Chinese** (Kokoro only):
- Female voices: zf_xiaobei, zf_xiaoni, zf_xiaoxiao, zf_xiaoyi
- Male voices: zm_yunjian, zm_yunxi, zm_yunxia, zm_yunyang

**Japanese** (Kokoro only):
- Female voices: jf_alpha, jf_gongitsune, jf_nezumi, jf_tebukuro
- Male voice: jm_kumo

**Hindi** (Kokoro only):
- Female voices: hf_alpha, hf_beta
- Male voices: hm_omega, hm_psi

**Important Notes**:
- Language-specific voices are only available with Kokoro
- OpenAI voices (nova, shimmer, etc.) will speak with an English accent
- Always use tts_provider="kokoro" when using language-specific voices
- Kokoro must be running locally or accessible at configured endpoint

**Auto-Selection Tip**:
Let the LLM detect the language and automatically select an appropriate voice:
- If the message contains Spanish text → use Spanish voice
- If the message contains French text → use French voice
- And so on for other languages
"""
