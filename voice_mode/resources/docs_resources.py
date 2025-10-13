"""MCP resources for VoiceMode documentation."""

from pathlib import Path
from voice_mode.server import mcp

# Base directory for documentation resources
DOCS_DIR = Path(__file__).parent / "docs"


@mcp.resource("voicemode://docs/quickstart")
def quickstart() -> str:
    """Basic usage examples and getting started guide."""
    doc_path = DOCS_DIR / "quickstart.md"
    if doc_path.exists():
        return doc_path.read_text()
    return "Documentation file not found."


@mcp.resource("voicemode://docs/parameters")
def parameters() -> str:
    """Complete parameter reference with descriptions."""
    doc_path = DOCS_DIR / "parameters.md"
    if doc_path.exists():
        return doc_path.read_text()
    return "Documentation file not found."


@mcp.resource("voicemode://docs/languages")
def languages() -> str:
    """Non-English language support guide."""
    doc_path = DOCS_DIR / "languages.md"
    if doc_path.exists():
        return doc_path.read_text()
    return "Documentation file not found."


@mcp.resource("voicemode://docs/patterns")
def patterns() -> str:
    """Best practices and conversation patterns."""
    doc_path = DOCS_DIR / "patterns.md"
    if doc_path.exists():
        return doc_path.read_text()
    return "Documentation file not found."


@mcp.resource("voicemode://docs/troubleshooting")
def troubleshooting() -> str:
    """Audio, VAD, and connectivity troubleshooting."""
    doc_path = DOCS_DIR / "troubleshooting.md"
    if doc_path.exists():
        return doc_path.read_text()
    return "Documentation file not found."
