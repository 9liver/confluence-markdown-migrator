"""
BookStack hierarchy mapper for Confluence page structures.

This module provides utilities to map Confluence's hierarchical page structure
to BookStack's 3-level structure (Shelf→Book→Chapter→Page).
"""

import logging
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from models import ConfluencePage, ConfluenceSpace

logger = logging.getLogger(__name__)


class BookStackHierarchyMapper:
    """Maps Confluence hierarchies to BookStack's three-level structure."""
    
    @staticmethod
    def identify_top_level_pages(pages: List[ConfluencePage]) -> List[ConfluencePage]:
        """
        Identify top-level pages (those without parents).
        
        Args:
            pages: List of ConfluencePage objects
            
        Returns:
            List of top-level pages (will become Books in BookStack)
        """
        top_level = [page for page in pages if page.parent_id is None]
        logger.debug(f"Identified {len(top_level)} top-level pages out of {len(pages)}")
        return top_level
    
    @staticmethod
    def categorize_children(children: List[ConfluencePage]) -> Dict[str, List[ConfluencePage]]:
        """
        Categorize children into chapters (pages with children) and pages (leaf nodes).
        
        Args:
            children: List of child ConfluencePage objects
            
        Returns:
            Dict with keys 'chapters' and 'pages'
        """
        chapters = []
        pages = []
        
        for child in children:
            if BookStackHierarchyMapper.should_be_chapter(child):
                chapters.append(child)
            else:
                pages.append(child)
        
        logger.debug(f"Categorized {len(chapters)} chapters and {len(pages)} pages")
        return {'chapters': chapters, 'pages': pages}
    
    @staticmethod
    def should_be_chapter(page: ConfluencePage) -> bool:
        """
        Determine if a page should become a Chapter (has children) or Page (no children).
        
        Args:
            page: ConfluencePage to evaluate
            
        Returns:
            True if page has children (should be Chapter), False otherwise
        """
        return len(page.children) > 0
    

    @staticmethod
    def calculate_description(page: ConfluencePage, max_length: int = 500) -> str:
        """
        Extract a plain text description from page content HTML.
        
        Args:
            page: ConfluencePage with HTML content
            max_length: Maximum description length in characters
            
        Returns:
            Plain text description (truncated if necessary)
        """
        try:
            if not page.content:
                return ""
            
            # Parse HTML and extract text
            soup = BeautifulSoup(page.content, 'html.parser')
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()
            
            # Get plain text
            text = soup.get_text()
            
            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = ' '.join(chunk for chunk in chunks if chunk)
            
            # Truncate if necessary
            if len(text) > max_length:
                text = text[:max_length].rsplit(' ', 1)[0] + "..."
            
            logger.debug(f"Extracted description ({len(text)} chars) for page: {page.title}")
            return text
            
        except Exception as e:
            logger.warning(f"Failed to extract description for page '{page.title}': {str(e)}")
            return ""