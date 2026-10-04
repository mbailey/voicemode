---
name: listening
description: Waiting for the user's reply: wait_for_response and its default, when to speak without listening, how the turn stays with you, and the listening knobs (floor, ceiling, silence detection, a long pause).
---
After you speak, `converse` listens: the user's next words come to you without your name, for as long as a call is listening.

# Listening

## `wait_for_response`

The default is `true`: a `converse` call speaks, then opens the microphone, and whatever the user says next is returned to you as the tool result. They do not say your name or pick an agent; speaking back is the address. That is the whole conversational contract, and it is why the default is right for a question.

Set it `false` to speak without listening: a narration before work you are about to start, a line of progress in the middle of it, a "done" you will follow with a question. A speak-only call ends with nobody listening, so the user's reply goes nowhere; call again with a question, or a plain "done" that listens.

## The other knobs

- **Silence** ends a listening turn once the user stops, and the result carries their words. An empty result means they said nothing, or STT heard nothing ([recovery](recovery.md)): ask again or say what you will do next. Never invent a reply.
- **`listen_duration_min`**, the floor: silence may not end the turn before it. Raise it when the user needs thinking time, e.g. after you read them a long list. It cannot cut an answer short.
- **`listen_duration_max`**, the ceiling: leave it unset. The user's `VOICEMODE_DEFAULT_LISTEN_DURATION` applies, and a value you pass replaces theirs without notice. Set it only for a need you can say out loud, e.g. with `disable_silence_detection=true` for a diagnostic, when it is the only thing that ends the turn.
- **`vad_aggressiveness`**, how strict voice detection is: leave it alone unless silence detection keeps ending the turn in a noisy room, or never ends it in a quiet one.
- **"Wait."** When a reply ends with "hang on", "give me a sec" or "wait", the call pauses for the configured `VOICEMODE_WAIT_DURATION` and listens again by itself. For a longer pause, run `sleep N` as a background Bash call (`run_in_background: true`): Claude Code refuses a long foreground sleep, and the background one wakes you when it ends. Then converse again.
- **Several agents** share one channel through the conch, the floor lock. While you hold it the user's words reach you; when your call ends without `hold_conch` the floor lapses and another agent may take the next turn. Hold it when you will speak again straight away: [conch](conch.md).

A spoken reply arrives as a tool result, not as a user message. Act on it exactly as you would on typed text, including loading a skill it calls for. Keep each utterance short: the user is listening, not reading.
