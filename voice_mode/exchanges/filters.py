"""
Filters for searching and filtering exchanges.
"""

import re
from datetime import datetime
from typing import Iterator, Callable, Optional, List

from voice_mode.exchanges.models import Exchange


class ExchangeFilter:
    """Filter exchanges by various criteria."""
    
    def __init__(self):
        """Initialize empty filter."""
        self.filters: List[Callable[[Exchange], bool]] = []
    
    def by_type(self, exchange_type: str) -> 'ExchangeFilter':
        """Filter by STT/TTS type.
        
        Args:
            exchange_type: "stt", "tts", or "all"
            
        Returns:
            Self for chaining
        """
        if exchange_type.lower() == "stt":
            self.filters.append(lambda e: e.is_stt)
        elif exchange_type.lower() == "tts":
            self.filters.append(lambda e: e.is_tts)
        # "all" doesn't add a filter
        
        return self
    
    def by_text(self, pattern: str, regex: bool = False, ignore_case: bool = True) -> 'ExchangeFilter':
        """Filter by text content.
        
        Args:
            pattern: Text pattern to search for
            regex: Whether to use regex matching
            ignore_case: Whether to ignore case
            
        Returns:
            Self for chaining
        """
        if regex:
            flags = re.IGNORECASE if ignore_case else 0
            compiled = re.compile(pattern, flags)
            self.filters.append(lambda e: bool(compiled.search(e.text)))
        else:
            if ignore_case:
                pattern_lower = pattern.lower()
                self.filters.append(lambda e: pattern_lower in e.text.lower())
            else:
                self.filters.append(lambda e: pattern in e.text)
        
        return self
    
    def by_transport(self, transport: str) -> 'ExchangeFilter':
        """Filter by transport type.
        
        Args:
            transport: Transport type (local, livekit, speak-only, etc.)
            
        Returns:
            Self for chaining
        """
        transport_lower = transport.lower()
        self.filters.append(
            lambda e: e.metadata and e.metadata.transport and 
                     e.metadata.transport.lower() == transport_lower
        )
        
        return self
    
    def by_provider(self, provider: str) -> 'ExchangeFilter':
        """Filter by provider.
        
        Args:
            provider: Provider name (openai, kokoro, etc.)
            
        Returns:
            Self for chaining
        """
        provider_lower = provider.lower()
        self.filters.append(
            lambda e: e.metadata and e.metadata.provider and 
                     e.metadata.provider.lower() == provider_lower
        )
        
        return self
    
    def by_voice(self, voice: str) -> 'ExchangeFilter':
        """Filter by TTS voice.
        
        Args:
            voice: Voice name (alloy, nova, etc.)
            
        Returns:
            Self for chaining
        """
        voice_lower = voice.lower()
        self.filters.append(
            lambda e: e.is_tts and e.metadata and e.metadata.voice and 
                     e.metadata.voice.lower() == voice_lower
        )
        
        return self
    
    def by_model(self, model: str) -> 'ExchangeFilter':
        """Filter by model.
        
        Args:
            model: Model name (whisper-1, tts-1, etc.)
            
        Returns:
            Self for chaining
        """
        model_lower = model.lower()
        self.filters.append(
            lambda e: e.metadata and e.metadata.model and 
                     e.metadata.model.lower() == model_lower
        )
        
        return self
    
    def by_conversation(self, conversation_id: str) -> 'ExchangeFilter':
        """Filter by conversation ID.
        
        Args:
            conversation_id: Conversation ID to filter by
            
        Returns:
            Self for chaining
        """
        self.filters.append(lambda e: e.conversation_id == conversation_id)
        
        return self
    
    def by_project(self, project_path: str) -> 'ExchangeFilter':
        """Filter by project path.
        
        Args:
            project_path: Project path (can be partial match)
            
        Returns:
            Self for chaining
        """
        self.filters.append(
            lambda e: e.project_path and project_path in e.project_path
        )
        
        return self
    
    def by_time_range(self, start: Optional[datetime] = None, end: Optional[datetime] = None) -> 'ExchangeFilter':
        """Filter by time range.
        
        Args:
            start: Start time (inclusive)
            end: End time (inclusive)
            
        Returns:
            Self for chaining
        """
        if start:
            self.filters.append(lambda e: e.timestamp >= start)
        if end:
            self.filters.append(lambda e: e.timestamp <= end)
        
        return self
    
    def has_audio(self) -> 'ExchangeFilter':
        """Filter to only exchanges with audio files.
        
        Returns:
            Self for chaining
        """
        self.filters.append(lambda e: e.has_audio)
        
        return self
    
    def has_error(self) -> 'ExchangeFilter':
        """Filter to only exchanges with errors.
        
        Returns:
            Self for chaining
        """
        self.filters.append(
            lambda e: e.metadata and e.metadata.error is not None
        )
        
        return self
    
    def by_silence_detection(self, enabled: Optional[bool] = None) -> 'ExchangeFilter':
        """Filter by silence detection status.
        
        Args:
            enabled: True for enabled, False for disabled, None for has any setting
            
        Returns:
            Self for chaining
        """
        if enabled is None:
            # Has any silence detection settings
            self.filters.append(
                lambda e: e.is_stt and e.metadata and e.metadata.silence_detection is not None
            )
        else:
            # Specific enabled/disabled state
            self.filters.append(
                lambda e: e.is_stt and e.metadata and e.metadata.silence_detection and
                         e.metadata.silence_detection.get('enabled') == enabled
            )
        
        return self
    
    def by_duration(self, min_ms: Optional[int] = None, max_ms: Optional[int] = None) -> 'ExchangeFilter':
        """Filter by audio duration.
        
        Args:
            min_ms: Minimum duration in milliseconds
            max_ms: Maximum duration in milliseconds
            
        Returns:
            Self for chaining
        """
        if min_ms is not None:
            self.filters.append(lambda e: e.duration_ms is not None and e.duration_ms >= min_ms)
        if max_ms is not None:
            self.filters.append(lambda e: e.duration_ms is not None and e.duration_ms <= max_ms)
        
        return self
    
    def apply(self, exchanges: Iterator[Exchange]) -> Iterator[Exchange]:
        """Apply all filters to exchanges.
        
        Args:
            exchanges: Iterator of exchanges to filter
            
        Yields:
            Filtered exchanges
        """
        for exchange in exchanges:
            # Check if all filters pass
            if all(f(exchange) for f in self.filters):
                yield exchange
    
    def clear(self) -> 'ExchangeFilter':
        """Clear all filters.
        
        Returns:
            Self for chaining
        """
        self.filters.clear()
        return self
    
    def __len__(self) -> int:
        """Get number of active filters."""
        return len(self.filters)