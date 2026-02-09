# MCP Tools Reference

VoiceMode Connect MCP tools available to agents.

## status

Check connected devices and agents.

```
status()
```

Returns information about active connections for your account:

- Device platform (iOS, web, etc.)
- Device name
- Capabilities (TTS, STT, wake)
- Connection status

Use this to verify clients are connected before calling `converse`.

### Local service tool

The local VoiceMode MCP server also shows Connect device status via `service("connect", "status")`. This displays:

1. **Standalone standby process** - if `voicemode connect standby` is running
2. **In-process WebSocket client** - remote devices from voicemode.dev (requires opt-in, see [Configuration](#connect-configuration))

### Connect configuration

The in-process WebSocket client is disabled by default. To enable it:

```bash
export VOICEMODE_CONNECT_AUTO=true
```

| Variable | Default | Description |
|----------|---------|-------------|
| `VOICEMODE_CONNECT_AUTO` | `false` | Enable in-process WebSocket connection to voicemode.dev |
| `VOICEMODE_CONNECT_WS_URL` | `wss://voicemode.dev/ws` | WebSocket gateway URL |

VoiceMode respects user privacy and will not connect to external services without explicit opt-in.

## converse

Have a voice conversation through a connected client.

```
converse(
    message: string,           # Required: text to speak
    wait_for_response?: bool,  # Listen for response (default: true)
    voice?: string,            # TTS voice name
    speed?: number,            # Speech rate (0.25-4.0)
    target_session_id?: string # Target specific device
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `message` | string | required | Text to speak via TTS |
| `wait_for_response` | bool | true | Whether to listen for voice response |
| `voice` | string | auto | TTS voice (e.g., 'nova', 'shimmer', 'alloy') |
| `speed` | number | 1.0 | Speech rate (0.25 = slow, 4.0 = fast) |
| `target_session_id` | string | auto | Target specific device by session ID |

### Examples

Simple message:
```
converse("Hello, how can I help you today?")
```

One-way announcement (no response expected):
```
converse("Task completed successfully", wait_for_response=false)
```

Specific voice and speed:
```
converse("Let me explain...", voice="nova", speed=1.2)
```

### Targeting Devices

When multiple clients are connected, use `status` to see session IDs, then specify `target_session_id` to direct the message to a specific device.

## Open Questions

- Exact behavior when multiple clients are connected and no target specified
- Voice names and availability may vary
- Error responses and retry behavior

These will be documented as the platform stabilizes.
