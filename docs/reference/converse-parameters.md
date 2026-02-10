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
Use `listen_duration_max` instead.

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
- `2` - Balanced (default) - good for most environments
- `3` - Most aggressive, strict detection, may cut off soft speech

**When to adjust:**
- Quiet room: Use 0-1 to catch all speech
- Normal home/office: Use default (2)
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

## Audio Format & Feedback

### audio_format
**Type:** string (optional)
Override audio format.

**Options:** pcm, mp3, wav, flac, aac, opus

**Default:** Uses VOICEMODE_TTS_AUDIO_FORMAT env var

## Audio Saving & Debugging

Audio files can be saved for debugging, manual transcription recovery, or archival purposes.

### Configuration

Set in `~/.voicemode/voicemode.env`:

```bash
# Save all audio files (STT recordings and TTS output)
VOICEMODE_SAVE_ALL=true

# Or enable individually
VOICEMODE_SAVE_AUDIO=true         # STT recordings only
VOICEMODE_SAVE_TRANSCRIPTIONS=true # Transcription JSON files

# Automatically enabled in debug mode
VOICEMODE_DEBUG=true
```

### Saved File Locations

```
~/.voicemode/audio/
├── latest-STT.wav          # Symlink to most recent STT recording
├── latest-TTS.mp3          # Symlink to most recent TTS output
├── 2026-02-09_14-15-23_STT_conv-abc123.wav
└── 2026-02-09_14-15-28_TTS_conv-abc123.mp3
```

### Manual STT Recovery

If STT fails but audio was recorded, manually transcribe:

```bash
whisper-cli ~/.voicemode/audio/latest-STT.wav
```

See [STT Recovery](../../.claude/skills/voicemode/SKILL.md#stt-recovery---manual-transcription) and [Troubleshooting - No Speech Detected](../../troubleshooting/index.md#1-no-speech-detected) for details.

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

## Barge-In (TTS Interruption)

Barge-in allows users to interrupt TTS playback by speaking, enabling more natural conversation flow.

### Enabling Barge-In

Barge-in is controlled by environment variables, not converse parameters:

```bash
# Enable barge-in (default: false)
export VOICEMODE_BARGE_IN=true

# VAD aggressiveness (0-3, default: 2)
export VOICEMODE_BARGE_IN_VAD=2

# Minimum speech duration in ms (default: 150)
export VOICEMODE_BARGE_IN_MIN_MS=150
```

### How It Works

1. When TTS playback starts, VoiceMode monitors the microphone
2. WebRTC VAD analyzes audio for speech activity
3. When voice is detected and sustained past the threshold:
   - TTS playback stops immediately
   - Captured speech (from voice onset) is passed to STT
   - Listening chime is skipped (user is already speaking)
   - Conversation continues normally

### Requirements

- `webrtcvad` library (installed automatically)
- `wait_for_response=true` (default)
- TTS not skipped via `skip_tts`

### Tuning Tips

- **False positives** (TTS stops randomly): Increase `VOICEMODE_BARGE_IN_VAD` (try 3) or `VOICEMODE_BARGE_IN_MIN_MS` (try 200-300)
- **Slow response**: Decrease `VOICEMODE_BARGE_IN_MIN_MS` (try 100)
- **Quiet environment**: Lower VAD (try 1)
- **Noisy environment**: Higher VAD (try 3)

## Endpoint Requirements

STT/TTS services must expose OpenAI-compatible endpoints:
- Whisper/Kokoro must serve on:
  - `/v1/audio/transcriptions` (STT)
  - `/v1/audio/speech` (TTS)

Connection errors will clearly report attempted endpoints.
