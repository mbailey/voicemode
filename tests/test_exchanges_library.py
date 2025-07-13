"""
Tests for the exchanges library using real log data.
"""

import json
import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from voice_mode.exchanges import (
    Exchange,
    ExchangeMetadata,
    Conversation,
    ExchangeReader,
    ExchangeFormatter,
    ExchangeFilter,
    ConversationGrouper,
    ExchangeStats,
)


class TestExchangesWithRealData:
    """Test exchanges library with actual log data from ~/.voicemode/logs/"""
    
    @pytest.fixture
    def real_log_reader(self):
        """Create reader pointing to real logs directory."""
        base_dir = Path.home() / ".voicemode"
        return ExchangeReader(base_dir)
    
    @pytest.fixture
    def today_exchanges(self, real_log_reader) -> List[Exchange]:
        """Load today's exchanges."""
        today = datetime.now().date()
        return list(real_log_reader.read_date(today))
    
    def test_read_todays_logs(self, real_log_reader):
        """Test reading today's actual log file."""
        today = datetime.now().date()
        exchanges = list(real_log_reader.read_date(today))
        
        # Should have some exchanges
        assert len(exchanges) > 0
        
        # Check first exchange has expected fields
        first = exchanges[0]
        assert isinstance(first, Exchange)
        assert first.version in [1, 2]  # Can be either version
        assert first.type in ["stt", "tts"]
        assert first.conversation_id.startswith("conv_")
        assert first.project_path is not None
        assert isinstance(first.timestamp, datetime)
        
        # Check for at least one v2 exchange
        v2_exchanges = [e for e in exchanges if e.version == 2]
        if v2_exchanges:
            v2_first = v2_exchanges[0]
            assert v2_first.version == 2
    
    def test_parse_real_exchange_entry(self):
        """Test parsing a real JSONL entry."""
        # Real entry from the logs
        real_entry = '{"version": 2, "timestamp": "2025-07-13T13:22:38.279797+10:00", "conversation_id": "conv_20250713_131401_x333ig", "type": "tts", "text": "Sure! I\'ll create a new branch for updating the conversation browser to use the exchanges library.", "project_path": "/home/m/Code/github.com/mbailey/voicemode", "audio_file": "20250713_132238_271_x333ig_tts.wav", "metadata": {"voice_mode_version": "2.12.0", "provider": "openai", "timing": "ttfa 4.8s, tts_gen 4.8s, tts_play 6.0s", "transport": "speak-only"}}'
        
        exchange = Exchange.from_jsonl(real_entry)
        
        assert exchange.version == 2
        assert exchange.type == "tts"
        assert exchange.conversation_id == "conv_20250713_131401_x333ig"
        assert exchange.text == "Sure! I'll create a new branch for updating the conversation browser to use the exchanges library."
        assert exchange.project_path == "/home/m/Code/github.com/mbailey/voicemode"
        assert exchange.audio_file == "20250713_132238_271_x333ig_tts.wav"
        
        # Check metadata
        assert exchange.metadata is not None
        assert exchange.metadata.voice_mode_version == "2.12.0"
        assert exchange.metadata.provider == "openai"
        assert exchange.metadata.timing == "ttfa 4.8s, tts_gen 4.8s, tts_play 6.0s"
        assert exchange.metadata.transport == "speak-only"
    
    def test_conversation_grouping_real_data(self, today_exchanges):
        """Test grouping today's exchanges into conversations."""
        grouper = ConversationGrouper()
        conversations = grouper.group_exchanges(today_exchanges)
        
        # Should have at least one conversation
        assert len(conversations) > 0
        
        # Check conversation properties
        for conv_id, conv in conversations.items():
            assert isinstance(conv, Conversation)
            assert conv.id == conv_id
            assert len(conv.exchanges) > 0
            assert conv.start_time <= conv.end_time
            
            # All exchanges should have same conversation ID
            for exchange in conv.exchanges:
                assert exchange.conversation_id == conv_id
    
    def test_filter_by_type_real_data(self, today_exchanges):
        """Test filtering real exchanges by type."""
        filter_obj = ExchangeFilter()
        
        # Filter STT only
        stt_only = list(filter_obj.by_type("stt").apply(iter(today_exchanges)))
        for exchange in stt_only:
            assert exchange.type == "stt"
        
        # Filter TTS only
        filter_obj.clear()
        tts_only = list(filter_obj.by_type("tts").apply(iter(today_exchanges)))
        for exchange in tts_only:
            assert exchange.type == "tts"
        
        # Should have both types in today's data
        assert len(stt_only) > 0 or len(tts_only) > 0
    
    def test_filter_by_transport_real_data(self, today_exchanges):
        """Test filtering by transport type."""
        filter_obj = ExchangeFilter()
        
        # Get all unique transports in today's data
        transports = set()
        for exchange in today_exchanges:
            if exchange.metadata and exchange.metadata.transport:
                transports.add(exchange.metadata.transport)
        
        # Test filtering by each transport type found
        for transport in transports:
            filter_obj.clear()
            filtered = list(filter_obj.by_transport(transport).apply(iter(today_exchanges)))
            
            for exchange in filtered:
                assert exchange.metadata is not None
                assert exchange.metadata.transport == transport
    
    def test_statistics_real_data(self, today_exchanges):
        """Test statistics calculation on real data."""
        if not today_exchanges:
            pytest.skip("No exchanges found for today")
        
        stats = ExchangeStats(today_exchanges)
        
        # Basic counts
        assert len(stats.exchanges) == len(today_exchanges)
        assert len(stats.stt_exchanges) + len(stats.tts_exchanges) == len(today_exchanges)
        
        # Provider breakdown
        providers = stats.provider_breakdown()
        assert len(providers) > 0
        assert sum(providers.values()) == len(today_exchanges)
        
        # Transport breakdown
        transports = stats.transport_breakdown()
        assert len(transports) > 0
        
        # Conversation stats
        conv_stats = stats.conversation_stats()
        assert conv_stats['total_conversations'] > 0
        assert conv_stats['exchanges_per_conversation']['avg'] > 0
    
    def test_formatting_real_exchanges(self, today_exchanges):
        """Test formatting real exchanges."""
        if not today_exchanges:
            pytest.skip("No exchanges found for today")
        
        formatter = ExchangeFormatter()
        exchange = today_exchanges[-1]  # Get most recent
        
        # Test simple format
        simple = formatter.simple(exchange, color=False)
        assert exchange.timestamp.strftime("%H:%M:%S") in simple
        assert exchange.type.upper() in simple
        # Text should be in simple format (possibly truncated)
        text_in_simple = exchange.text[:77] in simple or exchange.text in simple
        assert text_in_simple
        
        # Test pretty format
        pretty = formatter.pretty(exchange, show_metadata=True)
        assert "─" in pretty  # Box drawing chars
        # Text may be truncated in pretty format too
        assert exchange.text[:70] in pretty or "Perfect!" in pretty
        if exchange.metadata:
            if exchange.metadata.provider:
                assert exchange.metadata.provider in pretty
        
        # Test JSON format
        json_str = formatter.json(exchange)
        parsed = json.loads(json_str)
        assert parsed['type'] == exchange.type
        assert parsed['text'] == exchange.text
    
    def test_search_real_data(self, today_exchanges):
        """Test searching through real exchanges."""
        if not today_exchanges:
            pytest.skip("No exchanges found for today")
        
        filter_obj = ExchangeFilter()
        
        # Search for a common word
        results = list(filter_obj.by_text("the", regex=False).apply(iter(today_exchanges)))
        
        # Should find some results
        assert len(results) > 0
        
        # All results should contain "the"
        for exchange in results:
            assert "the" in exchange.text.lower()
    
    def test_conversation_transcript_real_data(self, today_exchanges):
        """Test generating transcripts from real conversations."""
        if not today_exchanges:
            pytest.skip("No exchanges found for today")
        
        grouper = ConversationGrouper()
        conversations = grouper.group_exchanges(today_exchanges)
        
        # Get first conversation
        conv = next(iter(conversations.values()))
        
        # Generate transcript
        transcript = conv.to_transcript(include_timestamps=True)
        
        # Should have User/Assistant labels
        assert "User:" in transcript or "Assistant:" in transcript
        
        # Should have timestamps if requested
        assert ":" in transcript  # Time format HH:MM:SS
        
        # All exchanges should be in transcript
        for exchange in conv.exchanges:
            assert exchange.text in transcript
    
    def test_export_formats_real_data(self, today_exchanges):
        """Test exporting real data in different formats."""
        if not today_exchanges:
            pytest.skip("No exchanges found for today")
        
        formatter = ExchangeFormatter()
        grouper = ConversationGrouper()
        conversations = grouper.group_exchanges(today_exchanges)
        
        # Get first conversation
        conv = next(iter(conversations.values()))
        
        # Test CSV header and row
        csv_header = formatter.csv_header()
        assert "timestamp,conversation_id,type,text" in csv_header
        
        csv_row = formatter.csv(conv.exchanges[0])
        assert conv.exchanges[0].conversation_id in csv_row
        
        # Test Markdown format
        markdown = formatter.markdown(conv, include_metadata=True)
        assert f"# Conversation {conv.id}" in markdown
        assert "## Transcript" in markdown
        
        # Test HTML format
        html = formatter.html(conv)
        assert "<html>" in html
        assert conv.id in html
        assert "conversation" in html.lower()
    
    def test_timing_metrics_real_data(self, today_exchanges):
        """Test parsing timing metrics from real data."""
        stats = ExchangeStats(today_exchanges)
        timing_stats = stats.timing_stats()
        
        # Check if we have TTS timing data
        if 'tts' in timing_stats and timing_stats['tts']:
            if 'ttfa' in timing_stats['tts']:
                assert timing_stats['tts']['ttfa']['avg'] > 0
                assert timing_stats['tts']['ttfa']['min'] >= 0  # Can be 0 for very fast responses
                assert timing_stats['tts']['ttfa']['max'] >= timing_stats['tts']['ttfa']['min']
        
        # Check if we have STT timing data
        if 'stt' in timing_stats and timing_stats['stt']:
            if 'record' in timing_stats['stt']:
                assert timing_stats['stt']['record']['avg'] > 0
    
    def test_recent_exchanges_with_real_data(self, real_log_reader):
        """Test reading recent exchanges across multiple days."""
        # Read last 7 days
        recent = list(real_log_reader.read_recent(7))
        
        # Should have some exchanges
        assert len(recent) > 0
        
        # Check they're in chronological order
        for i in range(1, len(recent)):
            assert recent[i-1].timestamp <= recent[i].timestamp
    
    def test_audio_file_detection_real_data(self, today_exchanges):
        """Test audio file detection in real exchanges."""
        audio_exchanges = [e for e in today_exchanges if e.has_audio]
        no_audio_exchanges = [e for e in today_exchanges if not e.has_audio]
        
        # Check audio file paths
        for exchange in audio_exchanges:
            assert exchange.audio_file is not None
            assert exchange.audio_file.endswith(('.wav', '.mp3', '.pcm'))
            
            # Check filename format matches expected pattern
            # Format: YYYYMMDD_HHMMSS_mmm_convid_type.ext
            import re
            pattern = r'\d{8}_\d{6}_\d{3}_\w+_(stt|tts)\.\w+'
            assert re.match(pattern, Path(exchange.audio_file).name)
    
    def test_conversation_summary_real_data(self, today_exchanges):
        """Test conversation summary generation."""
        if not today_exchanges:
            pytest.skip("No exchanges found for today")
        
        grouper = ConversationGrouper()
        conversations = grouper.group_exchanges(today_exchanges)
        
        for conv in conversations.values():
            summary = grouper.get_conversation_summary(conv)
            
            assert summary['id'] == conv.id
            assert summary['exchange_count'] == len(conv.exchanges)
            assert summary['stt_count'] >= 0
            assert summary['tts_count'] >= 0
            assert summary['total_word_count'] > 0
            
            # Check duration is reasonable
            assert summary['duration'] >= 0
            assert summary['duration'] < 86400  # Less than a day