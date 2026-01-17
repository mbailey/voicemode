# Third-Party Integration: Delayed Recording Control

This document proposes a third-party integration mechanism for VoiceMode that allows external tools to control when voice recording begins after TTS completes. This addresses the current behavior where recording starts immediately after Claude speaks, enabling more sophisticated interaction patterns.

## Table of Contents

- [Problem Statement](#problem-statement)
- [Current Behavior](#current-behavior)
- [Proposed Solution](#proposed-solution)
- [Integration Approaches](#integration-approaches)
- [Implementation Options](#implementation-options)
- [API Specification](#api-specification)
- [Usage Examples](#usage-examples)
- [Security Considerations](#security-considerations)
- [Migration Path](#migration-path)

## Problem Statement

### Current Limitation

VoiceMode currently starts recording user input immediately after TTS playback completes with only a brief 0.5-second pause. While this creates a natural conversation flow, it lacks flexibility for scenarios where:

1. **Processing Time Needed**: Claude needs time to execute commands before listening
2. **Multi-Agent Coordination**: Other agents need to complete actions before user responds
3. **Visual Feedback**: UI needs to update before accepting user input
4. **External State**: Third-party systems need to signal readiness
5. **Automated Workflows**: Scripts need to coordinate with voice interactions

### Use Cases

**Example 1: Code Execution**
```
Claude: "I'll run those tests now."
[TTS completes]
[DESIRED: Wait for tests to finish]
[CURRENT: Immediately starts recording]
[Tests are still running, user doesn't know when to speak]
```

**Example 2: File Operations**
```
Claude: "I've opened the file for you."
[TTS completes]
[DESIRED: Wait for file to open in editor]
[CURRENT: Immediately starts recording]
[User sees "opening..." and doesn't know if they can speak yet]
```

**Example 3: Multi-Agent Coordination**
```
Agent 1 (Voice): "Let me check with the search agent."
[TTS completes]
[Agent 2 performs search - takes 5 seconds]
[DESIRED: Wait until Agent 2 completes]
[CURRENT: Starts recording immediately]
[User hears nothing for 5 seconds, unclear if system is listening]
```

## Current Behavior

### Code Location

**File**: `voice_mode/tools/converse.py`
**Lines**: 1475-1499

```python
# Brief pause before listening
await asyncio.sleep(0.5)

# Play "listening" feedback sound
await play_audio_feedback(
    "listening",
    openai_clients,
    chime_enabled,
    "whisper",
    chime_leading_silence=chime_leading_silence,
    chime_trailing_silence=chime_trailing_silence
)

# Record response
logger.info(f"🎤 Listening for {listen_duration_max} seconds...")

# Log recording start
if event_logger:
    event_logger.log_event(event_logger.RECORDING_START)

record_start = time.perf_counter()
audio_data, speech_detected = await asyncio.get_event_loop().run_in_executor(
    None, record_audio_with_silence_detection, ...
)
```

### Current Flow Timeline

```
TTS Starts ━━━━━━━━━━━━━━━━▶ TTS Ends
                                 │
                                 ├─ 0.5s pause
                                 ├─ "listening" chime
                                 ▼
                           Recording Starts
                                 │
                                 ▼
                           [User must speak now]
```

### What We Need

```
TTS Starts ━━━━━━━━━━━━━━━━▶ TTS Ends
                                 │
                                 ├─ 0.5s pause
                                 ├─ Wait for signal ⏸️
                                 │  (third-party control)
                                 ├─ Signal received ✓
                                 ├─ "listening" chime
                                 ▼
                           Recording Starts
                                 │
                                 ▼
                           [User can speak]
```

## Proposed Solution

### Core Concept

Add a **recording gate** mechanism that allows third-party tools to control when recording begins after TTS completes. This gate can be:

1. **Signal-based**: Wait for external signal via file, socket, or HTTP
2. **Callback-based**: Python callback function registered by external code
3. **Condition-based**: Poll external condition until satisfied
4. **Time-based**: Configurable delay with optional override

### Design Principles

1. **Backward Compatible**: Default behavior unchanged (no signal = immediate recording)
2. **Opt-In**: Must explicitly enable external control
3. **Timeout Protection**: Always have max wait time to prevent hangs
4. **Clear Feedback**: User knows when system is waiting vs listening
5. **Multiple Mechanisms**: Support different integration patterns
6. **Low Overhead**: Minimal performance impact when not in use

## Integration Approaches

### Approach 1: Signal File (Simplest)

**Concept**: VoiceMode waits for a specific file to appear or be modified

**Pros**:
- Simple to implement
- Language-agnostic (any tool can create files)
- No network dependencies
- Easy to debug (just check filesystem)

**Cons**:
- Filesystem I/O overhead
- Race conditions possible
- Cleanup required

**Implementation**:
```python
# In converse.py
if VOICEMODE_WAIT_FOR_SIGNAL:
    signal_file = Path(VOICEMODE_SIGNAL_FILE)
    timeout = VOICEMODE_SIGNAL_TIMEOUT
    start_time = time.time()
    
    # Play "waiting" chime
    await play_audio_feedback("waiting", ...)
    
    # Poll for signal file
    while not signal_file.exists():
        if time.time() - start_time > timeout:
            logger.warning("Signal timeout, starting recording anyway")
            break
        await asyncio.sleep(0.1)
    
    # Clean up signal file
    if signal_file.exists():
        signal_file.unlink()

# Continue to "listening" chime and recording
```

**Usage**:
```bash
# Enable signal-based waiting
export VOICEMODE_WAIT_FOR_SIGNAL=true
export VOICEMODE_SIGNAL_FILE=/tmp/voicemode_ready
export VOICEMODE_SIGNAL_TIMEOUT=30

# Third-party tool signals readiness
touch /tmp/voicemode_ready
```

### Approach 2: Unix Socket (Most Flexible)

**Concept**: VoiceMode listens on a Unix socket for "ready" message

**Pros**:
- Fast (no filesystem)
- Bidirectional communication possible
- Can pass metadata
- Standard IPC mechanism

**Cons**:
- More complex implementation
- Platform-specific (Unix/Linux only)
- Requires socket programming in external tool

**Implementation**:
```python
import socket
import asyncio

# In converse.py
async def wait_for_socket_signal(socket_path, timeout):
    """Wait for external signal via Unix socket"""
    try:
        # Create socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(socket_path)
        sock.listen(1)
        sock.settimeout(timeout)
        
        # Wait for connection
        logger.info(f"Waiting for signal on {socket_path}")
        conn, addr = sock.accept()
        
        # Read message
        data = conn.recv(1024).decode()
        conn.close()
        sock.close()
        os.unlink(socket_path)
        
        logger.info(f"Received signal: {data}")
        return True
    except socket.timeout:
        logger.warning("Socket signal timeout")
        return False
    finally:
        if os.path.exists(socket_path):
            os.unlink(socket_path)

# In converse.py
if VOICEMODE_WAIT_FOR_SIGNAL and VOICEMODE_SIGNAL_METHOD == "socket":
    await play_audio_feedback("waiting", ...)
    success = await wait_for_socket_signal(
        VOICEMODE_SIGNAL_SOCKET,
        VOICEMODE_SIGNAL_TIMEOUT
    )
```

**Usage**:
```bash
# Enable socket-based waiting
export VOICEMODE_WAIT_FOR_SIGNAL=true
export VOICEMODE_SIGNAL_METHOD=socket
export VOICEMODE_SIGNAL_SOCKET=/tmp/voicemode.sock

# Third-party tool sends signal
echo "ready" | socat - UNIX-CONNECT:/tmp/voicemode.sock
```

### Approach 3: HTTP Endpoint (Network-Friendly)

**Concept**: VoiceMode polls an HTTP endpoint until it returns success

**Pros**:
- Network-compatible (can be remote)
- Standard protocol (HTTP)
- Can return status/metadata
- Easy to test with curl

**Cons**:
- Requires HTTP server in third-party tool
- Network latency
- More overhead

**Implementation**:
```python
import httpx

# In converse.py
async def wait_for_http_signal(url, timeout):
    """Poll HTTP endpoint until it signals ready"""
    start_time = time.time()
    interval = 0.5  # Poll every 500ms
    
    async with httpx.AsyncClient() as client:
        while time.time() - start_time < timeout:
            try:
                response = await client.get(url, timeout=1.0)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("ready"):
                        logger.info(f"Received ready signal: {data}")
                        return True
            except Exception as e:
                logger.debug(f"HTTP poll error: {e}")
            
            await asyncio.sleep(interval)
    
    logger.warning("HTTP signal timeout")
    return False

# In converse.py
if VOICEMODE_WAIT_FOR_SIGNAL and VOICEMODE_SIGNAL_METHOD == "http":
    await play_audio_feedback("waiting", ...)
    success = await wait_for_http_signal(
        VOICEMODE_SIGNAL_URL,
        VOICEMODE_SIGNAL_TIMEOUT
    )
```

**Usage**:
```bash
# Enable HTTP-based waiting
export VOICEMODE_WAIT_FOR_SIGNAL=true
export VOICEMODE_SIGNAL_METHOD=http
export VOICEMODE_SIGNAL_URL=http://localhost:9999/voicemode/ready

# Third-party tool provides endpoint
# GET /voicemode/ready returns: {"ready": true, "message": "Tests complete"}
```

### Approach 4: Python Callback (Most Integrated)

**Concept**: External code registers Python callback function

**Pros**:
- Most flexible
- No IPC overhead
- Can pass complex data
- Programmatic control

**Cons**:
- Python-only
- Requires code integration
- More complex setup

**Implementation**:
```python
# In config.py
_recording_gate_callback = None

def register_recording_gate(callback):
    """Register callback that controls recording start
    
    Args:
        callback: Async function that returns True when ready to record
    """
    global _recording_gate_callback
    _recording_gate_callback = callback

def get_recording_gate():
    """Get registered recording gate callback"""
    return _recording_gate_callback

# In converse.py
async def wait_for_callback_signal(callback, timeout):
    """Wait for callback to signal ready"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            if await callback():
                return True
        except Exception as e:
            logger.error(f"Callback error: {e}")
            return False
        await asyncio.sleep(0.1)
    
    logger.warning("Callback signal timeout")
    return False

# In converse.py
callback = get_recording_gate()
if callback:
    await play_audio_feedback("waiting", ...)
    success = await wait_for_callback_signal(
        callback,
        VOICEMODE_SIGNAL_TIMEOUT
    )
```

**Usage**:
```python
# In external code
from voice_mode.config import register_recording_gate
import asyncio

async def my_gate():
    """Wait for tests to complete"""
    while test_runner.is_running():
        await asyncio.sleep(0.5)
    return True

# Register the gate
register_recording_gate(my_gate)

# Now converse() will wait for tests
await converse("I'll run those tests now.")
```

### Approach 5: Conch Extension (Most Integrated with Existing System)

**Concept**: Extend the existing Conch mechanism to support "sub-states"

**Pros**:
- Builds on existing infrastructure
- File-based (like Conch)
- Already handles locking and coordination
- Consistent with current architecture

**Cons**:
- Modifies core coordination system
- More complex than simple signal

**Implementation**:
```python
# In conch.py - add state field
class Conch:
    def set_state(self, state: str):
        """Set current state in lock file"""
        if not self._acquired:
            return
        
        data = json.loads(self.LOCK_FILE.read_text())
        data["state"] = state
        data["state_updated"] = datetime.now().isoformat()
        self.LOCK_FILE.write_text(json.dumps(data, indent=2))
    
    def get_state(self) -> Optional[str]:
        """Get current state"""
        try:
            data = json.loads(self.LOCK_FILE.read_text())
            return data.get("state")
        except:
            return None
    
    @classmethod
    def wait_for_state(cls, target_state: str, timeout: float) -> bool:
        """Wait for conch holder to reach specific state"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            state = Conch().get_state()
            if state == target_state:
                return True
            time.sleep(0.1)
        return False

# In converse.py
conch.set_state("tts_playing")
# ... TTS plays ...
conch.set_state("tts_complete")

# If external control enabled, wait for state change
if VOICEMODE_WAIT_FOR_SIGNAL:
    await play_audio_feedback("waiting", ...)
    conch.set_state("waiting_for_ready")
    
    # External tool will change state to "ready_to_record"
    success = await asyncio.to_thread(
        Conch.wait_for_state,
        "ready_to_record",
        VOICEMODE_SIGNAL_TIMEOUT
    )

conch.set_state("recording")
# ... recording happens ...
```

**Usage**:
```bash
# External tool monitors conch state
while true; do
    STATE=$(jq -r .state ~/.voicemode/conch 2>/dev/null)
    if [ "$STATE" = "waiting_for_ready" ]; then
        # Do work (run tests, open file, etc.)
        run_tests
        
        # Signal ready
        jq '.state = "ready_to_record"' ~/.voicemode/conch > /tmp/conch.tmp
        mv /tmp/conch.tmp ~/.voicemode/conch
        break
    fi
    sleep 0.1
done
```

## Implementation Options

### Recommendation: Multi-Method Support

Implement **multiple methods** with a configuration option to choose:

1. **Signal File** (default for simplicity)
2. **HTTP Polling** (for networked scenarios)
3. **Python Callback** (for integrated tools)
4. **Conch State** (for advanced coordination)

### Configuration

```bash
# Enable external control
export VOICEMODE_WAIT_FOR_SIGNAL=true

# Choose method
export VOICEMODE_SIGNAL_METHOD=file  # file, http, socket, callback, conch

# Method-specific configuration
# For file method:
export VOICEMODE_SIGNAL_FILE=/tmp/voicemode_ready

# For HTTP method:
export VOICEMODE_SIGNAL_URL=http://localhost:9999/ready

# For socket method:
export VOICEMODE_SIGNAL_SOCKET=/tmp/voicemode.sock

# Common configuration
export VOICEMODE_SIGNAL_TIMEOUT=30          # Max wait time in seconds
export VOICEMODE_SIGNAL_POLL_INTERVAL=0.1   # Polling interval in seconds
export VOICEMODE_SIGNAL_AUDIO_CUE=true      # Play "waiting" chime
```

### Code Structure

```python
# voice_mode/signal_gate.py (new file)
"""Recording signal gate - controls when to start recording after TTS"""

from enum import Enum
from typing import Optional, Callable, Awaitable
import asyncio

class SignalMethod(Enum):
    """Signal methods for recording gate"""
    NONE = "none"         # No signal, immediate recording
    FILE = "file"         # Wait for signal file
    HTTP = "http"         # Poll HTTP endpoint
    SOCKET = "socket"     # Unix socket
    CALLBACK = "callback" # Python callback
    CONCH = "conch"       # Conch state-based

class RecordingGate:
    """Controls when to start recording after TTS completes"""
    
    def __init__(self, method: SignalMethod, config: dict):
        self.method = method
        self.config = config
        self._callback: Optional[Callable[[], Awaitable[bool]]] = None
    
    async def wait_for_signal(self) -> bool:
        """Wait for external signal, returns True if received, False if timeout"""
        if self.method == SignalMethod.NONE:
            return True
        
        timeout = self.config.get("timeout", 30)
        
        if self.method == SignalMethod.FILE:
            return await self._wait_file(timeout)
        elif self.method == SignalMethod.HTTP:
            return await self._wait_http(timeout)
        elif self.method == SignalMethod.SOCKET:
            return await self._wait_socket(timeout)
        elif self.method == SignalMethod.CALLBACK:
            return await self._wait_callback(timeout)
        elif self.method == SignalMethod.CONCH:
            return await self._wait_conch_state(timeout)
        
        return False
    
    async def _wait_file(self, timeout: float) -> bool:
        """Wait for signal file"""
        # Implementation here
        pass
    
    async def _wait_http(self, timeout: float) -> bool:
        """Wait for HTTP endpoint"""
        # Implementation here
        pass
    
    # ... other methods ...

# In config.py
def get_recording_gate() -> RecordingGate:
    """Get configured recording gate"""
    if not VOICEMODE_WAIT_FOR_SIGNAL:
        return RecordingGate(SignalMethod.NONE, {})
    
    method = SignalMethod(VOICEMODE_SIGNAL_METHOD)
    config = {
        "timeout": VOICEMODE_SIGNAL_TIMEOUT,
        "poll_interval": VOICEMODE_SIGNAL_POLL_INTERVAL,
        "file": VOICEMODE_SIGNAL_FILE,
        "url": VOICEMODE_SIGNAL_URL,
        "socket": VOICEMODE_SIGNAL_SOCKET,
    }
    
    return RecordingGate(method, config)
```

## API Specification

### Configuration Variables

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `VOICEMODE_WAIT_FOR_SIGNAL` | bool | false | Enable external signal waiting |
| `VOICEMODE_SIGNAL_METHOD` | str | "file" | Signal method: file, http, socket, callback, conch |
| `VOICEMODE_SIGNAL_TIMEOUT` | float | 30.0 | Maximum wait time in seconds |
| `VOICEMODE_SIGNAL_POLL_INTERVAL` | float | 0.1 | Polling interval in seconds |
| `VOICEMODE_SIGNAL_FILE` | str | "/tmp/voicemode_ready" | Signal file path (file method) |
| `VOICEMODE_SIGNAL_URL` | str | - | HTTP endpoint URL (http method) |
| `VOICEMODE_SIGNAL_SOCKET` | str | "/tmp/voicemode.sock" | Unix socket path (socket method) |
| `VOICEMODE_SIGNAL_AUDIO_CUE` | bool | true | Play "waiting" audio cue |

### Signal File Format

**Simple** (just create the file):
```bash
touch /tmp/voicemode_ready
```

**With Metadata** (JSON content):
```json
{
  "ready": true,
  "source": "test_runner",
  "message": "All tests passed",
  "timestamp": "2026-01-17T19:30:00Z"
}
```

### HTTP Endpoint Format

**Request**:
```
GET /voicemode/ready HTTP/1.1
Host: localhost:9999
```

**Response** (ready):
```json
{
  "ready": true,
  "message": "Tests complete",
  "details": {
    "tests_passed": 47,
    "duration": 5.2
  }
}
```

**Response** (not ready):
```json
{
  "ready": false,
  "message": "Still running tests",
  "progress": 0.75
}
```

### Python Callback API

```python
from voice_mode.config import register_recording_gate
from typing import Awaitable, Callable

# Type hint for callback
RecordingGateCallback = Callable[[], Awaitable[bool]]

# Register callback
def register_recording_gate(callback: RecordingGateCallback) -> None:
    """Register callback that controls recording start
    
    Args:
        callback: Async function that returns True when ready to record
        
    Example:
        async def my_gate():
            await wait_for_tests()
            return True
        
        register_recording_gate(my_gate)
    """
    pass

# Unregister callback
def unregister_recording_gate() -> None:
    """Remove registered recording gate"""
    pass
```

### Conch State API

**States**:
- `tts_playing`: Currently playing TTS
- `tts_complete`: TTS finished
- `waiting_for_ready`: Waiting for external signal
- `ready_to_record`: External tool signaled ready
- `recording`: Currently recording
- `recording_complete`: Recording finished
- `processing`: Processing STT

**Usage**:
```python
from voice_mode.conch import Conch

# External tool monitors state
conch = Conch()
state = conch.get_state()

if state == "waiting_for_ready":
    # Do work
    run_my_task()
    
    # Signal ready
    conch.set_state("ready_to_record")
```

## Usage Examples

### Example 1: Wait for Test Completion

**Scenario**: Claude runs tests, waits for completion before listening

**Setup**:
```bash
export VOICEMODE_WAIT_FOR_SIGNAL=true
export VOICEMODE_SIGNAL_METHOD=file
export VOICEMODE_SIGNAL_FILE=/tmp/voicemode_ready
```

**Test Runner Script**:
```bash
#!/bin/bash
# test_runner.sh

# Remove old signal file
rm -f /tmp/voicemode_ready

# Run tests
pytest tests/

# Signal completion
touch /tmp/voicemode_ready
```

**Claude Interaction**:
```python
# Claude's code
await converse("I'll run the tests now.")
# TTS plays: "I'll run the tests now."
# System waits for /tmp/voicemode_ready
# Test runner creates file after tests complete
# System starts recording
# User responds: "Great, what were the results?"
```

### Example 2: Multi-Step Workflow with HTTP

**Scenario**: Agent performs multiple actions, signals ready via HTTP

**Setup**:
```bash
export VOICEMODE_WAIT_FOR_SIGNAL=true
export VOICEMODE_SIGNAL_METHOD=http
export VOICEMODE_SIGNAL_URL=http://localhost:9999/voicemode/ready
```

**Agent Server**:
```python
from fastapi import FastAPI
import asyncio

app = FastAPI()
workflow_complete = False

@app.get("/voicemode/ready")
async def ready_check():
    return {"ready": workflow_complete}

async def run_workflow():
    global workflow_complete
    workflow_complete = False
    
    # Step 1: Open file
    await open_file("example.py")
    
    # Step 2: Run linter
    await run_linter()
    
    # Step 3: Format code
    await format_code()
    
    workflow_complete = True

# In conversation handler
await run_workflow()
await converse("I've opened and formatted the file. What would you like to do next?")
```

### Example 3: Python Callback for Code Execution

**Scenario**: Wait for code execution before listening

**Setup**:
```python
from voice_mode.config import register_recording_gate
import subprocess
import asyncio

async def wait_for_execution():
    """Wait for code to finish executing"""
    process = subprocess.Popen(
        ["python", "script.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for process to complete
    while process.poll() is None:
        await asyncio.sleep(0.1)
    
    return True

# Register the gate
register_recording_gate(wait_for_execution)

# Now this will wait for execution
await converse("Running your script now.")
# TTS plays, then waits for script.py to finish
# Then starts recording user response
```

### Example 4: Conch State for Multi-Agent Coordination

**Scenario**: Voice agent coordinates with search agent

**Agent 1 (Voice)**:
```python
from voice_mode.conch import Conch

# Enable conch state signaling
os.environ["VOICEMODE_WAIT_FOR_SIGNAL"] = "true"
os.environ["VOICEMODE_SIGNAL_METHOD"] = "conch"

conch = Conch(agent_name="voice")
conch.acquire()

# Start speaking
conch.set_state("tts_playing")
await converse("Let me search for that information.")

# After TTS, system automatically waits for state="ready_to_record"
```

**Agent 2 (Search)**:
```python
from voice_mode.conch import Conch
import time

# Monitor for voice agent waiting
while True:
    conch = Conch()
    if conch.get_state() == "waiting_for_ready":
        # Perform search
        results = search_knowledge_base(query)
        
        # Format results for voice
        summary = format_for_voice(results)
        
        # Store for voice agent to retrieve
        save_results(summary)
        
        # Signal ready
        conch.set_state("ready_to_record")
        break
    
    time.sleep(0.5)
```

### Example 5: Visual UI Synchronization

**Scenario**: Wait for UI to update before listening

**Setup**:
```bash
export VOICEMODE_WAIT_FOR_SIGNAL=true
export VOICEMODE_SIGNAL_METHOD=socket
export VOICEMODE_SIGNAL_SOCKET=/tmp/voicemode.sock
```

**UI Application**:
```javascript
// In Electron/web UI
async function updateUI(data) {
    // Update UI
    await renderResults(data);
    
    // Signal VoiceMode we're ready
    const socket = net.connect('/tmp/voicemode.sock');
    socket.write('ready\n');
    socket.end();
}

// When Claude sends results
ipcMain.on('claude-response', async (event, data) => {
    await updateUI(data);
    // VoiceMode will now start listening
});
```

## Security Considerations

### Timeout Protection

**Always enforce timeout** to prevent infinite waits:
- Default: 30 seconds
- Configurable via `VOICEMODE_SIGNAL_TIMEOUT`
- Log timeout events for debugging

### File Permission Security

**Signal File**:
- Create in `/tmp/` or user-specific temp directory
- Use restrictive permissions (0600)
- Clean up after use
- Validate file ownership

```python
# In signal_gate.py
signal_file = Path(VOICEMODE_SIGNAL_FILE)

# Validate ownership
stat_info = signal_file.stat()
if stat_info.st_uid != os.getuid():
    logger.error("Signal file owned by different user, ignoring")
    return False

# Validate permissions
if stat_info.st_mode & 0o777 > 0o600:
    logger.warning("Signal file has overly permissive permissions")
```

### Socket Security

**Unix Socket**:
- Use user-specific directory (`~/.voicemode/`)
- Set socket permissions to 0600
- Validate peer credentials
- Clean up socket on exit

```python
# In signal_gate.py
import socket
import os

sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
sock.bind(socket_path)

# Set restrictive permissions
os.chmod(socket_path, 0o600)
```

### HTTP Security

**Considerations**:
- Only allow localhost by default
- Support HTTPS for remote endpoints
- Validate response format
- Rate limit requests

```python
# In signal_gate.py
from urllib.parse import urlparse

url = urlparse(VOICEMODE_SIGNAL_URL)

# Warn on non-localhost
if url.hostname not in ["localhost", "127.0.0.1", "::1"]:
    logger.warning(f"Signal URL is not localhost: {url.hostname}")

# Require HTTPS for non-localhost
if url.hostname not in ["localhost", "127.0.0.1", "::1"]:
    if url.scheme != "https":
        logger.error("Remote signal URL must use HTTPS")
        return False
```

### Callback Security

**Python Callback**:
- Validate callback is actually callable
- Catch and log exceptions
- Implement timeout at callback level
- No untrusted code execution

```python
# In signal_gate.py
async def _wait_callback(self, timeout: float) -> bool:
    if not callable(self._callback):
        logger.error("Registered callback is not callable")
        return False
    
    try:
        # Use asyncio.wait_for for timeout
        result = await asyncio.wait_for(
            self._callback(),
            timeout=timeout
        )
        return bool(result)
    except asyncio.TimeoutError:
        logger.warning("Callback timeout")
        return False
    except Exception as e:
        logger.error(f"Callback error: {e}")
        return False
```

## Migration Path

### Phase 1: Core Implementation (Minimal)

**Implement signal file method only**:
1. Add configuration variables
2. Implement file-based waiting in `converse.py`
3. Add timeout protection
4. Add audio cue for "waiting" state
5. Document usage

**Changes**:
- `voice_mode/config.py`: Add new config variables
- `voice_mode/tools/converse.py`: Add signal waiting logic
- `voice_mode/data/audio/waiting.wav`: Add new audio cue
- Documentation: Add usage examples

**Timeline**: 1-2 days

### Phase 2: Multi-Method Support

**Add HTTP and callback methods**:
1. Create `voice_mode/signal_gate.py`
2. Implement `RecordingGate` class
3. Add HTTP polling method
4. Add callback registration API
5. Refactor converse.py to use RecordingGate

**Timeline**: 3-5 days

### Phase 3: Advanced Features

**Add socket and conch state methods**:
1. Implement Unix socket method
2. Extend Conch with state management
3. Add monitoring/debugging tools
4. Add metrics and logging

**Timeline**: 5-7 days

### Backward Compatibility

**Ensure zero breaking changes**:
- Default behavior: `VOICEMODE_WAIT_FOR_SIGNAL=false` (current behavior)
- All new configuration is opt-in
- Existing code continues to work unchanged
- New parameters are optional

### Testing Strategy

**Unit Tests**:
- Test each signal method independently
- Test timeout behavior
- Test error handling
- Test security validations

**Integration Tests**:
- Test with actual voice conversations
- Test with multiple signal methods
- Test edge cases (file permissions, network errors, etc.)

**Manual Tests**:
- Real-world workflows (test runner, UI sync, etc.)
- Performance testing (latency impact)
- User experience testing (audio cues, timing)

## Future Enhancements

### 1. Visual Progress Indicator

Show progress while waiting for signal:
```python
# Play progress sounds periodically
await play_audio_feedback("waiting", ...)
# ... wait 5 seconds ...
await play_audio_feedback("still-waiting", ...)
# ... wait 5 more seconds ...
await play_audio_feedback("almost-ready", ...)
```

### 2. Cancellation Support

Allow user to cancel wait and speak immediately:
```python
# Listen for cancel phrase during wait
# "actually" or "never mind" cancels wait
while waiting_for_signal:
    if user_pressed_button() or detected_cancel_phrase():
        break
```

### 3. Multiple Gates

Support multiple gates that must all signal:
```python
gates = [
    RecordingGate(SignalMethod.FILE, {"file": "/tmp/tests_done"}),
    RecordingGate(SignalMethod.HTTP, {"url": "http://localhost:9999/ready"}),
]

# Wait for all gates
await asyncio.gather(*[gate.wait_for_signal() for gate in gates])
```

### 4. Gate Metadata

Pass metadata from gate to conversation:
```python
# Gate returns dict instead of bool
result = await gate.wait_for_signal()
# result = {"ready": True, "tests_passed": 47, "duration": 5.2}

# Use metadata in response
await converse(f"Tests complete: {result['tests_passed']} passed in {result['duration']}s. What's next?")
```

### 5. WebSocket Support

Real-time bidirectional communication:
```python
# VoiceMode opens WebSocket server
# External tools connect and send messages
# More efficient than polling
```

## Conclusion

This third-party integration proposal provides **fine-grained control** over the voice recording timing after TTS completes. The solution:

✅ **Addresses the problem**: Allows external tools to control recording start
✅ **Backward compatible**: Default behavior unchanged
✅ **Flexible**: Multiple integration methods for different scenarios
✅ **Secure**: Timeout protection, permission validation
✅ **Well-documented**: Clear API and usage examples
✅ **Extensible**: Easy to add new methods

### Recommended Implementation Order

1. **Phase 1**: Signal file method (simplest, covers most use cases)
2. **Phase 2**: HTTP method (for networked scenarios)
3. **Phase 3**: Callback and conch state methods (for advanced integration)

### Key Benefits

- **Better user experience**: Clear indication when system is ready
- **More flexible workflows**: External tools can coordinate with voice
- **Multi-agent coordination**: Agents can work together seamlessly
- **No breaking changes**: Existing code continues to work

---

**Document Version**: 1.0
**Last Updated**: 2026-01-17
**Author**: Analysis by Claude Code
