"""Status tool for Kokoro text-to-speech service."""

import psutil
import time
import logging

from voice_mode.server import mcp
from voice_mode.config import KOKORO_PORT
from ..common import find_process_by_port

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def kokoro_status() -> str:
    """Check the status of the Kokoro text-to-speech service.
    
    Shows whether kokoro-fastapi is running, its resource usage, and configuration.
    
    Returns:
        Detailed status information
    """
    try:
        # Find process by port
        proc = find_process_by_port(KOKORO_PORT)
        
        if not proc:
            return f"Kokoro is not running on port {KOKORO_PORT}"
        
        # Get process info
        try:
            with proc.oneshot():
                cpu_percent = proc.cpu_percent(interval=0.1)
                memory_info = proc.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
                create_time = proc.create_time()
                
            # Calculate uptime
            uptime_seconds = time.time() - create_time
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            uptime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            
            status_lines = [
                f"✅ Kokoro is running",
                f"Port: {KOKORO_PORT}",
                f"PID: {proc.pid}",
                f"CPU Usage: {cpu_percent:.1f}%",
                f"Memory Usage: {memory_mb:.1f} MB",
                f"Uptime: {uptime_str}",
                f"Endpoint: http://127.0.0.1:{KOKORO_PORT}/v1"
            ]
            
            return "\n".join(status_lines)
            
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            return f"Kokoro process found but unable to get details: {str(e)}"
            
    except Exception as e:
        logger.error(f"Error checking Kokoro status: {e}")
        return f"❌ Error checking Kokoro status: {str(e)}"