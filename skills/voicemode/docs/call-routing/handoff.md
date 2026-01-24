# Voice Handoff Pattern

Transfer voice conversations between Claude Code agents seamlessly.

## Overview

Voice handoff enables transferring an active voice conversation from one agent to another. This is essential for multi-agent workflows where:

- A **personal assistant** routes to **project foremen** for focused work
- A **foreman** delegates to **workers** for specific tasks
- An agent **hands back** control when their work is complete

## The TV Magazine Show Pattern

Think of voice handoff like a TV magazine show:

1. **Host (Personal Assistant)**: Manages the overall conversation, introduces topics
2. **Specialist Reporter (Project Foreman)**: Deep dives into specific subjects
3. **Viewer (User)**: Experiences seamless transitions between segments

The host doesn't disappear during a specialist segment - they step back and let the specialist take over, then smoothly resume when the segment ends.

## Hand-off Process

### Step 1: Announce the Transfer

Always tell the user what's happening before transferring:

```python
voicemode:converse(
    "Transferring you now to a foreman for the VoiceMode project.",
    wait_for_response=False
)
```

**Why announce?**
- Users need context about who they'll be talking to
- Prevents confusion when a different voice responds
- Creates natural conversation flow

### Step 2: Spawn the Receiving Agent

Start a new agent instance with explicit instructions to use voice. The spawning mechanism depends on your multi-agent setup (subprocess, orchestrator, etc.):

```
Spawn an agent for [project] with these instructions:

"The user has been transferred to you to help with [task context].
Load the voicemode skill with /voicemode:voicemode.
Then use the converse tool to greet them and ask how you can help."
```

**Key elements in the spawn prompt:**
- **Context**: Why the user is being transferred
- **Skill loading**: Explicit instruction to load voicemode
- **Action**: Tell them to use converse to speak
- **Greeting**: Have them introduce themselves
- **Return path**: Who to transfer back to (see below)

### Handoff Context

Include metadata so the receiving agent knows how to hand back:

```
You were called by [originator name].
When finished, announce "Transferring you back to [originator name]"
and signal completion via [signaling method].
```

**Recommended context to pass:**
| Field | Purpose | Example |
|-------|---------|---------|
| Originator name | For verbal announcement | "Cora", "the assistant" |
| Session ID | For direct messaging (if available) | `session_abc123` |
| Signaling method | How to notify completion | "exit", "write to /tmp/done" |

This enables the receiving agent to:
1. Address the originator by name when handing back
2. Optionally send a direct wake-up signal
3. Use the appropriate completion mechanism

### Step 3: Go Quiet

After spawning the new agent, **stop using the converse tool**:

- Only one agent should speak at a time
- Competing for audio creates chaos
- The receiving agent now owns the conversation

```python
# DON'T do this after handoff:
# voicemode:converse("Let me know if you need anything else!")  # BAD

# DO: Stay silent and let the new agent take over
```

### Step 4: Monitor (Optional)

If your orchestration system allows you to observe the receiving agent's interactions, you can confirm the handoff succeeded before fully going quiet.

