"""Start tool for Kokoro text-to-speech service."""

import asyncio
import subprocess
import os
import platform
import logging
from pathlib import Path

from voice_mode.server import mcp
from voice_mode.config import KOKORO_PORT
from ..common import find_process_by_port
from .helpers import find_kokoro_fastapi

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def kokoro_start() -> str:
    """Start the Kokoro text-to-speech service.
    
    Starts the locally installed kokoro-fastapi service on the configured port
    (default: 8880). The service will be managed as a background process.
    
    Returns:
        Status message indicating success or failure
    """
    try:
        # Check if already running
        existing_proc = find_process_by_port(KOKORO_PORT)
        if existing_proc:
            return f"Kokoro is already running on port {KOKORO_PORT} (PID: {existing_proc.pid})"
        
        # Find kokoro-fastapi installation
        kokoro_dir = find_kokoro_fastapi()
        if not kokoro_dir:
            return "❌ kokoro-fastapi not found. Please run kokoro_install first."
        
        # Determine which start script to use
        system = platform.system()
        if system == "Darwin":
            start_script = Path(kokoro_dir) / "start-gpu_mac.sh"
        elif system == "Linux":
            start_script = Path(kokoro_dir) / "start.sh"
        else:
            return f"❌ Unsupported operating system: {system}"
        
        if not start_script.exists():
            return f"❌ Start script not found: {start_script}"
        
        # Make sure script is executable
        os.chmod(start_script, 0o755)
        
        logger.info(f"Starting Kokoro with script: {start_script}")
        
        # Start the process
        process = subprocess.Popen(
            [str(start_script)],
            cwd=kokoro_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True
        )
        
        # Wait a moment to check if it started successfully
        await asyncio.sleep(3)
        
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            error_msg = stderr.decode() if stderr else stdout.decode() if stdout else "Unknown error"
            return f"❌ Failed to start Kokoro: {error_msg}"
        
        # Verify it's listening
        proc = find_process_by_port(KOKORO_PORT)
        if proc:
            return f"✅ Kokoro started successfully on port {KOKORO_PORT} (PID: {proc.pid})"
        else:
            return f"⚠️ Kokoro process started but not listening on port {KOKORO_PORT}"
        
    except Exception as e:
        logger.error(f"Error starting Kokoro: {e}")
        return f"❌ Error starting Kokoro: {str(e)}"