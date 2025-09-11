"""Listen mode for continuous voice assistant functionality."""

import asyncio
import logging
import os
import subprocess
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger("voice-mode")


class SimpleCommandRouter:
    """Minimal command router for voice commands."""
    
    def __init__(self):
        self.tts_enabled = not os.getenv('VOICEMODE_LISTEN_NO_TTS')
        self.last_command = None
        self.command_count = 0
        
    async def route(self, wake_word: str, command: str):
        """Route command to appropriate handler.
        
        Args:
            wake_word: The wake word that triggered this command
            command: The command text to process
        """
        self.last_command = command
        self.command_count += 1
        command_lower = command.lower().strip()
        
        logger.info(f"Routing command #{self.command_count}: '{command}' (wake: '{wake_word}')")
        print(f"\n🎤 Heard: '{wake_word}, {command}'")
        
        # Time commands
        if any(phrase in command_lower for phrase in ["time", "what time", "current time", "what's the time"]):
            response = self._get_time()
            await self._speak(response)
            
        # Date commands
        elif any(phrase in command_lower for phrase in ["date", "what's the date", "what day", "today's date"]):
            response = self._get_date()
            await self._speak(response)
            
        # Weather commands (placeholder for now)
        elif any(phrase in command_lower for phrase in ["weather", "temperature", "how hot", "how cold", "forecast"]):
            response = await self._get_weather()
            await self._speak(response)
            
        # System info commands
        elif any(phrase in command_lower for phrase in ["battery", "battery level", "battery status"]):
            response = self._get_battery_status()
            await self._speak(response)
            
        # App control commands
        elif "open" in command_lower:
            response = await self._open_application(command)
            await self._speak(response)
            
        # Claude-specific commands or complex queries
        elif "claude" in wake_word.lower() or self._is_complex_query(command_lower):
            await self._route_to_claude(command)
            
        # Stop/exit commands
        elif any(phrase in command_lower for phrase in ["stop listening", "goodbye", "exit", "quit"]):
            await self._speak("Goodbye!")
            raise KeyboardInterrupt("User requested exit")
            
        # Default response
        else:
            response = f"I heard: {command}"
            await self._speak(response)
    
    def _get_time(self) -> str:
        """Get current time in friendly format."""
        now = datetime.now()
        hour = now.strftime("%I").lstrip('0')  # Remove leading zero
        minute = now.strftime("%M")
        period = now.strftime("%p")
        
        # Handle special cases for natural speech
        if minute == "00":
            return f"It's {hour} {period}"
        elif minute == "15":
            return f"It's quarter past {hour} {period}"
        elif minute == "30":
            return f"It's half past {hour} {period}"
        elif minute == "45":
            next_hour = (now.hour % 12) + 1
            return f"It's quarter to {next_hour} {period}"
        else:
            return f"It's {hour} {minute} {period}"
    
    def _get_date(self) -> str:
        """Get current date in friendly format."""
        now = datetime.now()
        weekday = now.strftime("%A")
        month = now.strftime("%B")
        day = now.day
        year = now.year
        
        # Add ordinal suffix to day
        if 10 <= day <= 20:
            suffix = "th"
        else:
            suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        
        return f"Today is {weekday}, {month} {day}{suffix}, {year}"
    
    def _get_battery_status(self) -> str:
        """Get battery status on macOS."""
        try:
            # Use pmset to get battery info on macOS
            result = subprocess.run(
                ["pmset", "-g", "batt"],
                capture_output=True,
                text=True,
                timeout=2
            )
            
            if result.returncode == 0:
                output = result.stdout
                # Parse battery percentage from output
                import re
                match = re.search(r'(\d+)%', output)
                if match:
                    percentage = match.group(1)
                    
                    # Check if charging
                    if "AC Power" in output or "charging" in output.lower():
                        return f"Battery is at {percentage} percent and charging"
                    else:
                        return f"Battery is at {percentage} percent"
            
            return "Unable to get battery status"
            
        except Exception as e:
            logger.error(f"Error getting battery status: {e}")
            return "Battery status unavailable"
    
    async def _get_weather(self) -> str:
        """Get weather information (placeholder for now)."""
        # TODO: Integrate with weather API
        # For now, return a message about configuration needed
        return "Weather information is not yet configured. You'll need to add an API key for weather services."
    
    async def _open_application(self, command: str) -> str:
        """Open an application on macOS."""
        # Extract app name from command
        command_lower = command.lower()
        
        # Common app mappings
        app_mappings = {
            "browser": "Safari",
            "safari": "Safari",
            "chrome": "Google Chrome",
            "firefox": "Firefox",
            "mail": "Mail",
            "calendar": "Calendar",
            "terminal": "Terminal",
            "iterm": "iTerm",
            "finder": "Finder",
            "music": "Music",
            "spotify": "Spotify",
            "slack": "Slack",
            "messages": "Messages",
            "notes": "Notes",
            "code": "Visual Studio Code",
            "vscode": "Visual Studio Code",
        }
        
        # Find app name in command
        app_name = None
        for keyword, app in app_mappings.items():
            if keyword in command_lower:
                app_name = app
                break
        
        if not app_name:
            # Try to extract app name after "open"
            words = command.split()
            try:
                open_idx = next(i for i, w in enumerate(words) if w.lower() == "open")
                if open_idx + 1 < len(words):
                    app_name = " ".join(words[open_idx + 1:])
            except StopIteration:
                pass
        
        if app_name:
            try:
                subprocess.run(["open", "-a", app_name], check=True, timeout=2)
                return f"Opening {app_name}"
            except subprocess.CalledProcessError:
                return f"Could not find application: {app_name}"
            except Exception as e:
                logger.error(f"Error opening app: {e}")
                return f"Failed to open {app_name}"
        
        return "I didn't understand which application to open"
    
    def _is_complex_query(self, command: str) -> bool:
        """Determine if a command is complex enough to need an LLM."""
        # Simple heuristics for complexity
        complex_indicators = [
            "explain", "describe", "how do", "how does", "what is", "what are",
            "why", "when", "where", "who", "help me", "tell me about",
            "create", "write", "generate", "make", "build", "code",
            "analyze", "compare", "difference between"
        ]
        
        return any(indicator in command for indicator in complex_indicators)
    
    async def _route_to_claude(self, command: str):
        """Route command to Claude session."""
        # For now, just indicate this would go to Claude
        response = f"This looks like a question for Claude: '{command}'. Claude integration is coming soon!"
        await self._speak(response)
        
        # TODO: Implement actual Claude session management
        # Options:
        # 1. Check for existing Claude session via tmux/socket
        # 2. Launch new Claude session if needed
        # 3. Send command via IPC
    
    async def _speak(self, text: str):
        """Speak response using TTS."""
        if not self.tts_enabled:
            logger.info(f"TTS disabled, would speak: {text}")
            print(f"Assistant: {text}")
            return
        
        try:
            # Try to use the existing TTS functionality from converse
            from voice_mode.tools.converse import speak_message
            
            # Speak the message
            await speak_message(
                text,
                voice=None,  # Use default voice
                tts_provider=None,  # Use default provider
                tts_model=None,  # Use default model
                tts_instructions=None,
                audio_format=None,
                speed=None
            )
            
        except ImportError:
            # Fallback to system TTS if converse module not available
            logger.warning("Could not import speak_message, using system TTS")
            try:
                # Use macOS 'say' command as fallback
                subprocess.run(["say", text], timeout=10)
            except Exception as e:
                logger.error(f"Failed to speak: {e}")
                print(f"Assistant: {text}")
        except Exception as e:
            logger.error(f"Error speaking: {e}")
            print(f"Assistant: {text}")


