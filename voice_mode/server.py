#!/usr/bin/env python
"""VoiceMode MCP Server - Modular version using FastMCP patterns."""

import logging
import os
import platform
from contextlib import asynccontextmanager

# Note: audioop deprecation warning is suppressed in tools/__init__.py
# (right before pydub is imported) to ensure it's applied after numpy/scipy
# filters are added

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

logger = logging.getLogger("voicemode")


@asynccontextmanager
async def _connect_lifespan(app: FastMCP):
    """Auto-connect to VoiceMode Connect gateway on MCP server startup."""
    from .connect import config as connect_config

    if connect_config.is_enabled():
        from .connect.client import get_client

        client = get_client()
        logger.info("Connect auto-connect: starting WebSocket connection")
        await client.connect()
    else:
        logger.debug("Connect auto-connect: disabled by config")

    yield {}

    # Shutdown: disconnect cleanly
    if connect_config.is_enabled():
        try:
            from .connect.client import get_client

            client = get_client()
            if client.is_connected or client.is_connecting:
                logger.info("Connect auto-connect: disconnecting")
                await client.disconnect()
        except Exception as e:
            logger.warning(f"Connect auto-connect: error during disconnect: {e}")


# Create FastMCP instance with Connect lifespan
mcp = FastMCP("voicemode", lifespan=_connect_lifespan)

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
    import sys
    from .config import setup_logging, EVENT_LOG_ENABLED, EVENT_LOG_DIR
    from .utils import initialize_event_logger
    from .utils.ffmpeg_check import check_ffmpeg, check_ffprobe, get_install_instructions
    from pathlib import Path

    # Note: Warning filters are set at module level (top of file) to catch
    # deprecation warnings from imports before main() is called

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