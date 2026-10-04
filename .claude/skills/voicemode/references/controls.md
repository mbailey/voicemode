---
name: controls
description: Pausing, barging in, replaying and skipping during a live converse turn; the control channel, Stream Deck buttons, macOS media keys through Hammerspoon, soundfonts.
---
While a turn is live the control channel takes pause, resume, stop, skip-forward and skip-back; bind them to buttons or to the media keys.

# Transport controls

`voicemode control pause | resume | stop | skip-forward | skip-back` drives a live converse turn: pause it, barge in (cut the utterance and take the mic), finish answering early, hear the question again. Enable it once with `VOICEMODE_CONTROL_CHANNEL_ENABLED=true` in `~/.voicemode/voicemode.env`; the server then binds `~/.voicemode/control.sock` for the turn. Ownership model, skip-back history and the raw socket protocol: `docs/reference/control-channel.md`.

- **Stream Deck**, or anything that runs a shell command: bind a button straight to `voicemode control skip-forward` and friends. No extra dependency.
- **macOS media keys** (▶❙❙ ⏭ ⏮) go through a Hammerspoon event tap that grabs the keys only while a turn is live, so music is untouched otherwise.

## Media keys: the agent's runbook (macOS)

Preflight: `uname -s` must be Darwin; `which voicemode`; `pgrep -x Hammerspoon`; `grep VOICEMODE_CONTROL_CHANNEL_ENABLED ~/.voicemode/voicemode.env`. Not macOS: stop, and point at skhd, xbindkeys or Karabiner in the control-channel reference.

1. `brew install --cask hammerspoon && open -a Hammerspoon` if it is not running (the first launch creates `~/.hammerspoon/`).
2. Enable the control channel (above): append the line, do not duplicate it.
3. Find the voicemode checkout, then append to `~/.hammerspoon/init.lua` (create it if absent; never overwrite an existing config): `dofile(os.getenv("HOME") .. "/Code/voicemode/scripts/hammerspoon/voicemode-media-keys.lua")` with the real path. The file's header comment documents its options (`voicemodePath`, `pauseEverything`); set none unprompted.
4. `hs -c 'hs.reload()'`. The `hs` CLI installs from Hammerspoon's Preferences → General → Install Command Line Tool; without it, Reload Config from the menubar.
5. **The human's step.** System Settings → Privacy & Security → Accessibility → enable Hammerspoon (some setups also need Input Monitoring). Without it nothing above does anything. Ask them to make Hammerspoon a login item too, or after a reboot the keys silently go back to the music app.

Verify and report the results, do not just say done: `pgrep -x Hammerspoon`; `hs -c 'print(hs.accessibilityState())'` must print true; `hs -c 'print(_G.__voicemodeMediaKeys.tap:isEnabled())'` true. Offline logic test: `luajit scripts/hammerspoon/test_voicemode_media_keys.lua`. Live: start a converse and have them press Next; it should barge, and the Hammerspoon console logs `barge`. Dead keys with everything else clean is almost always Accessibility. Keys reporting `FAST`/`REWIND` are already normalised. Skip-back replays recent utterances (since VM-1919); an older checkout shows a "replay not yet available" notice.

**Soundfonts** are the tones that play around tool use: `voicemode soundfonts on|off` (`docs/guides/soundfonts.md`).
