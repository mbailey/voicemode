#!/usr/bin/env python
"""VoiceMode MCP Server - Modular version using FastMCP patterns."""

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
    from .config import setup_logging, EVENT_LOG_ENABLED, EVENT_LOG_DIR
    from .utils import initialize_event_logger
    from .utils.ffmpeg_check import ensure_ffmpeg_or_exit
    from pathlib import Path
    
    # Check FFmpeg before setting up logging so the message is visible
    ensure_ffmpeg_or_exit()
    
    # Set up logging
    logger = setup_logging()
    
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