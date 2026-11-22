# Uninstalling VoiceMode

`voicemode uninstall` removes VoiceMode from your home directory on macOS and Linux.
It prints the full plan before it changes anything. This page lists everything it
removes, everything it keeps, and the few things it leaves for you to remove by hand.

## Quick

```bash
voicemode uninstall --dry-run    # print the plan, change nothing
voicemode uninstall              # print the plan, then ask [y/N]
```

| Flag | Effect |
|---|---|
| `--dry-run` | Print the plan and exit. Nothing is changed. |
| `-y`, `--yes` | Print the plan, then go ahead without asking. Needed when stdin is not a terminal. |
| `--remove-models` | Also remove models: the Whisper and Kokoro installs, `models/` and `kokoro-models/`. |
| `--remove-all-data` | Also remove your data and config, except voice clones. Implies `--remove-models`. |

It exits `0` when it is done (or there is nothing to remove) and `1` if anything went
wrong or you said no. It exits `2` when it refuses: when stdin is not a terminal and
there is no `--yes`, when it runs as root (no `sudo`), when `HOME` is unset or is not
your home directory, and on Windows (see [Windows](#windows)).

If an item fails, the `voice-mode` package is kept so you can run
`voicemode uninstall` again to finish.

## What it does, and in what order

1. **Services.** It stops and unregisters VoiceMode's launchd jobs or systemd user
   units, then deletes their unit files. A job is stopped only if it was loaded from
   this home directory's own unit file. A job loaded from anywhere else is left
   running, and the plan says so. Nothing is ever killed by port.
2. **Claude Code.** It removes VoiceMode's hook handlers from
   `~/.claude/settings.json`, leaving every other hook and setting alone. Then it runs
   `claude mcp remove <name> -s user` for each VoiceMode MCP server it found.
3. **Files** under `~/.voicemode`, by class (below), then shell completion files.
4. **Packages.** VoiceMode's own `mlx-audio` uv tool, then `uv tool uninstall voice-mode`
   last, because that deletes the running program.

What happens to each class of file:

| Class | Default | `--remove-models` | `--remove-all-data` |
|---|---|---|---|
| Software: services, `bin/` scripts, hooks, MCP entries, completion files, packages | removed | removed | removed |
| Models: the Whisper and Kokoro installs, `models/`, `kokoro-models/` | **kept**, listed with size | removed | removed |
| Config: `voicemode.env`, `.voicemode.env` | **backed up** | backed up | removed |
| Your data (below) | **kept**, listed | kept | removed |
| Voice clones: `voices/`, `voices.json` | **never removed** | never | never |
| Anything it doesn't recognise | kept, listed | kept | kept |

**Why the Whisper and Kokoro installs count as models.** Whisper keeps its models
inside `~/.voicemode/services/whisper/models`, and Kokoro keeps its model inside its
install. Keeping only the models would break a later reinstall. So by default the
whole installs are kept, with your models, while their services are removed.
`--remove-models` removes them.

**The config backup never overwrites an earlier one.** The first backup is
`voicemode.env.uninstalled`. If that exists, the new one is
`voicemode.env.uninstalled.<YYYYmmdd-HHMMSS>`.

## The footprint

`~` is your home directory. `VOICEMODE_BASE_DIR` (default `~/.voicemode`) moves your
data, but the Whisper and Kokoro installs, config and service logs always live in
`~/.voicemode`. A custom `VOICEMODE_BASE_DIR` is treated like `~/.voicemode` only
if it is named `.voicemode` or `voicemode`, sits inside your home directory (also
after following symlinks), and was not set by a project `.voicemode.env`. Otherwise
nothing there is touched, and the plan says why.

### Services

| Service | macOS: `~/Library/LaunchAgents/` | Linux: `~/.config/systemd/user/` |
|---|---|---|
| Whisper | `com.voicemode.whisper.plist` | `voicemode-whisper.service` |
| Kokoro | `com.voicemode.kokoro.plist` | `voicemode-kokoro.service` |
| VoiceMode (serve) | `com.voicemode.serve.plist` | `voicemode-serve.service` |
| mlx-audio (Apple Silicon) | `com.voicemode.mlx-audio.plist` | none |
| Whisper (old name) | `com.voicemode.whisper-server.plist` | none |

- **macOS:** it checks both the `gui/<uid>` and `user/<uid>` launchd domains and runs
  `launchctl bootout` where the job is loaded. It never runs `unload -w` or `disable`.
- **Linux:** it runs `systemctl --user disable --now`, and removes the
  `default.target.wants/voicemode-<name>.service` enable link if it points at the unit
  file. After a disable it runs `daemon-reload` and `reset-failed`.

**Listed, never touched** (with the manual command in the plan). Check that these
are VoiceMode's before you remove them:

- macOS: any other `com.voicemode.*.plist`, such as a VoiceMode app or an old
  `com.voicemode.kokoro-<port>` job, and `com.whisper.server.plist`.
- Linux: `kokoro-fastapi.service`, `kokoro-fastapi-*.service`,
  `whisper-server.service`, and any other `voicemode-*.service`. Old VoiceMode
  versions wrote some of these, but the names are generic: your own whisper.cpp or
  Kokoro-FastAPI server may own them.

### Claude Code

- **Hooks:** VoiceMode's handlers (`voicemode-hook-receiver`, `voicemode-heard-hook`)
  in `~/.claude/settings.json` are removed one handler at a time, so a hook entry you
  share with your own handlers keeps yours. If `settings.json` is a symlink (a
  dotfiles setup), the file it points to is edited, but only if that file is inside
  your home directory.
- **MCP servers, user scope:** `voicemode`, and the older names `voice-mode` and
  `voice-mcp`. They are read from `~/.claude.json`, or `$CLAUDE_CONFIG_DIR/.claude.json`
  if that is set. If `CLAUDE_CONFIG_DIR` is outside your home directory, or `claude`
  is not on your PATH, the command to run is listed instead.
- **Listed, never touched:** local-scope (per-project) MCP entries, shown as
  `cd <dir> && claude mcp remove <name> -s local`. Also VoiceMode hooks in the current
  project's `.claude/settings.json` or `.claude/settings.local.json`. Those are repo
  files, as is a project `.mcp.json`.

### Files under `~/.voicemode`

| Class | Entries |
|---|---|
| Software | `services/voicemode/`, `services/mlx-audio/`, `bin/voicemode-hook-receiver`, `bin/voicemode-heard-hook`, old installs `whisper.cpp/` and `kokoro-fastapi/`. `bin/` and `services/` are removed if they end up empty. |
| Models | `services/whisper/` (whisper.cpp and its models), `services/kokoro/` (Kokoro-FastAPI, its venv and model), `models/`, `kokoro-models/` |
| Config | `voicemode.env`, `.voicemode.env` |
| Your data | `audio/`, `transcriptions/`, `logs/`, `cache/`, `soundfonts/`, `mouth/`, `state.json`, `state/`, `conch`, `conch.grant`, `conch.queue.seq`, `conch.queue.d/`, `control.sock`, `focus-hold`, `autofocus-disabled`, `soundfonts-disabled`, `music-library.db`, `music-for-programming/`, `credentials`, `credentials.migrated`, `install.log`, `config/`, old logs `whisper-server.log`, `whisper-server.stdout.log`, `whisper-server.stderr.log`, `whisper-server.error.log`, `kokoro.log`, `kokoro.stdout.log`, `kokoro.stderr.log`, and earlier `voicemode.env.uninstalled*` backups |
| Voice clones | `voices/`, `voices.json`. An entry that holds your `VOICEMODE_VOICES_DIR` is kept too. |

`~/.voicemode` itself is removed only if it ends up empty. With voice clones in it,
it never does.

### Shell completion files

- `~/.zfunc/_voicemode` and `~/.config/fish/completions/voicemode.fish` are removed.
- `~/.bash_completion.d/voicemode` is removed unless a bash startup file names it:
  `~/.bashrc`, `~/.bash_profile`, `~/.bash_login`, `~/.profile`, `~/.bash_completion`,
  or a file in `~/.bashrc.d/`. If one does, the file is kept and the plan names the
  line to delete first.

### Packages

- `voice-mode` is removed with `uv tool uninstall voice-mode`, but only when the
  running `voicemode` is that uv tool and uv's tool directory is inside your home
  directory. Installed another way (pipx, a source checkout, nix)? The plan says so.
  Remove it the way you installed it.
- `mlx-audio` is removed with `uv tool uninstall mlx-audio` only if VoiceMode installed
  it (`~/.voicemode/services/mlx-audio` or `com.voicemode.mlx-audio.plist` exists).
  Otherwise it is listed and left alone.

## Left for you

The plan lists each of these under **Left for you**. It never removes them itself.

- **VoiceMode Connect login.** Run `voicemode connect auth logout` **before** you
  uninstall. It deletes your tokens from `~/.voicemode/credentials` (the default) or
  from the OS keychain (service `voicemode`, if you set
  `VOICEMODE_CREDENTIAL_STORE=keyring`). It signs you out locally only. The plan's
  line says whether the `credentials` file is kept (the default) or removed
  (`--remove-all-data`, which treats it as your data). The command never touches the
  keychain.
- **The Claude Code plugin**, if you installed VoiceMode that way. See the
  [next section](#the-claude-code-plugin).
- **Shared caches.** mlx-audio's models are in the Hugging Face hub cache
  (`~/.cache/huggingface/hub`, `models--mlx-community--*`). uv's cache has a copy of the
  package: `uv cache clean voice-mode`.
- **Custom locations** set by `VOICEMODE_MODELS_DIR`, `VOICEMODE_WHISPER_MODEL_PATH`,
  `VOICEMODE_KOKORO_MODELS_DIR`, `VOICEMODE_KOKORO_CACHE_DIR`, `VOICEMODE_EVENT_LOG_DIR`,
  `VOICEMODE_CONTROL_SOCKET`, `VOICEMODE_VOICES_DIR`, `VOICEMODE_MOUTH_DIR`,
  `VOICEMODE_MOUTH_AUDIO_DIR`, `VOICEMODE_MOUTH_SETTINGS`, `VOICEMODE_MOUTH_MAILBOX` or
  `VOICEMODE_MOUTH_LOG_DIR`, when they point outside `~/.voicemode`. The same goes for a
  custom `--install-dir` given to a Whisper or Kokoro install.
- **Files in your home directory itself:** `~/voicemode_debug.log`,
  `~/voicemode_trace.log`, `~/voicemode_logs/`, `~/voice-mode-audio-*`.
- **Shell rc lines.** Remove a `source ~/.bash_completion.d/voicemode` line, and the
  completion lines old installers added, by hand.
- **Never touched, by design:** `~/kokoro-fastapi` (your own clone, which VoiceMode
  uses if it is there), project `.voicemode.env` files, journald logs, and launchd's
  enabled/disabled override entries for VoiceMode's labels (harmless).

## The Claude Code plugin

If you installed VoiceMode with `claude plugin install voicemode@voicemode`:

```bash
claude plugin uninstall voicemode@voicemode
```

The plan prints the plugin id it found. Removing the marketplace is optional:

```bash
claude plugin marketplace remove voicemode
```

It takes the marketplace name, `voicemode`. It also **uninstalls every plugin you
installed from that marketplace**, including `show-me`, and deletes their saved options
and data. `claude plugin uninstall voicemode@voicemode` leaves `show-me` alone.

## Shared system tools

The installers (`install.sh` and `voice-mode-install`) install these only if they are
missing, and other tools may use them. Remove them only if nothing else needs them.

- **uv:** `rm ~/.local/bin/uv ~/.local/bin/uvx`, then `rm -rf ~/.local/share/uv ~/.cache/uv`.
  Also delete the PATH line its installer added to your shell rc file.
- **macOS (Homebrew):** `brew uninstall portaudio ffmpeg`, plus `cmake` if the
  Whisper install added it. The installer may also have added
  `eval "$(/opt/homebrew/bin/brew shellenv)"` (or `/usr/local/bin/brew`) to
  `~/.zprofile` or `~/.bash_profile`.
- **Debian/Ubuntu:** `sudo apt remove python3-dev gcc libasound2-dev libportaudio2 ffmpeg`
  (ARM64 also added `g++`).
- **Fedora/RHEL:** `sudo dnf remove python3-devel gcc alsa-lib-devel portaudio ffmpeg`
  (ARM64 also added `gcc-c++`).
- **Arch:** `sudo pacman -R python gcc alsa-lib portaudio ffmpeg`
- **rustup** (ARM64 Linux, for Kokoro's build): `rustup self uninstall`.

## Windows

`voicemode uninstall` does not support Windows yet: it refuses and points here.
VoiceMode runs Whisper and Kokoro on Windows as plain processes, with no service
units. In PowerShell:

```powershell
voicemode service stop whisper        # or end whisper-server.exe in Task Manager
voicemode service stop kokoro
voicemode connect auth logout         # if you signed in to VoiceMode Connect
voicemode claude hooks remove
claude mcp remove voicemode -s user
$vm = "$HOME\.voicemode"
Rename-Item "$vm\voicemode.env" voicemode.env.uninstalled
Remove-Item -Recurse -Force "$vm\services\whisper", "$vm\services\kokoro", "$vm\services\voicemode", "$vm\bin" -ErrorAction SilentlyContinue
uv tool uninstall voice-mode          # after every voicemode process has exited
```

`services\whisper` (the whisper.cpp build, `whisper-server.exe` and its models) and
`services\kokoro` (Kokoro-FastAPI, its venv, `start-cpu.ps1` and its model) are the
big ones. Your data is in the same places as on macOS and Linux (the table above),
and `voices\` and `voices.json` are your voice clones. The
[plugin](#the-claude-code-plugin) and the shared caches work the same way.

## If the `voicemode` command is already gone

Do by hand what the command would do, in the same order. Check each item with the
footprint above first.

```bash
# macOS
for n in whisper kokoro serve mlx-audio whisper-server; do
  launchctl bootout gui/$(id -u)/com.voicemode.$n 2>/dev/null
  rm -f ~/Library/LaunchAgents/com.voicemode.$n.plist
done
# Linux
for n in whisper kokoro serve; do
  systemctl --user disable --now voicemode-$n.service
  rm -f ~/.config/systemd/user/voicemode-$n.service
done
systemctl --user daemon-reload

claude mcp remove voicemode -s user
# Remove the voicemode-hook-receiver and voicemode-heard-hook entries
# from ~/.claude/settings.json by hand.
uv tool uninstall voice-mode
```

Then remove what you want from `~/.voicemode`. Keep `voices/` and `voices.json` unless
you want your voice clones gone too.

## See also

- [CLI Commands](cli.md)
- [Service Commands](cli/service-commands.md)
- [Claude Code Plugin](../guides/claude-code-plugin.md)
