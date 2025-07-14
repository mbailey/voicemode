"""Metadata storage for voice mode conversations."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


class ConversationMetadata:
    """Handles storage and retrieval of conversation metadata."""
    
    def __init__(self, base_dir: Optional[Path] = None):
        """Initialize metadata storage.
        
        Args:
            base_dir: Base directory for metadata storage. 
                     Defaults to ~/.voicemode/metadata/conversations
        """
        self.base_dir = base_dir or Path.home() / '.voicemode' / 'metadata' / 'conversations'
    
    def get_metadata_path(self, conversation_id: str, date: datetime) -> Path:
        """Get path for metadata file.
        
        Args:
            conversation_id: ID of the conversation
            date: Date of the conversation
            
        Returns:
            Path to the metadata JSON file
        """
        date_str = date.strftime('%Y-%m-%d')
        return self.base_dir / date_str / f"{conversation_id}.json"
    
    def read_metadata(self, conversation_id: str, date: datetime) -> Optional[Dict]:
        """Read metadata for a conversation.
        
        Args:
            conversation_id: ID of the conversation
            date: Date of the conversation
            
        Returns:
            Metadata dict if exists, None otherwise
        """
        path = self.get_metadata_path(conversation_id, date)
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, IOError):
                return None
        return None
    
    def write_metadata(self, conversation_id: str, date: datetime, metadata: Dict) -> None:
        """Write metadata for a conversation.
        
        Args:
            conversation_id: ID of the conversation
            date: Date of the conversation
            metadata: Metadata dict to write
        """
        path = self.get_metadata_path(conversation_id, date)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Preserve existing metadata, update with new
        existing = self.read_metadata(conversation_id, date) or {}
        existing.update(metadata)
        
        # Ensure conversation_id is set
        existing['conversation_id'] = conversation_id
        
        # Set timestamps
        if 'created_at' not in existing:
            existing['created_at'] = datetime.now().isoformat()
        existing['updated_at'] = datetime.now().isoformat()
        
        path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    
    def toggle_favorite(self, conversation_id: str, date: datetime) -> bool:
        """Toggle favorite status for a conversation.
        
        Args:
            conversation_id: ID of the conversation
            date: Date of the conversation
            
        Returns:
            New favorite status
        """
        metadata = self.read_metadata(conversation_id, date) or {}
        metadata['is_favorite'] = not metadata.get('is_favorite', False)
        self.write_metadata(conversation_id, date, metadata)
        return metadata['is_favorite']
    
    def update_tags(self, conversation_id: str, date: datetime, 
                   add_tags: Optional[List[str]] = None,
                   remove_tags: Optional[List[str]] = None) -> List[str]:
        """Update tags for a conversation.
        
        Args:
            conversation_id: ID of the conversation
            date: Date of the conversation
            add_tags: Tags to add
            remove_tags: Tags to remove
            
        Returns:
            Updated list of tags
        """
        metadata = self.read_metadata(conversation_id, date) or {}
        current_tags = set(metadata.get('tags', []))
        
        if add_tags:
            current_tags.update(add_tags)
        if remove_tags:
            current_tags.difference_update(remove_tags)
        
        metadata['tags'] = sorted(list(current_tags))
        self.write_metadata(conversation_id, date, metadata)
        return metadata['tags']
    
    def list_metadata_for_date(self, date: datetime) -> Dict[str, Dict]:
        """List all metadata for a specific date.
        
        Args:
            date: Date to list metadata for
            
        Returns:
            Dict mapping conversation_id to metadata
        """
        date_str = date.strftime('%Y-%m-%d')
        date_dir = self.base_dir / date_str
        
        metadata_by_id = {}
        if date_dir.exists():
            for metadata_file in date_dir.glob("*.json"):
                try:
                    metadata = json.loads(metadata_file.read_text())
                    conv_id = metadata_file.stem
                    metadata_by_id[conv_id] = metadata
                except (json.JSONDecodeError, IOError):
                    continue
        
        return metadata_by_id
    
    def get_all_favorites(self) -> Dict[str, Dict]:
        """Get all conversations marked as favorite.
        
        Returns:
            Dict mapping conversation_id to metadata for all favorites
        """
        favorites = {}
        
        if self.base_dir.exists():
            for date_dir in self.base_dir.iterdir():
                if date_dir.is_dir():
                    for metadata_file in date_dir.glob("*.json"):
                        try:
                            metadata = json.loads(metadata_file.read_text())
                            if metadata.get('is_favorite'):
                                conv_id = metadata_file.stem
                                favorites[conv_id] = metadata
                        except (json.JSONDecodeError, IOError):
                            continue
        
        return favorites
    
    def cleanup_orphaned_metadata(self, existing_conversation_ids: List[str]) -> int:
        """Remove metadata for conversations that no longer exist.
        
        Args:
            existing_conversation_ids: List of conversation IDs that still exist
            
        Returns:
            Number of orphaned metadata files removed
        """
        existing_ids = set(existing_conversation_ids)
        removed_count = 0
        
        if self.base_dir.exists():
            for date_dir in self.base_dir.iterdir():
                if date_dir.is_dir():
                    for metadata_file in date_dir.glob("*.json"):
                        conv_id = metadata_file.stem
                        if conv_id not in existing_ids:
                            metadata_file.unlink()
                            removed_count += 1
                    
                    # Remove empty date directories
                    if not any(date_dir.iterdir()):
                        date_dir.rmdir()
        
        return removed_count