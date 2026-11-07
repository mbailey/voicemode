---
name: voices
description: Choosing a voice for converse; names and their prefixes, the voice://voices resource, personas on disk, and speaking in a cloned voice.
---
Omit voice unless asked. A name is lowercase like af_sky; voice://voices lists them; a persona README says how that voice speaks.

# Voices

- **Default**: leave `voice` unset and the configured default speaks. Set it when the user asks, or to differ from another agent's voice ([conch](conch.md)).
- **Names are lowercase with underscores**: `af_sky`, `bm_daniel`; Kokoro rejects `AF_Sky`. The prefix is language and gender: `af_` American female, `am_` American male, `bf_` British female, `bm_` British male. OpenAI voices are plain words (`nova`, `shimmer`).
- **What is available**: read the MCP resource `voice://voices` (JSON; `voice://voices/{provider}` filters by backend). The `voice_registry` tool, where enabled, returns the same list as prose.
- **Personas**: a voice may have a character sheet at `~/.voicemode/voices/<name>/README.md` (grouped voices `<group>/<name>/README.md`; index `~/.voicemode/voices/PERSONAS.md`): who they are, how they speak, sample lines. Read it before speaking in character. Not every voice has one; fall back to the bare voice.
- **Cloned voices (impressions)**: a profile name under `~/.voicemode/voices/` routes to the local mlx-audio service by itself; an absolute `.wav` path clones from that clip directly. Pass `ref_text` (the clip's transcript, as text or a file path) or the model transcribes the clip itself and may stammer. Adding one: [impressions](impressions.md).
- **Tone and pace**: `tts_instructions` works only with `tts_model="gpt-4o-mini-tts"` (OpenAI, metered). `speed` runs 0.25 to 4.0.
- **Other languages**: `voicemode://docs/languages`.
