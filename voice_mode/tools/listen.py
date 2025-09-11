"""MCP tools for controlling the voice listener service."""

import asyncio
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

logger = logging.getLogger("voice-mode")

# Global listener state
_listener_task: Optional[asyncio.Task] = None
_listener_config: Dict[str, Any] = {}


async def start_listener(
    wake_words: Optional[List[str]] = None,
    config_path: Optional[str] = None,
    max_idle_time: Optional[float] = None
) -> str:
    """Start the voice listener service.
    
    The listener continuously monitors for wake words and processes voice commands.
    It can handle simple queries locally (time, date, battery) and route complex
    queries to AI assistants.
    
    Args:
        wake_words: List of wake words to listen for (default: ["hey voicemode", "hey claude"])
        config_path: Optional path to YAML configuration file
        max_idle_time: Maximum idle time in seconds before auto-shutdown (default: 3600)
        
    Returns:
        Status message indicating success or failure
    
    Examples:
        >>> await start_listener()
        "Listener started with wake words: ['hey voicemode', 'hey claude']"
        
        >>> await start_listener(wake_words=["computer", "assistant"])
        "Listener started with wake words: ['computer', 'assistant']"
    """
    global _listener_task, _listener_config
    
    # Check if listener is already running
    if _listener_task and not _listener_task.done():
        return "Listener is already running. Use stop_listener() to stop it first."
    
    # Default wake words if not provided
    if wake_words is None:
        wake_words = ["hey voicemode", "hey claude", "computer"]
    
    # Import required modules
    try:
        from voice_mode.listen_mode import SimpleCommandRouter, ListenerConfig, run_listener
        from voice_mode.whisper_stream import check_whisper_stream_available
    except ImportError as e:
        return f"Failed to import listener modules: {e}"
    
    # Check if whisper-stream is available
    if not check_whisper_stream_available():
        return "Error: whisper-stream not found. Please install whisper-stream to use the listener."
    
    # Store configuration
    _listener_config = {
        "wake_words": wake_words,
        "config_path": config_path,
        "max_idle_time": max_idle_time or 3600
    }
    
    # Convert config path if provided
    config_path_obj = Path(config_path) if config_path else None
    
    # Create and start the listener task
    async def listener_wrapper():
        """Wrapper to handle listener lifecycle."""
        try:
            logger.info(f"Starting listener with wake words: {wake_words}")
            await run_listener(
                wake_words=wake_words,
                config_path=config_path_obj,
                daemon=False  # Always run in foreground for MCP
            )
        except Exception as e:
            logger.error(f"Listener error: {e}")
            raise
    
    _listener_task = asyncio.create_task(listener_wrapper())
    
    # Give it a moment to start
    await asyncio.sleep(0.5)
    
    # Check if it started successfully
    if _listener_task.done():
        # Task ended immediately, likely an error
        try:
            await _listener_task  # This will raise any exception
        except Exception as e:
            return f"Failed to start listener: {e}"
    
    return f"Listener started with wake words: {wake_words}"


async def stop_listener() -> str:
    """Stop the voice listener service.
    
    Returns:
        Status message indicating whether the listener was stopped
        
    Examples:
        >>> await stop_listener()
        "Listener stopped successfully"
        
        >>> await stop_listener()  # When no listener is running
        "No listener is currently running"
    """
    global _listener_task
    
    if not _listener_task or _listener_task.done():
        return "No listener is currently running"
    
    logger.info("Stopping listener...")
    
    # Cancel the listener task
    _listener_task.cancel()
    
    try:
        # Wait for it to finish cancellation
        await asyncio.wait_for(_listener_task, timeout=5.0)
    except asyncio.CancelledError:
        pass  # Expected when task is cancelled
    except asyncio.TimeoutError:
        logger.warning("Listener did not stop gracefully, may still be running")
        return "Warning: Listener stop timed out"
    except Exception as e:
        logger.error(f"Error stopping listener: {e}")
        return f"Error stopping listener: {e}"
    
    _listener_task = None
    return "Listener stopped successfully"


