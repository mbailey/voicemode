"""MCP resources for voice conversations with metadata."""

import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

from ..mcp_instance import mcp
from ..config import logger
from ..exchanges import ExchangeReader, ConversationGrouper
from ..metadata import ConversationMetadata


def _format_conversation_for_resource(conv, metadata: Optional[Dict] = None) -> Dict[str, Any]:
    """Format a conversation object for resource output."""
    # Calculate word counts
    stt_words = sum(len(e.text.split()) for e in conv.exchanges if e.type == 'stt')
    tts_words = sum(len(e.text.split()) for e in conv.exchanges if e.type == 'tts')
    
    result = {
        'id': conv.id,
        'start_time': conv.start_time.isoformat(),
        'end_time': conv.end_time.isoformat(),
        'duration_seconds': conv.duration.total_seconds(),
        'exchange_count': conv.exchange_count,
        'stt_count': conv.stt_count,
        'tts_count': conv.tts_count,
        'word_count': {
            'user': stt_words,
            'assistant': tts_words,
            'total': stt_words + tts_words
        },
        'project_path': conv.project_path
    }
    
    # Add metadata if available
    if metadata:
        result['metadata'] = {
            'title': metadata.get('title'),
            'summary': metadata.get('summary'),
            'tags': metadata.get('tags', []),
            'is_favorite': metadata.get('is_favorite', False),
            'rating': metadata.get('rating'),
            'notes': metadata.get('notes'),
            'created_at': metadata.get('created_at'),
            'updated_at': metadata.get('updated_at')
        }
    
    # Get first few exchanges as preview
    result['preview'] = []
    for i, exchange in enumerate(conv.exchanges[:5]):
        result['preview'].append({
            'type': exchange.type,
            'text': exchange.text[:200] + '...' if len(exchange.text) > 200 else exchange.text,
            'timestamp': exchange.timestamp.isoformat()
        })
    
    return result


