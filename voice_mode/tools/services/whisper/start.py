"""Start tool for Whisper speech-to-text service."""

import asyncio
import subprocess
import logging
from pathlib import Path

from voice_mode.server import mcp
from voice_mode.config import WHISPER_PORT
from ..common import find_process_by_port
from .helpers import find_whisper_server, find_whisper_model

logger = logging.getLogger("voice-mode")


@mcp.tool()
async def whisper_start() -> str:
    """Start the Whisper speech-to-text service.
    
    Starts whisper-server on the configured port (default: 2022) with the
    available model. The service will be managed as a background process.
    
    Returns:
        Status message indicating success or failure
    """
    try:
        # Check if already running
        existing_proc = find_process_by_port(WHISPER_PORT)
        if existing_proc:
            return f"Whisper is already running on port {WHISPER_PORT} (PID: {existing_proc.pid})"
        
        # Find whisper-server binary
        whisper_bin = find_whisper_server()
        if not whisper_bin:
            return "❌ whisper-server not found. Please run whisper_install first."
        
        # Find model file
        model_file = find_whisper_model()
        if not model_file:
            return "❌ No Whisper model found. Please run whisper_install to download a model."
        
        # Construct command
        cmd = [
            whisper_bin,
            "--host", "0.0.0.0",
            "--port", str(WHISPER_PORT),
            "--model", model_file
        ]
        
        logger.info(f"Starting Whisper with command: {' '.join(cmd)}")
        
        # Start the process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True
        )
        
        # Wait a moment to check if it started successfully
        await asyncio.sleep(2)
        
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            error_msg = stderr.decode() if stderr else "Unknown error"
            return f"❌ Failed to start Whisper: {error_msg}"
        
        # Verify it's listening
        proc = find_process_by_port(WHISPER_PORT)
        if proc:
            return f"✅ Whisper started successfully on port {WHISPER_PORT} (PID: {proc.pid})"
        else:
            return f"⚠️ Whisper process started but not listening on port {WHISPER_PORT}"
        
    except Exception as e:
        logger.error(f"Error starting Whisper: {e}")
        return f"❌ Error starting Whisper: {str(e)}"