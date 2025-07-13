"""
Conversation grouping and analysis.
"""

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from voice_mode.exchanges.models import Exchange, Conversation


class ConversationGrouper:
    """Group exchanges into conversations."""
    
    # Default gap time to consider exchanges as separate conversations
    DEFAULT_CONVERSATION_GAP_MINUTES = 5
    
    def __init__(self, gap_minutes: int = DEFAULT_CONVERSATION_GAP_MINUTES):
        """Initialize grouper with conversation gap threshold.
        
        Args:
            gap_minutes: Minutes of inactivity to consider as conversation boundary
        """
        self.gap_minutes = gap_minutes
    
    def group_exchanges(self, exchanges: List[Exchange]) -> Dict[str, Conversation]:
        """Group exchanges by conversation ID.
        
        This respects the conversation IDs already in the exchanges,
        which are determined at logging time based on time gaps.
        
        Args:
            exchanges: List of exchanges to group
            
        Returns:
            Dictionary mapping conversation IDs to Conversation objects
        """
        conversations = defaultdict(list)
        
        # Group by conversation ID
        for exchange in exchanges:
            conversations[exchange.conversation_id].append(exchange)
        
        # Create Conversation objects
        result = {}
        for conv_id, conv_exchanges in conversations.items():
            if conv_exchanges:
                # Sort by timestamp
                conv_exchanges.sort(key=lambda e: e.timestamp)
                
                # Get project path from first exchange
                project_path = None
                for exchange in conv_exchanges:
                    if exchange.project_path:
                        project_path = exchange.project_path
                        break
                
                result[conv_id] = Conversation(
                    id=conv_id,
                    start_time=conv_exchanges[0].timestamp,
                    end_time=conv_exchanges[-1].timestamp,
                    project_path=project_path,
                    exchanges=conv_exchanges
                )
        
        return result
    
    def find_conversations(self, 
                          exchanges: List[Exchange],
                          project_path: Optional[str] = None,
                          date_range: Optional[Tuple[datetime, datetime]] = None,
                          min_exchanges: int = 1) -> List[Conversation]:
        """Find conversations matching criteria.
        
        Args:
            exchanges: List of all exchanges to search through
            project_path: Filter by project path (partial match)
            date_range: Filter by date range (start, end)
            min_exchanges: Minimum number of exchanges in conversation
            
        Returns:
            List of conversations matching criteria
        """
        # First group all exchanges
        all_conversations = self.group_exchanges(exchanges)
        
        # Filter conversations
        result = []
        for conversation in all_conversations.values():
            # Check exchange count
            if conversation.exchange_count < min_exchanges:
                continue
            
            # Check project path
            if project_path and conversation.project_path:
                if project_path not in conversation.project_path:
                    continue
            elif project_path and not conversation.project_path:
                continue
            
            # Check date range
            if date_range:
                start, end = date_range
                if conversation.start_time < start or conversation.end_time > end:
                    continue
            
            result.append(conversation)
        
        # Sort by start time
        result.sort(key=lambda c: c.start_time)
        
        return result
    
    def merge_conversations(self, conversations: List[Conversation], gap_minutes: Optional[int] = None) -> List[Conversation]:
        """Merge conversations that are close in time.
        
        This is useful for re-grouping conversations with different gap thresholds.
        
        Args:
            conversations: List of conversations to potentially merge
            gap_minutes: Gap threshold (uses instance default if not provided)
            
        Returns:
            List of merged conversations
        """
        if not conversations:
            return []
        
        if gap_minutes is None:
            gap_minutes = self.gap_minutes
        
        # Sort by start time
        sorted_convs = sorted(conversations, key=lambda c: c.start_time)
        
        # Merge adjacent conversations
        merged = []
        current_group = [sorted_convs[0]]
        
        for conv in sorted_convs[1:]:
            # Check gap from last exchange of previous to first of current
            last_end = current_group[-1].end_time
            gap = (conv.start_time - last_end).total_seconds() / 60
            
            if gap <= gap_minutes:
                # Merge into current group
                current_group.append(conv)
            else:
                # Start new group
                merged.append(self._merge_conversation_group(current_group))
                current_group = [conv]
        
        # Don't forget the last group
        if current_group:
            merged.append(self._merge_conversation_group(current_group))
        
        return merged
    
    def _merge_conversation_group(self, conversations: List[Conversation]) -> Conversation:
        """Merge a group of conversations into one.
        
        Args:
            conversations: Conversations to merge
            
        Returns:
            Single merged conversation
        """
        if len(conversations) == 1:
            return conversations[0]
        
        # Collect all exchanges
        all_exchanges = []
        for conv in conversations:
            all_exchanges.extend(conv.exchanges)
        
        # Sort by timestamp
        all_exchanges.sort(key=lambda e: e.timestamp)
        
        # Use first conversation's ID with suffix
        merged_id = f"{conversations[0].id}_merged"
        
        # Get common project path if any
        project_paths = [c.project_path for c in conversations if c.project_path]
        project_path = project_paths[0] if project_paths else None
        
        return Conversation(
            id=merged_id,
            start_time=all_exchanges[0].timestamp,
            end_time=all_exchanges[-1].timestamp,
            project_path=project_path,
            exchanges=all_exchanges
        )
    
    def get_conversation_summary(self, conversation: Conversation) -> Dict[str, any]:
        """Get summary statistics for a conversation.
        
        Args:
            conversation: Conversation to analyze
            
        Returns:
            Dictionary with summary statistics
        """
        summary = {
            'id': conversation.id,
            'start_time': conversation.start_time,
            'end_time': conversation.end_time,
            'duration': conversation.duration.total_seconds(),
            'exchange_count': conversation.exchange_count,
            'stt_count': conversation.stt_count,
            'tts_count': conversation.tts_count,
            'project_path': conversation.project_path,
        }
        
        # Calculate word counts
        stt_words = sum(len(e.text.split()) for e in conversation.exchanges if e.is_stt)
        tts_words = sum(len(e.text.split()) for e in conversation.exchanges if e.is_tts)
        
        summary['user_word_count'] = stt_words
        summary['assistant_word_count'] = tts_words
        summary['total_word_count'] = stt_words + tts_words
        
        # Get unique providers and voices used
        providers = set()
        voices = set()
        models = set()
        
        for exchange in conversation.exchanges:
            if exchange.metadata:
                if exchange.metadata.provider:
                    providers.add(exchange.metadata.provider)
                if exchange.metadata.model:
                    models.add(exchange.metadata.model)
                if exchange.metadata.voice and exchange.is_tts:
                    voices.add(exchange.metadata.voice)
        
        summary['providers'] = list(providers)
        summary['models'] = list(models)
        summary['voices'] = list(voices)
        
        # Calculate average response times
        response_times = []
        for i in range(len(conversation.exchanges) - 1):
            current = conversation.exchanges[i]
            next_ex = conversation.exchanges[i + 1]
            
            # If current is TTS and next is STT, this is user response time
            # If current is STT and next is TTS, this is assistant response time
            if current.type != next_ex.type:
                response_time = (next_ex.timestamp - current.timestamp).total_seconds()
                response_times.append(response_time)
        
        if response_times:
            summary['avg_response_time'] = sum(response_times) / len(response_times)
            summary['min_response_time'] = min(response_times)
            summary['max_response_time'] = max(response_times)
        
        return summary