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
voicemode:converse("Transferring you to the project agent.", wait_for_response=False)

# 2. Spawn with voice instructions (mechanism depends on your setup)
spawn_agent(path="/path", prompt="Load voicemode skill, use converse to greet user")

# 3. Go quiet - let new agent take over
```

### Basic Hand-back

```python
# 1. Announce return
voicemode:converse("Transferring you back to the assistant.", wait_for_response=False)

# 2. Stop conversing and exit
```

## Architecture

```
+------------------------------------------------------------------+
|                    Primary Agent (Orchestrator)                   |
|                      Voice: nova (familiar)                       |
|                                                                   |
|  - Routes conversations to appropriate project agents             |
|  - Maintains overview of all projects                             |
|  - Resumes after project agent completes work                     |
+------------------------------------------------------------------+
                              |
                    Handoff (announce -> spawn -> quiet)
                              |
        +---------------------+---------------------+
        v                     v                     v
+---------------+   +---------------+   +---------------+
| Project A     |   | Project B     |   | Project C     |
| Agent         |   | Agent         |   | Agent         |
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
                      Primary agent resumes
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

| Component | Status |
|-----------|--------|
| Handoff documentation | Complete |
| Hand-back documentation | Complete |
| Proxy documentation | Complete |
| The Conch (coordination) | Planned |
| Call waiting beeps | Planned |
| Voicemail | Planned |
| Operator patterns | Planned |
