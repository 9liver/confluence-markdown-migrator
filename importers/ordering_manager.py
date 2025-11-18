"""
Ordering manager for BookStack content hierarchy.

This module handles setting the correct order/priority for Books, Chapters,
and Pages in BookStack to preserve the original Confluence page sequence.
"""

import logging
from typing import List, Any, Optional, Dict

logger = logging.getLogger(__name__)


class OrderingManager:
    """Manages content ordering in BookStack using priority values."""
    
    def __init__(self, bookstack_client: Any, logger: Optional[logging.Logger] = None):
        """
        Initialize ordering manager.
        
        Args:
            bookstack_client: BookStackClient instance
            logger: Optional logger instance (defaults to module logger)
        """
        self.client = bookstack_client
        self.logger = logger or logging.getLogger(__name__)
        
        self.logger.debug("Initialized OrderingManager")
    
    def set_book_content_order(self, book_id: int, children: List[Any]) -> None:
        """
        Set the order of chapters and pages in a book.
        
        Args:
            book_id: BookStack book ID
            children: List of ConfluencePage objects (can be chapters or pages)
        """
        if not children:
            self.logger.debug(f"No children to order for book {book_id}")
            return
        
        self.logger.info(
            f"Setting order for {len(children)} items in book {book_id}"
        )
        
        # Track failures to continue processing
        failures = 0
        
        for index, child in enumerate(children):
            try:
                # Get BookStack metadata
                bookstack_id = child.metadata.get('bookstack_id')
                bookstack_type = child.metadata.get('bookstack_type')
                
                if not bookstack_id or not bookstack_type:
                    self.logger.warning(
                        f"Missing BookStack metadata for '{child.title}'. "
                        f"Cannot set priority."
                    )
                    continue
                
                # Set priority based on index (0-based for first position)
                priority = index
                
                self.logger.debug(
                    f"Setting priority {priority} for "
                    f"{bookstack_type} '{child.title}' (ID: {bookstack_id})"
                )
                
                if bookstack_type == 'chapter':
                    self.client.update_chapter(bookstack_id, priority=priority)
                elif bookstack_type == 'page':
                    # Direct pages in book (not in chapter)
                    self.client.update_page(bookstack_id, priority=priority)
                else:
                    self.logger.warning(
                        f"Unknown type '{bookstack_type}' for '{child.title}'"
                    )
                    continue
                
            except Exception as e:
                failures += 1
                self.logger.warning(
                    f"Failed to set priority for '{child.title}': {str(e)}"
                )
                # Continue with next item
                continue
        
        if failures == 0:
            self.logger.info(
                f"Successfully set order for all {len(children)} items in book {book_id}"
            )
        else:
            self.logger.warning(
                f"Failed to set order for {failures}/{len(children)} items in book {book_id}"
            )
    
    def set_chapter_page_order(self, chapter_id: int, pages: List[Any]) -> None:
        """
        Set the order of pages in a chapter.
        
        Args:
            chapter_id: BookStack chapter ID
            pages: List of ConfluencePage objects (leaf pages)
        """
        if not pages:
            self.logger.debug(f"No pages to order for chapter {chapter_id}")
            return
        
        self.logger.info(
            f"Setting order for {len(pages)} pages in chapter {chapter_id}"
        )
        
        failures = 0
        
        for index, page in enumerate(pages):
            try:
                # Get BookStack metadata
                bookstack_id = page.metadata.get('bookstack_id')
                bookstack_type = page.metadata.get('bookstack_type')
                
                if not bookstack_id:
                    self.logger.warning(
                        f"Missing BookStack ID for page '{page.title}'. "
                        f"Cannot set priority."
                    )
                    continue
                
                # Verify it's a page type
                if bookstack_type != 'page':
                    self.logger.warning(
                        f"Expected 'page' type for '{page.title}', "
                        f"got '{bookstack_type}'"
                    )
                    continue
                
                # Set priority
                priority = index
                
                self.logger.debug(
                    f"Setting priority {priority} for page "
                    f"'{page.title}' (ID: {bookstack_id})"
                )
                
                self.client.update_page(bookstack_id, priority=priority)
                
            except Exception as e:
                failures += 1
                self.logger.warning(
                    f"Failed to set priority for page '{page.title}': {str(e)}"
                )
                continue
        
        if failures == 0:
            self.logger.info(
                f"Successfully set order for all {len(pages)} pages in chapter {chapter_id}"
            )
        else:
            self.logger.warning(
                f"Failed to set order for {failures}/{len(pages)} pages in chapter {chapter_id}"
            )
    
    def apply_priority_on_create(self, index: int) -> int:
        """
        Helper to get priority value when creating entities.
        
        Args:
            index: Position in the list (0-based)
            
        Returns:
            Priority value to use during creation
        """
        # BookStack uses 0 as first priority, so index is correct
        return index