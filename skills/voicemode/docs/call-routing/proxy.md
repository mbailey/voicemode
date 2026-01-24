# Voice Proxy Pattern

Relay voice conversations for agents without direct audio access.

## Overview

The voice proxy pattern allows one agent to speak on behalf of another. This is useful when:

- A **worker agent** doesn't have the voicemode skill loaded
- An agent is running on a **remote machine** without audio devices
- You want to **centralize voice** through a single agent
- An agent's response needs **human review** before speaking

## How It Works

```
+------------------+    text     +------------------+    audio    +--------+
| Worker Agent     | ---------> | Proxy Agent      | ---------> | User   |
| (no voice)       |            | (has voice)      |            |        |
+------------------+            +------------------+            +--------+
                                       |
                                       v
                               voicemode:converse()
```

The proxy agent:
1. Receives text from the worker (via shared file, message queue, or output monitoring)
2. Speaks the text using converse
3. Optionally relays the user's response back to the worker

## Use Cases

### 1. Worker Without Voice Skill

A worker focused on a specific task doesn't need voicemode overhead:

```python
# Spawn worker for code review (no voice) - mechanism depends on your setup
spawn_agent(
    path="/path",
    name="reviewer",
    prompt="Review the PR and write findings to /tmp/review-output.txt"
)

# Primary agent monitors output and speaks it
while True:
    output = read_file("/tmp/review-output.txt")
    if output:
        voicemode:converse(f"The reviewer says: {output}")
        clear_file("/tmp/review-output.txt")
```

### 2. Remote Agent Without Audio

An agent on a remote server can't access local audio devices:

```python
# Assistant connects to remote agent via SSH
remote_response = Bash(command='ssh server "claude --query \"What is the status?\""')

# Assistant speaks the response locally
voicemode:converse(f"The remote agent reports: {remote_response}")
```

### 3. Human Review Before Speaking

Filter or review agent output before speaking:

```python
# Worker generates response
worker_output = get_worker_output()

# Human can review in console before it's spoken
print(f"Worker wants to say: {worker_output}")
if user_approves():
    voicemode:converse(worker_output)
```

## Implementation Patterns

### File-Based Relay

Simple and reliable for local agents:

```python
# Worker writes to shared file
OUTBOX = "/tmp/voice-outbox.txt"
INBOX = "/tmp/voice-inbox.txt"

# Worker side (no voice)
def say_via_proxy(message):
    write_file(OUTBOX, message)
    # Wait for response
    while not exists(INBOX):
        sleep(0.5)
    response = read_file(INBOX)
    delete_file(INBOX)
    return response

# Proxy side (has voice)
def relay_loop():
    while True:
        if exists(OUTBOX):
            message = read_file(OUTBOX)
            delete_file(OUTBOX)
            response = voicemode:converse(message)
            write_file(INBOX, response)
        sleep(0.5)
```

### Output Monitoring

Watch agent output for speech markers:

```python
# Worker marks speech with special prefix
print("SPEAK: I've finished the analysis")

# Proxy monitors output (use your orchestration system's output stream)
for line in monitor_agent_output("worker"):
    if line.startswith("SPEAK: "):
        message = line[7:]  # Remove prefix
        voicemode:converse(message, wait_for_response=False)
```

### Message Queue

For complex multi-agent systems:

```python
# Using a simple queue file
import json

QUEUE = "/tmp/voice-queue.json"

# Worker enqueues message
def enqueue_speech(message, wait_for_response=False):
    queue = read_json(QUEUE) or []
    queue.append({
        "message": message,
        "wait": wait_for_response,
        "from": "worker-1"
    })
    write_json(QUEUE, queue)

# Proxy processes queue
def process_queue():
    queue = read_json(QUEUE) or []
    for item in queue:
        response = voicemode:converse(
            item["message"],
            wait_for_response=item["wait"]
        )
        if item["wait"]:
            notify_agent(item["from"], response)
    write_json(QUEUE, [])  # Clear queue
```

## Voice Differentiation

When proxying for multiple agents, indicate who's speaking:

```python
def relay_with_attribution(agent_name, message):
    # Option 1: Announce the speaker
    voicemode:converse(f"{agent_name} says: {message}")

    # Option 2: Use different voice per agent
    voices = {"worker-1": "alloy", "worker-2": "echo"}
    voicemode:converse(message, voice=voices.get(agent_name, "nova"))

    # Option 3: Both
    voicemode:converse(
        f"{agent_name}: {message}",
        voice=voices.get(agent_name)
    )
```

## Bidirectional Relay

For agents that need to hear user responses:

```python
# Proxy relays both directions
def bidirectional_relay(worker_outbox, worker_inbox):
    while True:
        # Check for worker message
        if exists(worker_outbox):
            message = read_file(worker_outbox)
            delete_file(worker_outbox)

            # Speak and get response
            user_response = voicemode:converse(message, wait_for_response=True)

            # Relay response back to worker
            write_file(worker_inbox, user_response)

        sleep(0.5)
```

## Best Practices

1. **Clear attribution**: Make it obvious who's speaking when proxying
2. **Minimal latency**: Process messages quickly to maintain conversation flow
3. **Error handling**: Handle cases where the worker doesn't respond
4. **Queue management**: Prevent queue buildup with timeouts
5. **Voice consistency**: Use the same voice for the same agent
6. **Acknowledge receipt**: Let workers know their message was spoken

## Limitations

- **Added latency**: Proxy adds delay to the conversation
- **Lost context**: Proxy may not understand worker's full context
- **Single point of failure**: If proxy dies, voice is lost
- **Complexity**: More moving parts than direct voice

## When to Use vs Direct Handoff

| Scenario | Use Proxy | Use Direct Handoff |
|----------|-----------|-------------------|
| Worker is short-lived | Yes | No |
| Worker needs voice skill | No | Yes |
| Remote agent | Yes | No |
| Simple status updates | Yes | No |
| Interactive conversation | No | Yes |
| Human review needed | Yes | No |

## Related Patterns

- **[Handoff](./handoff.md)**: Direct voice transfer between agents
- **[Call Routing Overview](./README.md)**: All routing patterns
- **[Voicemail](./voicemail.md)**: Async message passing (planned)
