"""Listen mode for continuous voice assistant functionality."""

import asyncio
import logging
import os
import subprocess
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path

# aiohttp imported in _get_weather method when needed

logger = logging.getLogger("voice-mode")


class SimpleCommandRouter:
    """Minimal command router for voice commands."""
    
    def __init__(self):
        self.tts_enabled = not os.getenv('VOICEMODE_LISTEN_NO_TTS')
        self.last_command = None
        self.command_count = 0
        
        # Conversation mode state
        self.conversation_mode = False
        self.conversation_history = []  # Message history for context
        self.conversation_start_time = None
        self.max_conversation_history = 20  # Keep last N messages
        
    async def route(self, wake_word: str, command: str):
        """Route command to appropriate handler.
        
        Args:
            wake_word: The wake word that triggered this command
            command: The command text to process
        """
        self.last_command = command
        self.command_count += 1
        command_lower = command.lower().strip()
        
        # In conversation mode, we show commands differently
        if self.conversation_mode:
            logger.info(f"Conversation #{self.command_count}: '{command}'")
            print(f"\n💬 You: {command}")
            
            # Check for conversation exit triggers
            if any(phrase in command_lower for phrase in [
                "stop conversation", "exit chat", "stop chatting", 
                "end conversation", "stop talking", "back to listening"
            ]):
                await self._exit_conversation_mode()
                return
            
            # In conversation mode, everything goes to Ollama with context
            await self._continue_conversation(command)
            return
        else:
            logger.info(f"Routing command #{self.command_count}: '{command}' (wake: '{wake_word}')")
            print(f"\n🎤 Heard: '{wake_word}, {command}'")
        
        # Check for conversation entry triggers
        if any(phrase in command_lower for phrase in [
            "let's chat", "let's talk", "start conversation",
            "chat with me", "talk to me", "conversation mode"
        ]):
            await self._enter_conversation_mode()
            return
        
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
            
        # Ollama-specific commands (any mention of ollama or robot)
        elif "ollama" in command_lower or "robot" in command_lower:
            await self._route_to_claude(command)  # Routes to Ollama if available
            
        # Claude-specific commands or complex queries
        elif "claude" in wake_word.lower() or self._is_complex_query(command_lower):
            await self._route_to_claude(command)
            
        # Stop/exit commands
        elif any(phrase in command_lower for phrase in ["stop listening", "goodbye", "exit", "quit"]):
            await self._speak("Goodbye!")
            raise KeyboardInterrupt("User requested exit")
            
        # Default: send everything else to Ollama/LLM
        else:
            await self._route_to_claude(command)  # Routes to Ollama if available, falls back to message
    
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
        """Get weather information from OpenWeatherMap."""
        import os
        import aiohttp
        import json
        
        api_key = os.getenv("OPENWEATHER_API_KEY")
        if not api_key:
            return "Weather service not configured. Please set OPENWEATHER_API_KEY environment variable."
        
        # Get location from environment or use default
        location = os.getenv("WEATHER_LOCATION", "Melbourne,AU")
        
        try:
            # OpenWeatherMap API endpoint
            url = f"https://api.openweathermap.org/data/2.5/weather"
            params = {
                "q": location,
                "appid": api_key,
                "units": "metric"  # Use Celsius
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Extract weather info
                        temp = round(data["main"]["temp"])
                        feels_like = round(data["main"]["feels_like"])
                        description = data["weather"][0]["description"]
                        humidity = data["main"]["humidity"]
                        city = data["name"]
                        
                        # Format response
                        response_text = f"In {city}, it's currently {temp} degrees"
                        
                        if abs(feels_like - temp) > 2:
                            response_text += f", feels like {feels_like}"
                        
                        response_text += f", with {description}"
                        
                        if humidity > 70:
                            response_text += f" and {humidity}% humidity"
                        
                        return response_text
                    else:
                        logger.error(f"Weather API error: {response.status}")
                        return "Unable to get weather information right now"
                        
        except asyncio.TimeoutError:
            return "Weather service is taking too long to respond"
        except Exception as e:
            logger.error(f"Weather error: {e}")
            return "Sorry, I couldn't get the weather information"
    
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
        """Route command to Claude session or local LLM."""
        # First try Ollama if available
        ollama_response = await self._try_ollama(command)
        if ollama_response:
            await self._speak(ollama_response)
            return
            
        # Fall back to indicating Claude would handle it
        response = f"This looks like a question for Claude: '{command}'. Claude integration is coming soon!"
        await self._speak(response)
        
        # TODO: Implement actual Claude session management
        # Options:
        # 1. Check for existing Claude session via tmux/socket
        # 2. Launch new Claude session if needed
        # 3. Send command via IPC
    
    async def _enter_conversation_mode(self):
        """Enter conversation mode for continuous chat."""
        self.conversation_mode = True
        self.conversation_history = []
        self.conversation_start_time = datetime.now()
        
        # Play enter chime (rising tone)
        await self._play_chime("enter")
        
        response = "Entering conversation mode. Let's chat! Say 'stop conversation' when you're done."
        await self._speak(response)
        print("\n🤖 [Conversation Mode Active]")
        logger.info("Entered conversation mode")
    
    async def _exit_conversation_mode(self):
        """Exit conversation mode and return to wake word listening."""
        self.conversation_mode = False
        duration = (datetime.now() - self.conversation_start_time).total_seconds() if self.conversation_start_time else 0
        
        # Play exit chime (falling tone)
        await self._play_chime("exit")
        
        response = "Exiting conversation mode. Back to listening for wake words."
        await self._speak(response)
        print(f"\n🤖 [Conversation Mode Ended - Duration: {duration:.0f}s]")
        logger.info(f"Exited conversation mode after {duration:.0f} seconds")
        
        # Clear conversation history
        self.conversation_history = []
        self.conversation_start_time = None
    
    async def _continue_conversation(self, user_input: str):
        """Continue conversation with context."""
        # Add user message to history
        self.conversation_history.append({"role": "user", "content": user_input})
        
        # Trim history if too long
        if len(self.conversation_history) > self.max_conversation_history:
            # Keep system message if present, then trim oldest messages
            self.conversation_history = self.conversation_history[-self.max_conversation_history:]
        
        # Get response from Ollama with conversation context
        response = await self._try_ollama_with_context(self.conversation_history)
        
        if response:
            # Add assistant response to history
            self.conversation_history.append({"role": "assistant", "content": response})
            print(f"🤖 Assistant: {response}")
            await self._speak(response)
        else:
            # Fallback if Ollama isn't available
            fallback = "I'm having trouble connecting to the conversation service."
            print(f"🤖 Assistant: {fallback}")
            await self._speak(fallback)
    
    async def _try_ollama_with_context(self, messages: list) -> Optional[str]:
        """Try to get response from Ollama with full conversation context."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.debug("OpenAI SDK not available")
            return None
        
        # Check if Ollama is configured
        ollama_model = os.getenv("OLLAMA_MODEL", "voice-assistant")
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        
        try:
            # Create OpenAI client pointing to Ollama
            client = AsyncOpenAI(
                base_url=f"{ollama_url}/v1",
                api_key="ollama"
            )
            
            # Get completion from Ollama with full conversation history
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=ollama_model,
                    messages=messages,
                    max_tokens=200,  # Slightly longer for conversation
                    temperature=0.8
                ),
                timeout=30
            )
            
            if response and response.choices:
                llm_response = response.choices[0].message.content.strip()
                
                if llm_response:
                    logger.info(f"Got Ollama conversation response")
                    # Clean up response for speech
                    llm_response = llm_response.replace("*", "").replace("#", "")
                    # Keep response conversational length
                    sentences = llm_response.split(". ")[:4]  # Allow up to 4 sentences in conversation
                    return ". ".join(sentences)
            
            return None
                        
        except asyncio.TimeoutError:
            logger.debug("Ollama request timed out")
            return None
        except Exception as e:
            logger.debug(f"Ollama error: {e}")
            return None
    
    async def _try_ollama(self, command: str) -> Optional[str]:
        """Try to get response from local Ollama server using OpenAI SDK."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            logger.debug("OpenAI SDK not available")
            return None
        
        # Check if Ollama is configured
        ollama_model = os.getenv("OLLAMA_MODEL", "voice-assistant")
        ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
        
        try:
            # Create OpenAI client pointing to Ollama
            client = AsyncOpenAI(
                base_url=f"{ollama_url}/v1",
                api_key="ollama"  # Ollama doesn't need a real API key
            )
            
            # Get completion from Ollama
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=ollama_model,
                    messages=[
                        {"role": "user", "content": command}
                    ],
                    max_tokens=150,
                    temperature=0.8  # Match our model's temperature setting
                ),
                timeout=30
            )
            
            if response and response.choices:
                llm_response = response.choices[0].message.content.strip()
                
                if llm_response:
                    logger.info(f"Got Ollama response for: {command[:50]}...")
                    print(f"[Ollama Response] {llm_response[:100]}...")
                    # Clean up response for speech
                    # Remove markdown, excessive punctuation, etc.
                    llm_response = llm_response.replace("*", "").replace("#", "")
                    # Limit to first few sentences for voice
                    sentences = llm_response.split(". ")[:3]
                    return ". ".join(sentences)
            
            return None
                        
        except asyncio.TimeoutError:
            logger.debug("Ollama request timed out")
            return None
        except Exception as e:
            logger.debug(f"Ollama error: {e}")
            return None
    
    async def _play_chime(self, chime_type: str):
        """Play an audio chime for mode transitions."""
        try:
            # Use macOS system sounds for now
            if chime_type == "enter":
                # Rising tone - entering conversation
                subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], timeout=1)
            elif chime_type == "exit":
                # Falling tone - exiting conversation
                subprocess.run(["afplay", "/System/Library/Sounds/Blow.aiff"], timeout=1)
        except Exception as e:
            logger.debug(f"Could not play chime: {e}")
            # Fail silently - chimes are nice but not essential
    
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
    daemon: bool = False,
    show_audio_level: bool = True,
    debug_mode: bool = False
) -> None:
    """Run the continuous voice listener.
    
    Args:
        wake_words: Optional list of wake words to use
        config_path: Optional path to configuration file
        daemon: Whether to run as a background daemon
        show_audio_level: Whether to show audio level visualization
        debug_mode: Whether to show debug output (transcribed text)
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
    
    # Define conversation mode check
    def is_in_conversation_mode():
        """Check if we're in conversation mode."""
        return router.conversation_mode
    
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
            max_idle_time=config.max_idle_time,
            show_audio_level=show_audio_level,
            debug_mode=debug_mode,
            conversation_mode_check=is_in_conversation_mode
        )
    except KeyboardInterrupt:
        logger.info("Listener stopped by user")
    except Exception as e:
        logger.error(f"Listener error: {e}")
        raise