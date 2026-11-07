#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "flask",
# ]
# ///
"""
Conversation Browser for Voice Mode

A simple web interface to browse voice mode conversations and play associated audio.

Usage:
    uvx conversation_browser.py
    # or
    python conversation_browser.py
"""

import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import json
import time
from collections import defaultdict

from flask import Flask, render_template_string, jsonify, send_file, request

# Import get_audio_path from voice_mode
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from voice_mode.core import get_audio_path

app = Flask(__name__)

# Configuration
BASE_DIR = Path(os.getenv("VOICEMODE_BASE_DIR", str(Path.home() / ".voicemode")))
TRANSCRIPTIONS_DIR = BASE_DIR / "transcriptions"
AUDIO_DIR = BASE_DIR / "audio"
LOGS_DIR = BASE_DIR / "logs"

# Simple cache
CACHE = {
    'conversations': None,
    'last_update': 0,
    'cache_duration': 60  # Cache for 60 seconds
}

def parse_transcription_file(filepath: Path) -> Dict:
    """Parse a transcription file and extract metadata and content."""
    try:
        content = filepath.read_text(encoding="utf-8")
        
        # Split metadata and transcript
        parts = content.split("--- TRANSCRIPT ---")
        
        metadata = {}
        transcript = ""
        
        if len(parts) == 2:
            # Parse metadata
            metadata_text = parts[0].replace("--- METADATA ---", "").strip()
            for line in metadata_text.split("\n"):
                if ": " in line:
                    key, value = line.split(": ", 1)
                    metadata[key.strip()] = value.strip()
            
            transcript = parts[1].strip()
        else:
            # No metadata, just transcript
            transcript = content.strip()
        
        # Extract timestamp from filename
        filename_parts = filepath.stem.split("_")
        if len(filename_parts) >= 3:
            timestamp_str = "_".join(filename_parts[1:3])
            try:
                # Parse timestamp (YYYYMMDD_HHMMSS)
                timestamp = datetime.strptime(timestamp_str, "%Y%m%d_%H%M%S")
                metadata["file_timestamp"] = timestamp.isoformat()
            except:
                pass
        
        return {
            "filepath": str(filepath),
            "filename": filepath.name,
            "metadata": metadata,
            "transcript": transcript,
            "type": filename_parts[0] if filename_parts else "unknown"
        }
    except Exception as e:
        return {
            "filepath": str(filepath),
            "filename": filepath.name,
            "metadata": {"error": str(e)},
            "transcript": f"Error reading file: {e}",
            "type": "error"
        }

def find_matching_audio(transcription: Dict) -> Optional[str]:
    """Find audio file that matches the transcription timestamp."""
    # Extract timestamp from transcription filename
    filename = Path(transcription["filename"]).stem
    parts = filename.split("_")
    
    if len(parts) >= 3:
        # Get the timestamp part (YYYYMMDD_HHMMSS)
        timestamp = "_".join(parts[1:3])
        
        # Look for audio files with similar timestamp
        # Audio files are named like: tts_20250628_185848_123.mp3
        for audio_file in AUDIO_DIR.glob("*"):
            if timestamp in audio_file.name:
                return str(audio_file)
    
    return None

