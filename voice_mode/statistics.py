"""
Voice conversation statistics tracking and dashboard.

This module provides real-time tracking of voice conversation performance metrics
including turnaround times, processing speeds, and session statistics.
"""

import time
import json
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from statistics import mean, median
from pathlib import Path

import logging

logger = logging.getLogger("voicemode")


@dataclass
class ConversationMetric:
    """Individual conversation interaction metrics."""
    timestamp: float
    message: str
    response: str
    ttfa: Optional[float] = None  # Time to first audio
    tts_generation: Optional[float] = None
    tts_playback: Optional[float] = None
    tts_total: Optional[float] = None
    stt_processing: Optional[float] = None
    recording_duration: Optional[float] = None
    total_time: Optional[float] = None
    transport: Optional[str] = None
    voice_provider: Optional[str] = None
    voice_name: Optional[str] = None
    model: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


@dataclass 
class SessionStatistics:
    """Aggregated statistics for the current session."""
    start_time: float
    total_interactions: int = 0
    successful_interactions: int = 0
    failed_interactions: int = 0
    
    # Timing statistics (in seconds)
    avg_ttfa: Optional[float] = None
    min_ttfa: Optional[float] = None
    max_ttfa: Optional[float] = None
    
    avg_tts_generation: Optional[float] = None
    min_tts_generation: Optional[float] = None
    max_tts_generation: Optional[float] = None
    
    avg_tts_playback: Optional[float] = None
    min_tts_playback: Optional[float] = None
    max_tts_playback: Optional[float] = None
    
    avg_stt_processing: Optional[float] = None
    min_stt_processing: Optional[float] = None
    max_stt_processing: Optional[float] = None
    
    avg_total_time: Optional[float] = None
    min_total_time: Optional[float] = None
    max_total_time: Optional[float] = None
    
    # Provider usage counts
    voice_providers_used: Dict[str, int] = None
    transports_used: Dict[str, int] = None
    voices_used: Dict[str, int] = None
    models_used: Dict[str, int] = None
    
    # Session duration
    session_duration: Optional[float] = None
    
    def __post_init__(self):
        if self.voice_providers_used is None:
            self.voice_providers_used = {}
        if self.transports_used is None:
            self.transports_used = {}
        if self.voices_used is None:
            self.voices_used = {}
        if self.models_used is None:
            self.models_used = {}


