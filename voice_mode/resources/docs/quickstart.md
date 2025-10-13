# Voicemode Quickstart

## Basic Usage

### Simple conversation
```python
converse("What's your name?")
```
System auto-selects voice and model.

### Make a statement and wait
```python
converse("Tell me more about that")
```

### Speak without waiting for response
```python
converse("Goodbye!", wait_for_response=False)
```

### User requests specific voice
```python
converse("Hello", voice="nova")
```
Only specify voice when explicitly requested by user.

## Common Patterns

### Quick confirmation (no response needed)
```python
converse("Done! The file is saved", wait_for_response=False)
```

### Ask a question (wait for answer)
```python
converse("Which file should I open?")
```

### Status update during work
```python
converse("Searching for that file now", wait_for_response=False)
# Then immediately run grep/search tools
```

## Privacy Note
Microphone access required when `wait_for_response=True`. Audio processed via STT service, not stored.

## See Also
- `voicemode-parameters` - Full parameter reference
- `voicemode-patterns` - Advanced conversation patterns
- `voicemode-languages` - Non-English language support
