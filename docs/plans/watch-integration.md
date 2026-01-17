# VoiceMode Watch Integration Plan

## Overview

Enable voice conversations with Claude Code using a Pixel Watch (Athena app) for audio I/O, with beelink (no audio hardware) running VoiceMode MCP server.

**Scope:** Phases 1-4 (full mock conversation loop with Argus coordination)

**Decisions:**
- HTTP Bridge runs as systemd service (like Argus)
- Fresh VoiceModeScreen implementation (not reusing HomeVoice)
- Audio flows directly between watch and HTTP Bridge (Argus for coordination only)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    VLAN 10 (192.168.10.x)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐          ┌──────────────────────────────────┐ │
│  │ Pixel Watch  │          │           Beelink                │ │
│  │  (Athena)    │          │                                  │ │
│  │              │  HTTPS   │  ┌────────────────────────────┐  │ │
│  │ VoiceMode    │◄────────►│  │ Argus (8080)               │  │ │
│  │ Screen       │  coord   │  │ - Session state            │  │ │
│  │              │          │  │ - FCM push to activate     │  │ │
│  │              │          │  └────────────────────────────┘  │ │
│  │              │          │                                  │ │
│  │ VoiceMode    │   HTTP   │  ┌────────────────────────────┐  │ │
│  │ Client       │◄────────►│  │ VoiceMode HTTP Bridge      │  │ │
│  │              │  audio   │  │ (8890)                     │  │ │
│  │ - Record OGG │          │  │ - POST /audio/transcribe   │  │ │
│  │ - Play MP3   │          │  │ - POST /audio/synthesize   │  │ │
│  └──────────────┘          │  │ - Calls Whisper/Kokoro     │  │ │
│                            │  └────────────────────────────┘  │ │
│                            │                                  │ │
│                            │  ┌────────────────────────────┐  │ │
│                            │  │ VoiceMode MCP Server       │  │ │
│                            │  │ (stdio - unchanged)        │  │ │
│                            │  └────────────────────────────┘  │ │
│                            └──────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

**Key Design Decisions:**
- **HTTP for audio** (not WebSocket) - simpler, watch already has OkHttp, easier to debug
- **Argus for coordination** - signals watch to enter voice mode via FCM push
- **Direct audio path** - audio flows MCP Bridge <-> Watch (not through Argus)
- **OGG/OPUS for recording** - already used by AudioRecorder
- **MP3 for TTS playback** - Android MediaPlayer compatible

---

## Implementation Status

### Phase 1: Connectivity Test ✅

**VoiceMode HTTP Bridge** (`voice_mode/http_bridge.py`)
- Port 8890, no auth
- Endpoints: `/health`, `/session/start`, `/session/{id}/status`

**Athena VoiceMode Client** (`voicemode/VoiceModeClient.kt`)
- HTTP client following ArgusClient pattern
- Test UI with connection check

**Systemd Service** (`/etc/systemd/system/voicemode-bridge.service`)
- Running and enabled on beelink

### Phase 2: Audio Upload + STT ✅

**HTTP Bridge endpoint:** `POST /audio/transcribe`
- Accepts multipart (file: OGG, session_id: string)
- Returns: `{ "text": "...", "duration_ms": 3400 }`

**Athena VoiceModeScreen** - extended for recording/uploading

### Phase 3: TTS Audio Playback ✅

**HTTP Bridge endpoint:** `POST /audio/synthesize`
- Body: `{ "text": "Hello!", "voice": "af_sky" }`
- Returns: audio/mpeg stream (MP3)

**VoiceModeAudioPlayer** - MediaPlayer wrapper for MP3 playback

### Phase 4: Full Conversation Loop ✅

**HTTP Bridge endpoint:** `POST /converse`
- Full loop: STT → mock response → TTS
- Returns transcription, response, and base64 TTS audio

**Argus Coordination** (`src/routes/voicemode.rs`)
- `POST /api/voicemode/activate` - FCM push to watch
- `POST /api/voicemode/ready` - Watch signals ready
- `GET /api/voicemode/status/{id}` - Session status

**Athena VoiceMode Screen** - Full conversation UI
- States: IDLE → CONNECTING → LISTENING → PROCESSING → SPEAKING

---

## Files Created/Modified

### VoiceMode (Beelink)

| File | Action | Purpose |
|------|--------|---------|
| `voice_mode/http_bridge.py` | Create | HTTP server for watch communication |
| `voice_mode/templates/systemd/voicemode-bridge.service` | Create | Service template |

### Athena (Watch)

| File | Action | Purpose |
|------|--------|---------|
| `voicemode/VoiceModeScreen.kt` | Create | Main conversation UI |
| `voicemode/VoiceModeClient.kt` | Create | HTTP client |
| `MainActivity.kt` | Modify | Add navigation route |
| `audio/AudioScreen.kt` | Modify | Add VMode button |

### Argus (Beelink)

| File | Action | Purpose |
|------|--------|---------|
| `src/routes/voicemode.rs` | Create | Coordination endpoints |
| `src/routes/mod.rs` | Modify | Register new routes |

---

## Phase 5: Production Integration (TODO)

### Security
- Add mTLS to HTTP Bridge (reuse Argus certs)
- Or: token-based auth with session tokens

### Real Provider Integration
- Remove mock mode
- Connect to Whisper.cpp for STT
- Connect to Kokoro/OpenAI for TTS

### Claude Code Integration
- MCP tool `converse()` can specify `audio_source="watch"`
- HTTP Bridge exposes current session state
- Argus coordinates between MCP and watch

---

## Verification Checklist

### Phase 1
- [x] `curl http://192.168.10.10:8890/health` returns OK
- [ ] Watch "Test Connection" shows success (needs app rebuild)

### Phase 2
- [x] Upload test OGG via curl, get transcription (needs STT service)
- [ ] Watch records, uploads, shows transcription

### Phase 3
- [x] TTS endpoint returns playable MP3 (needs TTS service or OpenAI key)
- [ ] Watch plays audio through speaker
- [ ] Watch plays audio through Pixel Buds

### Phase 4
- [x] Full loop endpoint implemented
- [ ] Argus can activate watch voice mode via FCM
- [ ] Watch signals ready state to Argus

### Phase 5
- [ ] Real Whisper STT works
- [ ] Real Kokoro/OpenAI TTS works
- [ ] mTLS authentication working

---

## Next Steps

1. **Deploy TTS/STT services** on beelink or configure OpenAI API key
2. **Build and deploy Athena** to watch
3. **Build and deploy Argus** with voicemode routes
4. **End-to-end testing** with watch
