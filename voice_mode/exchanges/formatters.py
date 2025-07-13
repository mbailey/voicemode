"""
Formatters for displaying exchanges in various formats.
"""

import json
from datetime import datetime
from typing import Optional, List

from voice_mode.exchanges.models import Exchange, Conversation


class ExchangeFormatter:
    """Format exchanges for display."""
    
    # Color codes for terminal output
    COLORS = {
        'reset': '\033[0m',
        'bold': '\033[1m',
        'dim': '\033[2m',
        'red': '\033[31m',
        'green': '\033[32m',
        'yellow': '\033[33m',
        'blue': '\033[34m',
        'magenta': '\033[35m',
        'cyan': '\033[36m',
        'white': '\033[37m',
    }
    
    @classmethod
    def simple(cls, exchange: Exchange, color: bool = True, show_timing: bool = True) -> str:
        """One-line format with optional color.
        
        Format: [HH:MM:SS] 🎤/🔊 TYPE [transport] Text [timing]
        
        Args:
            exchange: Exchange to format
            color: Whether to include color codes
            show_timing: Whether to show timing info
            
        Returns:
            Formatted string
        """
        # Format timestamp
        time_str = exchange.timestamp.strftime("%H:%M:%S")
        
        # Choose emoji and color based on type
        if exchange.is_stt:
            emoji = "🎤"
            type_str = "STT"
            type_color = cls.COLORS['green'] if color else ''
        else:
            emoji = "🔊"
            type_str = "TTS"
            type_color = cls.COLORS['blue'] if color else ''
        
        # Get transport
        transport = exchange.metadata.transport if exchange.metadata else "unknown"
        
        # Format timing if available
        timing_str = ""
        if show_timing and exchange.metadata and exchange.metadata.timing:
            timing_str = f" [{exchange.metadata.timing}]"
        
        # Build the output
        parts = []
        
        # Time
        if color:
            parts.append(f"{cls.COLORS['dim']}[{time_str}]{cls.COLORS['reset']}")
        else:
            parts.append(f"[{time_str}]")
        
        # Emoji and type
        parts.append(emoji)
        if color:
            parts.append(f"{type_color}{type_str}{cls.COLORS['reset']}")
        else:
            parts.append(type_str)
        
        # Transport
        if color:
            parts.append(f"{cls.COLORS['dim']}[{transport}]{cls.COLORS['reset']}")
        else:
            parts.append(f"[{transport}]")
        
        # Text (truncated if too long)
        text = exchange.text
        if len(text) > 80:
            text = text[:77] + "..."
        parts.append(text)
        
        # Timing
        if timing_str:
            if color:
                parts.append(f"{cls.COLORS['dim']}{timing_str}{cls.COLORS['reset']}")
            else:
                parts.append(timing_str)
        
        return " ".join(parts)
    
    @classmethod
    def pretty(cls, exchange: Exchange, truncate: int = 80, show_metadata: bool = True) -> str:
        """Pretty format with box drawing and metadata.
        
        Args:
            exchange: Exchange to format
            truncate: Maximum text length (0 for no truncation)
            show_metadata: Whether to show metadata
            
        Returns:
            Multi-line formatted string
        """
        lines = []
        
        # Header line
        time_str = exchange.timestamp.strftime("%H:%M:%S")
        type_str = "STT" if exchange.is_stt else "TTS"
        emoji = "🎙️" if exchange.is_stt else "🔊"
        transport = exchange.metadata.transport if exchange.metadata else "unknown"
        
        header = f"┌─ {time_str} ─ {type_str} ─ {emoji} {transport} "
        header += "─" * (80 - len(header) - 1) + "┐"
        lines.append(header)
        
        # Text content (word-wrapped if needed)
        text = exchange.text
        if truncate > 0 and len(text) > truncate:
            text = text[:truncate-3] + "..."
        
        # Simple word wrapping
        text_lines = []
        words = text.split()
        current_line = ""
        
        for word in words:
            if len(current_line) + len(word) + 1 <= 76:  # Leave room for borders
                if current_line:
                    current_line += " "
                current_line += word
            else:
                if current_line:
                    text_lines.append(current_line)
                current_line = word
        
        if current_line:
            text_lines.append(current_line)
        
        for line in text_lines:
            lines.append(f"│ {line:<76} │")
        
        # Metadata
        if show_metadata and exchange.metadata:
            lines.append("├" + "─" * 78 + "┤")
            
            # Provider info
            if exchange.metadata.provider or exchange.metadata.model:
                provider_str = f"Provider: {exchange.metadata.provider or 'unknown'}"
                if exchange.metadata.model:
                    provider_str += f" | Model: {exchange.metadata.model}"
                if exchange.metadata.voice and exchange.is_tts:
                    provider_str += f" | Voice: {exchange.metadata.voice}"
                lines.append(f"│ {provider_str:<76} │")
            
            # Timing
            if exchange.metadata.timing:
                lines.append(f"│ Timing: {exchange.metadata.timing:<68} │")
            
            # Audio format
            if exchange.metadata.audio_format:
                lines.append(f"│ Audio Format: {exchange.metadata.audio_format:<62} │")
        
        # Footer
        lines.append("└" + "─" * 78 + "┘")
        
        return "\n".join(lines)
    
    @classmethod
    def json(cls, exchange: Exchange, indent: int = 2) -> str:
        """JSON format.
        
        Args:
            exchange: Exchange to format
            indent: JSON indentation level
            
        Returns:
            Pretty-printed JSON string
        """
        return json.dumps(exchange.to_dict(), indent=indent, default=str)
    
    @classmethod
    def markdown(cls, conversation: Conversation, include_metadata: bool = False) -> str:
        """Markdown transcript format.
        
        Args:
            conversation: Conversation to format
            include_metadata: Whether to include metadata table
            
        Returns:
            Markdown-formatted string
        """
        lines = []
        
        # Header
        lines.append(f"# Conversation {conversation.id}")
        lines.append("")
        
        # Metadata table
        if include_metadata:
            lines.append("| Property | Value |")
            lines.append("|----------|-------|")
            lines.append(f"| Start Time | {conversation.start_time.strftime('%Y-%m-%d %H:%M:%S')} |")
            lines.append(f"| End Time | {conversation.end_time.strftime('%Y-%m-%d %H:%M:%S')} |")
            lines.append(f"| Duration | {conversation.duration} |")
            lines.append(f"| Exchanges | {conversation.exchange_count} |")
            if conversation.project_path:
                lines.append(f"| Project | `{conversation.project_path}` |")
            lines.append("")
        
        # Transcript
        lines.append("## Transcript")
        lines.append("")
        
        for exchange in conversation.exchanges:
            time_str = exchange.timestamp.strftime("%H:%M:%S")
            speaker = "**User**" if exchange.is_stt else "**Assistant**"
            
            lines.append(f"*[{time_str}]* {speaker}: {exchange.text}")
            lines.append("")
        
        return "\n".join(lines)
    
    @classmethod
    def csv_header(cls) -> str:
        """Get CSV header row."""
        return "timestamp,conversation_id,type,text,transport,provider,model,voice,timing"
    
    @classmethod
    def csv(cls, exchange: Exchange) -> str:
        """CSV format for single exchange.
        
        Args:
            exchange: Exchange to format
            
        Returns:
            CSV row string
        """
        # Escape text for CSV
        text = exchange.text.replace('"', '""')
        if ',' in text or '\n' in text or '"' in text:
            text = f'"{text}"'
        
        # Get metadata fields
        transport = exchange.metadata.transport if exchange.metadata else ""
        provider = exchange.metadata.provider if exchange.metadata else ""
        model = exchange.metadata.model if exchange.metadata else ""
        voice = exchange.metadata.voice if exchange.metadata else ""
        timing = exchange.metadata.timing if exchange.metadata else ""
        
        return f"{exchange.timestamp.isoformat()},{exchange.conversation_id},{exchange.type},{text},{transport},{provider},{model},{voice},{timing}"
    
    @classmethod
    def html(cls, conversation: Conversation) -> str:
        """HTML format with styling.
        
        Args:
            conversation: Conversation to format
            
        Returns:
            HTML string with embedded styles
        """
        html_parts = ["""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Conversation {}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .conversation {{
            background: white;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .metadata {{
            background: #f8f9fa;
            border-radius: 4px;
            padding: 10px;
            margin-bottom: 20px;
            font-size: 14px;
        }}
        .exchange {{
            margin: 15px 0;
            display: flex;
            gap: 10px;
        }}
        .timestamp {{
            color: #666;
            font-size: 12px;
            min-width: 60px;
        }}
        .speaker {{
            font-weight: bold;
            min-width: 80px;
        }}
        .speaker.user {{
            color: #2e7d32;
        }}
        .speaker.assistant {{
            color: #1976d2;
        }}
        .text {{
            flex: 1;
        }}
    </style>
</head>
<body>
    <div class="conversation">
        <h1>Conversation {}</h1>
""".format(conversation.id, conversation.id)]
        
        # Metadata
        html_parts.append('<div class="metadata">')
        html_parts.append(f'<strong>Start:</strong> {conversation.start_time.strftime("%Y-%m-%d %H:%M:%S")}<br>')
        html_parts.append(f'<strong>Duration:</strong> {conversation.duration}<br>')
        html_parts.append(f'<strong>Exchanges:</strong> {conversation.exchange_count}')
        if conversation.project_path:
            html_parts.append(f'<br><strong>Project:</strong> <code>{conversation.project_path}</code>')
        html_parts.append('</div>')
        
        # Exchanges
        for exchange in conversation.exchanges:
            time_str = exchange.timestamp.strftime("%H:%M:%S")
            speaker_class = "user" if exchange.is_stt else "assistant"
            speaker_name = "User" if exchange.is_stt else "Assistant"
            
            html_parts.append('<div class="exchange">')
            html_parts.append(f'<div class="timestamp">{time_str}</div>')
            html_parts.append(f'<div class="speaker {speaker_class}">{speaker_name}:</div>')
            html_parts.append(f'<div class="text">{exchange.text}</div>')
            html_parts.append('</div>')
        
        html_parts.append("""
    </div>
</body>
</html>
""")
        
        return "".join(html_parts)