class ListenerConfig:
    """Configuration for the voice listener."""
    
    def __init__(self, config_path: Optional[Path] = None):
        self.wake_words = ["hey voicemode", "hey claude", "computer"]
        self.max_idle_time = 3600  # 1 hour
        self.whisper_model = "base"  # Use base model for efficiency
        self.tts_enabled = True
        self.weather_api_key = os.getenv("OPENWEATHER_API_KEY")
        
        if config_path and config_path.exists():
            self._load_config(config_path)
    
    def _load_config(self, path: Path):
        """Load configuration from YAML file."""
        try:
            import yaml
            with open(path) as f:
                config = yaml.safe_load(f)
            
            if "wake_words" in config:
                if isinstance(config["wake_words"], list):
                    # Simple list of wake words
                    self.wake_words = config["wake_words"]
                elif isinstance(config["wake_words"], dict):
                    # Advanced format with actions
                    self.wake_words = [w["phrase"] for w in config["wake_words"]]
            
            if "performance" in config:
                perf = config["performance"]
                self.whisper_model = perf.get("whisper_model", self.whisper_model)
                self.max_idle_time = perf.get("max_idle_time", self.max_idle_time)
            
            if "audio" in config:
                self.tts_enabled = config["audio"].get("tts_enabled", self.tts_enabled)
            
            if "apis" in config:
                self.weather_api_key = config["apis"].get("weather_key", self.weather_api_key)
                
        except Exception as e:
            logger.error(f"Error loading config from {path}: {e}")


async def run_listener(
    wake_words: Optional[list] = None,
    config_path: Optional[Path] = None,
    daemon: bool = False
) -> None:
    """Run the continuous voice listener.
    
    Args:
        wake_words: Optional list of wake words to use
        config_path: Optional path to configuration file
        daemon: Whether to run as a background daemon
    """
    # Load configuration
    config = ListenerConfig(config_path)
    if wake_words:
        config.wake_words = wake_words
    
    # Create router
    router = SimpleCommandRouter()
    router.tts_enabled = config.tts_enabled
    
    # Import whisper_stream module
    from voice_mode.whisper_stream import continuous_listen_with_whisper_stream, check_whisper_stream_available
    
    # Check if whisper-stream is available
    if not check_whisper_stream_available():
        raise RuntimeError("whisper-stream not found. Please install whisper-stream to use listen mode.")
    
    # Define command callback
    async def handle_command(wake: str, cmd: str):
        """Handle detected wake word and command."""
        try:
            await router.route(wake, cmd)
        except KeyboardInterrupt:
            raise  # Re-raise to stop listening
        except Exception as e:
            logger.error(f"Error handling command: {e}")
            await router._speak("Sorry, I encountered an error processing that command")
    
    # Start listening
    logger.info(f"Starting voice listener with wake words: {config.wake_words}")
    print(f"🎧 Listening for wake words: {', '.join(config.wake_words)}")
    print("📝 Say a wake word followed by your command")
    print("   Example: 'hey voicemode, what time is it?'")
    print("Press Ctrl+C to stop\n")
    
    if daemon:
        # TODO: Implement proper daemon mode
        logger.warning("Daemon mode not yet implemented, running in foreground")
        print("⚠️  Daemon mode not yet implemented, running in foreground")
    
    try:
        await continuous_listen_with_whisper_stream(
            wake_words=config.wake_words,
            command_callback=handle_command,
            max_idle_time=config.max_idle_time
        )
    except KeyboardInterrupt:
        logger.info("Listener stopped by user")
    except Exception as e:
        logger.error(f"Listener error: {e}")
        raise