# mlx-audio TTS Hangs / Apparent MCP Server Dropouts

**Applies to:** voice-mode 8.x with mlx-audio as a local TTS provider on Apple Silicon
**Verified on:** voice-mode 8.10.2, mlx-audio 0.4.3, macOS (M-series)

## Symptom

- A `converse` call hangs indefinitely. No audio, no error, no return.
- The whole VoiceMode MCP server appears to have "dropped out" or died.
- The mlx-audio server itself looks healthy: `GET /v1/models` and `GET /v1/audio/voices` respond normally.
- Restarting services or reverting to Kokoro "fixes" it (it doesn't; it masks it).

## Root Cause

mlx-audio's OpenAI-compatible `POST /v1/audio/speech` endpoint treats the request's `model` field as a **literal HuggingFace repo id** and passes it straight to the model loader. There is no mapping of generic OpenAI model names and no timeout on the resulting fetch.

VoiceMode's default TTS model list is `tts-1,tts-1-hd,gpt-4o-mini-tts`. When mlx-audio is the first TTS endpoint, every speech request asks mlx-audio to load a HuggingFace repo literally named `tts-1`. mlx-audio tries to download that nonexistent repo and the request hangs forever:

```
VoiceMode sends: {"model": "tts-1", ...}
mlx-audio does:  load_model("tts-1")  ->  HF fetch of huggingface.co/tts-1  ->  hang
```

Because the endpoint hangs rather than fails, VoiceMode's TTS failover never engages either: the first attempt never returns, so the fallback URL is never tried.

## Diagnosis

1. Confirm the server is alive but the speech endpoint hangs on generic model names:

    ```bash
    curl -s -m 5 http://127.0.0.1:8890/v1/models            # responds
    curl -s -m 10 -X POST http://127.0.0.1:8890/v1/audio/speech \
      -H "Content-Type: application/json" \
      -d '{"model":"tts-1","input":"test","voice":"af_bella"}'   # hangs, killed at 10s
    ```

2. Check the mlx-audio error log for a HuggingFace download attempt triggered by a speech request:

    ```bash
    tail -40 ~/.voicemode/logs/mlx-audio/mlx-audio.err.log
    ```

3. Confirm the fix works by sending a real, locally cached repo id:

    ```bash
    curl -s -m 30 -X POST http://127.0.0.1:8890/v1/audio/speech \
      -H "Content-Type: application/json" \
      -d '{"model":"mlx-community/Kokoro-82M-bf16","input":"test","voice":"af_bella"}' \
      -o /tmp/test.pcm    # returns in well under a second when warm
    ```

## Fix

Set `VOICEMODE_TTS_MODELS` to the actual MLX model repo id in `~/.voicemode/voicemode.env`:

```bash
VOICEMODE_TTS_BASE_URLS=http://127.0.0.1:8890/v1,http://127.0.0.1:8880/v1
VOICEMODE_TTS_MODELS=mlx-community/Kokoro-82M-bf16
```

See [voicemode.env.example](voicemode.env.example) in this directory for a complete working hybrid configuration (mlx-audio TTS + whisper.cpp STT, Kokoro fallback).

Notes:

- The model should already be in the local HuggingFace cache (`~/.cache/huggingface/hub`); otherwise the first request performs a one-time (legitimate) download.
- **The VoiceMode MCP server reads `voicemode.env` at startup only.** Reconnect the MCP server after changing the file (in Claude Code: `/mcp`). Killing the process does not respawn it in-session.

With this configuration on an M-series MacBook Pro: warm generation ~0.14s for a short sentence, time-to-first-audio ~0.38s through VoiceMode.

## Related Operational Gotchas

1. **Install/upgrade only via the voicemode installer.** voice-mode 8.10.2 pins mlx-audio to `>=0.4.3,<0.4.4` and patches `mlx_audio/server.py` (sentinel: `voicemode-patch: honor OpenAI-style response_format`). A bare `uv tool install mlx-audio` loses the patch. Use:

    ```bash
    voicemode service install mlx-audio --force
    ```

2. **`voicemode service restart mlx-audio` can stop without relaunching.** Recover with:

    ```bash
    launchctl kickstart -k gui/$(id -u)/com.voicemode.mlx-audio
    ```

3. **Cold start is slow and normal.** After a (re)start, poll `GET /v1/models` until it answers before concluding the service is broken.

A known-good launchd plist for running `mlx_audio.server` as a user service is included in this directory: [com.voicemode.mlx-audio.plist](com.voicemode.mlx-audio.plist).

## Suggested Upstream Improvements

These would have surfaced this bug immediately instead of letting it masquerade as random server dropouts for weeks:

1. **Map or reject generic OpenAI model names in mlx-audio.** `tts-1` should either resolve to a configured default local model or return a fast 4xx, never become a network fetch.
2. **Timeout on model resolution** inside the speech request path.
3. **VoiceMode-side default:** when a TTS base URL is the mlx-audio endpoint, default the model to the cached MLX Kokoro repo id rather than `tts-1`.
4. **Per-attempt timeout in TTS failover** so a hanging (not failing) primary endpoint still lets the fallback engage.
5. **Document the installer requirement** (`voicemode service install mlx-audio --force`) so users don't silently lose the response_format patch.
