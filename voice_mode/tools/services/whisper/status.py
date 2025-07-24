"""Status tool for Whisper speech-to-text service."""

import psutil
import time
import logging
from pathlib import Path

from voice_mode.server import mcp
from voice_mode.config import WHISPER_PORT
from ..common import find_process_by_port

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def whisper_status() -> str:
    """Check the status of the Whisper speech-to-text service.
    
    Shows whether whisper-server is running, its resource usage, and configuration.
    
    Returns:
        Detailed status information
    """
    try:
        # Find process by port
        proc = find_process_by_port(WHISPER_PORT)
        
        if not proc:
            return f"Whisper is not running on port {WHISPER_PORT}"
        
        # Get process info
        try:
            with proc.oneshot():
                cpu_percent = proc.cpu_percent(interval=0.1)
                memory_info = proc.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024
                create_time = proc.create_time()
                cmdline = proc.cmdline()
                
            # Extract model from command line
            model = "unknown"
            for i, arg in enumerate(cmdline):
                if arg == "--model" and i + 1 < len(cmdline):
                    model = Path(cmdline[i + 1]).name
                    break
            
            # Calculate uptime
            uptime_seconds = time.time() - create_time
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            uptime_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
            
            status_lines = [
                f"✅ Whisper is running",
                f"Port: {WHISPER_PORT}",
                f"PID: {proc.pid}",
                f"CPU Usage: {cpu_percent:.1f}%",
                f"Memory Usage: {memory_mb:.1f} MB",
                f"Model: {model}",
                f"Uptime: {uptime_str}",
                f"Endpoint: http://127.0.0.1:{WHISPER_PORT}/v1"
            ]
            
            return "\n".join(status_lines)
            
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            return f"Whisper process found but unable to get details: {str(e)}"
            
    except Exception as e:
        logger.error(f"Error checking Whisper status: {e}")
        return f"❌ Error checking Whisper status: {str(e)}"