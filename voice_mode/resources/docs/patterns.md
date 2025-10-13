# Voicemode Conversation Patterns

## Parallel Operations Pattern (RECOMMENDED)

When performing actions that don't require user confirmation, use `wait_for_response=False` to speak while simultaneously executing other tools. This creates natural, flowing conversations.

### Pattern
```python
converse("Status update", wait_for_response=False)
# Immediately run other tools in parallel
```

The speech plays while your actions execute simultaneously.

### Benefits
- No dead air during operations
- User knows what's happening
- More natural conversation flow
- Better user experience

## Parallel Pattern Examples

### Search narration
```python
converse("Searching for that file", wait_for_response=False)
# Immediately execute:
Grep(pattern="function_name", output_mode="files_with_matches")
```

### Processing update
```python
converse("Analyzing the screenshot", wait_for_response=False)
# Immediately execute:
Read(file_path="/path/to/screenshot.png")
```

### Creation status
```python
converse("Creating that document now", wait_for_response=False)
# Immediately execute:
Write(file_path="/path/to/file.md", content="...")
```

### Quick confirmation
```python
converse("Done! The file is saved", wait_for_response=False)
# No wait needed for simple confirmations
```

## When to Use Parallel Pattern

✅ **Use parallel pattern for:**
- File operations (reading, writing, searching)
- Data processing (analysis, computation)
- Status updates during long operations
- Confirmations that don't need response

❌ **Don't use parallel pattern for:**
- Questions requiring answers
- Confirmations needing user approval
- Error messages needing acknowledgment
- End of conversation farewells (unless doing cleanup)

## Emotional Speech Pattern

Use OpenAI's `gpt-4o-mini-tts` model with `tts_instructions` for emotional context.

### Excitement
```python
converse(
    "We did it!",
    tts_model="gpt-4o-mini-tts",
    tts_instructions="Sound extremely excited and celebratory"
)
```

### Sadness
```python
converse(
    "I'm sorry for your loss",
    tts_model="gpt-4o-mini-tts",
    tts_instructions="Sound gentle and sympathetic"
)
```

### Urgency
```python
converse(
    "Watch out!",
    tts_model="gpt-4o-mini-tts",
    tts_instructions="Sound urgent and concerned"
)
```

### Humor
```python
converse(
    "That's hilarious!",
    tts_model="gpt-4o-mini-tts",
    tts_instructions="Sound amused and playful"
)
```

**Note:** Emotional speech uses OpenAI API and incurs costs (~$0.02/minute)

## Speed Control Pattern

Adjust speech rate for different contexts.

### Normal speed (default)
```python
converse("This is normal speed")
```

### Faster speech (quick updates)
```python
converse("This is faster speech", speed=1.5)
```

### Double speed (very rapid)
```python
converse("This is double speed", speed=2.0)
```

### Slower speech (emphasis/clarity)
```python
converse("This is slower speech", speed=0.8)
```

**Note:** Works with both OpenAI and Kokoro providers

## VAD Aggressiveness Pattern

Adjust Voice Activity Detection based on environment.

### Quiet room - capture all speech
```python
converse("Let's have a conversation", vad_aggressiveness=0)
```

### Normal home/office (default)
```python
converse("Tell me about your day")  # Uses default (2)
```

### Noisy cafe/outdoors
```python
converse("Can you hear me?", vad_aggressiveness=3)
```

### Balanced for most cases
```python
converse("How are you?", vad_aggressiveness=2)
```

**Remember:**
- Lower values (0-1) = more permissive, may detect non-speech
- Higher values (2-3) = more strict, may miss soft speech

## Skip TTS Pattern

Use text-only mode for faster development iterations.

### Fast iteration mode
```python
converse("Processing your request", skip_tts=True)  # Text only
```

### Important announcement (always voice)
```python
converse("Warning: System will restart", skip_tts=False)
```

### Quick confirmation
```python
converse("Done!", skip_tts=True, wait_for_response=False)
```

### Follow user preference (default)
```python
converse("Hello")  # Uses VOICEMODE_SKIP_TTS setting
```

## Multi-step Conversation Pattern

Handle complex multi-turn conversations.

### Ask follow-up questions
```python
# First question
response1 = converse("What would you like to do?")

# Process response and ask follow-up
if "edit" in response1.lower():
    response2 = converse("Which file should I edit?")
    # Continue based on response2
```

### Confirm before action
```python
converse("I'll delete all temporary files. Is that okay?")
# Wait for confirmation before proceeding
```

### Provide progress updates
```python
converse("Starting backup process", wait_for_response=False)
# Do first part
converse("50% complete", wait_for_response=False)
# Do second part
converse("Backup complete!", wait_for_response=False)
```

## Error Handling Pattern

Communicate errors clearly.

### Simple error
```python
try:
    # Some operation
    pass
except Exception as e:
    converse(f"I encountered an error: {str(e)}. Would you like me to try again?")
```

### Provide alternatives
```python
converse("I couldn't find that file. Would you like me to search in a different directory?")
```

### Request clarification
```python
converse("I found multiple files with that name. Which one did you mean?")
```

## See Also
- `voicemode-quickstart` - Basic usage examples
- `voicemode-parameters` - Full parameter reference
- `voicemode-troubleshooting` - Common issues
