"""
Service management tools for Voice Mode.

This module provides tools for managing external services like Kokoro TTS.
"""

import asyncio
import subprocess
import logging
from typing import Optional, Dict
from pathlib import Path

import psutil
from voice_mode.mcp_instance import mcp

logger = logging.getLogger("voice-mode")

# Global state for service management
service_processes: Dict[str, subprocess.Popen] = {}


@mcp.tool()
async def kokoro_start(models_dir: Optional[str] = None) -> str:
    """Start the Kokoro TTS service using uvx.
    
    Args:
        models_dir: Optional path to models directory (defaults to ~/Models/kokoro)
    """
    global service_processes
    
    # Check if already running
    if "kokoro" in service_processes and service_processes["kokoro"].poll() is None:
        return "Kokoro is already running"
    
    try:
        # Default models directory
        if models_dir is None:
            models_dir = str(Path.home() / "Models" / "kokoro")
        
        # Construct the uvx command
        cmd = [
            "uvx",
            "--from", "git+https://github.com/mbailey/Kokoro-FastAPI",
            "kokoro-start",
            "--models-dir", models_dir
        ]
        
        logger.info(f"Starting Kokoro with command: {' '.join(cmd)}")
        
        # Start the process in the background
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True  # Detach from parent process group
        )
        
        # Give it a moment to start
        await asyncio.sleep(2)
        
        # Check if it's still running
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            error_msg = stderr.decode() if stderr else "Unknown error"
            return f"Failed to start Kokoro: {error_msg}"
        
        service_processes["kokoro"] = process
        return f"Kokoro started successfully (PID: {process.pid})"
        
    except Exception as e:
        logger.error(f"Error starting Kokoro: {e}")
        return f"Error starting Kokoro: {str(e)}"


@mcp.tool()
async def kokoro_stop() -> str:
    """Stop the Kokoro TTS service"""
    global service_processes
    
    if "kokoro" not in service_processes:
        return "Kokoro is not running"
    
    process = service_processes["kokoro"]
    
    try:
        # Check if still running
        if process.poll() is None:
            # Try graceful termination first
            process.terminate()
            
            # Wait up to 5 seconds for graceful shutdown
            try:
                await asyncio.wait_for(
                    asyncio.create_task(asyncio.to_thread(process.wait)),
                    timeout=5.0
                )
            except asyncio.TimeoutError:
                # Force kill if graceful shutdown failed
                process.kill()
                await asyncio.to_thread(process.wait)
            
            del service_processes["kokoro"]
            return "Kokoro stopped successfully"
        else:
            del service_processes["kokoro"]
            return "Kokoro was already stopped"
            
    except Exception as e:
        logger.error(f"Error stopping Kokoro: {e}")
        return f"Error stopping Kokoro: {str(e)}"


@mcp.tool()
async def kokoro_status() -> str:
    """Check the status of the Kokoro TTS service"""
    global service_processes
    
    if "kokoro" not in service_processes:
        return "Kokoro is not running"
    
    process = service_processes["kokoro"]
    
    if process.poll() is None:
        # Get more detailed info using psutil if available
        try:
            proc = psutil.Process(process.pid)
            cpu_percent = proc.cpu_percent(interval=0.1)
            memory_info = proc.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            
            # Check if port 8880 is listening
            port_status = "unknown"
            for conn in proc.connections():
                if conn.laddr.port == 8880 and conn.status == 'LISTEN':
                    port_status = "listening"
                    break
            
            return (
                f"Kokoro is running (PID: {process.pid})\n"
                f"CPU Usage: {cpu_percent:.1f}%\n"
                f"Memory Usage: {memory_mb:.1f} MB\n"
                f"Port 8880: {port_status}"
            )
        except:
            # Fallback if psutil fails
            return f"Kokoro is running (PID: {process.pid})"
    else:
        # Process has ended
        del service_processes["kokoro"]
        return "Kokoro has stopped"