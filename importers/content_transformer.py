"""
Content transformer for BookStack import.

This module converts markdown content to HTML for BookStack storage.
"""

import logging
import re
from typing import Optional
import markdown as md

logger = logging.getLogger(__name__)


class ContentTransformer:
    """Transforms markdown content to HTML for BookStack storage."""
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize content transformer.
        
        Args:
            logger: Optional logger instance (defaults to module logger)
        """
        self.logger = logger or logging.getLogger(__name__)
        
        # Initialize markdown converter with extensions
        self.md = md.Markdown(
            extensions=[
                'extra',           # Miscellaneous useful extensions
                'codehilite',      # Syntax highlighting
                'toc',             # Table of contents
                'nl2br',           # Convert newlines to <br>
                'sane_lists'       # Better list handling
            ],
            extension_configs={
                'codehilite': {
                    'css_class': 'highlight'
                }
            }
        )
        
        self.logger.debug("Initialized ContentTransformer with markdown extensions")
    
    def transform_markdown_to_html(self, markdown_content: str) -> str:
        """
        Convert markdown content to HTML.
        
        Args:
            markdown_content: Markdown string to convert
            
        Returns:
            HTML string
        """
        if not markdown_content:
            self.logger.debug("Empty markdown content provided")
            return ""
        
        try:
            # Reset the markdown converter state
            self.md.reset()
            
            # Convert markdown to HTML
            html_content = self.md.convert(markdown_content)
            
            self.logger.debug(f"Converted {len(markdown_content)} chars of markdown to {len(html_content)} chars of HTML")
            
            return html_content
            
        except Exception as e:
            self.logger.error(f"Failed to convert markdown to HTML: {str(e)}")
            return ""
    
    def transform_title(self, title: str) -> str:
        """
        Sanitize and truncate title for BookStack compatibility.
        
        Args:
            title: Original page title
            
        Returns:
            Sanitized title (max 255 chars, no control characters)
        """
        if not title:
            return "Untitled"
        
        # Remove control characters
        sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', title)
        
        # Strip whitespace
        sanitized = sanitized.strip()
        
        # Truncate to 255 characters (BookStack limit)
        max_length = 255
        if len(sanitized) > max_length:
            self.logger.warning(f"Title truncated from {len(sanitized)} to {max_length} chars")
            sanitized = sanitized[:max_length]
        
        self.logger.debug(f"Transformed title: '{title}' -> '{sanitized}'")
        
        return sanitized or "Untitled"