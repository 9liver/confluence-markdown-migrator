"""
ID mapping tracker for Confluence to BookStack import.

This module tracks and manages the mapping between Confluence and BookStack IDs
during the import process.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class IdMappingTracker:
    """Tracks mappings between Confluence and BookStack IDs."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize ID mapping tracker.
        
        Args:
            logger: Optional logger instance (defaults to module logger)
        """
        self.logger = logger or logging.getLogger(__name__)
        
        # Mapping: Confluence page ID -> BookStack info
        self._confluence_to_bookstack: Dict[str, Dict[str, Any]] = {}
        
        # Reverse mapping: BookStack ID -> Confluence page ID
        self._bookstack_to_confluence: Dict[int, str] = {}
        
        # Space mappings: Confluence space key -> BookStack shelf ID
        self._space_mappings: Dict[str, int] = {}
        
        self.logger.debug("Initialized IdMappingTracker")
    
    def add_page_mapping(
        self,
        confluence_id: str,
        bookstack_id: int,
        bookstack_type: str,
        bookstack_slug: str = ''
    ) -> None:
        """
        Store mapping for a Confluence page to BookStack entity.
        
        Args:
            confluence_id: Confluence page ID
            bookstack_id: BookStack entity ID
            bookstack_type: Type of BookStack entity ('shelf', 'book', 'chapter', 'page')
            bookstack_slug: Slug/identifier for the entity (optional)
        """
        mapping_info = {
            'bookstack_id': bookstack_id,
            'bookstack_type': bookstack_type,
            'bookstack_slug': bookstack_slug
        }
        
        self._confluence_to_bookstack[confluence_id] = mapping_info
        self._bookstack_to_confluence[bookstack_id] = confluence_id
        
        self.logger.debug(
            f"Page mapping added: {confluence_id} -> "
            f"{bookstack_type}:{bookstack_id}"
        )
    
    def add_space_mapping(self, space_key: str, shelf_id: int) -> None:
        """
        Store mapping for a Confluence space to BookStack shelf.
        
        Args:
            space_key: Confluence space key
            shelf_id: BookStack shelf ID
        """
        self._space_mappings[space_key] = shelf_id
        self.logger.debug(f"Space mapping added: {space_key} -> shelf:{shelf_id}")
    
    def get_bookstack_id(self, confluence_id: str) -> Optional[int]:
        """
        Get BookStack ID for a Confluence page ID.
        
        Args:
            confluence_id: Confluence page ID
            
        Returns:
            BookStack ID or None if not found
        """
        mapping = self._confluence_to_bookstack.get(confluence_id)
        return mapping['bookstack_id'] if mapping else None
    
    def get_bookstack_info(self, confluence_id: str) -> Optional[Dict[str, Any]]:
        """
        Get complete BookStack info for a Confluence page ID.
        
        Args:
            confluence_id: Confluence page ID
            
        Returns:
            Dict with 'bookstack_id', 'bookstack_type', 'bookstack_slug' or None
        """
        return self._confluence_to_bookstack.get(confluence_id)
    
    def get_confluence_id(self, bookstack_id: int) -> Optional[str]:
        """
        Get Confluence ID for a BookStack entity ID.
        
        Args:
            bookstack_id: BookStack entity ID
            
        Returns:
            Confluence page ID or None if not found
        """
        return self._bookstack_to_confluence.get(bookstack_id)
    
    def get_shelf_id(self, space_key: str) -> Optional[int]:
        """
        Get BookStack shelf ID for a Confluence space key.
        
        Args:
            space_key: Confluence space key
            
        Returns:
            BookStack shelf ID or None if not found
        """
        return self._space_mappings.get(space_key)
    
    def get_all_mappings(self) -> Dict[str, Any]:
        """
        Get complete mapping structure.
        
        Returns:
            Dict with 'pages', 'spaces' keys containing all mappings
        """
        return {
            'pages': dict(self._confluence_to_bookstack),
            'spaces': dict(self._space_mappings)
        }
    
    def get_statistics(self) -> Dict[str, int]:
        """
        Get mapping statistics.
        
        Returns:
            Dict with counts of mapped items
        """
        # Count by type
        type_counts = {}
        for mapping in self._confluence_to_bookstack.values():
            bookstack_type = mapping.get('bookstack_type', 'unknown')
            type_counts[bookstack_type] = type_counts.get(bookstack_type, 0) + 1
        
        return {
            'total_pages': len(self._confluence_to_bookstack),
            'total_spaces': len(self._space_mappings),
            'by_type': type_counts
        }
    
    def page_exists(self, confluence_id: str) -> bool:
        """
        Check if a Confluence page has been mapped.
        
        Args:
            confluence_id: Confluence page ID
            
        Returns:
            True if mapping exists
        """
        return confluence_id in self._confluence_to_bookstack
    
    def space_exists(self, space_key: str) -> bool:
        """
        Check if a Confluence space has been mapped.
        
        Args:
            space_key: Confluence space key
            
        Returns:
            True if mapping exists
        """
        return space_key in self._space_mappings
    
    def clear(self) -> None:
        """Clear all mappings."""
        self._confluence_to_bookstack.clear()
        self._bookstack_to_confluence.clear()
        self._space_mappings.clear()
        
        self.logger.debug("Cleared all ID mappings")