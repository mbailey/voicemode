# Voicemode Parameters Reference

## Core Parameters

### message (required)
**Type:** string
The message to speak to the user.

### wait_for_response
**Type:** boolean (default: true)
Whether to listen for a voice response after speaking.

## Timing Parameters

### listen_duration_max
**Type:** number (default: 120.0 seconds)
Maximum time to listen for response. The tool handles silence detection well.

**When to override:**
- Silence detection is disabled and you need specific timeout
- Response will be exceptionally long (>120s)
- Special timing requirements

**Usually:** Let default and silence detection handle it.

### listen_duration_min
**Type:** number (default: 2.0 seconds)
Minimum recording time before silence detection can stop.

**Use cases:**
- Complex questions: 2-3 seconds
- Open-ended prompts: 3-5 seconds
- Quick responses: 0.5-1 second

### timeout (DEPRECATED)
Use `listen_duration_max` instead. Only applies to LiveKit transport.

## Voice & TTS Parameters

### voice
**Type:** string (optional)
Override TTS voice selection.

**When to specify:**
- User explicitly requests specific voice
- Speaking non-English languages (see languages resource)

**Examples:**
- OpenAI: nova, shimmer, alloy, echo, fable, onyx
- Kokoro: af_sky, af_sarah, am_adam, ef_dora, etc.

**Important:** Never use 'coral' voice.

### tts_provider
**Type:** "openai" | "kokoro" (optional)
TTS provider selection.

**When to specify:**
- User explicitly requests provider
- Failover testing
- Non-English languages (usually kokoro)

**Usually:** Let system auto-select.

### tts_model
**Type:** string (optional)
TTS model selection.

**Options:**
- `tts-1` - Standard quality (OpenAI)
- `tts-1-hd` - High definition (OpenAI)
- `gpt-4o-mini-tts` - Emotional speech support (OpenAI)

**When to specify:**
- Need HD quality
- Want emotional speech (with tts_instructions)

**Usually:** Let system auto-select.

### tts_instructions
**Type:** string (optional)
Tone/style instructions for emotional speech.

**Requirements:** Only works with `tts_model="gpt-4o-mini-tts"`

**Examples:**
- "Speak in a cheerful tone"
- "Sound angry"
- "Be extremely sad"
- "Sound urgent and concerned"

**Note:** Uses OpenAI API, incurs costs (~$0.02/minute)

### speed
**Type:** number (0.25 to 4.0, optional)
Speech playback rate.

**Examples:**
- 0.5 = half speed
- 1.0 = normal speed (default)
- 1.5 = 1.5x speed
- 2.0 = double speed

**Supported by:** Both OpenAI and Kokoro

## Audio & Silence Detection

### disable_silence_detection
**Type:** boolean (default: false)
Disable automatic silence detection.

**When to use:**
- User reports being cut off
- Noisy environments
- Dictation mode where pauses are expected

**Usually:** Leave enabled (false).

### vad_aggressiveness
**Type:** integer 0-3 (optional)
Voice Activity Detection strictness level.

**Levels:**
- `0` - Least aggressive, includes more audio, may include non-speech
- `1` - Slightly stricter filtering
- `2` - Balanced - good for most environments
- `3` - Most aggressive, strict detection (default) - best for filtering background noise

**When to adjust:**
- Quiet room: Use 0-1 to catch all speech
- Normal home/office: Use default (3)
- Noisy cafe/outdoors: Use 3

### chime_leading_silence
**Type:** number (seconds, optional)
Time to add before audio chime starts.

**Use case:** Bluetooth devices that need audio buffer (e.g., 1.0 seconds)

**Default:** Uses VOICEMODE_CHIME_LEADING_SILENCE env var (0.1s)

### chime_trailing_silence
**Type:** number (seconds, optional)
Time to add after audio chime ends.

**Use case:** Prevent chime cutoff (e.g., 0.5 seconds)

