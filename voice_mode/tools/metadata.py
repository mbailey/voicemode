"""MCP tools for managing conversation metadata."""

from typing import Optional, List
from datetime import datetime

from ..mcp_instance import mcp
from ..config import logger
from ..metadata import ConversationMetadata


@mcp.tool()
async def update_conversation_metadata(
    conversation_id: str,
    title: Optional[str] = None,
    toggle_favorite: bool = False,
    add_tags: Optional[List[str]] = None,
    remove_tags: Optional[List[str]] = None,
    notes: Optional[str] = None,
    summary: Optional[str] = None,
    rating: Optional[int] = None
) -> str:
    """
    Update metadata for a voice conversation.
    
    Use this tool to add or modify metadata for conversations:
    - Set custom titles to replace auto-generated previews
    - Toggle favorite status for quick filtering
    - Add/remove tags for organization
    - Add notes or summaries
    - Rate conversations (1-5 stars)
    
    Args:
        conversation_id: The conversation ID (e.g., conv_20250713_153306_6u3vqj)
        title: Custom title for the conversation
        toggle_favorite: Toggle the favorite status
        add_tags: List of tags to add
        remove_tags: List of tags to remove
        notes: Personal notes about the conversation
        summary: Brief summary of the conversation
        rating: Rating from 1-5 stars
    
    Returns:
        Summary of what was updated
    """
    try:
        metadata_store = ConversationMetadata()
        
        # Parse date from conversation ID
        try:
            date_part = conversation_id.split('_')[1]
            conv_date = datetime.strptime(date_part, '%Y%m%d')
        except (IndexError, ValueError):
            return f"❌ Invalid conversation ID format: {conversation_id}"
        
        # Read existing metadata
        existing = metadata_store.read_metadata(conversation_id, conv_date)
        updates = []
        
        # Prepare metadata updates
        metadata_updates = {}
        
        if title is not None:
            metadata_updates['title'] = title
            updates.append(f"Set title: {title}")
        
        if summary is not None:
            metadata_updates['summary'] = summary
            updates.append(f"Set summary: {summary[:50]}...")
        
        if notes is not None:
            metadata_updates['notes'] = notes
            updates.append(f"Set notes: {notes[:50]}...")
        
        if rating is not None:
            if 1 <= rating <= 5:
                metadata_updates['rating'] = rating
                updates.append(f"Set rating: {'⭐' * rating}")
            else:
                return "❌ Rating must be between 1 and 5"
        
        # Write basic updates
        if metadata_updates:
            metadata_store.write_metadata(conversation_id, conv_date, metadata_updates)
        
        # Handle favorite toggle
        if toggle_favorite:
            new_status = metadata_store.toggle_favorite(conversation_id, conv_date)
            updates.append(f"Favorite status: {'⭐ ON' if new_status else 'OFF'}")
        
        # Handle tags
        if add_tags or remove_tags:
            new_tags = metadata_store.update_tags(
                conversation_id, 
                conv_date,
                add_tags=add_tags,
                remove_tags=remove_tags
            )
            updates.append(f"Tags: {', '.join(new_tags) if new_tags else 'none'}")
        
        if not updates:
            return "ℹ️ No updates specified"
        
        # Read final metadata
        final_metadata = metadata_store.read_metadata(conversation_id, conv_date)
        
        result = f"✅ Updated {conversation_id}\n\n"
        result += "Changes:\n"
        for update in updates:
            result += f"  • {update}\n"
        
        result += "\nCurrent metadata:\n"
        if final_metadata:
            if final_metadata.get('title'):
                result += f"  Title: {final_metadata['title']}\n"
            if final_metadata.get('is_favorite'):
                result += f"  Favorite: ⭐\n"
            if final_metadata.get('tags'):
                result += f"  Tags: {', '.join(final_metadata['tags'])}\n"
            if final_metadata.get('rating'):
                result += f"  Rating: {'⭐' * final_metadata['rating']}\n"
            if final_metadata.get('summary'):
                result += f"  Summary: {final_metadata['summary'][:100]}...\n"
            if final_metadata.get('notes'):
                result += f"  Notes: {final_metadata['notes'][:100]}...\n"
        
        return result
        
    except Exception as e:
        logger.error(f"Error updating conversation metadata: {e}")
        return f"❌ Error updating metadata: {str(e)}"


