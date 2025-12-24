#!/usr/bin/env python
"""VoiceMode MCP Server - Modular version using FastMCP patterns."""

import os
import platform

# Extend PATH to include common tool locations before any imports that might need them
# MCP servers run in isolated environments that may not inherit shell PATH
if platform.system() == "Darwin":
    # macOS: Add Homebrew paths (Intel and Apple Silicon)
    homebrew_paths = ["/opt/homebrew/bin", "/usr/local/bin"]
    current_path = os.environ.get("PATH", "")
    paths_to_add = [p for p in homebrew_paths if p not in current_path]
    if paths_to_add:
        os.environ["PATH"] = ":".join(paths_to_add) + ":" + current_path

from fastmcp import FastMCP

# Create FastMCP instance
mcp = FastMCP("voicemode")

# Import shared configuration and utilities
from . import config

# Auto-import all tools, prompts, and resources
# The __init__.py files in each directory handle the imports
from . import tools
from . import prompts 
from . import resources

# Main entry point
def main():
    """Run the VoiceMode MCP server."""
    import os
    import sys
    import warnings
    from .config import setup_logging, EVENT_LOG_ENABLED, EVENT_LOG_DIR
    from .utils import initialize_event_logger
    from .utils.ffmpeg_check import check_ffmpeg, check_ffprobe, get_install_instructions
    from pathlib import Path
    
    # Suppress known deprecation warnings from dependencies
    # These are upstream issues that don't affect functionality
    warnings.filterwarnings("ignore", category=SyntaxWarning, module="pydub.utils")
    warnings.filterwarnings("ignore", message="'audioop' is deprecated", category=DeprecationWarning)
    warnings.filterwarnings("ignore", message="pkg_resources is deprecated", category=UserWarning)
    
    # For MCP mode (stdio transport), we need to let the server start
    # so the LLM can see error messages in tool responses
    # MCP servers use stdio with stdin/stdout connected to pipes, not terminals
    is_mcp_mode = not sys.stdin.isatty() or not sys.stdout.isatty()
    
    # Check FFmpeg availability
    ffmpeg_installed, _ = check_ffmpeg()
    ffprobe_installed, _ = check_ffprobe()
    ffmpeg_available = ffmpeg_installed and ffprobe_installed
    
    if not ffmpeg_available and not is_mcp_mode:
        # Interactive mode - show error and exit
        print("\n" + "="*60)
        print("⚠️  FFmpeg Installation Required")
        print("="*60)
        print(get_install_instructions())
        print("="*60 + "\n")
        print("❌ Voice Mode cannot start without FFmpeg.")
        print("Please install FFmpeg and try again.\n")
        sys.exit(1)
    
    # Set up logging
    logger = setup_logging()
    
    # Log version information
    from .version import __version__
    logger.info(f"Starting VoiceMode v{__version__}")
    
    # Log FFmpeg status for MCP mode
    if not ffmpeg_available:
        logger.warning("FFmpeg is not installed - audio conversion features will not work")
        logger.warning("Voice features will fail with helpful error messages")
        # Store this globally so tools can check it
        config.FFMPEG_AVAILABLE = False
    else:
        config.FFMPEG_AVAILABLE = True
    
    # Initialize event logger
    if EVENT_LOG_ENABLED:
        event_logger = initialize_event_logger(
            log_dir=Path(EVENT_LOG_DIR),
            enabled=True
        )
        logger.info(f"Event logging enabled, writing to {EVENT_LOG_DIR}")
    else:
        logger.info("Event logging disabled")
    
    # Run the server
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()