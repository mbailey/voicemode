"""Voice Mode utility modules."""

from .event_logger import (
    EventLogger,
    get_event_logger,
    initialize_event_logger,
    log_tts_start,
    log_tts_first_audio,
    log_recording_start,
    log_recording_end,
    log_stt_start,
    log_stt_complete,
    log_tool_request_start,
    log_tool_request_end
)

# macos_mic is intentionally not imported here - it uses lazy loading
# via voice_mode.utils.macos_mic to avoid loading CoreAudio frameworks
# on non-macOS platforms or when the feature is disabled.

__all__ = [
    "EventLogger",
    "get_event_logger",
    "initialize_event_logger",
    "log_tts_start",
    "log_tts_first_audio",
    "log_recording_start",
    "log_recording_end",
    "log_stt_start",
    "log_stt_complete",
    "log_tool_request_start",
    "log_tool_request_end"
]