**Default:** Uses VOICEMODE_CHIME_TRAILING_SILENCE env var (0.2s)

## Vocabulary Biasing (STT Prompt)

### VOICEMODE_STT_PROMPT
**Type:** environment variable (string, optional)

Bias Whisper's speech recognition toward specific words and names using a prompt hint. This helps improve recognition of technical terms, proper names, and domain-specific vocabulary that Whisper might otherwise mishear.

**How it works:**

Whisper uses a "prompt" field to condition its recognition. By providing words and phrases you frequently use, the model is primed to hear them correctly. This is especially useful for:

- **Names**: People, pets, places (Tali, Mike, Brisbane)
- **Technical terms**: Command names, tools (tmux, kubectl, pytest)
- **Project vocabulary**: Your codebase-specific terms
- **Acronyms**: Common abbreviations in your domain

**Format flexibility:**

All of these formats work equivalently:
```bash
# Comma-separated
export VOICEMODE_STT_PROMPT="tmux, Tali, VoiceMode, kubectl"

# Space-separated
export VOICEMODE_STT_PROMPT="tmux Tali VoiceMode kubectl"

# Sentence-style (can help with context)
export VOICEMODE_STT_PROMPT="The user often talks about Tali, tmux sessions, and VoiceMode features."
```

**Examples:**
```bash
# Developer working with Kubernetes and tmux
export VOICEMODE_STT_PROMPT="kubectl, tmux, pytest, FastAPI, VoiceMode"

# User with a pet named Tali
export VOICEMODE_STT_PROMPT="Tali, my dog Tali, taking Tali for a walk"

# Mix of technical and personal vocabulary
export VOICEMODE_STT_PROMPT="tmux, neovim, Tali, Brisbane, taskmaster"
```

**Token limit:**

Whisper uses the last 224 tokens of the prompt. In practice, this means:
- Short word lists: No problem (most use cases)
- Long prompts: Only the end matters, so put important words last
- Typical vocabulary: 50-100 words fits easily within the limit

**When to use:**

- Whisper consistently mishears specific words
- You use unusual names or technical jargon
- Domain-specific vocabulary isn't recognized

**Troubleshooting tip:**

If a word is still misrecognized after adding it to the prompt, try including it in context: instead of just "Tali", use "my dog Tali" or "Tali is a Rottweiler".

**See also:** [Troubleshooting - Words Misrecognized](troubleshooting.md#specific-words-consistently-misrecognized)

## Audio Format & Feedback

### audio_format
**Type:** string (optional)
Override audio format.

**Options:** pcm, mp3, wav, flac, aac, opus

**Default:** Uses VOICEMODE_TTS_AUDIO_FORMAT env var

### chime_enabled
**Type:** boolean | string (optional)
Enable or disable audio feedback chimes.

**Default:** Uses VOICEMODE_CHIME_ENABLED env var

### skip_tts
**Type:** boolean (optional)
Skip text-to-speech, show text only.

**Values:**
- `true` - Skip TTS, faster response, text-only
- `false` - Always use TTS
- `null` (default) - Follow VOICEMODE_SKIP_TTS env var

**Use cases:**
- Rapid development iterations
- When voice isn't needed
- Text-only mode

## Transport Parameters

### transport
**Type:** "auto" | "local" | "livekit" (default: "auto")
Transport method selection.

**Options:**
- `auto` - Try LiveKit first, fallback to local
- `local` - Direct microphone access
- `livekit` - Room-based communication

### room_name
**Type:** string (optional)
LiveKit room name.

**Only for:** livekit transport
**Default:** Auto-discovered if empty

## Endpoint Requirements

STT/TTS services must expose OpenAI-compatible endpoints:
- Whisper/Kokoro must serve on:
  - `/v1/audio/transcriptions` (STT)
  - `/v1/audio/speech` (TTS)

Connection errors will clearly report attempted endpoints.
