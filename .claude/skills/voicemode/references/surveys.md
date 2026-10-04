---
name: surveys
description: Asking several questions in one converse call with turns; keeping a scripted sequence legible to the user, and reading what comes back.
---
A survey asks several questions in one call, one spoken turn each: announce the count first, acknowledge the answers at your next call.

# Surveys (the `turns` parameter)

`turns` scripts a sequence up front: `{"say": …}` speaks and advances, `{"ask": …}` speaks, listens and records the reply. Turns are pipelined (the next is synthesised while this one plays), so there is no dead air between questions. It is the one sanctioned way to ask more than one thing per call, and it is still one question per spoken turn.

The script advances on its own, without reacting to each answer, so the user cannot tell "heard you" from "moved on" unless you make it legible:

1. **Announce the count** with a leading say turn: "I've got three quick questions."
2. **Acknowledge at the top of your next call**, with content: "Got it: chicken, twice a week, no allergies." That cannot be pipelined mid-survey without dead air, so it belongs after.
3. **Keep it short**: about seven asks at most.
4. **Set no listening ceiling on the ask turns.** The user's configured default owns it.
5. `ack: true` (per turn, or call-level) plays a short cue when a reply is captured, so the user hears "heard" from "didn't hear".

What comes back: if any turn asks, a JSON string `{"survey": {"completed", "asked", "answered", "stopped_at", "turns": […]}}` with one entry per turn (`status`: spoken, answered, no_speech, tts_failed, stt_failed, not_reached; and `reply`). Re-ask the no_speech and not_reached turns in a follow-up call. Every reply is written to the conversation log as it arrives, so a killed call keeps the answers already given.

While it runs the user can skip-forward (done answering), skip-back or say "repeat" (hear it again), say "wait" (pause), or say only "break" / "stop the survey" (returns the replies so far and where it stopped). Those are the [controls](controls.md).
