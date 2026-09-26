## ADDED Requirements

### Requirement: Wake words and end words are configured strings, matched on recognised text, written as events, and interpreted by the model

VoiceMode SHALL let a user configure wake words and end words, per
machine and per agent, as plain strings. While `listen` runs, it SHALL
match them case-insensitively on the recognised text of partials and turns
and, on a match, SHALL write an `event` line naming the kind (`wake-word`
or `end-word`) and the word. An end word SHALL end the current turn and
cause `listen` to return with reason `end-word`. A wake word SHALL mark
the start of attention: it gates the partial return when `wake_on_partial`
is on (see *listen*), and it is available to the hook and the model as an
event. VoiceMode MUST NOT act on a control word beyond writing the event
and, for an end word, returning: what "hey Claude" means to the agent is
the agent's decision, read from the log. This change adds no acoustic
wake-word model; matching is on text. RULED in substance by Mike, voice
03:21-03:22 Thu 2026-09-24: *"we can have end words ... over, or over and
out, control words that signal different things. Might even make VoiceMode
activate: hey Claude might make it activate and start recording, pulling
together to send to you."* The default words are PROPOSED (Q4).

#### Scenario: An end word closes the turn

- GIVEN "over" is an end word and `listen` is running
- WHEN the speaker says "put it on the card, over"
- THEN a `turn` line holds "put it on the card"
- AND an `event` line holds `end-word: over`
- AND `listen` returns with reason `end-word`

#### Scenario: A wake word is an event, not an action

- GIVEN "hey claude" is a wake word and `wake_on_partial` is off
- WHEN the speaker says "hey Claude, remind me about the AdBlue"
- THEN an `event` line records the wake word
- AND `listen` does not return until the turn is aged
- AND the hook shows the event and the turn together

#### Scenario: Words are per agent

- GIVEN Cora's config adds the wake word "cora" and Pip's adds "pip"
- WHEN the speaker says "Pip, are you there"
- THEN Pip's listen writes a `wake-word` event
- AND Cora's listen writes none
