"""
Exchange data models for voice mode conversation logs.
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Literal, Dict, Any, List


@dataclass
class ExchangeMetadata:
    """Metadata for an exchange."""
    voice_mode_version: str
    model: Optional[str] = None
    voice: Optional[str] = None
    provider: Optional[str] = None
    timing: Optional[str] = None
    transport: Optional[str] = None
    audio_format: Optional[str] = None
    silence_detection: Optional[Dict[str, Any]] = None
    language: Optional[str] = None
    emotion: Optional[str] = None
    error: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExchangeMetadata':
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Exchange:
    """Single exchange (STT or TTS) entry."""
    version: int
    timestamp: datetime
    conversation_id: str
    type: Literal["stt", "tts"]
    text: str
    project_path: Optional[str] = None
    audio_file: Optional[str] = None
    duration_ms: Optional[int] = None
    metadata: Optional[ExchangeMetadata] = None
    
    @classmethod
    def from_jsonl(cls, line: str) -> 'Exchange':
        """Parse from JSONL line."""
        data = json.loads(line)
        
        # Parse timestamp
        timestamp_str = data['timestamp']
        # Handle both formats: with Z suffix and with timezone offset
        if timestamp_str.endswith('Z'):
            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        else:
            timestamp = datetime.fromisoformat(timestamp_str)
        
        # Parse metadata
        metadata = None
        if 'metadata' in data and data['metadata']:
            metadata = ExchangeMetadata.from_dict(data['metadata'])
        
        return cls(
            version=data.get('version', 1),  # Default to v1 for backward compatibility
            timestamp=timestamp,
            conversation_id=data['conversation_id'],
            type=data['type'],
            text=data['text'],
            project_path=data.get('project_path'),
            audio_file=data.get('audio_file'),
            duration_ms=data.get('duration_ms'),
            metadata=metadata
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {
            'version': self.version,
            'timestamp': self.timestamp.isoformat(),
            'conversation_id': self.conversation_id,
            'type': self.type,
            'text': self.text,
        }
        
        # Add optional fields
        if self.project_path:
            result['project_path'] = self.project_path
        if self.audio_file:
            result['audio_file'] = self.audio_file
        if self.duration_ms is not None:
            result['duration_ms'] = self.duration_ms
        if self.metadata:
            result['metadata'] = self.metadata.to_dict()
        
        return result
    
    def to_jsonl(self) -> str:
        """Convert to JSONL string."""
        return json.dumps(self.to_dict())
    
    @property
    def is_stt(self) -> bool:
        """Check if this is an STT entry."""
        return self.type == "stt"
    
    @property
    def is_tts(self) -> bool:
        """Check if this is a TTS entry."""
        return self.type == "tts"
    
    @property
    def has_audio(self) -> bool:
        """Check if this exchange has an associated audio file."""
        return self.audio_file is not None
    
    @property
    def provider_info(self) -> str:
        """Get provider information string."""
        if not self.metadata:
            return "unknown"
        
        parts = []
        if self.metadata.provider:
            parts.append(self.metadata.provider)
        if self.metadata.model:
            parts.append(self.metadata.model)
        if self.metadata.voice and self.is_tts:
            parts.append(f"voice: {self.metadata.voice}")
        
        return " | ".join(parts) if parts else "unknown"


@dataclass
class Conversation:
    """A complete conversation with multiple exchanges."""
    id: str
    start_time: datetime
    end_time: datetime
    project_path: Optional[str]
    exchanges: List[Exchange] = field(default_factory=list)
    
    @property
    def duration(self) -> timedelta:
        """Total conversation duration."""
        return self.end_time - self.start_time
    
    @property
    def exchange_count(self) -> int:
        """Number of exchanges."""
        return len(self.exchanges)
    
    @property
    def stt_count(self) -> int:
        """Number of STT exchanges."""
        return sum(1 for e in self.exchanges if e.is_stt)
    
    @property
    def tts_count(self) -> int:
        """Number of TTS exchanges."""
        return sum(1 for e in self.exchanges if e.is_tts)
    
    def to_transcript(self, include_timestamps: bool = False) -> str:
        """Format as readable transcript."""
        lines = []
        
        for exchange in self.exchanges:
            prefix = "User" if exchange.is_stt else "Assistant"
            
            if include_timestamps:
                timestamp = exchange.timestamp.strftime("%H:%M:%S")
                lines.append(f"[{timestamp}] {prefix}: {exchange.text}")
            else:
                lines.append(f"{prefix}: {exchange.text}")
        
        return "\n".join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'id': self.id,
            'start_time': self.start_time.isoformat(),
            'end_time': self.end_time.isoformat(),
            'duration_seconds': self.duration.total_seconds(),
            'project_path': self.project_path,
            'exchange_count': self.exchange_count,
            'stt_count': self.stt_count,
            'tts_count': self.tts_count,
            'exchanges': [e.to_dict() for e in self.exchanges]
        }