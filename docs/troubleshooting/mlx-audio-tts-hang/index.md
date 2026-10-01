# mlx-audio TTS Hangs / Apparent MCP Server Dropouts

**Applies to:** voice-mode 8.x with mlx-audio as a local TTS provider on Apple Silicon

> **Fixed by default (VM-1390).** VoiceMode now resolves the model *per endpoint*,
> so an mlx-audio endpoint automatically gets its real repo id
> (`mlx-community/Kokoro-82M-bf16`) instead of the generic `tts-1`. A default
> install no longer triggers the hang described below. This page is kept for the
> **operational recovery notes** at the bottom, and for anyone on an older build
> — or a custom config that still sends a non-repo-id model name to mlx-audio.

## Symptom

- A `converse` call hangs, then eventually times out with no audio.
- The whole VoiceMode MCP server appears to have "dropped out" or died.
- `GET /v1/models` on the mlx-audio server still responds normally.

## Why it happened (historical, pre-VM-1390)

mlx-audio's `POST /v1/audio/speech` treats the request's `model` field as a
**literal HuggingFace repo id**. VoiceMode's old default sent `tts-1` to whatever
TTS endpoint was first; against mlx-audio that became a lookup of
`huggingface.co/api/models/tts-1`, which **404s** and manifests as a hung request
— and, worse, wedges the mlx-audio server so subsequent *valid* requests hang too
(recover with the kickstart below). VM-1390 removes the trigger by resolving the
model per endpoint.

**If you still hit it** (older build, or you've explicitly set a bad model), set a
real repo id for the mlx-audio endpoint — either the per-provider var or the
global one:

```bash
VOICEMODE_TTS_MODELS_MLX_AUDIO=mlx-community/Kokoro-82M-bf16   # per-provider (preferred)
# or, single-provider setups:
VOICEMODE_TTS_MODELS=mlx-community/Kokoro-82M-bf16
```

The MCP server reads `voicemode.env` at **startup only** — reconnect it after
editing (`voicemode reconnect`, or `/mcp` in Claude Code). See
[voicemode.env.example](voicemode.env.example) for a complete hybrid config.

## Recovering a wedged mlx-audio server

These operational notes are independent of VM-1390 and still apply.

1. **Install/upgrade only via the voicemode installer.** voice-mode pins mlx-audio
   to a tested range (`>=0.5.7,<0.6`) and installs the runtime extras the server
   needs; a bare `uv tool install mlx-audio` gets neither. (It no longer patches
   `mlx_audio/server.py`: upstream has served OpenAI-style `response_format`
   natively since 0.4.4.) Use:

    ```bash
    voicemode service install mlx-audio --force
    ```

2. **`voicemode service restart mlx-audio` can stop without relaunching**, and a
   wedged server needs a hard restart. Recover with:

    ```bash
    launchctl kickstart -k gui/$(id -u)/com.voicemode.mlx-audio
    ```

3. **The server dies on the first Kokoro request if its espeak-ng data path is
   160+ characters.** espeak-ng truncates the path, cannot find `phontab`
   (`Error processing file '.../espeak-ng-data/phontab'` in the error log) and
   exits the whole process. The installer warns when
   `<site-packages>/espeakng_loader/espeak-ng-data` is that long; fix it with a
   shorter `HOME`, `UV_TOOL_DIR` or `XDG_DATA_HOME` and reinstall.

4. **Cold start is slow and normal.** After a (re)start, poll `GET /v1/models`
   until it answers before concluding the service is broken.

A known-good launchd plist for running `mlx_audio.server` as a user service is
included in this directory: [com.voicemode.mlx-audio.plist](com.voicemode.mlx-audio.plist).

## Remaining upstream hardening

VM-1390 fixed the VoiceMode-side default. Still open as defence-in-depth:

- **mlx-audio:** map or reject generic OpenAI model names, and add a timeout on
  model resolution, so a bad `model` fast-fails instead of becoming a hanging
  network fetch.
- **VoiceMode:** per-attempt timeout in TTS failover so a *hanging* (not failing)
  endpoint still lets the fallback engage — tracked in **VM-1574**. Auto-recovery
  of a wedged mlx-audio server — tracked in **VM-1520**.
