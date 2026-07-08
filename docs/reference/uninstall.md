# Uninstalling VoiceMode

`voicemode uninstall` (see [CLI Commands](cli.md)) automates most of this, but
it deliberately does **not** touch everything VoiceMode's installer
(`docs/web/install.sh` / `uvx voice-mode-install`) puts on disk — some of it
(voice clones) is sacred and never auto-removed, some of it (build
dependencies, `uv` itself) is shared with other tools and not VoiceMode's to
remove. This page maps **every** path/command VoiceMode (or its installer)
writes, so you can finish the job by hand if you want a fully clean machine.

## 1. The command (`voicemode uninstall`)

```bash
voicemode uninstall [-y/--yes] [--remove-models] [--remove-all-data]
```

Automates, in order:

1. Stops + removes the **Whisper**, **Kokoro**, and **mlx-audio** services.
2. Stops + removes the **voicemode** service ("serve", the HTTP MCP server) —
   its launchd/systemd unit and `~/.voicemode/services/voicemode/` start
   script.
3. Removes the Claude Code **MCP registration** (`claude mcp remove
   voicemode`), tried at both `--scope user` and the local/default scope.
4. **Backs up** (does not delete) `~/.voicemode/voicemode.env` →
   `voicemode.env.uninstalled`.
5. With `--remove-all-data`: removes every other entry under
   `~/.voicemode/` — **except** `voices/` and `voices.json`.
6. Removes the `voice-mode` package (`uv tool uninstall voice-mode`) — done
   **last**, since it deletes the running binary; skipped if any earlier
   step errored, so a re-run can pick up where it left off.

Prints a residual-footprint report of what was removed and what remains.
Equivalent single-service teardown: `voicemode service uninstall
whisper|kokoro|mlx-audio|voicemode`.

**Never auto-removed, by design** — voice clones (`~/.voicemode/voices/`,
`voices.json`), recordings, conversations, transcriptions, and models unless
`--remove-models`/`--remove-all-data` is given.

## 2. What it can't reach: the Claude Code plugin path

If VoiceMode was installed via `claude plugin install voicemode@voicemode`
(Quick Start Option 1), `claude mcp remove` cannot see or remove a
plugin-managed MCP server — `voicemode uninstall` detects this and reports
it, but the actual removal is a separate command:

```bash
claude plugin uninstall voicemode
# and, if you added the marketplace only for this plugin:
claude plugin marketplace remove mbailey/voicemode
```

## 3. `~/.voicemode/` layout

Everything VoiceMode's own state lives under `$VOICEMODE_BASE_DIR` (default
`~/.voicemode`):

| Path | Contents | Removed by `uninstall`? |
|---|---|---|
| `voicemode.env` | Configuration (API keys, preferences) | Backed up to `voicemode.env.uninstalled`, never deleted |
| `.voicemode.env` | Legacy config file location | Same as above |
| `services/whisper/` | whisper.cpp binary + service scripts | Yes (via `whisper_uninstall`) |
| `services/kokoro/` | Kokoro TTS service + venv | Yes (via `kokoro_uninstall`) |
| `services/mlx-audio/` | mlx-audio service (Apple Silicon) | Yes (via `mlx_audio_uninstall`) |
| `services/voicemode/` | "serve" (HTTP MCP server) start script | Yes (step 2, `_teardown_serve_service`) |
| `models/` (incl. `models/kokoro/`) | Downloaded Whisper/Kokoro model weights | Only with `--remove-models` or `--remove-all-data` |
| `voices/` + `voices.json` | Voice clone reference audio + registry | **Never** — remove manually if you really want them gone |
| `audio/` | Saved TTS/STT audio (`VOICEMODE_SAVE_AUDIO=true`) | Only with `--remove-all-data` |
| `transcriptions/` | Saved transcription text | Only with `--remove-all-data` |
| `logs/` (incl. `logs/conversations/`, `logs/events/`, `logs/debug/`) | Conversation history, operational logs | Only with `--remove-all-data` |
| `cache/kokoro/` | Kokoro runtime cache | Only with `--remove-all-data` |

