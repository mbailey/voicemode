"""Tools to list available versions for services."""

from voice_mode.server import mcp
from voice_mode.utils.version_helpers import (
    get_git_tags, get_latest_stable_tag, get_current_version
)
from pathlib import Path


WHISPER_REPO = "https://github.com/ggerganov/whisper.cpp"
KOKORO_REPO = "https://github.com/remsky/kokoro-fastapi"


@mcp.tool(
    name="list_whisper_versions",
    description="List available versions of whisper.cpp"
)
def list_whisper_versions() -> str:
    """List available versions of whisper.cpp."""
    tags = get_git_tags(WHISPER_REPO)
    
    if not tags:
        return "❌ Failed to fetch whisper.cpp versions"
    
    # Get current version
    install_dir = Path.home() / ".voicemode" / "whisper.cpp"
    current = get_current_version(install_dir)
    
    # Get latest stable
    latest = get_latest_stable_tag(tags)
    
    result = ["Available versions for whisper.cpp:"]
    result.append("")
    
    # Show recent versions (limit to 15)
    for i, tag in enumerate(tags[:15]):
        indicators = []
        if tag == latest:
            indicators.append("latest")
        if current and (tag in current or current.startswith(tag)):
            indicators.append("installed")
        
        if indicators:
            result.append(f"  * {tag} ({', '.join(indicators)})")
        else:
            result.append(f"  * {tag}")
    
    if len(tags) > 15:
        result.append(f"  ... and {len(tags) - 15} more versions")
    
    return "\n".join(result)


@mcp.tool(
    name="list_kokoro_versions",
    description="List available versions of kokoro-fastapi"
)
def list_kokoro_versions() -> str:
    """List available versions of kokoro-fastapi."""
    tags = get_git_tags(KOKORO_REPO)
    
    if not tags:
        return "❌ Failed to fetch kokoro-fastapi versions"
    
    # Get current version
    install_dir = Path.home() / ".voicemode" / "kokoro-fastapi"
    current = get_current_version(install_dir)
    
    # Get latest stable
    latest = get_latest_stable_tag(tags)
    
    result = ["Available versions for kokoro-fastapi:"]
    result.append("")
    
    # Show all versions (kokoro has fewer)
    for tag in tags:
        indicators = []
        if tag == latest:
            indicators.append("latest")
        if current and (tag in current or current.startswith(tag)):
            indicators.append("installed")
        
        if indicators:
            result.append(f"  * {tag} ({', '.join(indicators)})")
        else:
            result.append(f"  * {tag}")
    
    return "\n".join(result)