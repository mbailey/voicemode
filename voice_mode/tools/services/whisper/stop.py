"""Stop tool for Whisper speech-to-text service."""

import psutil
import logging

from voice_mode.server import mcp
from voice_mode.config import WHISPER_PORT
from ..common import find_process_by_port

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def whisper_stop() -> str:
    """Stop the Whisper speech-to-text service.
    
    Finds and terminates the whisper-server process.
    
    Returns:
        Status message indicating success or failure
    """
    try:
        # Find process by port
        proc = find_process_by_port(WHISPER_PORT)
        if not proc:
            return f"Whisper is not running on port {WHISPER_PORT}"
        
        pid = proc.pid
        
        # Try graceful termination
        proc.terminate()
        
        # Wait up to 5 seconds for graceful shutdown
        try:
            proc.wait(timeout=5)
            return f"✅ Whisper stopped successfully (was PID: {pid})"
        except psutil.TimeoutExpired:
            # Force kill if graceful shutdown failed
            proc.kill()
            proc.wait()
            return f"✅ Whisper force stopped (was PID: {pid})"
            
    except Exception as e:
        logger.error(f"Error stopping Whisper: {e}")
        return f"❌ Error stopping Whisper: {str(e)}"