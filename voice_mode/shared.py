"""Shared initialization for voicemode."""

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

import httpx
import sounddevice as sd

# Import all configuration from config.py
from .config import (
    DEBUG, DEBUG_DIR, SAVE_AUDIO, AUDIO_DIR,
    AUDIO_FEEDBACK_ENABLED,
    OPENAI_API_KEY,
    AUTO_START_KOKORO, PREFER_LOCAL,
    SAMPLE_RATE, CHANNELS,
    audio_operation_lock, service_processes,
    logger, disable_sounddevice_stderr_redirect
)

# All configuration imported from config.py
# Track if startup has been initialized
_startup_initialized = False


# Sounddevice workaround already applied in config.py


async def startup_initialization():
    """Initialize services on startup based on configuration"""
    global _startup_initialized
    
    if _startup_initialized:
        return
    
    _startup_initialized = True
    logger.info("Running startup initialization...")
    
    # Check if we should auto-start Kokoro
    if AUTO_START_KOKORO:
        try:
            # Check if Kokoro is already running
            async with httpx.AsyncClient(timeout=3.0) as client:
                base_url = 'http://127.0.0.1:8880'  # Kokoro default endpoint
                health_url = f"{base_url}/health"
                response = await client.get(health_url)
                
                if response.status_code == 200:
                    logger.info("Kokoro TTS is already running externally")
                else:
                    raise Exception("Not running")
        except:
            # Kokoro is not running, start it
            logger.info("Auto-starting Kokoro TTS service...")
            try:
                global service_processes
                if "kokoro" not in service_processes:
                    process = subprocess.Popen(
                        ["uvx", "kokoro-fastapi"],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        env={**os.environ}
                    )
                    service_processes["kokoro"] = process
                    
                    # Wait a moment for it to start
                    await asyncio.sleep(2.0)
                    
                    # Verify it started
                    if process.poll() is None:
                        logger.info(f"✓ Kokoro TTS started successfully (PID: {process.pid})")
                    else:
                        logger.error("Failed to start Kokoro TTS")
            except Exception as e:
                logger.error(f"Error auto-starting Kokoro: {e}")
    
    # Log initial status
    logger.info("Service initialization complete")


def cleanup_on_shutdown():
    """Cleanup function called on shutdown"""
    from voice_mode.core import cleanup as cleanup_clients
    
    # Cleanup OpenAI clients
    cleanup_clients()
    
    # Stop any services we started
    for name, process in service_processes.items():
        if process and process.poll() is None:
            logger.info(f"Stopping {name} service (PID: {process.pid})...")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            logger.info(f"✓ {name} service stopped")
