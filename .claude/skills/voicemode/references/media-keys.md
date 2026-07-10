# Media keys setup — agent runbook (macOS)

Audience: **the AI assistant**, doing this setup on the user's behalf. The
user typically just says something like "set up media keys for VoiceMode" —
this is the end-to-end procedure, including the one step you cannot do for
them.

**Human-readable version of this same procedure:** [macOS Media Keys guide](../../../../docs/guides/macos-media-keys.md).
**Full ownership model / architecture:** [Control Channel reference](../../../../docs/reference/control-channel.md#media-keys).

## What this gets the user

Their keyboard's media keys (▶❙❙ / ⏭ / ⏮) drive VoiceMode — pause, barge in
(cut the current utterance and take the mic), replay — while a converse is
live, and behave exactly as before (control their music app) otherwise. This
is macOS-only and needs [Hammerspoon](https://www.hammerspoon.org/), a
scriptable window/event manager, as the key interceptor.

## Preflight — check before doing anything

```bash
uname -s                    # must be Darwin — this doesn't apply on Linux/other
which voicemode              # confirms VoiceMode CLI is on PATH
pgrep -x Hammerspoon          # non-empty = already installed and running
grep VOICEMODE_CONTROL_CHANNEL_ENABLED ~/.voicemode/voicemode.env 2>/dev/null
```

If `uname -s` isn't `Darwin`, stop and tell the user this feature is
macOS-only (point at skhd/xbindkeys/Karabiner in the
[Control Channel reference](../../../../docs/reference/control-channel.md#simple-unconditional-bindings-skhd-xbindkeys-karabiner)
instead).

## Steps you (the agent) can do

1. **Install Hammerspoon**, if `pgrep -x Hammerspoon` above found nothing:
   ```bash
   brew install --cask hammerspoon
   open -a Hammerspoon   # first launch — creates ~/.hammerspoon/
   ```

2. **Enable the control channel.** Append (don't duplicate) to
   `~/.voicemode/voicemode.env`:
   ```bash
   grep -q '^VOICEMODE_CONTROL_CHANNEL_ENABLED=' ~/.voicemode/voicemode.env 2>/dev/null \
     || echo 'VOICEMODE_CONTROL_CHANNEL_ENABLED=true' >> ~/.voicemode/voicemode.env
   ```
   Without this, the socket (`~/.voicemode/control.sock`) is never bound —
   everything else below will install cleanly but silently do nothing.

3. **Locate the voicemode checkout** so you can point `dofile` at the right
   path. If you don't already know it, ask the user or check common
   locations (`~/Code/voicemode`, wherever their `git_url:
   github.com/mbailey/voicemode` clone lives).

4. **Write (or merge into) `~/.hammerspoon/init.lua`.** If the file doesn't
   exist, create it with just the dofile line. If it exists, **append** —
   don't overwrite an existing Hammerspoon config:
   ```lua
   -- ~/.hammerspoon/init.lua
   dofile(os.getenv("HOME") .. "/Code/voicemode/scripts/hammerspoon/voicemode-media-keys.lua")
   ```
   Substitute the real checkout path from step 3. Optional tuning (mention if
   the user asks for it, don't set unprompted):
   ```lua
   _G.voicemodeMediaKeys = {
     voicemodePath   = "/opt/homebrew/bin/voicemode",  -- absolute path, media-key handlers don't inherit shell PATH
     pauseEverything = true,   -- Play/Pause also toggles the media app (default false: VoiceMode-only)
   }
   ```
   Read the config file's own header comment
   (`scripts/hammerspoon/voicemode-media-keys.lua`) before writing — it documents
   every option and the current defaults, and may have changed since this
   reference was written.

5. **Reload Hammerspoon config** so the new file takes effect:
   ```bash
   hs -c 'hs.reload()'
   ```
   (Requires Hammerspoon's `hs` CLI — see the "hs CLI not found" note below.)

## The one step that needs the human

**Grant Accessibility.** This cannot be scripted — macOS requires an
interactive click in a system dialog. Tell the user explicitly:

> Open **System Settings → Privacy & Security → Accessibility**, and enable
> **Hammerspoon**. Hammerspoon should prompt for this automatically the first
> time it tries to install the event tap — if it doesn't, add it manually via
> the toggle.

This is the load-bearing step: without it, Hammerspoon's event tap cannot see
or swallow key events at all, and every other step above is a no-op. Some
setups also need **Input Monitoring** in the same pane.

**Make Hammerspoon a login item**, so the setup survives a reboot (also needs
the human, via System Settings → **General → Login Items** → add
Hammerspoon) — mention it, but it's lower priority than the Accessibility
grant. If skipped, the failure mode is silent: media keys just pass through
to Music/Spotify with no error, whenever Hammerspoon isn't running.

## Verify it worked

Run these and report the results back to the user — don't just say "done":

```bash
pgrep -x Hammerspoon                                              # running?
hs -c 'print(hs.accessibilityState())'                            # true = granted
hs -c 'print(_G.__voicemodeMediaKeys.tap:isEnabled())'            # true = tap live
```

If `hs.accessibilityState()` prints `false`, the setup is incomplete —
Accessibility hasn't been granted yet. Tell the user this specifically rather
than a generic "something's wrong"; it's almost always the fix.

Offline logic test (exercises the key-name normalization and command mapping
without needing a live Hammerspoon or a converse):
```bash
luajit scripts/hammerspoon/test_voicemode_media_keys.lua
```

Live check, if the user is willing: ask them to start a converse, then press
**Next** — it should cut the current utterance (barge) rather than skip a
music track. Check the Hammerspoon Console for a logged `barge` line to
confirm server-side, without relying on the user's report alone.

## Version note

The **Previous** (skip-back) key binding replays the assistant's recent
utterances (wired since VM-1919). If the user's checkout predates that, the
key shows a "replay not yet available" notice instead — update the checkout,
or fall back to the CLI: `voicemode control skip-back`.

## Troubleshooting

- **`hs` command not found:** Hammerspoon's CLI isn't installed. From the
  Hammerspoon menubar: **Preferences → General → Install Command Line Tool**.
  Without it you can still reload via the menubar's **Reload Config**, but you
  can't script the checks above — ask the user to click it, or check
  `~/.hammerspoon/hs/` conventions have changed.
- **Everything above ran clean but keys still do nothing:** almost always
  Accessibility (see Verify above) — check it before anything else.
- **Media keys report as `FAST`/`REWIND` instead of `NEXT`/`PREVIOUS`** (some
  keyboards, e.g. Logitech MX Keys Mini): the shipped config already
  normalizes both names, so this alone isn't the problem — but if a key still
  seems dead, have the user open the Hammerspoon Console and press it; it logs
  the raw `systemKey` name it saw.
