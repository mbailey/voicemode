"""Statistics tools for voice conversation tracking and dashboard."""

import json
import time
from typing import Optional
from datetime import datetime

from ..mcp_instance import mcp
from ..statistics import get_statistics_tracker, track_conversation
from ..config import logger


@mcp.tool()
async def voice_statistics() -> str:
    """
    Display live statistics dashboard for voice conversation performance.
    
    Shows current session statistics including:
    - Total responses and success rate
    - Average turnaround times (TTFA, TTS, STT)
    - Min/max performance metrics
    - Provider usage statistics
    - Recent interaction history
    
    Returns:
        Formatted text dashboard with real-time conversation statistics
    """
    try:
        tracker = get_statistics_tracker()
        dashboard = tracker.format_dashboard()
        
        logger.debug("Generated voice statistics dashboard")
        return dashboard
        
    except Exception as e:
        logger.error(f"Error generating statistics dashboard: {e}")
        return f"Error generating statistics dashboard: {str(e)}"


@mcp.tool()
async def voice_statistics_summary() -> str:
    """
    Get a concise summary of voice conversation performance metrics.
    
    Returns key performance indicators for the current session:
    - Session duration and interaction count
    - Average total turnaround time
    - Average time to first audio (TTFA)
    - Success rate
    
    Returns:
        Brief summary of key performance metrics
    """
    try:
        tracker = get_statistics_tracker()
        stats = tracker.get_session_statistics()
        
        lines = []
        lines.append("📊 Voice Performance Summary")
        lines.append("=" * 35)
        
        # Basic session info
        duration_minutes = (stats.session_duration or 0) / 60
        lines.append(f"Session Duration: {duration_minutes:.1f} minutes")
        lines.append(f"Total Interactions: {stats.total_interactions}")
        
        if stats.total_interactions > 0:
            success_rate = (stats.successful_interactions / stats.total_interactions) * 100
            lines.append(f"Success Rate: {success_rate:.1f}%")
        
        # Key performance metrics
        if stats.successful_interactions > 0:
            if stats.avg_total_time:
                lines.append(f"Avg Turnaround: {stats.avg_total_time:.1f}s")
            if stats.avg_ttfa:
                lines.append(f"Avg Time to First Audio: {stats.avg_ttfa:.1f}s")
            if stats.avg_tts_generation:
                lines.append(f"Avg TTS Generation: {stats.avg_tts_generation:.1f}s")
            if stats.avg_stt_processing:
                lines.append(f"Avg STT Processing: {stats.avg_stt_processing:.1f}s")
        
        # Top providers
        if stats.voice_providers_used:
            top_provider = max(stats.voice_providers_used.items(), key=lambda x: x[1])
            lines.append(f"Primary Voice Provider: {top_provider[0]} ({top_provider[1]} uses)")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error generating statistics summary: {e}")
        return f"Error generating statistics summary: {str(e)}"


@mcp.tool()
async def voice_statistics_reset() -> str:
    """
    Reset all voice conversation statistics and start a new session.
    
    Clears all tracked metrics and resets the session timer.
    Use this to start fresh tracking or when testing performance changes.
    
    Returns:
        Confirmation message that statistics have been reset
    """
    try:
        tracker = get_statistics_tracker()
        old_stats = tracker.get_session_statistics()
        
        tracker.clear_statistics()
        
        logger.info("Voice conversation statistics reset")
        
        result = []
        result.append("✅ Voice conversation statistics reset")
        result.append(f"Previous session had {old_stats.total_interactions} interactions")
        if old_stats.session_duration:
            duration_minutes = old_stats.session_duration / 60
            result.append(f"Previous session duration: {duration_minutes:.1f} minutes")
        result.append("New tracking session started")
        
        return "\n".join(result)
        
    except Exception as e:
        logger.error(f"Error resetting statistics: {e}")
        return f"Error resetting statistics: {str(e)}"


@mcp.tool()
async def voice_statistics_export() -> str:
    """
    Export detailed voice conversation statistics as JSON data.
    
    Exports all tracked metrics and calculated statistics in machine-readable format.
    Useful for analysis, reporting, or integration with external monitoring tools.
    
    Returns:
        JSON string containing all metrics and session statistics
    """
    try:
        tracker = get_statistics_tracker()
        export_data = tracker.export_metrics()
        
        # Format the export data nicely
        json_output = json.dumps(export_data, indent=2, default=str)
        
        logger.debug(f"Exported {len(export_data.get('metrics', []))} voice metrics")
        
        return f"Voice Statistics Export:\n```json\n{json_output}\n```"
        
    except Exception as e:
        logger.error(f"Error exporting statistics: {e}")
        return f"Error exporting statistics: {str(e)}"


@mcp.tool()
async def voice_statistics_recent(limit: int = 10) -> str:
    """
    Show recent voice conversation interactions with timing details.
    
    Args:
        limit: Maximum number of recent interactions to show (default: 10, max: 50)
    
    Returns:
        Detailed list of recent interactions with performance metrics
    """
    try:
        # Validate and clamp limit
        limit = max(1, min(limit, 50))
        
        tracker = get_statistics_tracker()
        recent_metrics = tracker.get_recent_metrics(limit)
        
        if not recent_metrics:
            return "No voice interactions recorded yet in this session."
        
        lines = []
        lines.append(f"🕐 RECENT VOICE INTERACTIONS (last {len(recent_metrics)})")
        lines.append("=" * 60)
        
        for i, metric in enumerate(reversed(recent_metrics), 1):
            timestamp = datetime.fromtimestamp(metric.timestamp).strftime("%H:%M:%S")
            status = "✅" if metric.success else "❌"
            
            # Basic info line
            provider = metric.voice_provider or "unknown"
            voice = metric.voice_name or "default"
            transport = metric.transport or "auto"
            
            lines.append(f"\n{i}. {timestamp} {status} [{provider}/{voice}] via {transport}")
            lines.append(f"   Message: {metric.message}")
            
            if metric.success:
                if metric.response:
                    lines.append(f"   Response: {metric.response}")
                
                # Timing details
                timing_parts = []
                if metric.ttfa:
                    timing_parts.append(f"TTFA: {metric.ttfa:.1f}s")
                if metric.tts_generation:
                    timing_parts.append(f"TTS-gen: {metric.tts_generation:.1f}s")
                if metric.tts_playback:
                    timing_parts.append(f"TTS-play: {metric.tts_playback:.1f}s")
                if metric.stt_processing:
                    timing_parts.append(f"STT: {metric.stt_processing:.1f}s")
                if metric.total_time:
                    timing_parts.append(f"Total: {metric.total_time:.1f}s")
                
                if timing_parts:
                    lines.append(f"   Timing: {', '.join(timing_parts)}")
            else:
                if metric.error_message:
                    lines.append(f"   Error: {metric.error_message}")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"Error showing recent statistics: {e}")
        return f"Error showing recent statistics: {str(e)}"


# Integration function for conversation tools
def track_voice_interaction(message: str, 
                           response: str,
                           timing_str: Optional[str] = None,
                           transport: Optional[str] = None,
                           voice_provider: Optional[str] = None,
                           voice_name: Optional[str] = None,
                           model: Optional[str] = None,
                           success: bool = True,
                           error_message: Optional[str] = None) -> None:
    """
    Track a voice interaction for statistics.
    
    This function should be called from conversation tools to record metrics.
    """
    try:
        track_conversation(
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
        logger.debug(f"Tracked voice interaction: {len(message)} chars, success={success}")
        
    except Exception as e:
        logger.error(f"Error tracking voice interaction: {e}")
        # Don't raise the error - statistics tracking shouldn't break the main flow