**What to look for:**
- Skill loaded successfully
- First converse call made (confirms they're speaking)
- User response received (confirms audio round-trip works)

**Confirming handoff via converse:**

If you can observe the receiving agent's tool calls, watch for their first `converse` call. Once they've started speaking to the user, you know the handoff worked. This is more reliable than just watching for process startup.

**If handoff fails:**

If the receiving agent doesn't start speaking within a reasonable time:
- Resume the conversation yourself
- Apologize and explain there was an issue
- Either retry the handoff or continue directly

## Hand-back Process

When the receiving agent's work is complete, they must:
1. Announce the return to the user
2. Signal the originating agent to resume
3. Go quiet

### Step 1: Announce the Return

Use the originator's name (passed during handoff):

```python
voicemode:converse(
    "I've finished reviewing the task. Transferring you back to Cora.",
    wait_for_response=False
)
```

### Step 2: Signal the Originating Agent

The originating agent needs to know when to resume speaking. Choose a signaling method based on your orchestration system:

| Method | How It Works | Best For |
|--------|--------------|----------|
| **Process exit** | Originator waits for subprocess to end | Simple spawning |
| **File signal** | Write to agreed-upon path (e.g., `/tmp/handback-ready`) | Any setup |
| **Direct message** | Send to originator's session ID | Frameworks with messaging |
| **Status polling** | Originator polls for "completed" status | Orchestration systems |

**Example: File-based signaling**
```python
# Receiving agent signals completion
write_file("/tmp/handback-ready", "done")

# Originating agent detects and resumes
while not exists("/tmp/handback-ready"):
    sleep(1)
delete_file("/tmp/handback-ready")
voicemode:converse("I'm back! How did it go with the project agent?")
```

**Example: Process-based (simplest)**
```python
# Originating agent spawns and waits
process = spawn_agent(...)
process.wait()  # Blocks until receiving agent exits
voicemode:converse("Welcome back! The project agent has finished.")
```

### Step 3: Go Quiet and Exit

After signaling, stop using converse immediately:

```python
# Signal sent, now go quiet
# Exit or idle - originating agent takes over
```

**Important:** The receiving agent must not call converse after signaling, or audio will conflict with the resuming originator.

## Complete Example

### Primary Agent Initiating Handoff

```python
# User asks to work on a project
user_request = "I want to work on the voice handoff documentation"

# Announce transfer
voicemode:converse(
    "Great! Let me transfer you to a project agent for VoiceMode.",
    wait_for_response=False
)

# Spawn project agent with different voice (mechanism depends on your setup)
# Key: include handoff context in the prompt
spawn_agent(
    project="~/Code/voicemode",
    prompt="""The user wants to work on voice handoff documentation.

    HANDOFF CONTEXT:
    - You were called by: Cora (the personal assistant)
    - When finished: Announce "Transferring you back to Cora" then exit

    Load the voicemode skill with /voicemode:voicemode.
    Use converse to greet the user and ask which aspect of handoff docs they'd like to focus on.""",
    env={"VOICEMODE_TTS_VOICE": "alloy"}  # Different voice
)

# Go quiet while project agent works
# Wait for project agent to exit, then resume
process.wait()
voicemode:converse("Welcome back! How did it go with the project agent?")
```

### Project Agent Greeting and Working

```python
# Project agent's first action after loading skill
voicemode:converse(
    "Hey! I'm the VoiceMode project agent. I understand you want to work on handoff documentation. Would you like to focus on the hand-off process, hand-back process, or the examples section?",
    wait_for_response=True
)

# Continue conversation based on response
# ... do work ...
```

### Project Agent Handing Back

```python
# Work complete - use originator name from handoff context
voicemode:converse(
    "I've updated the handoff documentation and committed the changes. Transferring you back to Cora.",
    wait_for_response=False
)

# Exit cleanly - this signals Cora to resume
# (Cora is waiting on process.wait())
```

## Voice Configuration

### Different Voices for Different Agents

Make handoffs audible by using distinct voices:

| Agent Type | Suggested Voice | Why |
|------------|-----------------|-----|
| Primary/Orchestrator | User preference (e.g., `nova`) | Familiar, comfortable |
| Project Agent | `alloy` or `onyx` | Professional, distinct |
| Task Agent | `echo` or `fable` | Different again |

### Setting Voice per Agent

**Via environment variable (when spawning):**
```bash
VOICEMODE_TTS_VOICE=alloy  # Set before spawning agent
```

**Via project .voicemode file:**
```bash
# In project root
echo "VOICEMODE_TTS_VOICE=onyx" > .voicemode
```

**Via converse parameter:**
```python
voicemode:converse("Hello!", voice="alloy", tts_provider="kokoro")
```

### Voice Fallback Chain

VoiceMode uses `VOICEMODE_VOICES` for fallback:
```bash
# Try Kokoro's af_alloy first, fall back to OpenAI's alloy
export VOICEMODE_VOICES=af_alloy,alloy
```

## Troubleshooting

### New Agent Doesn't Speak

1. **Check skill loaded**: Look for "Successfully loaded skill" in output
2. **Verify services**: `voicemode:service("whisper", "status")`
3. **Check prompt**: Ensure instructions say to use converse

### Audio Conflicts

1. **Multiple agents speaking**: Only one should have converse active
2. **Check for competing calls**: Search output for "converse" calls
3. **Use The Conch**: See [multi-agent coordination](./coordination.md)

### User Can't Hear New Agent

1. **Check TTS service**: `voicemode:service("kokoro", "status")`
2. **Verify audio output**: Same device as before handoff?
3. **Check voice setting**: Is the voice available?

### Handoff Feels Abrupt

1. **Add context**: More detail in announcement
2. **Warm greeting**: Have receiving agent introduce themselves
3. **Slower pace**: Add brief pauses if needed

## Best Practices

1. **Always announce**: Never transfer without telling the user
2. **Provide context**: Tell the receiving agent why the user is coming
3. **One speaker**: Go completely quiet after handoff
4. **Distinct voices**: Make it obvious who's speaking
5. **Graceful exits**: Announce before handing back
6. **Monitor first few**: Confirm handoffs work before going fully async

## Related Patterns

- **[Call Routing Overview](./README.md)**: All routing patterns
- **[Voice Proxy](./proxy.md)**: Relay for agents without voice
- **[Multi-Agent Coordination](./coordination.md)**: The Conch lock system (planned)
- **[Call Waiting](./call-waiting.md)**: Handling multiple waiting agents (planned)
- **[Voicemail](./voicemail.md)**: Async message passing (planned)