@mcp.resource("conversations://today")
async def conversations_today() -> str:
    """
    Today's voice conversations with metadata.
    
    Returns all conversations from today including:
    - Conversation metadata (title, tags, favorites)
    - Exchange counts and duration
    - Word counts by speaker
    - Preview of first few exchanges
    """
    try:
        reader = ExchangeReader()
        grouper = ConversationGrouper()
        metadata_store = ConversationMetadata()
        
        # Read today's exchanges
        today = datetime.now().date()
        exchanges = list(reader.read_date(today))
        
        if not exchanges:
            return json.dumps({
                'date': today.isoformat(),
                'conversations': [],
                'summary': {
                    'total_conversations': 0,
                    'total_exchanges': 0,
                    'total_duration_seconds': 0
                }
            }, indent=2)
        
        # Group into conversations
        conversations = grouper.group_exchanges(exchanges)
        
        # Format conversations with metadata
        conv_list = []
        total_duration = 0
        total_exchanges = 0
        
        for conv in sorted(conversations.values(), key=lambda c: c.start_time, reverse=True):
            metadata = metadata_store.read_metadata(conv.id, conv.start_time)
            conv_data = _format_conversation_for_resource(conv, metadata)
            conv_list.append(conv_data)
            total_duration += conv.duration.total_seconds()
            total_exchanges += conv.exchange_count
        
        return json.dumps({
            'date': today.isoformat(),
            'conversations': conv_list,
            'summary': {
                'total_conversations': len(conv_list),
                'total_exchanges': total_exchanges,
                'total_duration_seconds': total_duration,
                'favorite_count': sum(1 for c in conv_list if c.get('metadata', {}).get('is_favorite', False))
            }
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error generating today's conversations resource: {e}")
        return json.dumps({"error": str(e)}, indent=2)


@mcp.resource("conversations://recent")
async def conversations_recent() -> str:
    """
    Recent voice conversations (last 7 days) with metadata.
    
    Returns conversations from the past week including:
    - Conversation metadata (title, tags, favorites)
    - Daily grouping
    - Summary statistics
    """
    try:
        reader = ExchangeReader()
        grouper = ConversationGrouper()
        metadata_store = ConversationMetadata()
        
        # Read recent exchanges
        exchanges = list(reader.read_recent(7))
        
        if not exchanges:
            return json.dumps({
                'period': 'last_7_days',
                'conversations': [],
                'summary': {
                    'total_conversations': 0,
                    'total_exchanges': 0,
                    'total_duration_seconds': 0
                }
            }, indent=2)
        
        # Group into conversations
        conversations = grouper.group_exchanges(exchanges)
        
        # Group by date
        by_date = {}
        for conv in conversations.values():
            date_str = conv.start_time.date().isoformat()
            if date_str not in by_date:
                by_date[date_str] = []
            
            metadata = metadata_store.read_metadata(conv.id, conv.start_time)
            conv_data = _format_conversation_for_resource(conv, metadata)
            by_date[date_str].append(conv_data)
        
        # Sort dates and conversations
        sorted_dates = sorted(by_date.keys(), reverse=True)
        result = {
            'period': 'last_7_days',
            'conversations_by_date': {}
        }
        
        total_conversations = 0
        total_exchanges = 0
        total_duration = 0
        total_favorites = 0
        
        for date_str in sorted_dates:
            convs = sorted(by_date[date_str], key=lambda c: c['start_time'], reverse=True)
            result['conversations_by_date'][date_str] = convs
            
            # Update totals
            total_conversations += len(convs)
            for conv in convs:
                total_exchanges += conv['exchange_count']
                total_duration += conv['duration_seconds']
                if conv.get('metadata', {}).get('is_favorite', False):
                    total_favorites += 1
        
        result['summary'] = {
            'total_conversations': total_conversations,
            'total_exchanges': total_exchanges,
            'total_duration_seconds': total_duration,
            'favorite_count': total_favorites,
            'days_with_conversations': len(sorted_dates)
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error generating recent conversations resource: {e}")
        return json.dumps({"error": str(e)}, indent=2)


@mcp.resource("conversations://favorites")
async def conversations_favorites() -> str:
    """
    Favorite conversations with full metadata.
    
    Returns all conversations marked as favorites including:
    - Full metadata (title, summary, tags, notes)
    - Exchange details
    - Sorted by date (newest first)
    """
    try:
        reader = ExchangeReader()
        grouper = ConversationGrouper()
        metadata_store = ConversationMetadata()
        
        # Get all favorites from metadata
        favorites_metadata = metadata_store.get_all_favorites()
        
        if not favorites_metadata:
            return json.dumps({
                'favorites': [],
                'summary': {
                    'total_favorites': 0
                }
            }, indent=2)
        
        # Read exchanges for dates that have favorites
        # Extract dates from conversation IDs
        dates_to_read = set()
        for conv_id, metadata in favorites_metadata.items():
            # Parse date from conv_id format: conv_YYYYMMDD_HHMMSS_xxxxx
            try:
                date_part = conv_id.split('_')[1]
                date = datetime.strptime(date_part, '%Y%m%d').date()
                dates_to_read.add(date)
            except (IndexError, ValueError):
                continue
        
        # Read exchanges for those dates
        all_exchanges = []
        for date in dates_to_read:
            all_exchanges.extend(reader.read_date(date))
        
        # Group into conversations
        conversations = grouper.group_exchanges(all_exchanges)
        
        # Filter to only favorites and format
        favorite_convs = []
        for conv_id, metadata in favorites_metadata.items():
            if conv_id in conversations:
                conv = conversations[conv_id]
                conv_data = _format_conversation_for_resource(conv, metadata)
                favorite_convs.append(conv_data)
        
        # Sort by start time (newest first)
        favorite_convs.sort(key=lambda c: c['start_time'], reverse=True)
        
        # Group by tags
        tags_summary = {}
        for conv in favorite_convs:
            for tag in conv.get('metadata', {}).get('tags', []):
                tags_summary[tag] = tags_summary.get(tag, 0) + 1
        
        return json.dumps({
            'favorites': favorite_convs,
            'summary': {
                'total_favorites': len(favorite_convs),
                'tags': tags_summary,
                'oldest_favorite': favorite_convs[-1]['start_time'] if favorite_convs else None,
                'newest_favorite': favorite_convs[0]['start_time'] if favorite_convs else None
            }
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error generating favorites resource: {e}")
        return json.dumps({"error": str(e)}, indent=2)


@mcp.resource("conversations://untagged")
async def conversations_untagged() -> str:
    """
    Conversations without titles or tags.
    
    Returns recent conversations that need metadata including:
    - Conversations without titles
    - Conversations without tags
    - Sorted by date (newest first)
    """
    try:
        reader = ExchangeReader()
        grouper = ConversationGrouper()
        metadata_store = ConversationMetadata()
        
        # Read recent exchanges (last 30 days)
        exchanges = list(reader.read_recent(30))
        
        if not exchanges:
            return json.dumps({
                'untagged': [],
                'summary': {
                    'total_untagged': 0
                }
            }, indent=2)
        
        # Group into conversations
        conversations = grouper.group_exchanges(exchanges)
        
        # Find untagged conversations
        untagged_convs = []
        for conv in conversations.values():
            metadata = metadata_store.read_metadata(conv.id, conv.start_time)
            
            # Check if needs metadata
            needs_metadata = (
                not metadata or
                not metadata.get('title') or
                not metadata.get('tags')
            )
            
            if needs_metadata:
                conv_data = _format_conversation_for_resource(conv, metadata)
                conv_data['needs'] = {
                    'title': not metadata or not metadata.get('title'),
                    'tags': not metadata or not metadata.get('tags'),
                    'summary': not metadata or not metadata.get('summary')
                }
                untagged_convs.append(conv_data)
        
        # Sort by start time (newest first)
        untagged_convs.sort(key=lambda c: c['start_time'], reverse=True)
        
        return json.dumps({
            'untagged': untagged_convs,
            'summary': {
                'total_untagged': len(untagged_convs),
                'needs_title': sum(1 for c in untagged_convs if c['needs']['title']),
                'needs_tags': sum(1 for c in untagged_convs if c['needs']['tags']),
                'needs_summary': sum(1 for c in untagged_convs if c['needs']['summary'])
            }
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error generating untagged conversations resource: {e}")
        return json.dumps({"error": str(e)}, indent=2)


@mcp.resource("conversations://{conversation_id}")
async def conversation_detail(conversation_id: str) -> str:
    """
    Detailed view of a specific conversation.
    
    Returns complete conversation data including:
    - Full metadata
    - All exchanges (not just preview)
    - Timing statistics
    - Provider usage
    """
    try:
        reader = ExchangeReader()
        grouper = ConversationGrouper()
        metadata_store = ConversationMetadata()
        
        # Parse date from conversation ID
        try:
            date_part = conversation_id.split('_')[1]
            date = datetime.strptime(date_part, '%Y%m%d').date()
        except (IndexError, ValueError):
            return json.dumps({
                "error": f"Invalid conversation ID format: {conversation_id}"
            }, indent=2)
        
        # Read exchanges for that date
        exchanges = list(reader.read_date(date))
        
        # Group and find specific conversation
        conversations = grouper.group_exchanges(exchanges)
        
        if conversation_id not in conversations:
            return json.dumps({
                "error": f"Conversation not found: {conversation_id}"
            }, indent=2)
        
        conv = conversations[conversation_id]
        metadata = metadata_store.read_metadata(conv.id, conv.start_time)
        
        # Get full conversation data
        result = _format_conversation_for_resource(conv, metadata)
        
        # Add full exchanges (not just preview)
        result['exchanges'] = []
        for exchange in conv.exchanges:
            exchange_data = {
                'type': exchange.type,
                'text': exchange.text,
                'timestamp': exchange.timestamp.isoformat(),
                'duration': exchange.duration
            }
            
            # Add metadata if available
            if exchange.metadata:
                exchange_data['metadata'] = {
                    'provider': exchange.metadata.provider,
                    'model': exchange.metadata.model,
                    'voice': exchange.metadata.voice,
                    'ttfa': exchange.metadata.ttfa,
                    'processing_time': exchange.metadata.processing_time,
                    'audio_duration': exchange.metadata.audio_duration
                }
            
            result['exchanges'].append(exchange_data)
        
        # Remove preview since we have full exchanges
        del result['preview']
        
        # Add conversation summary from grouper
        summary = grouper.get_conversation_summary(conv)
        result['analysis'] = {
            'providers': summary['providers'],
            'models': summary['models'],
            'voices': summary['voices'],
            'avg_response_time': summary.get('avg_response_time'),
            'min_response_time': summary.get('min_response_time'),
            'max_response_time': summary.get('max_response_time')
        }
        
        return json.dumps(result, indent=2)
        
    except Exception as e:
        logger.error(f"Error generating conversation detail resource: {e}")
        return json.dumps({"error": str(e)}, indent=2)


@mcp.resource("conversations://{date}")
async def conversations_by_date(date: str) -> str:
    """
    Conversations for a specific date.
    
    Date format: YYYY-MM-DD
    
    Returns all conversations for the specified date including:
    - Metadata for each conversation
    - Summary statistics for the day
    """
    try:
        reader = ExchangeReader()
        grouper = ConversationGrouper()
        metadata_store = ConversationMetadata()
        
        # Parse date
        try:
            target_date = datetime.strptime(date, '%Y-%m-%d').date()
        except ValueError:
            return json.dumps({
                "error": f"Invalid date format: {date}. Use YYYY-MM-DD"
            }, indent=2)
        
        # Read exchanges for that date
        exchanges = list(reader.read_date(target_date))
        
        if not exchanges:
            return json.dumps({
                'date': target_date.isoformat(),
                'conversations': [],
                'summary': {
                    'total_conversations': 0,
                    'total_exchanges': 0,
                    'total_duration_seconds': 0
                }
            }, indent=2)
        
        # Group into conversations
        conversations = grouper.group_exchanges(exchanges)
        
        # Format conversations with metadata
        conv_list = []
        total_duration = 0
        total_exchanges = 0
        favorite_count = 0
        
        for conv in sorted(conversations.values(), key=lambda c: c.start_time, reverse=True):
            metadata = metadata_store.read_metadata(conv.id, conv.start_time)
            conv_data = _format_conversation_for_resource(conv, metadata)
            conv_list.append(conv_data)
            total_duration += conv.duration.total_seconds()
            total_exchanges += conv.exchange_count
            if metadata and metadata.get('is_favorite'):
                favorite_count += 1
        
        return json.dumps({
            'date': target_date.isoformat(),
            'conversations': conv_list,
            'summary': {
                'total_conversations': len(conv_list),
                'total_exchanges': total_exchanges,
                'total_duration_seconds': total_duration,
                'favorite_count': favorite_count,
                'average_duration_seconds': total_duration / len(conv_list) if conv_list else 0,
                'average_exchanges_per_conversation': total_exchanges / len(conv_list) if conv_list else 0
            }
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Error generating conversations by date resource: {e}")
        return json.dumps({"error": str(e)}, indent=2)