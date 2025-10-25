"""
Unified event logging system for Voice Mode.

This module provides real-time event tracking for voice interactions,
enabling accurate timing calculations, debugging, and analytics.
"""

import json
import time
import threading
import queue
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field
import logging
import atexit

logger = logging.getLogger("voicemode.event-logger")


@dataclass
class VoiceEvent:
    """Represents a single event in the voice interaction timeline."""
    timestamp: str
    event_type: str
    session_id: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "session_id": self.session_id,
            "data": self.data
        }


class EventLogger:
    """Thread-safe event logging system for voice interactions."""
    
    # Event type constants
    # TTS Events
    TTS_REQUEST = "TTS_REQUEST"
    TTS_START = "TTS_START"
    TTS_FIRST_AUDIO = "TTS_FIRST_AUDIO"
    TTS_PLAYBACK_START = "TTS_PLAYBACK_START"
    TTS_PLAYBACK_END = "TTS_PLAYBACK_END"
    TTS_ERROR = "TTS_ERROR"
    
    # Recording Events
    RECORDING_START = "RECORDING_START"
    RECORDING_END = "RECORDING_END"
    RECORDING_SAVED = "RECORDING_SAVED"
    
    # STT Events
    STT_REQUEST = "STT_REQUEST"
    STT_START = "STT_START"
    STT_COMPLETE = "STT_COMPLETE"
    STT_NO_SPEECH = "STT_NO_SPEECH"
    STT_ERROR = "STT_ERROR"
    
    # System Events
    SESSION_START = "SESSION_START"
    SESSION_END = "SESSION_END"
    TRANSPORT_SWITCH = "TRANSPORT_SWITCH"
    PROVIDER_SWITCH = "PROVIDER_SWITCH"
    
    # Tool Events
    TOOL_REQUEST_START = "TOOL_REQUEST_START"
    TOOL_REQUEST_END = "TOOL_REQUEST_END"
    
    def __init__(self, log_dir: Optional[Path] = None, enabled: bool = True):
        """
        Initialize the event logger.
        
        Args:
            log_dir: Directory for log files (default: ~/voicemode_logs)
            enabled: Whether event logging is enabled
        """
        self.enabled = enabled
        if not self.enabled:
            logger.info("Event logging disabled")
            return
            
        self.log_dir = log_dir or Path.home() / "voicemode_logs"
        self.log_dir.mkdir(exist_ok=True)
        
        # Current log file (rotated daily)
        self.log_file: Optional[Path] = None
        self.current_date: Optional[datetime] = None
        
        # Thread-safe queue for async writing
        self.event_queue: queue.Queue = queue.Queue()
        self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer_thread.start()
        
        # In-memory event buffer for current session
        self.session_events: List[VoiceEvent] = []
        self.session_id: Optional[str] = None
        self._lock = threading.Lock()
        
        # Register cleanup on exit
        atexit.register(self._cleanup)
        
        logger.info(f"Event logger initialized, logging to {self.log_dir}")
    
    def log_event(self, event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
        """
        Log an event with automatic timestamp.
        
        Args:
            event_type: Type of event (use class constants)
            data: Optional event-specific data
        """
        if not self.enabled:
            return
            
        event = VoiceEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            session_id=self.session_id,
            data=data or {}
        )
        
        # Add to queue for file writing
        self.event_queue.put(event)
        
        # Keep in memory for current session
        with self._lock:
            if self.session_id:
                self.session_events.append(event)
        
        logger.debug(f"Event logged: {event_type} (session: {self.session_id})")
    
    def start_session(self, session_id: Optional[str] = None) -> str:
        """
        Start a new conversation session.
        
        Args:
            session_id: Optional session ID (generated if not provided)
            
        Returns:
            The session ID
        """
        if not self.enabled:
            return ""
            
        with self._lock:
            self.session_id = session_id or f"conv_{int(time.time() * 1000)}"
            self.session_events = []
        
        self.log_event(self.SESSION_START)
        logger.info(f"Started session: {self.session_id}")
        return self.session_id
    
    def end_session(self) -> Optional[Dict[str, Any]]:
        """
        End current session and return timing metrics.
        
        Returns:
            Dictionary of calculated metrics or None if no session
        """
        if not self.enabled or not self.session_id:
            return None
        
        self.log_event(self.SESSION_END)
        
        with self._lock:
            metrics = self._calculate_metrics()
            
            # Clear session
            self.session_id = None
            self.session_events = []
        
        logger.info("Session ended, metrics calculated")
        return metrics
    
    def _calculate_metrics(self) -> Dict[str, float]:
        """Calculate timing metrics from session events."""
        metrics = {}
        events_by_type = {}
        
        # Group events by type
        for event in self.session_events:
            event_type = event.event_type
            if event_type not in events_by_type:
                events_by_type[event_type] = []
            events_by_type[event_type].append(event)
        
        # Helper to parse timestamps
        def parse_ts(event: VoiceEvent) -> datetime:
            return datetime.fromisoformat(event.timestamp.replace('Z', '+00:00'))
        
        # Calculate key metrics
        # Time to First Audio (TTFA)
        if self.TTS_START in events_by_type and self.TTS_FIRST_AUDIO in events_by_type:
            tts_start = parse_ts(events_by_type[self.TTS_START][0])
            ttfa = parse_ts(events_by_type[self.TTS_FIRST_AUDIO][0])
            metrics["ttfa"] = (ttfa - tts_start).total_seconds()
        
        # Recording duration
        if self.RECORDING_START in events_by_type and self.RECORDING_END in events_by_type:
            rec_start = parse_ts(events_by_type[self.RECORDING_START][0])
            rec_end = parse_ts(events_by_type[self.RECORDING_END][0])
            metrics["recording_duration"] = (rec_end - rec_start).total_seconds()
        
        # STT processing time
        if self.STT_START in events_by_type and self.STT_COMPLETE in events_by_type:
            stt_start = parse_ts(events_by_type[self.STT_START][0])
            stt_complete = parse_ts(events_by_type[self.STT_COMPLETE][0])
            metrics["stt_processing"] = (stt_complete - stt_start).total_seconds()
        
        # User-perceived response time: from end of recording to start of TTS playback
        if self.RECORDING_END in events_by_type and self.TTS_PLAYBACK_START in events_by_type:
            rec_end = parse_ts(events_by_type[self.RECORDING_END][0])
            tts_playback = parse_ts(events_by_type[self.TTS_PLAYBACK_START][0])
            metrics["response_time"] = (tts_playback - rec_end).total_seconds()
        
        # Total conversation time
        if self.SESSION_START in events_by_type and self.SESSION_END in events_by_type:
            session_start = parse_ts(events_by_type[self.SESSION_START][0])
            session_end = parse_ts(events_by_type[self.SESSION_END][0])
            metrics["session_duration"] = (session_end - session_start).total_seconds()
        
        return metrics
    
    def get_session_events(self) -> List[VoiceEvent]:
        """Get all events from the current session."""
        with self._lock:
            return list(self.session_events)
    
    def _writer_loop(self) -> None:
        """Background thread for writing events to file."""
        while True:
            try:
                # Use timeout to allow thread to exit on shutdown
                event = self.event_queue.get(timeout=1)
                self._write_event(event)
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in event writer: {e}")
    
    def _write_event(self, event: VoiceEvent) -> None:
        """Write event to log file."""
        # Check if we need to rotate log file
        today = datetime.now().date()
        if self.current_date != today:
            self.current_date = today
            log_filename = f"voicemode_events_{today.isoformat()}.jsonl"
            self.log_file = self.log_dir / log_filename
            logger.info(f"Rotating log file to: {self.log_file}")
        
        # Append event
        try:
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(event.to_dict()) + '\n')
        except Exception as e:
            logger.error(f"Failed to write event to log: {e}")
    
    def _cleanup(self) -> None:
        """Cleanup on exit - flush any remaining events."""
        if not self.enabled:
            return
            
        # Give writer thread time to flush queue
        timeout = time.time() + 2  # 2 second timeout
        while not self.event_queue.empty() and time.time() < timeout:
            time.sleep(0.1)
        
        logger.info("Event logger cleanup complete")


