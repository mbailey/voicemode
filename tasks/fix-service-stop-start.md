# Fix Service Stop/Start Commands to Use launchctl

## Problem

Currently, the service stop command just terminates the process:
```python
proc.terminate()
```

On macOS with launchd and KeepAlive=true, this causes the service to immediately restart.

## Current Behavior

1. `stop` - Kills the process, launchd restarts it immediately
2. `start` - Starts the process directly
3. `disable` - Uses `launchctl unload -w` and removes plist (correct)
4. `enable` - Installs plist and uses `launchctl load -w` (correct)

## Proposed Fix

### For macOS (launchd)

**Stop command should:**
1. Check if service is managed by launchd (plist exists)
2. If yes: Use `launchctl unload` (without -w flag)
3. If no: Use current process termination

**Start command should:**
1. Check if service is managed by launchd (plist exists)
2. If yes: Use `launchctl load`
3. If no: Start process directly

### For Linux (systemd)

**Stop command should:**
1. Check if service is managed by systemd (unit file exists)
2. If yes: Use `systemctl --user stop`
3. If no: Use current process termination

**Start command should:**
1. Check if service is managed by systemd (unit file exists)
2. If yes: Use `systemctl --user start`
3. If no: Start process directly

### Implementation

```python
async def stop_service(service_name: str) -> str:
    """Stop a service."""
    port = WHISPER_PORT if service_name == "whisper" else KOKORO_PORT
    
    # Check if managed by launchd
    if platform.system() == "Darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.voicemode.{service_name}.plist"
        if plist_path.exists():
            # Use launchctl unload (without -w to preserve enable state)
            result = subprocess.run(
                ["launchctl", "unload", str(plist_path)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return f"✅ {service_name.capitalize()} stopped"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to stop {service_name}: {error}"
    
    # Fallback to process termination
    proc = find_process_by_port(port)
    if not proc:
        return f"{service_name.capitalize()} is not running"
    # ... existing termination code
```

```python
async def start_service(service_name: str) -> str:
    """Start a service."""
    port = WHISPER_PORT if service_name == "whisper" else KOKORO_PORT
    
    # Check if already running
    if find_process_by_port(port):
        return f"{service_name.capitalize()} is already running on port {port}"
    
    # Check if managed by launchd
    if platform.system() == "Darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"com.voicemode.{service_name}.plist"
        if plist_path.exists():
            # Use launchctl load
            result = subprocess.run(
                ["launchctl", "load", str(plist_path)],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # Wait for service to start
                for _ in range(10):
                    if find_process_by_port(port):
                        return f"✅ {service_name.capitalize()} started"
                    await asyncio.sleep(0.5)
                return f"⚠️ {service_name.capitalize()} loaded but not yet running"
            else:
                error = result.stderr or result.stdout
                if "already loaded" in error.lower():
                    return f"{service_name.capitalize()} service is already loaded"
                return f"❌ Failed to start {service_name}: {error}"
    
    # Fallback to direct process start
    # ... existing start code
```

### For Linux (systemd)

```python
async def stop_service(service_name: str) -> str:
    """Stop a service."""
    port = WHISPER_PORT if service_name == "whisper" else KOKORO_PORT
    
    # Check if managed by systemd
    if platform.system() == "Linux":
        service_file = Path.home() / ".config" / "systemd" / "user" / f"voicemode-{service_name}.service"
        if service_file.exists():
            # Use systemctl stop
            result = subprocess.run(
                ["systemctl", "--user", "stop", f"voicemode-{service_name}.service"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return f"✅ {service_name.capitalize()} stopped"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to stop {service_name}: {error}"
    
    # ... existing macOS code and fallback
```

```python
async def start_service(service_name: str) -> str:
    """Start a service."""
    port = WHISPER_PORT if service_name == "whisper" else KOKORO_PORT
    
    # Check if already running
    if find_process_by_port(port):
        return f"{service_name.capitalize()} is already running on port {port}"
    
    # Check if managed by systemd
    if platform.system() == "Linux":
        service_file = Path.home() / ".config" / "systemd" / "user" / f"voicemode-{service_name}.service"
        if service_file.exists():
            # Use systemctl start
            result = subprocess.run(
                ["systemctl", "--user", "start", f"voicemode-{service_name}.service"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                # Wait for service to start
                for _ in range(10):
                    if find_process_by_port(port):
                        return f"✅ {service_name.capitalize()} started"
                    await asyncio.sleep(0.5)
                return f"⚠️ {service_name.capitalize()} started but not yet listening on port {port}"
            else:
                error = result.stderr or result.stdout
                return f"❌ Failed to start {service_name}: {error}"
    
    # ... existing macOS code and fallback
```

## Benefits

1. **Predictable behavior**: Stop means stop, not restart
2. **Preserves enable state**: Stop doesn't affect boot behavior
3. **Works with service managers**: Respects both launchd and systemd
4. **Backward compatible**: Falls back to process control if not managed
5. **Cross-platform consistency**: Same behavior on macOS and Linux

## Testing

### macOS
1. Stop Kokoro - should actually stop, not restart
2. Start Kokoro - should start via launchctl
3. Restart - should stop then start properly
4. Enable/disable - should continue working as before

### Linux
1. Stop service - should use systemctl stop
2. Start service - should use systemctl start
3. Test with Restart=always in unit file
4. Verify enable/disable continue working