def read_jsonl_exchanges() -> List[Dict[str, Any]]:
    """Read exchanges from JSONL log files."""
    exchanges = []
    
    if not LOGS_DIR.exists():
        return exchanges
    
    # Read all JSONL files
    for jsonl_file in sorted((LOGS_DIR / "conversations").glob("exchanges_*.jsonl")):
        try:
            with open(jsonl_file, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            entry = json.loads(line)
                            # Convert JSONL format to exchange format
                            exchange = {
                                "filepath": str(jsonl_file),
                                "filename": f"{entry['type']}_{entry['timestamp'].replace(':', '-')}.txt",
                                "metadata": {
                                    "file_timestamp": entry.get("timestamp"),
                                    "project_path": entry.get("project_path"),
                                    "conversation_id": entry.get("conversation_id"),
                                    "model": entry.get("metadata", {}).get("model"),
                                    "voice": entry.get("metadata", {}).get("voice"),
                                    "provider": entry.get("metadata", {}).get("provider"),
                                    "timing": entry.get("metadata", {}).get("timing"),
                                },
                                "transcript": entry.get("text", ""),
                                "type": entry.get("type", "unknown"),
                                "audio_path": entry.get("audio_file")
                            }
                            exchanges.append(exchange)
                        except json.JSONDecodeError:
                            continue
        except Exception as e:
            print(f"Error reading JSONL file {jsonl_file}: {e}")
    
    return exchanges

def get_all_exchanges() -> List[Dict]:
    """Get all exchanges from both transcription files and JSONL logs."""
    # Check cache
    current_time = time.time()
    if (CACHE['conversations'] is not None and 
        current_time - CACHE['last_update'] < CACHE['cache_duration']):
        return CACHE['conversations']
    
    exchanges = []
    
    # First, read from JSONL files (preferred source)
    jsonl_exchanges = read_jsonl_exchanges()
    exchanges.extend(jsonl_exchanges)
    
    # Then, read from transcription files if they exist
    if TRANSCRIPTIONS_DIR.exists():
        # Get all transcription files
        for filepath in sorted(TRANSCRIPTIONS_DIR.glob("*.txt"), reverse=True):
            transcription = parse_transcription_file(filepath)
            
            # Find matching audio
            audio_path = find_matching_audio(transcription)
            if audio_path:
                transcription["audio_path"] = audio_path
            
            exchanges.append(transcription)
    
    # Update cache
    CACHE['conversations'] = exchanges
    CACHE['last_update'] = current_time
    
    return exchanges

def group_by_project(exchanges: List[Dict]) -> Dict[str, List[Dict]]:
    """Group exchanges by project path."""
    grouped = {}
    
    for exchange in exchanges:
        project = exchange["metadata"].get("project_path", "Unknown Project")
        if project not in grouped:
            grouped[project] = []
        grouped[project].append(exchange)
    
    # Sort exchanges within each project by timestamp (newest first)
    for project_exchanges in grouped.values():
        project_exchanges.sort(key=lambda x: x["metadata"].get("file_timestamp", ""), reverse=True)
    
    return grouped

def group_exchanges_into_conversations(exchanges: List[Dict], gap_minutes: int = 5) -> List[Dict[str, any]]:
    """Group exchanges into conversations based on conversation_id or time gaps.
    
    Args:
        exchanges: List of exchange dictionaries
        gap_minutes: Maximum minutes between exchanges to be considered same conversation
        
    Returns:
        List of conversation dictionaries containing grouped exchanges
    """
    if not exchanges:
        return []
    
    # First, try to group by conversation_id
    conversations_by_id = defaultdict(list)
    exchanges_without_id = []
    
    for exchange in exchanges:
        conv_id = exchange["metadata"].get("conversation_id")
        if conv_id:
            conversations_by_id[conv_id].append(exchange)
        else:
            exchanges_without_id.append(exchange)
    
    # Convert conversation_id groups to conversation format
    conversations = []
    for conv_id, conv_exchanges in conversations_by_id.items():
        sorted_exch = sorted(conv_exchanges, key=lambda x: x["metadata"].get("file_timestamp", ""))
        conversations.append({
            "exchanges": sorted_exch,
            "start_time": sorted_exch[0]["metadata"].get("file_timestamp", ""),
            "end_time": sorted_exch[-1]["metadata"].get("file_timestamp", ""),
            "project": sorted_exch[0]["metadata"].get("project_path", "Unknown Project"),
            "conversation_id": conv_id
        })
    
    # Then handle exchanges without conversation_id using time-based grouping
    if exchanges_without_id:
        sorted_exchanges = sorted(exchanges_without_id, key=lambda x: x["metadata"].get("file_timestamp", ""))
        
        current_conversation = {
            "exchanges": [sorted_exchanges[0]],
            "start_time": sorted_exchanges[0]["metadata"].get("file_timestamp", ""),
            "project": sorted_exchanges[0]["metadata"].get("project_path", "Unknown Project")
        }
        
        for i in range(1, len(sorted_exchanges)):
            exchange = sorted_exchanges[i]
            prev_exchange = sorted_exchanges[i-1]
            
            # Parse timestamps
            try:
                current_time = datetime.fromisoformat(exchange["metadata"].get("file_timestamp", ""))
                prev_time = datetime.fromisoformat(prev_exchange["metadata"].get("file_timestamp", ""))
                time_diff = (current_time - prev_time).total_seconds() / 60  # Convert to minutes
                
                # Check if same project and within time gap
                same_project = exchange["metadata"].get("project_path") == prev_exchange["metadata"].get("project_path")
                
                if same_project and time_diff <= gap_minutes:
                    # Add to current conversation
                    current_conversation["exchanges"].append(exchange)
                else:
                    # Start new conversation
                    current_conversation["end_time"] = prev_exchange["metadata"].get("file_timestamp", "")
                    conversations.append(current_conversation)
                    
                    current_conversation = {
                        "exchanges": [exchange],
                        "start_time": exchange["metadata"].get("file_timestamp", ""),
                        "project": exchange["metadata"].get("project_path", "Unknown Project")
                    }
            except:
                # If timestamp parsing fails, start new conversation
                current_conversation["end_time"] = prev_exchange["metadata"].get("file_timestamp", "")
                conversations.append(current_conversation)
                
                current_conversation = {
                    "exchanges": [exchange],
                    "start_time": exchange["metadata"].get("file_timestamp", ""),
                    "project": exchange["metadata"].get("project_path", "Unknown Project")
                }
    
        # Add last conversation
        if current_conversation["exchanges"]:
            current_conversation["end_time"] = current_conversation["exchanges"][-1]["metadata"].get("file_timestamp", "")
            conversations.append(current_conversation)
    
    # Calculate conversation summaries
    for conv in conversations:
        conv["exchange_count"] = len(conv["exchanges"])
        # Get first few words from each exchange for summary
        summaries = []
        for ex in conv["exchanges"][:3]:  # First 3 exchanges
            transcript = ex.get("transcript", "").strip()
            words = transcript.split()[:10]  # First 10 words
            if words:
                summaries.append(" ".join(words) + "...")
        conv["summary"] = " | ".join(summaries)
    
    return conversations

def group_by_date(exchanges: List[Dict]) -> Dict[str, Dict[str, List[Dict]]]:
    """Group exchanges by date, then by project."""
    grouped = {}
    
    for exchange in exchanges:
        # Extract date from timestamp
        timestamp_str = exchange["metadata"].get("file_timestamp", "")
        if timestamp_str:
            try:
                dt = datetime.fromisoformat(timestamp_str)
                date_key = dt.strftime("%Y-%m-%d")
                date_display = dt.strftime("%A, %B %d, %Y")  # e.g., "Friday, June 28, 2024"
            except:
                date_key = "Unknown Date"
                date_display = "Unknown Date"
        else:
            date_key = "Unknown Date"
            date_display = "Unknown Date"
        
        if date_key not in grouped:
            grouped[date_key] = {
                "display": date_display,
                "exchanges": [],
                "projects": set()
            }
        
        grouped[date_key]["exchanges"].append(exchange)
        project = exchange["metadata"].get("project_path", "Unknown Project")
        grouped[date_key]["projects"].add(project)
    
    # Sort by date (newest first) - ensure proper date sorting
    sorted_grouped = dict(sorted(grouped.items(), key=lambda x: x[0], reverse=True))
    
    # Convert sets to lists for display
    for date_data in sorted_grouped.values():
        date_data["projects"] = sorted(list(date_data["projects"]))
    
    return sorted_grouped

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Voice Mode Conversation Browser</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }
        .date-group {
            background: white;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            overflow: hidden;
        }
        .date-header {
            background: #f8f9fa;
            padding: 15px 20px;
            cursor: pointer;
            border-bottom: 1px solid #ddd;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background 0.2s;
        }
        .date-header:hover {
            background: #e9ecef;
        }
        .date-header.expanded {
            background: #007bff;
            color: white;
        }
        .date-title {
            font-size: 1.2em;
            font-weight: bold;
        }
        .date-stats {
            font-size: 0.9em;
            opacity: 0.8;
        }
        .expand-hint {
            font-size: 0.85em;
            font-style: italic;
            opacity: 0.7;
            margin-left: 10px;
        }
        .date-content {
            display: none;
            padding: 20px;
        }
        .date-group.expanded .date-content {
            display: block;
        }
        .project-section {
            margin-bottom: 20px;
        }
        .project-title {
            font-size: 1.1em;
            font-weight: bold;
            color: #007bff;
            margin-bottom: 10px;
            padding: 5px 0;
            border-bottom: 1px solid #eee;
            word-break: break-all;
        }
        .conversation {
            border: 1px solid #ddd;
            border-radius: 4px;
            padding: 15px;
            margin-bottom: 10px;
            background: #fafafa;
            cursor: pointer;
            transition: all 0.2s;
            position: relative;
        }
        .conversation:hover {
            background: #f0f0f0;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .conversation.selected {
            background: #e3f2fd;
            border-color: #2196f3;
        }
        .play-button {
            display: inline-block;
            background: #4caf50;
            color: white;
            border: none;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
            margin-right: 10px;
            transition: background 0.2s;
        }
        .play-button:hover {
            background: #45a049;
        }
        .play-button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .play-button.playing {
            background: #ff5722;
        }
        .conversation-checkbox {
            margin-right: 10px;
            cursor: pointer;
        }
        .select-all-container {
            margin-bottom: 10px;
            padding: 10px;
            background: #f0f0f0;
            border-radius: 4px;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        .play-all-button {
            background: #2196f3;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9em;
            transition: background 0.2s;
        }
        .play-all-button:hover {
            background: #1976d2;
        }
        .play-all-button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .audio-controls {
            display: flex;
            align-items: center;
            margin-bottom: 5px;
        }
        .metadata {
            font-size: 0.85em;
            color: #666;
            margin-bottom: 10px;
        }
        .transcript-preview {
            color: #333;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        .full-transcript {
            display: none;
            margin-top: 15px;
            padding: 15px;
            background: white;
            border-radius: 4px;
            white-space: pre-wrap;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.9em;
            line-height: 1.5;
        }
        .conversation.selected .full-transcript {
            display: block;
        }
        .audio-player {
            margin-top: 10px;
            width: 100%;
        }
        .type-badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.8em;
            font-weight: bold;
            margin-right: 10px;
        }
        .type-conversation {
            background: #4caf50;
            color: white;
        }
        .type-stt {
            background: #ff9800;
            color: white;
        }
        .stats {
            background: white;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .view-controls {
            background: white;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            text-align: center;
        }
        .view-button {
            background: #f8f9fa;
            border: 1px solid #ddd;
            padding: 8px 16px;
            margin: 0 5px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .view-button:hover {
            background: #e9ecef;
        }
        .view-button.active {
            background: #007bff;
            color: white;
            border-color: #007bff;
        }
    </style>
</head>
<body>
    <h1>Voice Mode Conversation Browser</h1>
    
    <div class="stats">
        <strong>Total Conversations:</strong> {{ total_count }} |
        <strong>Projects:</strong> {{ project_count }} |
        <strong>Latest:</strong> {{ latest_date }}
    </div>
    
    <div class="view-controls">
        <button class="view-button {% if view_mode == 'date' %}active{% endif %}" 
                onclick="window.location.href='/?view=date'">
            Group by Date
        </button>
        <button class="view-button {% if view_mode == 'project' %}active{% endif %}"
                onclick="window.location.href='/?view=project'">
            Group by Project
        </button>
        <button class="view-button {% if view_mode == 'conversation' %}active{% endif %}"
                onclick="window.location.href='/?view=conversation'">
            Group by Conversation
        </button>
    </div>
    
    {% if view_mode == 'date' %}
    {% for date_key, date_data in grouped_exchanges.items() %}
    <div class="date-group" id="date-{{ date_key }}">
        <div class="date-header" onclick="toggleDateGroup(this)">
            <div>
                <div class="date-title">{{ date_data.display }}</div>
                <div class="date-stats">
                    {{ date_data.conversations|length }} conversations |
                    {{ date_data.projects|length }} project{% if date_data.projects|length != 1 %}s{% endif %}
                    <span class="expand-hint">Click to expand</span>
                </div>
            </div>
        </div>
        <div class="date-content">
            {% set conversations_by_project = {} %}
            {% for conv in date_data.conversations %}
                {% set project = conv.metadata.get('project_path', 'Unknown Project') %}
                {% if project not in conversations_by_project %}
                    {% set _ = conversations_by_project.update({project: []}) %}
                {% endif %}
                {% set _ = conversations_by_project[project].append(conv) %}
            {% endfor %}
            
            {% for project, project_convs in conversations_by_project.items() %}
            <div class="project-section">
                <div class="project-title">{{ project }}</div>
                {% for conv in project_exchanges %}
                <div class="conversation exchange" onclick="toggleExchange(this)">
                    <div class="metadata">
                        <span class="type-badge type-{{ conv.type }}">{{ conv.type|upper }}</span>
                        {% if conv.metadata.file_timestamp %}
                            <strong>{{ conv.metadata.file_timestamp|format_timestamp }}</strong>
                        {% else %}
                            <strong>{{ conv.filename }}</strong>
                        {% endif %}
                        {% if conv.metadata.timing %}
                            | {{ conv.metadata.timing }}
                        {% endif %}
                    </div>
                    <div class="transcript-preview">
                        {{ conv.transcript[:200] }}{% if conv.transcript|length > 200 %}...{% endif %}
                    </div>
                    <div class="full-transcript">
                        {{ conv.transcript }}
                        
                        {% if conv.audio_path %}
                        <audio class="audio-player" controls preload="none">
                            <source src="/audio/{{ conv.audio_path|basename }}" type="audio/mpeg">
                            Your browser does not support the audio element.
                        </audio>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            </div>
            {% endfor %}
        </div>
    </div>
    {% endfor %}
    
    {% elif view_mode == 'project' %}
    <!-- Project View -->
    {% for project, project_exchanges in grouped_exchanges.items() %}
    <div class="date-group expanded">
        <div class="date-header expanded">
            <div class="date-title">{{ project }}</div>
            <div class="date-stats">{{ project_exchanges|length }} exchanges</div>
        </div>
        <div class="date-content" style="display: block;">
            {% for conv in project_exchanges %}
            <div class="conversation exchange" onclick="toggleExchange(this)">
                <div class="metadata">
                    <span class="type-badge type-{{ conv.type }}">{{ conv.type|upper }}</span>
                    {% if conv.metadata.file_timestamp %}
                        <strong>{{ conv.metadata.file_timestamp|format_timestamp }}</strong>
                    {% else %}
                        <strong>{{ conv.filename }}</strong>
                    {% endif %}
                    {% if conv.metadata.timing %}
                        | {{ conv.metadata.timing }}
                    {% endif %}
                </div>
                <div class="transcript-preview">
                    {{ conv.transcript[:200] }}{% if conv.transcript|length > 200 %}...{% endif %}
                </div>
                <div class="full-transcript">
                    {{ conv.transcript }}
                    
                    {% if conv.audio_path %}
                    <audio class="audio-player" controls>
                        <source src="/audio/{{ conv.audio_path|basename }}" type="audio/mpeg">
                        Your browser does not support the audio element.
                    </audio>
                    {% endif %}
                </div>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endfor %}
    
    {% elif view_mode == 'conversation' %}
    <!-- Conversation View -->
    {% for date_key, date_data in grouped_exchanges.items() %}
    <div class="date-group" id="date-{{ date_key }}">
        <div class="date-header" onclick="toggleDateGroup(this)">
            <div>
                <div class="date-title">{{ date_data.display }}</div>
                <div class="date-stats">
                    {{ date_data.conversations|length }} conversation{% if date_data.conversations|length != 1 %}s{% endif %} |
                    {{ date_data.projects|length }} project{% if date_data.projects|length != 1 %}s{% endif %}
                    <span class="expand-hint">Click to expand</span>
                </div>
            </div>
        </div>
        <div class="date-content">
            {% for conv in date_data.conversations %}
            {% set conv_idx = loop.index0 %}
            <div class="conversation-group" id="conv-{{ conv_idx }}" style="border: 2px solid #007bff; border-radius: 8px; padding: 15px; margin-bottom: 15px; background: #f0f8ff;">
                <div class="select-all-container">
                    <input type="checkbox" class="select-all-checkbox" id="select-all-{{ conv_idx }}" 
                           onchange="toggleSelectAll(this, {{ conv_idx }})" checked>
                    <label for="select-all-{{ conv_idx }}">Select All</label>
                    <button class="play-all-button" onclick="playConversation({{ conv_idx }})">
                        <span class="play-icon">▶</span> Play Conversation
                    </button>
                </div>
                <div style="font-weight: bold; color: #007bff; margin-bottom: 10px;">
                    Conversation ({{ conv.exchange_count }} exchanges) - {{ conv.project }}
                    <br>
                    <span style="font-size: 0.9em; color: #666;">
                        {{ conv.start_time|format_timestamp }} - {{ conv.end_time|format_timestamp }}
                    </span>
                </div>
                <div style="margin-bottom: 10px; font-style: italic; color: #555;">
                    {{ conv.summary }}
                </div>
                {% for exchange in conv.exchanges %}
                {% set exchange_idx = loop.index0 %}
                <div class="conversation exchange" data-audio-url="{% if exchange.audio_path %}/audio/{{ exchange.audio_path|basename }}{% endif %}" 
                     data-conv-id="{{ conv_idx }}" data-exchange-id="{{ exchange_idx }}" style="margin-left: 20px;">
                    <div class="audio-controls">
                        <input type="checkbox" class="conversation-checkbox" id="checkbox-{{ conv_idx }}-{{ exchange_idx }}" checked
                               onclick="event.stopPropagation()">
                        {% if exchange.audio_path %}
                        <button class="play-button" onclick="event.stopPropagation(); playAudio(this, '/audio/{{ exchange.audio_path|basename }}')">
                            ▶ Play
                        </button>
                        {% endif %}
                    </div>
                    <div class="metadata" onclick="toggleExchange(this.parentElement)">
                        <span class="type-badge type-{{ exchange.type }}">{{ exchange.type|upper }}</span>
                        <strong>{{ exchange.metadata.file_timestamp|format_timestamp }}</strong>
                        {% if exchange.metadata.timing %}
                            | {{ exchange.metadata.timing }}
                        {% endif %}
                    </div>
                    <div class="transcript-preview" onclick="toggleExchange(this.parentElement)">
                        {{ exchange.transcript[:200] }}{% if exchange.transcript|length > 200 %}...{% endif %}
                    </div>
                    <div class="full-transcript">
                        {{ exchange.transcript }}
                        
                        {% if exchange.audio_path %}
                        <audio class="audio-player" controls preload="none">
                            <source src="/audio/{{ exchange.audio_path|basename }}" type="audio/mpeg">
                            Your browser does not support the audio element.
                        </audio>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            </div>
            {% endfor %}
        </div>
    </div>
    {% endfor %}
    {% endif %}
    
    <script>
        let currentAudio = null;
        let currentButton = null;
        let playlistQueue = [];
        let isPlayingPlaylist = false;

        function toggleDateGroup(header) {
            const dateGroup = header.parentElement;
            dateGroup.classList.toggle('expanded');
            header.classList.toggle('expanded');
        }
        
        function toggleConversation(element) {
            // Remove selected class from all conversations
            document.querySelectorAll('.conversation').forEach(el => {
                if (el !== element) {
                    el.classList.remove('selected');
                }
            });
            // Toggle selected class on clicked element
            element.classList.toggle('selected');
        }
        
        function toggleExchange(element) {
            // Remove selected class from all exchanges
            document.querySelectorAll('.exchange').forEach(el => {
                if (el !== element) {
                    el.classList.remove('selected');
                }
            });
            // Toggle selected class on clicked element
            element.classList.toggle('selected');
        }

        function toggleSelectAll(checkbox, convId) {
            const conversationGroup = document.getElementById('conv-' + convId);
            const checkboxes = conversationGroup.querySelectorAll('.conversation-checkbox');
            checkboxes.forEach(cb => {
                cb.checked = checkbox.checked;
            });
        }

        function playAudio(button, audioUrl) {
            // If currently playing, stop it
            if (currentAudio && currentButton === button) {
                currentAudio.pause();
                currentAudio = null;
                currentButton = null;
                button.innerHTML = '▶ Play';
                button.classList.remove('playing');
                return;
            }

            // Stop any currently playing audio
            if (currentAudio) {
                currentAudio.pause();
                if (currentButton) {
                    currentButton.innerHTML = '▶ Play';
                    currentButton.classList.remove('playing');
                }
            }

            // Create and play new audio
            currentAudio = new Audio(audioUrl);
            currentButton = button;
            button.innerHTML = '⏸ Pause';
            button.classList.add('playing');

            currentAudio.play().catch(error => {
                console.error('Error playing audio:', error);
                button.innerHTML = '▶ Play';
                button.classList.remove('playing');
            });

            currentAudio.onended = () => {
                button.innerHTML = '▶ Play';
                button.classList.remove('playing');
                currentButton = null;
                currentAudio = null;

                // If playing a playlist, play next
                if (isPlayingPlaylist && playlistQueue.length > 0) {
                    playNextInPlaylist();
                }
            };
        }

        function playConversation(convId) {
            const conversationGroup = document.getElementById('conv-' + convId);
            const playButton = conversationGroup.querySelector('.play-all-button');
            
            // Stop any current playback
            if (currentAudio) {
                currentAudio.pause();
                if (currentButton) {
                    currentButton.innerHTML = '▶ Play';
                    currentButton.classList.remove('playing');
                }
                currentAudio = null;
                currentButton = null;
            }

            // Get all checked exchanges with audio
            const exchanges = conversationGroup.querySelectorAll('.exchange');
            playlistQueue = [];

            exchanges.forEach(exchange => {
                const checkbox = exchange.querySelector('.conversation-checkbox');
                const audioUrl = exchange.getAttribute('data-audio-url');
                
                if (checkbox && checkbox.checked && audioUrl) {
                    playlistQueue.push({
                        url: audioUrl,
                        button: exchange.querySelector('.play-button')
                    });
                }
            });

            if (playlistQueue.length === 0) {
                alert('No audio files selected to play');
                return;
            }

            // Start playing playlist
            isPlayingPlaylist = true;
            playButton.innerHTML = '⏸ Stop All';
            playButton.onclick = () => stopPlaylist(convId);
            
            playNextInPlaylist();
        }

        function playNextInPlaylist() {
            if (playlistQueue.length === 0) {
                isPlayingPlaylist = false;
                // Reset all play buttons
                document.querySelectorAll('.play-all-button').forEach(btn => {
                    btn.innerHTML = '<span class="play-icon">▶</span> Play Conversation';
                    btn.onclick = function() { 
                        const convId = this.closest('.conversation-group').id.replace('conv-', '');
                        playConversation(convId);
                    };
                });
                return;
            }

            const next = playlistQueue.shift();
            if (next.button) {
                playAudio(next.button, next.url);
            } else {
                // Play without button animation
                currentAudio = new Audio(next.url);
                currentAudio.play().catch(error => {
                    console.error('Error playing audio:', error);
                    if (playlistQueue.length > 0) {
                        playNextInPlaylist();
                    }
                });

                currentAudio.onended = () => {
                    if (isPlayingPlaylist && playlistQueue.length > 0) {
                        playNextInPlaylist();
                    } else {
                        isPlayingPlaylist = false;
                    }
                };
            }
        }

        function stopPlaylist(convId) {
            isPlayingPlaylist = false;
            playlistQueue = [];
            
            if (currentAudio) {
                currentAudio.pause();
                currentAudio = null;
            }
            
            if (currentButton) {
                currentButton.innerHTML = '▶ Play';
                currentButton.classList.remove('playing');
                currentButton = null;
            }

            const conversationGroup = document.getElementById('conv-' + convId);
            const playButton = conversationGroup.querySelector('.play-all-button');
            playButton.innerHTML = '<span class="play-icon">▶</span> Play Conversation';
            playButton.onclick = () => playConversation(convId);
        }
        
        // Auto-expand today's conversations
        window.onload = function() {
            const today = new Date().toISOString().split('T')[0];
            const todayGroup = document.getElementById('date-' + today);
            if (todayGroup) {
                todayGroup.classList.add('expanded');
                todayGroup.querySelector('.date-header').classList.add('expanded');
            }
        };
    </script>
</body>
</html>
"""

@app.template_filter('format_timestamp')
def format_timestamp(timestamp_str):
    """Format ISO timestamp to readable format."""
    try:
        dt = datetime.fromisoformat(timestamp_str)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return timestamp_str

@app.template_filter('basename')
def basename(path):
    """Get basename of a path."""
    return os.path.basename(path)

@app.route('/')
def index():
    """Main page showing all exchanges."""
    view_mode = request.args.get('view', 'date')  # Default to date view
    exchanges = get_all_exchanges()
    
    # Group based on view mode
    if view_mode == 'project':
        grouped = group_by_project(exchanges)
    elif view_mode == 'conversation':
        # Group exchanges into conversations
        conversations = group_exchanges_into_conversations(exchanges)
        # Then group conversations by date
        grouped = {}
        for conv in conversations:
            # Extract date from start time
            try:
                dt = datetime.fromisoformat(conv["start_time"])
                date_key = dt.strftime("%Y-%m-%d")
                date_display = dt.strftime("%A, %B %d, %Y")
            except:
                date_key = "Unknown Date"
                date_display = "Unknown Date"
            
            if date_key not in grouped:
                grouped[date_key] = {
                    "display": date_display,
                    "conversations": [],
                    "projects": set()
                }
            
            grouped[date_key]["conversations"].append(conv)
            grouped[date_key]["projects"].add(conv["project"])
        
        # Convert sets to lists
        for date_data in grouped.values():
            date_data["projects"] = sorted(list(date_data["projects"]))
        
        # Sort by date (newest first)
        grouped = dict(sorted(grouped.items(), key=lambda x: x[0], reverse=True))
    else:
        grouped = group_by_date(exchanges)
    
    # Calculate stats
    total_count = len(exchanges)
    project_count = len(set(exchange["metadata"].get("project_path", "Unknown") 
                           for exchange in exchanges))
    latest_date = "N/A"
    
    if exchanges:
        latest = max(exchanges, 
                    key=lambda x: x["metadata"].get("file_timestamp", ""))
        if "file_timestamp" in latest["metadata"]:
            latest_date = format_timestamp(latest["metadata"]["file_timestamp"])
    
    return render_template_string(
        HTML_TEMPLATE,
        grouped_exchanges=grouped,
        total_count=total_count,
        project_count=project_count,
        latest_date=latest_date,
        view_mode=view_mode
    )

def contained_path(candidate: Path, base_dir: Path) -> Optional[str]:
    """Return ``candidate`` resolved, or None if it lies outside ``base_dir``.

    Resolves symlinks and ``..`` on both sides, then requires the result to sit
    strictly under ``base_dir`` (VM-2484, CodeQL py/path-injection).
    """
    base = os.path.realpath(base_dir)
    resolved = os.path.realpath(candidate)
    if not resolved.startswith(base + os.sep):
        return None
    return resolved


@app.route('/audio/<filename>')
def serve_audio(filename):
    """Serve audio files from AUDIO_DIR, and only from AUDIO_DIR."""
    # Try new path structure first, then the flat structure for older files
    for candidate in (get_audio_path(filename, AUDIO_DIR), AUDIO_DIR / filename):
        safe_path = contained_path(candidate, AUDIO_DIR)
        if safe_path is None:
            return "Invalid filename", 400
        if os.path.isfile(safe_path):
            return send_file(safe_path)

    return "Audio file not found", 404

@app.route('/api/conversations')
def api_conversations():
    """API endpoint to get all conversations as JSON."""
    conversations = get_all_conversations()
    return jsonify(conversations)

if __name__ == '__main__':
    print(f"Starting Voice Mode Conversation Browser...")
    print(f"Base directory: {BASE_DIR}")
    print(f"Transcriptions: {TRANSCRIPTIONS_DIR}")
    print(f"Audio files: {AUDIO_DIR}")
    print(f"\nOpen http://localhost:5000 in your browser\n")
    
    # The Werkzeug debugger executes arbitrary code for anyone who can reach
    # it, so it is off unless asked for (VM-2484, CodeQL py/flask-debug).
    debug = os.environ.get("VOICEMODE_BROWSER_DEBUG", "").lower() in ("1", "true", "yes")
    app.run(debug=debug, host='0.0.0.0', port=5000)