# Service Management Commands

Voice Mode now includes built-in service management commands for Kokoro and Whisper services.

## Usage

### Backward Compatibility

The default behavior is preserved:
```bash
voicemode              # Starts MCP server (existing behavior)
```

### Service Management

New subcommands allow direct service control without starting the MCP server:

#### Kokoro TTS Service
```bash
voicemode kokoro status           # Show service status and resource usage
voicemode kokoro start            # Start Kokoro service
voicemode kokoro stop             # Stop Kokoro service
voicemode kokoro restart          # Restart Kokoro service
voicemode kokoro enable           # Enable service at boot/login
voicemode kokoro disable          # Disable service from boot/login
voicemode kokoro logs             # View service logs (default: 50 lines)
voicemode kokoro logs --lines 100 # View last 100 log lines
voicemode kokoro health           # Check health endpoint
voicemode kokoro update-service-files # Update service files to latest
```

#### Waiting for Services to Start

The `status` command supports `--wait` and `--timeout` flags to block until a service becomes ready:

```bash
# Wait for service to be ready (default 60s timeout)
voicemode kokoro status --wait

# Wait with custom timeout
voicemode whisper status --wait --timeout 120
```

This is useful for scripts that need to wait for services to be fully operational before proceeding.

**How it works:**
- Polls the service every second
- Shows progress dots (`.`) during wait
- Returns when service is ready or timeout is reached
- Timeout message uses `⏱️` prefix

#### Whisper STT Service
```bash
voicemode whisper status          # Show service status and resource usage
voicemode whisper start           # Start Whisper service
voicemode whisper stop            # Stop Whisper service
voicemode whisper restart         # Restart Whisper service  
voicemode whisper enable          # Enable service at boot/login
voicemode whisper disable         # Disable service from boot/login
voicemode whisper logs            # View service logs (default: 50 lines)
voicemode whisper logs --lines 100 # View last 100 log lines
voicemode whisper health          # Check health endpoint
voicemode whisper update-service-files # Update service files to latest
```

## Examples

### Quick Status Check
```bash
$ voicemode kokoro status
✅ Kokoro is running
   PID: 12345
   Port: 8880
   CPU: 0.1%
   Memory: 8.9 MB
   Uptime: 2h 15m 30s
   Service files: v1.1.1 (latest)
```

### Starting Services
```bash
$ voicemode whisper start
✅ Whisper started successfully (PID: 54321)

$ voicemode kokoro start
✅ Kokoro started
```

### Waiting for Service Readiness
```bash
# Start service and wait for it to be ready
$ voicemode kokoro start && voicemode kokoro status --wait
✅ Kokoro started
Waiting for kokoro to become ready... (timeout: 60s)
................
✅ Kokoro is running locally
   PID: 12345
   Port: 8880
   CPU: 0.1%
   Memory: 256.3 MB
   Uptime: 16s

# Wait with custom timeout
$ voicemode whisper status --wait --timeout 120
Waiting for whisper to become ready... (timeout: 120s)
....
✅ Whisper is running locally
   PID: 54321
   Port: 2022
   ...

# Timeout example
$ voicemode kokoro status --wait --timeout 5
Waiting for kokoro to become ready... (timeout: 5s)
.....
⏱️ Timeout: kokoro did not become ready within 5 seconds
```

### Health Checks
```bash
$ voicemode kokoro health
✅ Kokoro is responding
   Status: healthy
   Uptime: 2h 15m 30s

$ voicemode whisper health
❌ Whisper not responding on port 2022
```

### Service Management
```bash
$ voicemode kokoro enable
✅ Kokoro service enabled. It will start automatically at login.
Plist: /Users/user/Library/LaunchAgents/com.voicemode.kokoro.plist

$ voicemode whisper disable
✅ Whisper service disabled and removed
```

### Viewing Logs
```bash
$ voicemode kokoro logs --lines 20
=== Last 20 log entries for kokoro ===
[2025-08-11 15:30:42] Starting Kokoro FastAPI server...
[2025-08-11 15:30:43] Server listening on 0.0.0.0:8880
...
```

## Cross-Platform Support

Commands work on both macOS and Linux:
- **macOS**: Uses launchctl for service management
- **Linux**: Uses systemctl for service management  
- **Fallback**: Direct process control when service managers not available


## Benefits

1. **No shell setup required** - Commands work immediately after installing voicemode
2. **Consistent interface** - Same commands on all platforms
3. **Better help text** - Built-in help with `--help`
4. **Standardized options** - Consistent flags like `--lines`
5. **No MCP overhead** - Service commands don't start the MCP server
6. **Future-proof** - Easy to add new service management features
