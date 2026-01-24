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

You can watch the new agent's output to confirm the handoff succeeded. Use your orchestration system's monitoring capabilities to check the receiving agent's output.

**What to look for:**
- Skill loaded successfully
- First converse call made
- User response received (confirms audio is working)

## Hand-back Process

When the receiving agent's work is complete:

### Step 1: Announce the Return

```python
voicemode:converse(
    "I've finished reviewing the task. Transferring you back to Cora.",
    wait_for_response=False
)
```

### Step 2: Stop Conversing

After announcing, don't call converse again:

```python
# Final message sent, now go quiet
# Let the original agent resume
```

### Step 3: Exit or Idle

The agent can:
- Exit cleanly (session ends)
- Go idle (available for future work)
- Signal completion through a status file or message

The original agent detects this through:
- Your orchestration system's status monitoring
- Polling output for completion signals
- Watching for process exit

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
# Key: include voice instructions in the prompt
spawn_agent(
    project="~/Code/voicemode",
    prompt="""The user wants to work on voice handoff documentation.
    Load the voicemode skill with /voicemode:voicemode.
    Use converse to greet the user and ask which aspect of handoff docs they'd like to focus on.""",
    env={"VOICEMODE_TTS_VOICE": "alloy"}  # Different voice
)

# Go quiet - project agent takes over
# Monitor in background if needed
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
# Work complete
voicemode:converse(
    "I've updated the handoff documentation and committed the changes. Transferring you back to the assistant.",
    wait_for_response=False
)

# Exit or go idle - primary agent resumes
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

