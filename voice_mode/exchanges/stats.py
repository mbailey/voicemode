"""
Statistics calculation for exchanges.
"""

from collections import defaultdict, Counter
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import re

from voice_mode.exchanges.models import Exchange


class ExchangeStats:
    """Calculate statistics from exchanges."""
    
    def __init__(self, exchanges: List[Exchange]):
        """Initialize with list of exchanges.
        
        Args:
            exchanges: List of exchanges to analyze
        """
        self.exchanges = exchanges
        
        # Separate by type for convenience
        self.stt_exchanges = [e for e in exchanges if e.is_stt]
        self.tts_exchanges = [e for e in exchanges if e.is_tts]
    
    def timing_stats(self) -> Dict[str, Any]:
        """Calculate timing statistics.
        
        Returns:
            Dictionary with timing metrics
        """
        stats = {
            'stt': self._calculate_stt_timing_stats(),
            'tts': self._calculate_tts_timing_stats(),
            'overall': {}
        }
        
        # Calculate overall turnaround times
        turnaround_times = []
        
        for i in range(len(self.exchanges) - 1):
            current = self.exchanges[i]
            next_ex = self.exchanges[i + 1]
            
            # Only count when switching between STT and TTS
            if current.type != next_ex.type:
                turnaround = (next_ex.timestamp - current.timestamp).total_seconds()
                turnaround_times.append(turnaround)
        
        if turnaround_times:
            stats['overall']['avg_turnaround'] = sum(turnaround_times) / len(turnaround_times)
            stats['overall']['min_turnaround'] = min(turnaround_times)
            stats['overall']['max_turnaround'] = max(turnaround_times)
            stats['overall']['turnaround_count'] = len(turnaround_times)
        
        return stats
    
    def _calculate_stt_timing_stats(self) -> Dict[str, Any]:
        """Calculate STT-specific timing stats."""
        record_times = []
        stt_times = []
        
        for exchange in self.stt_exchanges:
            if exchange.metadata and exchange.metadata.timing:
                # Parse timing string: "record 3.2s, stt 1.4s"
                timing_match = re.findall(r'(\w+)\s+([\d.]+)s', exchange.metadata.timing)
                for metric, value in timing_match:
                    if metric == 'record':
                        record_times.append(float(value))
                    elif metric == 'stt':
                        stt_times.append(float(value))
        
        stats = {}
        
        if record_times:
            stats['record'] = {
                'avg': sum(record_times) / len(record_times),
                'min': min(record_times),
                'max': max(record_times),
                'count': len(record_times)
            }
        
        if stt_times:
            stats['processing'] = {
                'avg': sum(stt_times) / len(stt_times),
                'min': min(stt_times),
                'max': max(stt_times),
                'count': len(stt_times)
            }
        
        return stats
    
    def _calculate_tts_timing_stats(self) -> Dict[str, Any]:
        """Calculate TTS-specific timing stats."""
        ttfa_times = []
        gen_times = []
        play_times = []
        
        for exchange in self.tts_exchanges:
            if exchange.metadata and exchange.metadata.timing:
                # Parse timing string: "ttfa 1.2s, gen 2.3s, play 5.6s"
                timing_match = re.findall(r'(\w+)\s+([\d.]+)s', exchange.metadata.timing)
                for metric, value in timing_match:
                    if metric == 'ttfa':
                        ttfa_times.append(float(value))
                    elif metric == 'gen':
                        gen_times.append(float(value))
                    elif metric == 'play':
                        play_times.append(float(value))
        
        stats = {}
        
        if ttfa_times:
            stats['ttfa'] = {
                'avg': sum(ttfa_times) / len(ttfa_times),
                'min': min(ttfa_times),
                'max': max(ttfa_times),
                'count': len(ttfa_times)
            }
        
        if gen_times:
            stats['generation'] = {
                'avg': sum(gen_times) / len(gen_times),
                'min': min(gen_times),
                'max': max(gen_times),
                'count': len(gen_times)
            }
        
        if play_times:
            stats['playback'] = {
                'avg': sum(play_times) / len(play_times),
                'min': min(play_times),
                'max': max(play_times),
                'count': len(play_times)
            }
        
        return stats
    
    def provider_breakdown(self) -> Dict[str, int]:
        """Count exchanges by provider.
        
        Returns:
            Dictionary mapping provider names to counts
        """
        provider_counts = Counter()
        
        for exchange in self.exchanges:
            if exchange.metadata and exchange.metadata.provider:
                provider_counts[exchange.metadata.provider] += 1
            else:
                provider_counts['unknown'] += 1
        
        return dict(provider_counts)
    
    def model_breakdown(self) -> Dict[str, Dict[str, int]]:
        """Count exchanges by model, separated by type.
        
        Returns:
            Dictionary with 'stt' and 'tts' sub-dictionaries of model counts
        """
        stt_models = Counter()
        tts_models = Counter()
        
        for exchange in self.exchanges:
            model = 'unknown'
            if exchange.metadata and exchange.metadata.model:
                model = exchange.metadata.model
            
            if exchange.is_stt:
                stt_models[model] += 1
            else:
                tts_models[model] += 1
        
        return {
            'stt': dict(stt_models),
            'tts': dict(tts_models)
        }
    
    def voice_breakdown(self) -> Dict[str, int]:
        """Count TTS exchanges by voice.
        
        Returns:
            Dictionary mapping voice names to counts
        """
        voice_counts = Counter()
        
        for exchange in self.tts_exchanges:
            if exchange.metadata and exchange.metadata.voice:
                voice_counts[exchange.metadata.voice] += 1
            else:
                voice_counts['unknown'] += 1
        
        return dict(voice_counts)
    
    def transport_breakdown(self) -> Dict[str, int]:
        """Count exchanges by transport type.
        
        Returns:
            Dictionary mapping transport types to counts
        """
        transport_counts = Counter()
        
        for exchange in self.exchanges:
            if exchange.metadata and exchange.metadata.transport:
                transport_counts[exchange.metadata.transport] += 1
            else:
                transport_counts['unknown'] += 1
        
        return dict(transport_counts)
    
    def hourly_distribution(self) -> Dict[int, int]:
        """Distribution of exchanges by hour of day.
        
        Returns:
            Dictionary mapping hour (0-23) to count
        """
        hour_counts = defaultdict(int)
        
        for exchange in self.exchanges:
            hour = exchange.timestamp.hour
            hour_counts[hour] += 1
        
        # Ensure all hours are represented
        return {hour: hour_counts.get(hour, 0) for hour in range(24)}
    
    def daily_distribution(self) -> Dict[str, int]:
        """Distribution of exchanges by date.
        
        Returns:
            Dictionary mapping date string (YYYY-MM-DD) to count
        """
        daily_counts = defaultdict(int)
        
        for exchange in self.exchanges:
            date_str = exchange.timestamp.date().isoformat()
            daily_counts[date_str] += 1
        
        return dict(sorted(daily_counts.items()))
    
    def conversation_stats(self) -> Dict[str, Any]:
        """Conversation-level statistics.
        
        Returns:
            Dictionary with conversation metrics
        """
        # Group by conversation ID
        conversations = defaultdict(list)
        for exchange in self.exchanges:
            conversations[exchange.conversation_id].append(exchange)
        
        # Calculate stats per conversation
        conv_lengths = []
        conv_durations = []
        conv_exchange_counts = []
        
        for conv_id, conv_exchanges in conversations.items():
            if len(conv_exchanges) > 0:
                conv_exchange_counts.append(len(conv_exchanges))
                
                # Sort by timestamp
                conv_exchanges.sort(key=lambda e: e.timestamp)
                
                # Calculate duration
                duration = (conv_exchanges[-1].timestamp - conv_exchanges[0].timestamp).total_seconds()
                conv_durations.append(duration)
                
                # Calculate total word count
                total_words = sum(len(e.text.split()) for e in conv_exchanges)
                conv_lengths.append(total_words)
        
        stats = {
            'total_conversations': len(conversations),
            'exchanges_per_conversation': {
                'avg': sum(conv_exchange_counts) / len(conv_exchange_counts) if conv_exchange_counts else 0,
                'min': min(conv_exchange_counts) if conv_exchange_counts else 0,
                'max': max(conv_exchange_counts) if conv_exchange_counts else 0,
            },
            'duration_seconds': {
                'avg': sum(conv_durations) / len(conv_durations) if conv_durations else 0,
                'min': min(conv_durations) if conv_durations else 0,
                'max': max(conv_durations) if conv_durations else 0,
            },
            'word_count': {
                'avg': sum(conv_lengths) / len(conv_lengths) if conv_lengths else 0,
                'min': min(conv_lengths) if conv_lengths else 0,
                'max': max(conv_lengths) if conv_lengths else 0,
            }
        }
        
        return stats
    
    def error_stats(self) -> Dict[str, Any]:
        """Statistics about errors.
        
        Returns:
            Dictionary with error metrics
        """
        error_exchanges = [e for e in self.exchanges if e.metadata and e.metadata.error]
        
        error_types = Counter()
        for exchange in error_exchanges:
            # Try to categorize error
            error_msg = exchange.metadata.error.lower()
            if 'timeout' in error_msg:
                error_types['timeout'] += 1
            elif 'auth' in error_msg or 'unauthorized' in error_msg:
                error_types['authentication'] += 1
            elif 'rate' in error_msg:
                error_types['rate_limit'] += 1
            elif 'network' in error_msg or 'connection' in error_msg:
                error_types['network'] += 1
            else:
                error_types['other'] += 1
        
        return {
            'total_errors': len(error_exchanges),
            'error_rate': len(error_exchanges) / len(self.exchanges) if self.exchanges else 0,
            'error_types': dict(error_types),
            'errors_by_type': {
                'stt': sum(1 for e in error_exchanges if e.is_stt),
                'tts': sum(1 for e in error_exchanges if e.is_tts),
            }
        }
    
    def silence_detection_stats(self) -> Dict[str, Any]:
        """Statistics about silence detection usage.
        
        Returns:
            Dictionary with silence detection metrics
        """
        stt_with_vad = []
        stt_without_vad = []
        
        for exchange in self.stt_exchanges:
            if exchange.metadata and exchange.metadata.silence_detection:
                if exchange.metadata.silence_detection.get('enabled'):
                    stt_with_vad.append(exchange)
                else:
                    stt_without_vad.append(exchange)
        
        # Calculate average recording times
        with_vad_times = []
        without_vad_times = []
        
        for exchange in stt_with_vad:
            if exchange.metadata and exchange.metadata.timing:
                match = re.search(r'record\s+([\d.]+)s', exchange.metadata.timing)
                if match:
                    with_vad_times.append(float(match.group(1)))
        
        for exchange in stt_without_vad:
            if exchange.metadata and exchange.metadata.timing:
                match = re.search(r'record\s+([\d.]+)s', exchange.metadata.timing)
                if match:
                    without_vad_times.append(float(match.group(1)))
        
        stats = {
            'vad_enabled_count': len(stt_with_vad),
            'vad_disabled_count': len(stt_without_vad),
            'vad_usage_rate': len(stt_with_vad) / len(self.stt_exchanges) if self.stt_exchanges else 0,
        }
        
        if with_vad_times:
            stats['avg_record_time_with_vad'] = sum(with_vad_times) / len(with_vad_times)
        
        if without_vad_times:
            stats['avg_record_time_without_vad'] = sum(without_vad_times) / len(without_vad_times)
        
        return stats
    
    def get_summary_report(self) -> str:
        """Generate a human-readable summary report.
        
        Returns:
            Formatted string report
        """
        lines = ["Exchange Statistics Summary", "=" * 40, ""]
        
        # Basic counts
        lines.append(f"Total Exchanges: {len(self.exchanges)}")
        lines.append(f"  STT: {len(self.stt_exchanges)}")
        lines.append(f"  TTS: {len(self.tts_exchanges)}")
        lines.append("")
        
        # Date range
        if self.exchanges:
            sorted_exchanges = sorted(self.exchanges, key=lambda e: e.timestamp)
            start = sorted_exchanges[0].timestamp
            end = sorted_exchanges[-1].timestamp
            lines.append(f"Date Range: {start.date()} to {end.date()}")
            lines.append(f"Duration: {end - start}")
            lines.append("")
        
        # Providers
        lines.append("Providers:")
        for provider, count in self.provider_breakdown().items():
            lines.append(f"  {provider}: {count}")
        lines.append("")
        
        # Transports
        lines.append("Transports:")
        for transport, count in self.transport_breakdown().items():
            lines.append(f"  {transport}: {count}")
        lines.append("")
        
        # Timing
        timing = self.timing_stats()
        if timing.get('overall') and timing['overall'].get('avg_turnaround'):
            lines.append("Timing:")
            lines.append(f"  Avg Turnaround: {timing['overall']['avg_turnaround']:.2f}s")
            
            if timing.get('tts') and timing['tts'].get('ttfa'):
                lines.append(f"  Avg TTFA: {timing['tts']['ttfa']['avg']:.2f}s")
            
            lines.append("")
        
        # Conversations
        conv_stats = self.conversation_stats()
        lines.append(f"Conversations: {conv_stats['total_conversations']}")
        lines.append(f"  Avg Exchanges: {conv_stats['exchanges_per_conversation']['avg']:.1f}")
        lines.append(f"  Avg Duration: {conv_stats['duration_seconds']['avg']:.1f}s")
        
        return "\n".join(lines)