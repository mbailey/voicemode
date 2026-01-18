# Call Routing

Voice conversation routing patterns for multi-agent VoiceMode systems.

## Overview

Call routing enables sophisticated voice conversation management across multiple Claude Code agents. Inspired by traditional telephony systems, these patterns provide:

- **Seamless transfers** between agents
- **Coordinated speaking** to prevent audio conflicts
- **Async messaging** when agents are busy
- **Operator capabilities** for voice-controlled routing

## Patterns

| Pattern | Description | Status |
|---------|-------------|--------|
| [Handoff](./handoff.md) | Transfer voice to another agent | Documented |
| [Hand-back](./handoff.md#hand-back-process) | Return voice to original agent | Documented |
| [Proxy](./proxy.md) | Relay for agents without voice | Documented |
| [Coordination](./coordination.md) | The Conch - prevent overlapping speech | Planned |
| [Call Waiting](./call-waiting.md) | Notify when another agent wants to speak | Planned |
| [Voicemail](./voicemail.md) | Leave messages for busy agents | Planned |

## Quick Reference

### Basic Handoff

```python
# 1. Announce
voicemode:converse("Transferring you to the project foreman.", wait_for_response=False)

# 2. Spawn with voice instructions
Bash(command='agents minion start /path --prompt "Load voicemode skill, use converse to greet user"')

# 3. Go quiet - let new agent take over
```

### Basic Hand-back

```python
# 1. Announce return
voicemode:converse("Transferring you back to Cora.", wait_for_response=False)

# 2. Stop conversing and exit
```

## Architecture

```
+------------------------------------------------------------------+
|                    Personal Assistant (Cora)                      |
|                     Voice: nova (familiar)                        |
|                                                                   |
|  - Routes conversations to appropriate foremen                    |
|  - Maintains overview of all projects                             |
|  - Resumes after foreman completes work                           |
+------------------------------------------------------------------+
                              |
                    Handoff (announce -> spawn -> quiet)
                              |
        +---------------------+---------------------+
        v                     v                     v
+---------------+   +---------------+   +---------------+
| VoiceMode     |   | Agents        |   | Taskmaster    |
| Foreman       |   | Foreman       |   | Foreman       |
| Voice: alloy  |   | Voice: onyx   |   | Voice: echo   |
|               |   |               |   |               |
| Deep context  |   | Deep context  |   | Deep context  |
| Project focus |   | Project focus |   | Project focus |
+---------------+   +---------------+   +---------------+
        |                     |                     |
        +---------------------+---------------------+
                              |
                    Hand-back (announce -> quiet -> exit)
                              |
                              v
                    Personal Assistant resumes
```

## Key Concepts

### The Operator Role

The personal assistant naturally serves as an "operator" - like a telephone switchboard:

- Knows who's available
- Routes calls to appropriate agents
- Can relay messages between agents
- Manages conversation flow

### One Speaker at a Time

Critical rule: **Only one agent should use converse at a time.**

Without coordination:
- Multiple TTS streams compete for audio output
- User hears cacophony of overlapping voices
- STT picks up agent speech instead of user

With coordination (The Conch):
- Agents acquire a lock before speaking
- Waiting agents queue politely
- User hears clear, sequential conversation

### Voice Identity

Different voices signal different agents:
- User knows who they're talking to
- Handoffs are audible, not just announced
- Creates natural conversation rhythm

## Implementation Status

| Component | Status | Task |
|-----------|--------|------|
| Handoff documentation | Complete | VM-293 |
| Hand-back documentation | Complete | VM-293 |
| Proxy documentation | Complete | VM-293 |
| The Conch (coordination) | Planned | VM-326 |
| Call waiting beeps | Planned | VM-326 |
| Voicemail | Planned | VM-326 |
| Operator patterns | Planned | VM-326 |

## Related Resources

- [VM-293: Voice Handoff Documentation](~/tasks/projects/voicemode/VM-293_docs_document-voice-handoff-pattern-in-voicemode-skill-how-to-transfer-voice-conversation-between-agents/)
- [VM-326: The Conch Epic](~/tasks/projects/voicemode/VM-326_feat_the-conch-multi-agent-voice-coordination-to-prevent-overlapping-speech/)
- [AG-114: Handoff Architecture](~/tasks/projects/agents/AG-114_epic_personal-assistant-to-project-foreman-voice-handoff-architecture/)
