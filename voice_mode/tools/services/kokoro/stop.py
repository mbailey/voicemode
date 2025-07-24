"""Stop tool for Kokoro text-to-speech service."""

import psutil
import logging

from voice_mode.server import mcp
from voice_mode.config import KOKORO_PORT
from ..common import find_process_by_port

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def kokoro_stop() -> str:
    """Stop the Kokoro text-to-speech service.
    
    Finds and terminates the kokoro-fastapi process.
    
    Returns:
        Status message indicating success or failure
    """
    try:
        # Find process by port
        proc = find_process_by_port(KOKORO_PORT)
        if not proc:
            return f"Kokoro is not running on port {KOKORO_PORT}"
        
        pid = proc.pid
        
        # Try graceful termination
        proc.terminate()
        
        # Wait up to 5 seconds for graceful shutdown
        try:
            proc.wait(timeout=5)
            return f"✅ Kokoro stopped successfully (was PID: {pid})"
        except psutil.TimeoutExpired:
            # Force kill if graceful shutdown failed
            proc.kill()
            proc.wait()
            return f"✅ Kokoro force stopped (was PID: {pid})"
            
    except Exception as e:
        logger.error(f"Error stopping Kokoro: {e}")
        return f"❌ Error stopping Kokoro: {str(e)}"