With `--remove-all-data`, `~/.voicemode/` itself is removed too, **if** it
ends up empty (i.e. `voices/`/`voices.json` didn't survive) — otherwise it's
left in place holding just the voice clones.

Manual removal of everything, including voice clones:

```bash
rm -rf ~/.voicemode
```

## 4. Service units (launchd / systemd)

Each service registers a per-platform background-service unit; `uninstall`
disables and removes these for you, but if you're cleaning up after a
partial/failed uninstall, the paths are:

**macOS (launchd)** — `~/Library/LaunchAgents/`:

- `com.voicemode.whisper.plist`
- `com.voicemode.kokoro.plist`
- `com.voicemode.mlx-audio.plist`
- `com.voicemode.serve.plist` (the "voicemode"/"serve" service)

```bash
launchctl unload ~/Library/LaunchAgents/com.voicemode.<name>.plist
rm ~/Library/LaunchAgents/com.voicemode.<name>.plist
```

**Linux (systemd user units)** — `~/.config/systemd/user/`:

- `voicemode-whisper.service`
- `voicemode-kokoro.service`
- `voicemode-mlx-audio.service`
- `voicemode-serve.service`

```bash
systemctl --user disable --now voicemode-<name>.service
rm ~/.config/systemd/user/voicemode-<name>.service
```

## 5. MCP registration

```bash
claude mcp remove voicemode --scope user   # global registration
claude mcp remove voicemode                # local/default-scope registration
```

`voicemode uninstall` tries both scopes and tolerates "not registered" at
either. For the Claude Code **plugin** path, see section 2 above instead.

## 6. The `voice-mode` package itself

Installed as a [uv tool](https://docs.astral.sh/uv/guides/tools/):

```bash
uv tool uninstall voice-mode
```

`voicemode uninstall` runs this last (it deletes the running binary) and
skips it entirely if an earlier step failed, so a re-run of `voicemode
uninstall` can finish the job later. If VoiceMode was installed from source
(`uv tool install -e .`) or via `pip`/`pipx` instead, use the matching
uninstall command for that tool.

## 7. System dependencies (shared with other tools — VoiceMode does not remove these)

Installed by `install.sh` / `voice-mode-install`; **not** VoiceMode-specific,
so `voicemode uninstall` never touches them.

### uv (the package manager)

```bash
rm ~/.local/bin/uv ~/.local/bin/uvx
rm -rf ~/.local/share/uv          # installed tools/venvs
rm -rf ~/.cache/uv                # uv/uvx package cache
```

### Hugging Face model cache (used by mlx-audio)

```bash
rm -rf ~/.cache/huggingface/hub
```

### macOS (Homebrew)

```bash
brew uninstall portaudio ffmpeg
```

If you no longer want Homebrew's `eval "$(/opt/homebrew/bin/brew
shellenv)"` (or `/usr/local/bin/brew shellenv` on Intel) line the installer
added to your shell profile, remove it from `~/.zprofile` or
`~/.bash_profile` by hand.

### Linux (sudo-installed system packages)

Only remove these if nothing else on the machine depends on them.

**Debian/Ubuntu:**

```bash
sudo apt remove python3-dev gcc libasound2-dev libportaudio2 ffmpeg
# ARM64 only, added for Kokoro's mojimoji dependency:
sudo apt remove g++
```

**Fedora/RHEL:**

```bash
sudo dnf remove python3-devel gcc alsa-lib-devel portaudio ffmpeg
# ARM64 only:
sudo dnf remove gcc-c++
```

**Arch:**

```bash
sudo pacman -R python gcc alsa-lib portaudio ffmpeg
```

### rustup (ARM64 Linux only — needed to build some Kokoro dependencies)

```bash
rustup self uninstall
# or, if that's unavailable:
rm -rf ~/.cargo ~/.rustup
```

## See also

- [README — Uninstall](../README.md#uninstall)
- [CLI Commands — `uninstall` / `service uninstall`](cli.md)
- [Claude Code Plugin guide](../guides/claude-code-plugin.md)