# Global event logger instance (singleton)
_event_logger: Optional[EventLogger] = None


def get_event_logger() -> Optional[EventLogger]:
    """Get the global event logger instance."""
    return _event_logger


def initialize_event_logger(log_dir: Optional[Path] = None, enabled: bool = True) -> EventLogger:
    """
    Initialize the global event logger.
    
    This should be called once on server startup.
    
    Args:
        log_dir: Directory for log files
        enabled: Whether event logging is enabled
        
    Returns:
        The initialized event logger
    """
    global _event_logger
    if _event_logger is None:
        _event_logger = EventLogger(log_dir=log_dir, enabled=enabled)
    return _event_logger


# Convenience functions for common events
def log_tts_start(message: str, voice: str, model: str) -> None:
    """Log TTS start event."""
    logger = get_event_logger()
    if logger:
        logger.log_event(EventLogger.TTS_START, {
            "message": message,
            "voice": voice,
            "model": model
        })


def log_tts_first_audio() -> None:
    """Log TTS first audio received."""
    logger = get_event_logger()
    if logger:
        logger.log_event(EventLogger.TTS_FIRST_AUDIO)


def log_recording_start() -> None:
    """Log recording start."""
    logger = get_event_logger()
    if logger:
        logger.log_event(EventLogger.RECORDING_START)


def log_recording_end(duration: Optional[float] = None, samples: Optional[int] = None) -> None:
    """Log recording end."""
    logger = get_event_logger()
    if logger:
        data = {}
        if duration is not None:
            data["duration"] = duration
        if samples is not None:
            data["samples"] = samples
        logger.log_event(EventLogger.RECORDING_END, data)


def log_stt_start() -> None:
    """Log STT start."""
    logger = get_event_logger()
    if logger:
        logger.log_event(EventLogger.STT_START)


def log_stt_complete(text: str) -> None:
    """Log STT completion."""
    logger = get_event_logger()
    if logger:
        logger.log_event(EventLogger.STT_COMPLETE, {"text": text})


def log_tool_request_start(tool_name: str, parameters: Optional[Dict[str, Any]] = None) -> None:
    """Log tool request start."""
    logger = get_event_logger()
    if logger:
        data = {"tool_name": tool_name}
        if parameters:
            # Don't log full message content, just basic params
            data["has_params"] = True
            if "wait_for_response" in parameters:
                data["wait_for_response"] = parameters["wait_for_response"]
        logger.log_event(EventLogger.TOOL_REQUEST_START, data)


def log_tool_request_end(tool_name: str, success: bool = True) -> None:
    """Log tool request end."""
    logger = get_event_logger()
    if logger:
        logger.log_event(EventLogger.TOOL_REQUEST_END, {
            "tool_name": tool_name,
            "success": success
        })