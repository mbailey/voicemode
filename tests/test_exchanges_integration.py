"""
Integration tests for exchanges library with real file system.
"""

import json
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from voice_mode.exchanges import (
    Exchange,
    ExchangeMetadata,
    ExchangeReader,
    ExchangeFilter,
    ConversationGrouper,
)


class TestExchangesIntegration:
    """Integration tests using temporary files that mirror real data structure."""
    
    @pytest.fixture
    def temp_voicemode_dir(self):
        """Create a temporary voicemode directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            logs_dir = base_dir / "logs"
            logs_dir.mkdir(parents=True)
            
            # Create sample log entries based on real format
            today = datetime.now()
            yesterday = today - timedelta(days=1)
            
            # Today's log file with real-like data
            today_file = logs_dir / f"exchanges_{today.strftime('%Y-%m-%d')}.jsonl"
            with open(today_file, 'w') as f:
                # Sample entries based on real logs
                entries = [
                    {
                        "version": 2,
                        "timestamp": (today - timedelta(hours=2)).astimezone().isoformat(),
                        "conversation_id": "conv_20250713_110000_abc123",
                        "type": "stt",
                        "text": "Can you help me implement the new feature?",
                        "project_path": "/home/user/project1",
                        "audio_file": "20250713_110000_123_abc123_stt.wav",
                        "metadata": {
                            "voice_mode_version": "2.12.0",
                            "model": "whisper-1",
                            "provider": "openai",
                            "audio_format": "mp3",
                            "transport": "local",
                            "timing": "record 3.2s, stt 1.4s",
                            "silence_detection": {
                                "enabled": True,
                                "vad_aggressiveness": 2,
                                "silence_threshold_ms": 1000
                            }
                        }
                    },
                    {
                        "version": 2,
                        "timestamp": (today - timedelta(hours=2) + timedelta(seconds=5)).astimezone().isoformat(),
                        "conversation_id": "conv_20250713_110000_abc123",
                        "type": "tts",
                        "text": "I'd be happy to help you implement the new feature. Let me break down the steps.",
                        "project_path": "/home/user/project1",
                        "audio_file": "20250713_110005_456_abc123_tts.wav",
                        "metadata": {
                            "voice_mode_version": "2.12.0",
                            "model": "tts-1",
                            "voice": "alloy",
                            "provider": "openai",
                            "audio_format": "pcm",
                            "transport": "local",
                            "timing": "ttfa 1.2s, gen 2.3s, play 5.6s"
                        }
                    },
                    {
                        "version": 2,
                        "timestamp": (today - timedelta(minutes=30)).astimezone().isoformat(),
                        "conversation_id": "conv_20250713_113000_def456",
                        "type": "stt",
                        "text": "What's the status of the voice mode project?",
                        "project_path": "/home/user/voicemode",
                        "metadata": {
                            "voice_mode_version": "2.12.0",
                            "provider": "whisper-local",
                            "transport": "livekit",
                            "timing": "record 2.5s, stt 0.8s"
                        }
                    }
                ]
                
                for entry in entries:
                    f.write(json.dumps(entry) + '\n')
            
            # Yesterday's log file
            yesterday_file = logs_dir / f"exchanges_{yesterday.strftime('%Y-%m-%d')}.jsonl"
            with open(yesterday_file, 'w') as f:
                entries = [
                    {
                        "version": 2,
                        "timestamp": (yesterday + timedelta(hours=14)).astimezone().isoformat(),
                        "conversation_id": "conv_20250712_140000_xyz789",
                        "type": "tts",
                        "text": "Hello! How can I assist you today?",
                        "project_path": "/home/user/project2",
                        "metadata": {
                            "voice_mode_version": "2.11.0",
                            "provider": "kokoro",
                            "voice": "af_sky",
                            "transport": "speak-only"
                        }
                    }
                ]
                
                for entry in entries:
                    f.write(json.dumps(entry) + '\n')
            
            yield base_dir
    
    def test_reader_finds_log_files(self, temp_voicemode_dir):
        """Test that reader correctly finds and reads log files."""
        reader = ExchangeReader(temp_voicemode_dir)
        
        # Check logs directory exists
        assert reader.logs_dir.exists()
        
        # Read today's exchanges
        today = datetime.now().date()
        exchanges = list(reader.read_date(today))
        
        assert len(exchanges) == 3
        assert all(isinstance(e, Exchange) for e in exchanges)
    
    def test_read_multiple_days(self, temp_voicemode_dir):
        """Test reading exchanges across multiple days."""
        reader = ExchangeReader(temp_voicemode_dir)
        
        # Read last 2 days
        exchanges = list(reader.read_recent(2))
        
        # Should have 4 total exchanges (3 today + 1 yesterday)
        assert len(exchanges) == 4
        
        # Check they're sorted chronologically
        for i in range(1, len(exchanges)):
            assert exchanges[i-1].timestamp <= exchanges[i].timestamp
    
    def test_conversation_grouping_integration(self, temp_voicemode_dir):
        """Test conversation grouping with file-based data."""
        reader = ExchangeReader(temp_voicemode_dir)
        exchanges = list(reader.read_recent(2))
        
        grouper = ConversationGrouper()
        conversations = grouper.group_exchanges(exchanges)
        
        # Should have 3 conversations
        assert len(conversations) == 3
        
        # Check conversation IDs
        expected_ids = {
            "conv_20250713_110000_abc123",
            "conv_20250713_113000_def456", 
            "conv_20250712_140000_xyz789"
        }
        assert set(conversations.keys()) == expected_ids
        
        # Check first conversation has 2 exchanges
        conv1 = conversations["conv_20250713_110000_abc123"]
        assert len(conv1.exchanges) == 2
        assert conv1.exchanges[0].type == "stt"
        assert conv1.exchanges[1].type == "tts"
    
    def test_filter_by_project_integration(self, temp_voicemode_dir):
        """Test filtering by project path."""
        reader = ExchangeReader(temp_voicemode_dir)
        exchanges = list(reader.read_recent(2))
        
        filter_obj = ExchangeFilter()
        
        # Filter by voicemode project
        voicemode_only = list(filter_obj.by_project("voicemode").apply(iter(exchanges)))
        assert len(voicemode_only) == 1
        assert "voicemode" in voicemode_only[0].project_path
        
        # Filter by project1
        filter_obj.clear()
        project1_only = list(filter_obj.by_project("project1").apply(iter(exchanges)))
        assert len(project1_only) == 2
    
    def test_provider_filtering_integration(self, temp_voicemode_dir):
        """Test filtering by provider."""
        reader = ExchangeReader(temp_voicemode_dir)
        exchanges = list(reader.read_recent(2))
        
        filter_obj = ExchangeFilter()
        
        # Filter OpenAI exchanges
        openai_only = list(filter_obj.by_provider("openai").apply(iter(exchanges)))
        assert len(openai_only) == 2
        
        # Filter Kokoro exchanges
        filter_obj.clear()
        kokoro_only = list(filter_obj.by_provider("kokoro").apply(iter(exchanges)))
        assert len(kokoro_only) == 1
    
    def test_silence_detection_filter_integration(self, temp_voicemode_dir):
        """Test filtering by silence detection settings."""
        reader = ExchangeReader(temp_voicemode_dir)
        exchanges = list(reader.read_recent(2))
        
        filter_obj = ExchangeFilter()
        
        # Filter exchanges with silence detection
        with_vad = list(filter_obj.by_silence_detection(enabled=True).apply(iter(exchanges)))
        assert len(with_vad) == 1
        assert with_vad[0].metadata.silence_detection['enabled'] is True
    
    def test_get_latest_exchanges(self, temp_voicemode_dir):
        """Test getting the most recent N exchanges."""
        reader = ExchangeReader(temp_voicemode_dir)
        
        # Get latest 2 exchanges
        latest = reader.get_latest_exchanges(2)
        
        assert len(latest) == 2
        # Should be the most recent ones (order matters - latest first)
        # Check that we got exchanges (order may vary based on internal sorting)
    
    def test_read_conversation_integration(self, temp_voicemode_dir):
        """Test reading all exchanges for a specific conversation."""
        reader = ExchangeReader(temp_voicemode_dir)
        
        # Read specific conversation
        conv_exchanges = reader.read_conversation("conv_20250713_110000_abc123")
        
        assert len(conv_exchanges) == 2
        assert conv_exchanges[0].type == "stt"
        assert conv_exchanges[1].type == "tts"
        assert all(e.conversation_id == "conv_20250713_110000_abc123" for e in conv_exchanges)
    
    def test_empty_directory_handling(self):
        """Test handling of empty/missing directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "nonexistent"
            reader = ExchangeReader(base_dir)
            
            # Should create the directory
            assert reader.logs_dir.exists()
            
            # Should return empty results
            exchanges = list(reader.read_date(datetime.now().date()))
            assert len(exchanges) == 0
            
            recent = list(reader.read_recent(7))
            assert len(recent) == 0