async def listener_status() -> Dict[str, Any]:
    """Get current listener status and configuration.
    
    Returns:
        Dictionary containing listener status information:
        - running: Boolean indicating if listener is active
        - wake_words: List of configured wake words
        - config_path: Path to configuration file (if any)
        - max_idle_time: Maximum idle time in seconds
        - uptime: Time in seconds since listener started (if running)
        
    Examples:
        >>> await listener_status()
        {
            "running": True,
            "wake_words": ["hey voicemode", "hey claude"],
            "config_path": None,
            "max_idle_time": 3600,
            "uptime": 45.2
        }
    """
    global _listener_task, _listener_config
    
    status = {
        "running": _listener_task is not None and not _listener_task.done(),
        "wake_words": _listener_config.get("wake_words", []),
        "config_path": _listener_config.get("config_path"),
        "max_idle_time": _listener_config.get("max_idle_time", 3600)
    }
    
    # Add uptime if running
    if status["running"]:
        # Note: This is approximate since we don't track exact start time
        # In a production version, we'd store the start time
        status["uptime"] = "Active (exact uptime not tracked)"
    else:
        status["uptime"] = None
    
    return status


async def test_wake_word_detection(
    text: str,
    wake_words: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Test if a text contains any wake words and extract the command.
    
    This is a utility function for testing wake word detection logic without
    actually starting the listener.
    
    Args:
        text: Text to test for wake words
        wake_words: List of wake words to check (default: ["hey voicemode", "hey claude"])
        
    Returns:
        Dictionary with detection results:
        - detected: Boolean indicating if a wake word was found
        - wake_word: The detected wake word (if any)
        - command: The extracted command after the wake word (if any)
        
    Examples:
        >>> await test_wake_word_detection("hey voicemode what time is it")
        {
            "detected": True,
            "wake_word": "hey voicemode",
            "command": "what time is it"
        }
        
        >>> await test_wake_word_detection("what's the weather")
        {
            "detected": False,
            "wake_word": None,
            "command": None
        }
    """
    if wake_words is None:
        wake_words = ["hey voicemode", "hey claude", "computer"]
    
    text_lower = text.lower()
    wake_words_lower = [w.lower() for w in wake_words]
    
    for wake_word in wake_words_lower:
        if wake_word in text_lower:
            # Find position of wake word
            pos = text_lower.find(wake_word)
            # Extract command after wake word
            command = text[pos + len(wake_word):].strip()
            
            return {
                "detected": True,
                "wake_word": wake_word,
                "command": command if command else None
            }
    
    return {
        "detected": False,
        "wake_word": None,
        "command": None
    }


# Additional helper for configuration
async def create_listener_config(
    wake_words: List[str],
    output_path: str,
    weather_api_key: Optional[str] = None,
    whisper_model: str = "base"
) -> str:
    """Create a configuration file for the listener.
    
    Args:
        wake_words: List of wake words to configure
        output_path: Path where to save the configuration file
        weather_api_key: Optional OpenWeatherMap API key
        whisper_model: Whisper model to use (base, small, medium, large)
        
    Returns:
        Success message with the configuration file path
        
    Examples:
        >>> await create_listener_config(
        ...     wake_words=["hey computer"],
        ...     output_path="~/.voicemode/listen.yaml"
        ... )
        "Configuration saved to ~/.voicemode/listen.yaml"
    """
    from pathlib import Path
    import yaml
    
    config = {
        "wake_words": wake_words,
        "performance": {
            "whisper_model": whisper_model,
            "max_idle_time": 3600,
            "cpu_limit": 25,
            "memory_limit": 512
        },
        "audio": {
            "tts_enabled": True,
            "input_device": "default",
            "vad_aggressiveness": 2
        },
        "local_commands": {
            "time": {
                "enabled": True,
                "patterns": ["time", "what time", "current time"]
            },
            "date": {
                "enabled": True,
                "patterns": ["date", "what day", "today"]
            },
            "battery": {
                "enabled": True,
                "patterns": ["battery", "battery level", "battery status"]
            }
        }
    }
    
    # Add weather API key if provided
    if weather_api_key:
        config["apis"] = {
            "weather_key": weather_api_key
        }
        config["local_commands"]["weather"] = {
            "enabled": True,
            "patterns": ["weather", "temperature", "forecast"]
        }
    
    # Expand user path and create parent directories
    output = Path(output_path).expanduser()
    output.parent.mkdir(parents=True, exist_ok=True)
    
    # Write configuration
    with open(output, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    return f"Configuration saved to {output}"