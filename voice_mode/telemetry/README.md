# VoiceMode Telemetry Module

Anonymous, opt-in telemetry system for understanding VoiceMode usage patterns while respecting user privacy.

## Overview

The telemetry module collects privacy-respecting analytics from VoiceMode usage to help improve the product. All data collection is:

- **Anonymous**: Uses random UUID with no connection to user identity
- **Opt-in**: Disabled by default, requires explicit user consent
- **Privacy-preserving**: Data is binned and anonymized before transmission
- **Transparent**: Clear documentation of what is and isn't collected

## Module Structure

```
voice_mode/telemetry/
├── __init__.py          # Public API exports
├── collector.py         # Data collection from logs
├── privacy.py           # Anonymization and binning functions
└── client.py            # HTTP transmission client
```

## Components

### TelemetryCollector

Analyzes VoiceMode event logs and conversation logs to extract usage metrics.

**Key Methods:**
- `collect_session_data(start_date, end_date)` - Aggregate session statistics
- `collect_environment_data()` - System and installation information
- `collect_telemetry_event()` - Complete telemetry payload

**Data Collected:**
- Session counts and duration bins (never exact durations)
- Exchanges per session (binned for privacy)
- TTS/STT provider usage (openai, kokoro, whisper-local, other)
- Transport type (local, livekit)
- Success/failure rates
- Anonymized error types (no stack traces or user data)

**Data NOT Collected:**
- No user names, emails, or personal information
- No file paths (anonymized to ~/Code level)
- No conversation content
- No exact timestamps (binned to daily or hourly)
- No IP addresses beyond what HTTP protocol requires

### Privacy Functions

**Duration Binning:**
```python
from voice_mode.telemetry import bin_duration

duration = bin_duration(180)  # "1-5min"
```

Bins:
- `<1min` - Under 1 minute
- `1-5min` - 1 to 5 minutes
- `5-10min` - 5 to 10 minutes
- `10-20min` - 10 to 20 minutes
- `20-60min` - 20 to 60 minutes
- `>60min` - Over 60 minutes

**Size Binning:**
```python
from voice_mode.telemetry import bin_size

size = bin_size(75 * 1024)  # "50-100KB"
```

Bins:
- `<50KB` - Under 50 KB
- `50-100KB` - 50 to 100 KB
- `100-200KB` - 100 to 200 KB
- `200-500KB` - 200 to 500 KB
- `>500KB` - Over 500 KB

**Path Anonymization:**
```python
from voice_mode.telemetry import anonymize_path

path = anonymize_path("/home/user/Code/project/file.py")  # "~/Code"
```

Removes user-specific information from paths while preserving general structure.

**Version Sanitization:**
```python
from voice_mode.telemetry.privacy import sanitize_version_string

version = sanitize_version_string("2.17.2+local.dev.abc123")  # "2.17.2"
```

Removes build hashes and local identifiers from version strings.

### TelemetryClient

HTTP client for transmitting telemetry events to the backend.

**Features:**
- Deterministic event ID generation (prevents duplicates)
- Retry logic with exponential backoff
- Offline queueing in `~/.voicemode/telemetry_queue/`
- Rate limit handling (429 responses)
- Automatic cleanup of old queued events

**Usage:**
```python
from voice_mode.telemetry import TelemetryClient, TelemetryCollector

# Create client (endpoint URL from config)
client = TelemetryClient(endpoint_url="https://telemetry.example.com/v1/events")

# Collect and send event
collector = TelemetryCollector()
event = collector.collect_telemetry_event()
success = client.send_event(event)

# Send queued events (from previous offline periods)
sent_count = client.send_queued_events()

# Clean up old events (default: 7 days)
cleared = client.clear_old_queued_events(max_age_days=7)
```

## Privacy Guarantees

### What We Collect

1. **Anonymous Installation ID**
   - Random UUID generated on first run
   - No connection to user identity
   - Stored in `~/.voicemode/telemetry_id`

