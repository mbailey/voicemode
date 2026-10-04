---
name: voicemode
description: Talk with the user by voice through the converse tool: speak, listen, run a short survey, pick or clone a voice, share the channel with other agents, recover when voice drops. Use when the user mentions voice, speaking, talking, listening, a voice name, an impression, or background music.
---

# VoiceMode

You speak with the `converse` tool. Its description and schema are the contract; this page is how to use it well. No `converse` in your tool list? See [recovery].

## How a conversation goes

- `converse("…")` speaks, then listens: the user's reply comes back as the result, and they never have to address you. The turn stays with you for as long as you keep listening: [linger].
- Narrate with `wait_for_response=false` and fire the work in the same response (Bash, Agent, Read…), so speech and action overlap. Then listen with the next call: a speak-only call leaves nobody listening.
- Short utterances, one question per turn. More than one thing to ask? `turns` runs them as a survey: [surveys].
- Leave `listen_duration_max` unset. The user owns that ceiling, and silence detection ends the turn for you.
- Leave `voice` unset unless asked; a name is lowercase with its prefix (`bm_daniel`, `af_sky`). Personas, cloning, impressions: [voices].
- Other agents on the channel: `hold_conch=true` when you will continue the thread; `wait_for_conch` to queue: [conch].
- "Hang on" or "wait" at the end of a reply pauses and re-listens on its own. For minutes, run `sleep N` as a background Bash call; converse again when it finishes.

## When something is off

- Tool missing, `-32000 Connection closed`, permission prompts, an empty reply after they spoke, misheard names: [recovery].
- Pause, barge in, replay or skip during a turn; media keys and Stream Deck: [controls].
- Background music: [music].

## References

Every bracketed name above is a file in `references/`; this list is here so the links render.

[conch]: references/conch.md
[controls]: references/controls.md
[linger]: references/linger.md
[music]: references/music.md
[recovery]: references/recovery.md
[surveys]: references/surveys.md
[voices]: references/voices.md
