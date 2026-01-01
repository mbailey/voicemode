"""MCP resources for telemetry status and information."""

from ..server import mcp
from ..config import (
    logger,
    get_telemetry_status,
    get_telemetry_id,
    VOICEMODE_TELEMETRY,
    DO_NOT_TRACK,
    VOICEMODE_TELEMETRY_ENDPOINT,
)


@mcp.resource("voicemode://telemetry/status")
async def telemetry_status() -> str:
    """
    Telemetry opt-in status and information.

    Shows:
    - Current telemetry enabled/disabled status
    - Reason for current status (DO_NOT_TRACK, explicit opt-in/out, or pending prompt)
    - What data is collected (anonymized usage stats)
    - How to opt-in or opt-out
    - Telemetry ID (if enabled)
    - Endpoint URL (if configured)

    Use this resource to:
    - Check if user needs to be prompted for telemetry consent
    - Explain telemetry to users
    - Show current telemetry configuration
    """
    status = get_telemetry_status()

    lines = []
    lines.append("VoiceMode Telemetry Status")
    lines.append("=" * 80)
    lines.append("")

    # Current status
    status_emoji = "✅" if status["enabled"] else "❌"
    lines.append(f"Status: {status_emoji} {'ENABLED' if status['enabled'] else 'DISABLED'}")
    lines.append(f"Reason: {status['reason']}")
    lines.append("")

    # If user needs to be prompted
    if VOICEMODE_TELEMETRY == "ask":
        lines.append("⚠️  USER CONSENT REQUIRED")
        lines.append("")
        lines.append("The user has not yet been asked about telemetry collection.")
        lines.append("Please present the opt-in information below and use the")
        lines.append("telemetry_set_preference tool to record their choice.")
        lines.append("")

    # What is collected
    lines.append("📊 What Data is Collected")
    lines.append("-" * 80)
    lines.append("")
    lines.append("VoiceMode collects anonymous usage statistics to help improve the tool:")
    lines.append("")
    lines.append("  • Session counts and durations (binned: <1min, 1-5min, 5-10min, etc.)")
    lines.append("  • Number of voice exchanges per session (binned: 0, 1-5, 6-10, etc.)")
    lines.append("  • TTS/STT provider usage (openai, kokoro, whisper-local, other)")
    lines.append("  • Transport type (local microphone vs LiveKit)")
    lines.append("  • Success/failure rates")
    lines.append("  • Error types (anonymized, no personal info)")
    lines.append("  • Operating system type")
    lines.append("  • Installation method (dev, uv, pip)")
    lines.append("  • Execution source (MCP server, CLI)")
    lines.append("")
    lines.append("Privacy protections:")
    lines.append("  • All data is anonymized using a random UUID")
    lines.append("  • No personal information, file paths, or API keys are collected")
    lines.append("  • Durations and counts are binned to prevent identification")
    lines.append("  • Error messages are sanitized to remove specific details")
    lines.append("  • Data is opt-in only - disabled by default")
    lines.append("")

    # How to opt-in/out
    lines.append("🔧 How to Control Telemetry")
    lines.append("-" * 80)
    lines.append("")
    lines.append("Via MCP tool (for LLM use):")
    lines.append("  • Use telemetry_set_preference(enabled=true) to opt-in")
    lines.append("  • Use telemetry_set_preference(enabled=false) to opt-out")
    lines.append("")
    lines.append("Via environment variable:")
    lines.append("  • Set VOICEMODE_TELEMETRY=true to enable")
    lines.append("  • Set VOICEMODE_TELEMETRY=false to disable")
    lines.append("  • Set DO_NOT_TRACK=1 to disable all telemetry (universal opt-out)")
    lines.append("")
    lines.append("Via configuration file (~/.voicemode/voicemode.env):")
    lines.append("  • Add VOICEMODE_TELEMETRY=true to enable")
    lines.append("  • Add VOICEMODE_TELEMETRY=false to disable")
    lines.append("")

    # Current configuration
    lines.append("⚙️  Current Configuration")
    lines.append("-" * 80)
    lines.append("")
    if status["do_not_track"]:
        lines.append(f"  DO_NOT_TRACK: Set (telemetry disabled by universal opt-out)")
    else:
        lines.append(f"  DO_NOT_TRACK: Not set")
    lines.append(f"  VOICEMODE_TELEMETRY: {status['voicemode_telemetry']}")

    if status["enabled"]:
        lines.append(f"  Telemetry ID: {status['telemetry_id']}")
    else:
        lines.append(f"  Telemetry ID: (not shown - telemetry disabled)")

    if status["endpoint"]:
        lines.append(f"  Endpoint: {status['endpoint']}")
    else:
        lines.append(f"  Endpoint: Not configured (telemetry data will be queued locally)")
    lines.append("")

    # More information
    lines.append("💡 More Information")
    lines.append("-" * 80)
    lines.append("")
    lines.append("For more details about privacy and data collection:")
    lines.append("  • See the Privacy section in the VoiceMode documentation")
    lines.append("  • Review the source code at voice_mode/telemetry/")
    lines.append("  • Contact the maintainers with questions or concerns")

    return "\n".join(lines)


@mcp.resource("voicemode://telemetry/opt-in-prompt")
async def telemetry_opt_in_prompt() -> str:
    """
    User-friendly telemetry opt-in prompt text.

    This resource provides a concise, friendly prompt that LLMs can use to ask
    users about telemetry collection. It's designed to be:
    - Clear about what is collected
    - Honest about privacy protections
    - Easy to understand
    - Not pushy or manipulative

    Use this when VOICEMODE_TELEMETRY=ask to present the opt-in choice to users.
    """
    lines = []
    lines.append("VoiceMode Telemetry")
    lines.append("=" * 60)
    lines.append("")
    lines.append("VoiceMode would like to collect anonymous usage statistics")
    lines.append("to help improve the tool.")
    lines.append("")
    lines.append("What we collect:")
    lines.append("  • Session counts and durations (binned for privacy)")
    lines.append("  • Voice exchanges per session")
    lines.append("  • TTS/STT provider usage (openai, kokoro, whisper)")
    lines.append("  • Success/failure rates")
    lines.append("  • Anonymized error types")
    lines.append("")
    lines.append("What we DON'T collect:")
    lines.append("  • Your conversations or voice recordings")
    lines.append("  • Personal information or file paths")
    lines.append("  • API keys or credentials")
    lines.append("  • Anything that could identify you")
    lines.append("")
    lines.append("Privacy protections:")
    lines.append("  • All data is anonymized with a random UUID")
    lines.append("  • Numbers are binned to prevent identification")
    lines.append("  • You can opt-out anytime")
    lines.append("  • Set DO_NOT_TRACK=1 to disable universally")
    lines.append("")
    lines.append("Would you like to enable telemetry?")
    lines.append("")
    lines.append("  [Yes] - Help improve VoiceMode with anonymous stats")
    lines.append("  [No]  - Don't collect any usage data")
    lines.append("")
    lines.append("(You can change this later in ~/.voicemode/voicemode.env)")

    return "\n".join(lines)
