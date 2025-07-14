"""MCP resources for voice conversation statistics."""

import json
from typing import Dict, Any

from ..mcp_instance import mcp
from ..statistics import get_statistics_tracker
from ..config import logger


@mcp.resource("voice://statistics/{type}")
async def current_statistics(type: str = "current") -> str:
    """
    Current voice conversation statistics in JSON format.
    
    Provides real-time access to conversation performance metrics including:
    - Session overview (duration, interaction counts, success rate)
    - Performance metrics (TTFA, TTS, STT timing statistics)
    - Provider usage statistics
    - Recent interaction history
    
    This resource updates automatically as new voice interactions occur.
    """
    try:
        tracker = get_statistics_tracker()
        stats = tracker.get_session_statistics()
        recent = tracker.get_recent_metrics(10)
        
        # Format comprehensive statistics
        data = {
            "session": {
                "start_time": stats.start_time,
                "duration_seconds": stats.session_duration,
                "total_interactions": stats.total_interactions,
                "successful_interactions": stats.successful_interactions,
                "failed_interactions": stats.failed_interactions,
                "success_rate": (stats.successful_interactions / stats.total_interactions * 100) if stats.total_interactions > 0 else 0
            },
            "performance": {
                "ttfa": {
                    "average": stats.avg_ttfa,
                    "minimum": stats.min_ttfa,
                    "maximum": stats.max_ttfa
                },
                "tts_generation": {
                    "average": stats.avg_tts_generation,
                    "minimum": stats.min_tts_generation,
                    "maximum": stats.max_tts_generation
                },
                "tts_playback": {
                    "average": stats.avg_tts_playback,
                    "minimum": stats.min_tts_playback,
                    "maximum": stats.max_tts_playback
                },
                "stt_processing": {
                    "average": stats.avg_stt_processing,
                    "minimum": stats.min_stt_processing,
                    "maximum": stats.max_stt_processing
                },
                "total_turnaround": {
                    "average": stats.avg_total_time,
                    "minimum": stats.min_total_time,
                    "maximum": stats.max_total_time
                }
            },
            "usage": {
                "voice_providers": stats.voice_providers_used,
                "transports": stats.transports_used,
                "voices": stats.voices_used,
                "models": stats.models_used
            },
            "recent_interactions": [
                {
                    "timestamp": metric.timestamp,
                    "message": metric.message,
                    "response": metric.response,
                    "success": metric.success,
                    "timings": {
                        "ttfa": metric.ttfa,
                        "tts_generation": metric.tts_generation,
                        "tts_playback": metric.tts_playback,
                        "stt_processing": metric.stt_processing,
                        "total_time": metric.total_time
                    },
                    "config": {
                        "transport": metric.transport,
                        "voice_provider": metric.voice_provider,
                        "voice_name": metric.voice_name,
                        "model": metric.model
                    },
                    "error_message": metric.error_message
                }
                for metric in recent
            ]
        }
        
        return json.dumps(data, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error generating statistics resource: {e}")
        return json.dumps({"error": str(e)}, indent=2)


@mcp.resource("voice://statistics/summary/{format}")
async def statistics_summary(format: str = "json") -> str:
    """
    Voice conversation performance summary in JSON format.
    
    Provides a concise overview of key performance indicators:
    - Session duration and total interactions
    - Average performance metrics
    - Success rate
    - Primary voice provider usage
    
    This is a lightweight version of the full statistics resource.
    """
    try:
        tracker = get_statistics_tracker()
        stats = tracker.get_session_statistics()
        
        # Get primary providers
        primary_voice_provider = None
        primary_transport = None
        
        if stats.voice_providers_used:
            primary_voice_provider = max(stats.voice_providers_used.items(), key=lambda x: x[1])
        
        if stats.transports_used:
            primary_transport = max(stats.transports_used.items(), key=lambda x: x[1])
        
        data = {
            "session_duration_minutes": (stats.session_duration or 0) / 60,
            "total_interactions": stats.total_interactions,
            "success_rate_percent": (stats.successful_interactions / stats.total_interactions * 100) if stats.total_interactions > 0 else 0,
            "performance": {
                "avg_total_turnaround_seconds": stats.avg_total_time,
                "avg_time_to_first_audio_seconds": stats.avg_ttfa,
                "avg_tts_generation_seconds": stats.avg_tts_generation,
                "avg_stt_processing_seconds": stats.avg_stt_processing
            },
            "primary_providers": {
                "voice_provider": primary_voice_provider[0] if primary_voice_provider else None,
                "voice_provider_uses": primary_voice_provider[1] if primary_voice_provider else 0,
                "transport": primary_transport[0] if primary_transport else None,
                "transport_uses": primary_transport[1] if primary_transport else 0
            },
            "last_updated": tracker._session_start if hasattr(tracker, '_session_start') else None
        }
        
        return json.dumps(data, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error generating statistics summary resource: {e}")
        return json.dumps({"error": str(e)}, indent=2)


@mcp.resource("voice://statistics/export/{timestamp}")
async def statistics_export(timestamp: str = "latest") -> str:
    """
    Complete voice conversation statistics export in JSON format.
    
    Provides access to all tracked metrics and raw data:
    - Complete session statistics
    - All individual conversation metrics
    - Raw timing data for analysis
    - Provider configuration history
    
    This resource contains the full dataset for external analysis tools.
    """
    try:
        tracker = get_statistics_tracker()
        export_data = tracker.export_metrics()
        
        return json.dumps(export_data, indent=2, default=str)
        
    except Exception as e:
        logger.error(f"Error generating statistics export resource: {e}")
        return json.dumps({"error": str(e)}, indent=2)