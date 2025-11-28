"""Type definitions for transcription module."""

from typing import TypedDict, List, Optional, Literal
from enum import Enum


class TranscriptionBackend(str, Enum):
    """Available transcription backends."""
    OPENAI = "openai"
    WHISPERX = "whisperx"
    WHISPER_CPP = "whisper-cpp"
    WHISPER_CLI = "whisper-cli"


class OutputFormat(str, Enum):
    """Available output formats."""
    JSON = "json"
    SRT = "srt"
    VTT = "vtt"
    CSV = "csv"


class WordData(TypedDict, total=False):
    """Word-level timestamp data."""
    word: str
    start: float
    end: float
    probability: Optional[float]
    speaker: Optional[str]


class SegmentData(TypedDict, total=False):
    """Segment-level timestamp data."""
    id: Optional[int]
    text: str
    start: float
    end: float
    words: Optional[List[WordData]]
    speaker: Optional[str]


class TranscriptionResult(TypedDict, total=False):
    """Complete transcription result."""
    text: str
    language: str
    duration: Optional[float]
    segments: List[SegmentData]
    words: Optional[List[WordData]]
    backend: str
    model: Optional[str]
    success: bool
    error: Optional[str]
    formatted_content: Optional[str]  # For non-JSON output formats