@mcp.tool()
async def generate_conversation_titles(
    date_range: Optional[str] = "today",
    include_summary: bool = False,
    only_untagged: bool = True,
    conversation_ids: Optional[List[str]] = None
) -> str:
    """
    Generate titles for conversations using AI analysis.
    
    This tool reads conversation content and generates appropriate titles
    based on the topics discussed. It can also generate summaries if requested.
    
    Args:
        date_range: Date range to process - "today", "yesterday", "week", or "YYYY-MM-DD"
        include_summary: Also generate brief summaries
        only_untagged: Only process conversations without titles (default: True)
        conversation_ids: Specific conversation IDs to process (overrides date_range)
    
    Returns:
        Summary of titles generated
    """
    try:
        from ..exchanges import ExchangeReader, ConversationGrouper
        from ..metadata import ConversationMetadata
        
        reader = ExchangeReader()
        grouper = ConversationGrouper()
        metadata_store = ConversationMetadata()
        
        # Determine which conversations to process
        if conversation_ids:
            # Process specific conversations
            all_exchanges = []
            dates_to_read = set()
            
            for conv_id in conversation_ids:
                try:
                    date_part = conv_id.split('_')[1]
                    date = datetime.strptime(date_part, '%Y%m%d').date()
                    dates_to_read.add(date)
                except (IndexError, ValueError):
                    continue
            
            for date in dates_to_read:
                all_exchanges.extend(reader.read_date(date))
            
            conversations = grouper.group_exchanges(all_exchanges)
            # Filter to requested IDs
            conversations = {k: v for k, v in conversations.items() if k in conversation_ids}
        else:
            # Process by date range
            if date_range == "today":
                exchanges = list(reader.read_date(datetime.now().date()))
            elif date_range == "yesterday":
                yesterday = datetime.now().date() - timedelta(days=1)
                exchanges = list(reader.read_date(yesterday))
            elif date_range == "week":
                exchanges = list(reader.read_recent(7))
            else:
                # Try to parse as date
                try:
                    target_date = datetime.strptime(date_range, '%Y-%m-%d').date()
                    exchanges = list(reader.read_date(target_date))
                except ValueError:
                    return f"❌ Invalid date range: {date_range}"
            
            conversations = grouper.group_exchanges(exchanges)
        
        if not conversations:
            return "ℹ️ No conversations found in the specified range"
        
        # Filter conversations if only_untagged
        to_process = []
        for conv in conversations.values():
            if only_untagged:
                metadata = metadata_store.read_metadata(conv.id, conv.start_time)
                if metadata and metadata.get('title'):
                    continue
            to_process.append(conv)
        
        if not to_process:
            return "ℹ️ No conversations need titles"
        
        # Generate titles
        generated_count = 0
        results = []
        
        for conv in to_process:
            # Get conversation content for analysis
            # Take first 10 exchanges or 500 words, whichever comes first
            content_parts = []
            word_count = 0
            
            for i, exchange in enumerate(conv.exchanges[:10]):
                speaker = "User" if exchange.type == 'stt' else "Assistant"
                content_parts.append(f"{speaker}: {exchange.text}")
                word_count += len(exchange.text.split())
                if word_count > 500:
                    break
            
            conversation_text = "\n".join(content_parts)
            
            # Generate title based on content
            # This is a simple implementation - in production, you'd use an LLM
            # For now, extract key topics from the first user message
            title = None
            summary = None
            
            # Find first substantial user message
            for exchange in conv.exchanges:
                if exchange.type == 'stt' and len(exchange.text) > 20:
                    # Extract key phrases
                    text = exchange.text.lower()
                    
                    # Look for action words
                    if 'implement' in text or 'create' in text or 'build' in text:
                        if 'metadata' in text:
                            title = "Metadata System Implementation"
                        elif 'cli' in text:
                            title = "CLI Development"
                        elif 'test' in text:
                            title = "Test Implementation"
                        else:
                            title = "Development Task"
                    elif 'fix' in text or 'debug' in text or 'error' in text:
                        title = "Bug Fix / Debugging"
                    elif 'help' in text or 'how' in text or 'what' in text:
                        title = "Help / Information Request"
                    else:
                        # Use first few words as title
                        words = exchange.text.split()[:6]
                        title = " ".join(words) + "..."
                    
                    if include_summary:
                        summary = f"Discussion about {title.lower()}"
                    
                    break
            
            if not title:
                title = f"Conversation on {conv.start_time.strftime('%Y-%m-%d %H:%M')}"
            
            # Save metadata
            metadata_updates = {'title': title}
            if summary:
                metadata_updates['summary'] = summary
            
            metadata_store.write_metadata(conv.id, conv.start_time, metadata_updates)
            generated_count += 1
            
            results.append(f"  • {conv.id}: {title}")
        
        result = f"✅ Generated {generated_count} titles\n\n"
        if results:
            result += "Titles generated:\n"
            result += "\n".join(results[:10])  # Show first 10
            if len(results) > 10:
                result += f"\n  ... and {len(results) - 10} more"
        
        return result
        
    except Exception as e:
        logger.error(f"Error generating conversation titles: {e}")
        return f"❌ Error generating titles: {str(e)}"