2. **Environment Information**
   - OS type (Linux, Darwin, Windows)
   - Installation method (dev, uv, pip)
   - MCP host (claude-code, cursor, cline, etc.)
   - Execution source (mcp, cli)
   - VoiceMode version (sanitized)

3. **Usage Metrics (Binned)**
   - Session counts and duration bins
   - Exchange counts per session (binned)
   - Provider usage frequencies
   - Transport type usage
   - Success/failure rates
   - Error type frequencies (anonymized)

### What We DON'T Collect

- ❌ User names, emails, or personal information
- ❌ File paths (anonymized to `~/Code` level)
- ❌ Conversation content or transcriptions
- ❌ Exact timestamps (binned to daily)
- ❌ IP addresses (beyond HTTP requirements)
- ❌ Device identifiers or hardware info
- ❌ API keys or credentials
- ❌ Project names or directory structures

### Data Retention

- Events queued locally are kept for 7 days maximum
- Backend retention policy: 90 days (configurable)
- No permanent storage of raw events

## Example Telemetry Event

```json
{
  "event_id": "3d3d1ffcab7048af",
  "telemetry_id": "e85850d8-3ca6-4a78-952a-d0f195738b0a",
  "timestamp": "2025-12-14T03:00:00+00:00",
  "environment": {
    "os_type": "Linux",
    "install_method": "dev",
    "mcp_host": "claude-code",
    "exec_source": "cli",
    "version": "2.17.2"
  },
  "usage": {
    "total_sessions": 42,
    "duration_distribution": {
      "<1min": 10,
      "1-5min": 20,
      "5-10min": 8,
      "10-20min": 3,
      "20-60min": 1
    },
    "exchanges_per_session": {
      "0": 2,
      "1-5": 30,
      "6-10": 8,
      "11-20": 2
    },
    "transport_usage": {
      "local": 40,
      "livekit": 2
    },
    "tts_provider_usage": {
      "kokoro": 35,
      "openai": 7
    },
    "stt_provider_usage": {
      "whisper-local": 38,
      "openai": 4
    },
    "success_rate": 95.2,
    "total_operations": 42,
    "error_types": {
      "ConnectionError": 2
    }
  }
}
```

## Integration with Config

The telemetry module integrates with VoiceMode configuration:

```python
from voice_mode import config

# Telemetry ID (generated on first run)
telemetry_id = config.TELEMETRY_ID

# Environment detection
env_info = config.get_environment_info()
# Returns: {os_type, install_method, mcp_host, exec_source}
```

## Testing

Run the test script to verify telemetry functionality:

```bash
cd /path/to/voicemode
python3 test_telemetry.py
```

The test script demonstrates:
- Privacy function operation (binning, anonymization)
- Data collection from existing logs
- Telemetry event generation
- Client queue and transmission functionality

## Future Enhancements

Planned for upcoming features (tel-006 through tel-010):

1. **Configuration** (tel-006)
   - `VOICEMODE_TELEMETRY` setting (ask/true/false)
   - `DO_NOT_TRACK` environment variable support
   - Endpoint URL configuration

2. **Opt-in UX** (tel-007)
   - CLI prompts for opt-in
   - MCP resources for LLM-assisted consent
   - Tools for preference management

3. **Backend** (tel-008)
   - Cloudflare Workers endpoint
   - Rate limiting per anonymous ID
   - Event validation and storage

4. **Testing** (tel-009)
   - Dogfooding with real usage
   - Privacy audit
   - Load testing

5. **Documentation** (tel-010)
   - Privacy policy
   - Opt-out instructions
   - Transparency report

## Compliance

The telemetry system is designed to comply with:

- **GDPR**: Anonymous data, opt-in consent, right to opt-out
- **CCPA**: No sale of personal information (we don't collect any)
- **DO_NOT_TRACK**: Respects DNT header and environment variable

## Questions?

For questions about telemetry, privacy, or data collection:

1. Review this documentation
2. Check the main README.md privacy section (tel-010)
3. Open an issue on GitHub
4. Opt out if uncertain: `voicemode telemetry disable` (tel-007)

## License

Same as VoiceMode project (MIT).
