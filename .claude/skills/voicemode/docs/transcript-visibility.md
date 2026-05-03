# Transcript visibility — deep dive

The `## Transcript visibility` section in `SKILL.md` is the always-loaded summary. This file holds the detail you only need when something out of the ordinary comes up — modes, edge cases, worked examples, override phrasings.

## Why this exists

Newer Claude Code releases collapse MCP tool calls in the visible transcript. The spoken side of a `voicemode:converse` exchange — both the message you passed in and the user message that came back — disappears from the conversation record unless you mirror it as visible Markdown.

The fix is a soft instruction (this skill), not a hook or output style. Hooks can't directly write into the transcript at the moment the user reads it; output styles are too coarse-grained for "after tool X, print Y." A skill instruction matches how the model already produces visible text after a tool call returns, and inherits the right opt-out behaviour for free.

## When to echo

| Tool call shape | User message in result | Echo? |
|---|---|---|
| `wait_for_response=true` | yes | echo BOTH sides |
| `wait_for_response=true` | empty / transcription failure / timeout | NO echo (don't fabricate) |
| `wait_for_response=false` | (n/a — no listen window) | NO echo (no user message to surface) |

The assistant echo appears in the response that issues the converse call (immediately before the tool use). The user echo appears in the next assistant response (immediately after receiving the tool result).

## Worked example

In the response that issues the converse call:

```markdown
> **ASSISTANT (voicemode):** What would you like to work on next?
[voicemode:converse("What would you like to work on next?") tool call]
```

In the next response, after the tool result:

```markdown
> **USER (voicemode):** Let's pick up the auth refactor where we left off.

Sure — pulling up that branch now.
```

A future reader can reconstruct the full voice exchange from the visible blockquotes alone, without expanding any collapsed tool calls.

## Verbatim vs companion modes

Spoken content is prose by necessity — TTS doesn't read bullet points or headings. But the visible echo is rendered Markdown, so a long spoken sentence often reads much better in the transcript as a list.

| Mode | Description | Default for |
|---|---|---|
| **Verbatim** | Exact words spoken or heard, no reformatting. Faithful to the audio. | **User** echo. Rewriting the user's words risks distorting their intent. |
| **Companion** | Same content, Markdown-formatted: lists become bullets, multi-step reasoning becomes numbered steps, code references become inline code or fenced blocks, file paths get backticks, etc. | **Assistant** echo. You authored the prose and can faithfully render your own intent in better Markdown. |

### Companion is constrained

Same content, better formatting — that's it. Companion must NOT:

- Paraphrase or summarise to the point that meaning shifts
- Add information that wasn't in the spoken content
- Drop substantive content to make the echo "tidier"
- Change the tone (e.g. casual → formal)

If in doubt, fall back to verbatim. The constraint exists because companion mode is a presentation layer, not a chance to "improve" the conversation.

### Companion-mode worked example

A spoken assistant message like:

> *"Three options for you. One, triage TM-698 children — flip the nine inbox tasks to todo. Two, flesh out TM-720 — design the rename properly: scope, order, what breaks. Three, switch tracks to CC-164 — the settle skill still needs triage."*

…echoes in companion mode as:

```markdown
> **ASSISTANT (voicemode):**
> - **(1) Triage TM-698 children** — flip the nine inbox tasks to todo
> - **(2) Flesh out TM-720** — design the rename properly: scope, order, what breaks
> - **(3) Switch tracks to CC-164** — the settle skill still needs triage
```

Same content, same options, same emphasis — just a list instead of run-on prose.

## Per-turn and per-session overrides

Either side can be flipped:

| User says | Effect |
|---|---|
| *"Echo my last reply verbatim"* | Just that user echo flips, others stay at default. |
| *"Verbatim only from now on"* | Both sides flip to verbatim for the rest of the session. |
| *"Skip the assistant companion"* | Assistant echo flips to verbatim for the session. |
| *"Companion mode for me too"* | User echo flips to companion (rare — mainly when the user has spoken a long structured list and wants it formatted). |

## No double-echo

If the assistant message you pass to `converse` is identical to a sentence already written as visible prose in the same response, don't also produce a separate `> **ASSISTANT (voicemode):**` line — the prose already serves the same purpose.

The same rule applies to the user side: if you naturally quote the user's words back in your reasoning ("You said 'X', so..."), don't also add a separate `> **USER (voicemode):**` line for the same content. One visible record of each utterance is enough.

The common case is that the visible reasoning text and the spoken `message` argument differ — in that case both should appear.

## Opt-out phrasings

The behaviour is a default, not a hard rule. Honour any of these for the rest of the session:

- *"stop echoing"*
- *"drop the voicemode lines"*
- *"you don't need to repeat me"*
- *"no more transcript echoes"*

Resume only if the user asks.
