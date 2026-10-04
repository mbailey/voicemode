---
name: linger
description: After you speak, the user's next words are yours without your name; how the turn stays with you, when it lapses, and what a speak-only call leaves behind.
---
After you speak, the floor lingers with you: the user's next turn comes to you without your name, for as long as you keep listening.

# Linger

A `converse` call with `wait_for_response=true` (the default) speaks, then opens the microphone. Whatever the user says next is returned to you as the tool result. They do not say your name or pick an agent; speaking back is the address. That is the whole conversational contract, and it is why the defaults are right for a question.

The turn lingers only while a call is listening:

- **Speak-only** (`wait_for_response=false`) ends with nobody listening. The user's reply goes nowhere. Narrate, do the work, then call again with a question, or a plain "done" that listens.
- **Silence** ends a listening turn once the user stops, and the result carries their words. An empty result means they said nothing, or STT heard nothing ([recovery](recovery.md)): ask again or say what you will do next. Never invent a reply.
- **"Wait."** When a reply ends with "hang on", "give me a sec" or "wait", the call pauses for the configured `VOICEMODE_WAIT_DURATION` and listens again by itself. For a longer pause, `sleep N` in Bash, then converse again.
- **Several agents** share one channel through the conch, the floor lock. While you hold it the user's words reach you; when your call ends without `hold_conch` the floor lapses and another agent may take the next turn. Hold it when you will speak again straight away: [conch](conch.md).

A spoken reply arrives as a tool result, not as a user message. Act on it exactly as you would on typed text, including loading a skill it calls for. Keep each utterance short: the user is listening, not reading.