class ConversationStatistics:
    """Thread-safe conversation statistics tracker."""
    
    def __init__(self):
        self._lock = threading.Lock()
        self._metrics: List[ConversationMetric] = []
        self._session_start = time.time()
        self._max_metrics = 1000  # Keep last 1000 interactions
        
    def add_metric(self, metric: ConversationMetric) -> None:
        """Add a new conversation metric."""
        with self._lock:
            self._metrics.append(metric)
            
            # Keep only the most recent metrics to prevent memory bloat
            if len(self._metrics) > self._max_metrics:
                self._metrics = self._metrics[-self._max_metrics:]
                
    def parse_timing_string(self, timing_str: str) -> Dict[str, float]:
        """Parse timing string from conversation tools response."""
        timings = {}
        if not timing_str:
            return timings
            
        # Example: "ttfa 0.5s, tts_gen 1.2s, tts_play 2.1s, tts_total 3.3s, record 15.0s, stt 0.8s, total 19.1s"
        parts = timing_str.split(", ")
        for part in parts:
            if " " in part:
                key, value = part.split(" ", 1)
                if value.endswith("s"):
                    try:
                        timings[key] = float(value[:-1])
                    except ValueError:
                        continue
        return timings
        
    def add_conversation_result(self, 
                              message: str, 
                              response: str,
                              timing_str: Optional[str] = None,
                              transport: Optional[str] = None,
                              voice_provider: Optional[str] = None,
                              voice_name: Optional[str] = None,
                              model: Optional[str] = None,
                              success: bool = True,
                              error_message: Optional[str] = None) -> None:
        """Add a conversation result with parsed timing data."""
        
        # Parse timing information
        timings = self.parse_timing_string(timing_str) if timing_str else {}
        
        metric = ConversationMetric(
            timestamp=time.time(),
            message=message[:100] + "..." if len(message) > 100 else message,
            response=response[:200] + "..." if len(response) > 200 else response,
            ttfa=timings.get('ttfa'),
            tts_generation=timings.get('tts_gen'),
            tts_playback=timings.get('tts_play'),
            tts_total=timings.get('tts_total'),
            stt_processing=timings.get('stt'),
            recording_duration=timings.get('record'),
            total_time=timings.get('total'),
            transport=transport,
            voice_provider=voice_provider,
            voice_name=voice_name,
            model=model,
            success=success,
            error_message=error_message
        )
        
        self.add_metric(metric)
        
    def get_session_statistics(self) -> SessionStatistics:
        """Calculate current session statistics."""
        with self._lock:
            if not self._metrics:
                return SessionStatistics(start_time=self._session_start)
                
            successful_metrics = [m for m in self._metrics if m.success]
            
            def safe_stat(values: List[float], stat_func):
                """Safely calculate statistics, handling empty lists."""
                if not values:
                    return None
                return stat_func(values)
            
            def safe_values(metrics: List[ConversationMetric], attr: str) -> List[float]:
                """Extract non-None values for an attribute."""
                return [getattr(m, attr) for m in metrics if getattr(m, attr) is not None]
            
            # Calculate timing statistics from successful interactions
            ttfa_values = safe_values(successful_metrics, 'ttfa')
            tts_gen_values = safe_values(successful_metrics, 'tts_generation')
            tts_play_values = safe_values(successful_metrics, 'tts_playback')
            stt_values = safe_values(successful_metrics, 'stt_processing')
            total_values = safe_values(successful_metrics, 'total_time')
            
            # Count provider usage
            voice_providers = {}
            transports = {}
            voices = {}
            models = {}
            
            for metric in self._metrics:
                if metric.voice_provider:
                    voice_providers[metric.voice_provider] = voice_providers.get(metric.voice_provider, 0) + 1
                if metric.transport:
                    transports[metric.transport] = transports.get(metric.transport, 0) + 1
                if metric.voice_name:
                    voices[metric.voice_name] = voices.get(metric.voice_name, 0) + 1
                if metric.model:
                    models[metric.model] = models.get(metric.model, 0) + 1
            
            stats = SessionStatistics(
                start_time=self._session_start,
                total_interactions=len(self._metrics),
                successful_interactions=len(successful_metrics),
                failed_interactions=len(self._metrics) - len(successful_metrics),
                
                # TTFA statistics
                avg_ttfa=safe_stat(ttfa_values, mean),
                min_ttfa=safe_stat(ttfa_values, min),
                max_ttfa=safe_stat(ttfa_values, max),
                
                # TTS generation statistics
                avg_tts_generation=safe_stat(tts_gen_values, mean),
                min_tts_generation=safe_stat(tts_gen_values, min),
                max_tts_generation=safe_stat(tts_gen_values, max),
                
                # TTS playback statistics
                avg_tts_playback=safe_stat(tts_play_values, mean),
                min_tts_playback=safe_stat(tts_play_values, min),
                max_tts_playback=safe_stat(tts_play_values, max),
                
                # STT statistics
                avg_stt_processing=safe_stat(stt_values, mean),
                min_stt_processing=safe_stat(stt_values, min),
                max_stt_processing=safe_stat(stt_values, max),
                
                # Total time statistics
                avg_total_time=safe_stat(total_values, mean),
                min_total_time=safe_stat(total_values, min),
                max_total_time=safe_stat(total_values, max),
                
                # Provider usage
                voice_providers_used=voice_providers,
                transports_used=transports,
                voices_used=voices,
                models_used=models,
                
                # Session duration
                session_duration=time.time() - self._session_start
            )
            
            return stats
    
    def get_recent_metrics(self, limit: int = 10) -> List[ConversationMetric]:
        """Get the most recent conversation metrics."""
        with self._lock:
            return self._metrics[-limit:] if self._metrics else []
    
    def clear_statistics(self) -> None:
        """Clear all statistics and restart the session."""
        with self._lock:
            self._metrics.clear()
            self._session_start = time.time()
    
    def export_metrics(self) -> Dict[str, Any]:
        """Export all metrics and statistics as a dictionary."""
        with self._lock:
            return {
                'session_start': self._session_start,
                'metrics': [asdict(m) for m in self._metrics],
                'statistics': asdict(self.get_session_statistics())
            }
    
    def format_dashboard(self) -> str:
        """Format a text-based dashboard of current statistics."""
        stats = self.get_session_statistics()
        recent = self.get_recent_metrics(5)
        
        lines = []
        lines.append("🎙️ VOICE CONVERSATION STATISTICS")
        lines.append("=" * 50)
        
        # Session overview
        duration = timedelta(seconds=int(stats.session_duration or 0))
        lines.append(f"\n📊 SESSION OVERVIEW")
        lines.append(f"Duration: {duration}")
        lines.append(f"Total Interactions: {stats.total_interactions}")
        lines.append(f"Successful: {stats.successful_interactions}")
        lines.append(f"Failed: {stats.failed_interactions}")
        if stats.total_interactions > 0:
            success_rate = (stats.successful_interactions / stats.total_interactions) * 100
            lines.append(f"Success Rate: {success_rate:.1f}%")
        
        # Performance metrics
        if stats.successful_interactions > 0:
            lines.append(f"\n⚡ PERFORMANCE METRICS (seconds)")
            lines.append("-" * 30)
            
            def format_stat(label: str, avg: Optional[float], min_val: Optional[float], max_val: Optional[float]):
                if avg is not None:
                    return f"{label:20} {avg:6.2f}s  (min: {min_val:5.2f}s, max: {max_val:5.2f}s)"
                return f"{label:20} No data"
            
            if stats.avg_ttfa is not None:
                lines.append(format_stat("Time to First Audio:", stats.avg_ttfa, stats.min_ttfa, stats.max_ttfa))
            
            if stats.avg_tts_generation is not None:
                lines.append(format_stat("TTS Generation:", stats.avg_tts_generation, stats.min_tts_generation, stats.max_tts_generation))
            
            if stats.avg_tts_playback is not None:
                lines.append(format_stat("TTS Playback:", stats.avg_tts_playback, stats.min_tts_playback, stats.max_tts_playback))
            
            if stats.avg_stt_processing is not None:
                lines.append(format_stat("STT Processing:", stats.avg_stt_processing, stats.min_stt_processing, stats.max_stt_processing))
            
            if stats.avg_total_time is not None:
                lines.append(format_stat("Total Turnaround:", stats.avg_total_time, stats.min_total_time, stats.max_total_time))
        
        # Provider usage
        if any([stats.voice_providers_used, stats.transports_used, stats.voices_used]):
            lines.append(f"\n🔧 PROVIDER USAGE")
            lines.append("-" * 30)
            
            if stats.voice_providers_used:
                lines.append("Voice Providers:")
                for provider, count in sorted(stats.voice_providers_used.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"  {provider}: {count} uses")
            
            if stats.transports_used:
                lines.append("Transports:")
                for transport, count in sorted(stats.transports_used.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"  {transport}: {count} uses")
            
            if stats.voices_used:
                lines.append("Voices:")
                for voice, count in sorted(stats.voices_used.items(), key=lambda x: x[1], reverse=True):
                    lines.append(f"  {voice}: {count} uses")
        
        # Recent interactions
        if recent:
            lines.append(f"\n📝 RECENT INTERACTIONS ({len(recent)} of {len(self._metrics)})")
            lines.append("-" * 30)
            
            for i, metric in enumerate(reversed(recent), 1):
                timestamp = datetime.fromtimestamp(metric.timestamp).strftime("%H:%M:%S")
                status = "✅" if metric.success else "❌"
                total_time = f"{metric.total_time:.1f}s" if metric.total_time else "N/A"
                provider = metric.voice_provider or "unknown"
                lines.append(f"{i}. {timestamp} {status} {total_time:>6} [{provider}] {metric.message[:30]}...")
        
        return "\n".join(lines)


# Global statistics tracker instance
_statistics_tracker = ConversationStatistics()


def get_statistics_tracker() -> ConversationStatistics:
    """Get the global statistics tracker instance."""
    return _statistics_tracker


def track_conversation(message: str, 
                      response: str,
                      timing_str: Optional[str] = None,
                      transport: Optional[str] = None,
                      voice_provider: Optional[str] = None,
                      voice_name: Optional[str] = None,
                      model: Optional[str] = None,
                      success: bool = True,
                      error_message: Optional[str] = None) -> None:
    """
    Convenience function to track a conversation interaction.
    
    This should be called from the conversation tools after each interaction.
    """
    _statistics_tracker.add_conversation_result(
        message=message,
        response=response,
        timing_str=timing_str,
        transport=transport,
        voice_provider=voice_provider,
        voice_name=voice_name,
        model=model,
        success=success,
        error_message=error_message
    )