# macOS Media Keys Setup

Use your keyboard's media keys (▶❙❙ / ⏭ / ⏮) to control VoiceMode — pause,
barge in, or replay — without touching your music. This guide covers the
[Hammerspoon](https://www.hammerspoon.org/)-based setup on macOS: install →
configure → grant permission → verify.

**Why Hammerspoon?** macOS routes media keys straight to Music/Spotify. Making
them also drive VoiceMode needs an interceptor, and you don't want VoiceMode
permanently stealing your media keys — Hammerspoon's `hs.eventtap` can pass a
key through to your media app *or* swallow it, per-event, based on whether a
VoiceMode converse is currently live. When no converse is live, every key
behaves exactly as it did before you installed anything.

For the full ownership model (what each key does in each state, the
`pauseEverything` toggle, manual override, the skip-back replay buffer) see the
[Control Channel reference](../reference/control-channel.md#media-keys) — this
guide only covers getting it installed and working.

## 1. Install Hammerspoon

```bash
brew install --cask hammerspoon
```

Launch it once from `/Applications` so it creates its config directory
(`~/.hammerspoon/`) and shows its menubar icon.

## 2. Enable the control channel

VoiceMode only opens the control socket when told to. Add this to
`~/.voicemode/voicemode.env`:

```bash
VOICEMODE_CONTROL_CHANNEL_ENABLED=true
```

Without this, the socket (`~/.voicemode/control.sock`) is never bound, and the
Hammerspoon config can never see a converse as "live" — media keys will
install cleanly but silently do nothing for VoiceMode.

## 3. Load the config

VoiceMode ships the Hammerspoon config in its own repo checkout:
[`scripts/hammerspoon/voicemode-media-keys.lua`](https://github.com/mbailey/voicemode/blob/master/scripts/hammerspoon/voicemode-media-keys.lua).
`dofile` it from `~/.hammerspoon/init.lua`, pointing at wherever you checked
out `voicemode`:

```lua
-- ~/.hammerspoon/init.lua
-- Optional config (all keys have sane defaults):
-- _G.voicemodeMediaKeys = {
--   voicemodePath   = "/opt/homebrew/bin/voicemode",
--   pauseEverything = true,   -- Play/Pause also toggles your media app (default false)
-- }
dofile(os.getenv("HOME") .. "/Code/voicemode/scripts/hammerspoon/voicemode-media-keys.lua")
```

Adjust the path to match your checkout (`git_url:
github.com/mbailey/voicemode`). Then reload: click the Hammerspoon menubar
icon → **Reload Config** (or run `hs.reload()` from the Hammerspoon Console).

## 4. Grant Accessibility (load-bearing step)

System Settings → **Privacy & Security → Accessibility** → enable
**Hammerspoon**.

This is the step that actually matters — without it, Hammerspoon's event tap
cannot see or swallow key events at all, and nothing in steps 1–3 will have
any effect. Hammerspoon prompts for this on first run; if you missed the
prompt, add it manually via the toggle above. Some setups also need **Input
Monitoring** (same Privacy & Security pane).

## 5. Keep Hammerspoon running (login item)

The event tap only exists while Hammerspoon itself is running — it's a GUI
app, not a background daemon. If Hammerspoon quits or hasn't started, media
keys silently pass straight through to Music/Spotify and VoiceMode never sees
them. There's no error; the keys just do nothing for VoiceMode.

Add Hammerspoon as a login item so it survives a reboot: System Settings →
**General → Login Items** → add Hammerspoon (or run `open -a Hammerspoon` to
start it right now).

*(Stream Deck buttons don't need this — they shell out to `voicemode control`
directly and never touch Hammerspoon. So a working Stream Deck with dead media
keys is the tell-tale sign Hammerspoon isn't running.)*

## Verify

1. **Is Hammerspoon running?** `pgrep -x Hammerspoon` should print a PID (or
   look for the `VM⌨︎` item in the menubar).
2. **Is the event tap live?** From the Hammerspoon Console:
   ```
   hs -c 'print(_G.__voicemodeMediaKeys.tap:isEnabled())'
   ```
   should print `true`.
3. **Is Accessibility actually granted?**
   ```
   hs -c 'print(hs.accessibilityState())'
   ```
4. **No converse running:** press a media key — behavior is unchanged, keys
   go straight to your music app.
5. **Converse live** (start one, let VoiceMode speak): **Next** cuts it off
   (barge); **Play/Pause** pauses VoiceMode (and your media app too, if you
   set `pauseEverything = true`).
6. Watch the **Hammerspoon Console** — it logs
   `[voicemode-media-keys] started (...)` on load and a line for each action
   (`barge`, `pause`, `resume`) as you press keys.
7. Offline logic test, no Hammerspoon needed:
   ```bash
   luajit scripts/hammerspoon/test_voicemode_media_keys.lua
   ```

## Skip-back (Previous)

**Previous** replays what the assistant just said: the first press restarts
the current utterance, further presses step back through recent ones. It
replays cached audio only — no new agent turn, no model call. (Wired to
`voicemode control skip-back` since VM-1919; on older checkouts it was a
notice-only stub.)

## Troubleshooting

- **Nothing happens on any key press, ever (even with music):** Hammerspoon
  probably isn't running — check with `pgrep -x Hammerspoon` and start it
  (step 5).
- **Music still gets the key even mid-converse:** Accessibility likely isn't
  granted (step 4) — re-check the toggle, since macOS sometimes silently
  revokes it after an app update.
- **Keyboard is a Logitech MX Keys Mini (or similar) and keys don't register:**
  some keyboards report next/previous as `FAST`/`REWIND` instead of
  `NEXT`/`PREVIOUS`. The shipped config normalizes both, but if a key still
  seems to do nothing, open the Hammerspoon Console and check the `systemKey`
  name it reports for that press.

For everything else — the full ownership table, `pauseEverything` semantics,
the manual override hotkey, and the liveness signal — see the
[Control Channel reference](../reference/control-channel.md#media-keys).
