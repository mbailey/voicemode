"""
Conversation logging system using JSONL format.

Tracks all utterances (STT and TTS) in a structured, append-only format
for real-time conversation tracking and analysis.
"""

import json
import os
import random
import string
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

from voice_mode.__version__ import __version__
from voice_mode.config import BASE_DIR


class ConversationLogger:
    """Handles JSONL-based conversation logging."""
    
    SCHEMA_VERSION = 2
    CONVERSATION_GAP_MINUTES = 5
    
    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize the conversation logger.
        
        Args:
            base_dir: Base directory for logs. Defaults to ~/.voicemode/logs/
        """
        self.base_dir = base_dir or Path(BASE_DIR) / "logs"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        self.conversation_id = None
        self.current_project_path = os.getcwd()
        
        # Initialize conversation ID on startup
        self._initialize_conversation_id()
    
    def _initialize_conversation_id(self):
        """Initialize conversation ID, checking for continuity from previous logs."""
        last_entry = self._get_last_log_entry()
        
        if last_entry:
            try:
                last_timestamp = datetime.fromisoformat(
                    last_entry['timestamp'].replace('Z', '+00:00')
                )
                time_diff = (datetime.now().astimezone() - last_timestamp).total_seconds()
                
                # Check if within conversation window and same project
                if (time_diff < self.CONVERSATION_GAP_MINUTES * 60 and
                    last_entry.get('project_path') == self.current_project_path):
                    self.conversation_id = last_entry['conversation_id']
                    return
            except Exception:
                pass  # Generate new ID on any parsing error
        
        # Generate new conversation ID
        self.conversation_id = self._generate_conversation_id()
    
    def _get_last_log_entry(self) -> Optional[Dict[str, Any]]:
        """Get the last entry from today's or yesterday's log file."""
        # Try today's log first
        today = datetime.now().date()
        log_file = self._get_log_file_path(today)
        
        last_entry = self._read_last_line(log_file)
        if last_entry:
            return last_entry
        
        # Check yesterday's log for midnight rollover
        yesterday = today - timedelta(days=1)
        yesterday_log = self._get_log_file_path(yesterday)
        
        return self._read_last_line(yesterday_log)
    
    def _read_last_line(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """Read the last line from a log file."""
        if not file_path.exists() or file_path.stat().st_size == 0:
            return None
        
        try:
            # Read file backwards to get last line efficiently
            with open(file_path, 'rb') as f:
                # Go to end of file
                f.seek(0, 2)
                file_size = f.tell()
                
                # Read backwards until we find a newline
                buffer_size = min(file_size, 1024)
                f.seek(max(0, file_size - buffer_size))
                
                lines = f.read().decode('utf-8').strip().split('\n')
                if lines:
                    return json.loads(lines[-1])
        except Exception:
            return None
        
        return None
    
    def _generate_conversation_id(self) -> str:
        """Generate a new conversation ID."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"conv_{timestamp}_{random_suffix}"
    
    def _get_log_file_path(self, date: datetime.date) -> Path:
        """Get the log file path for a given date."""
        filename = f"exchanges_{date.strftime('%Y-%m-%d')}.jsonl"
        return self.base_dir / filename
    
    def log_utterance(self,
                     utterance_type: str,
                     text: str,
                     audio_file: Optional[str] = None,
                     duration_ms: Optional[int] = None,
                     metadata: Optional[Dict[str, Any]] = None) -> None:
        """Log an utterance to the JSONL file.
        
        Args:
            utterance_type: Either "stt" or "tts"
            text: The transcribed or synthesized text
            audio_file: Path to the audio file (relative to base_dir)
            duration_ms: Duration of the audio in milliseconds
            metadata: Additional metadata about the utterance
        """
        # Check if we need to start a new conversation
        self._check_conversation_continuity()
        
        # Build the log entry
        entry = {
            "version": self.SCHEMA_VERSION,
            "timestamp": datetime.now().astimezone().isoformat(),
            "conversation_id": self.conversation_id,
            "type": utterance_type,
            "text": text,
            "project_path": self.current_project_path,
            "audio_file": audio_file,
            "duration_ms": duration_ms,
            "metadata": {
                "voice_mode_version": __version__,
                **(metadata or {})
            }
        }
        
        # Remove None values for cleaner logs
        entry = {k: v for k, v in entry.items() if v is not None}
        if "metadata" in entry:
            entry["metadata"] = {k: v for k, v in entry["metadata"].items() if v is not None}
        
        # Write to today's log file
        log_file = self._get_log_file_path(datetime.now().date())
        with open(log_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')
    
    def _check_conversation_continuity(self):
        """Check if we need to start a new conversation based on time gap."""
        # This could be called periodically to ensure conversations
        # are properly segmented even during long sessions
        last_entry = self._get_last_log_entry()
        
        if last_entry and last_entry['conversation_id'] == self.conversation_id:
            try:
                last_timestamp = datetime.fromisoformat(
                    last_entry['timestamp'].replace('Z', '+00:00')
                )
                time_diff = (datetime.now().astimezone() - last_timestamp).total_seconds()
                
                # Start new conversation if gap is too large or project changed
                if (time_diff >= self.CONVERSATION_GAP_MINUTES * 60 or
                    last_entry.get('project_path') != self.current_project_path):
                    self.conversation_id = self._generate_conversation_id()
            except Exception:
                pass  # Keep current conversation ID on error
    
    def log_stt(self, text: str, audio_file: Optional[str] = None,
                duration_ms: Optional[int] = None, **kwargs) -> None:
        """Log a speech-to-text utterance."""
        metadata = {
            "model": kwargs.get("model"),
            "provider": kwargs.get("provider"),
            "language": kwargs.get("language"),
            "audio_format": kwargs.get("audio_format"),
            "transport": kwargs.get("transport"),
            "timing": kwargs.get("timing"),
            "silence_detection": kwargs.get("silence_detection"),
            "error": kwargs.get("error"),
        }
        
        self.log_utterance("stt", text, audio_file, duration_ms, metadata)
    
    def log_tts(self, text: str, audio_file: Optional[str] = None,
                duration_ms: Optional[int] = None, **kwargs) -> None:
        """Log a text-to-speech utterance."""
        metadata = {
            "model": kwargs.get("model"),
            "voice": kwargs.get("voice"),
            "provider": kwargs.get("provider"),
            "audio_format": kwargs.get("audio_format"),
            "timing": kwargs.get("timing"),
            "transport": kwargs.get("transport"),
            "emotion": kwargs.get("emotion"),
            "error": kwargs.get("error"),
        }
        
        self.log_utterance("tts", text, audio_file, duration_ms, metadata)


# Global instance for easy access
_conversation_logger = None


def get_conversation_logger() -> ConversationLogger:
    """Get the global conversation logger instance."""
    global _conversation_logger
    if _conversation_logger is None:
        _conversation_logger = ConversationLogger()
    return _conversation_logger