"""Converters package for high-fidelity Confluence HTML to Markdown conversion."""

import logging

from .html_cleaner import HtmlCleaner
from .link_processor import LinkProcessor
from .macro_handler import MacroHandler
from .markdown_converter import MarkdownConverter

logger = logging.getLogger('confluence_markdown_migrator.converters')


def convert_page(page, config=None, logger=None):
    """
    Convenience function to convert a ConfluencePage from HTML to Markdown.
    
    This orchestrates the full conversion pipeline:
    1. HTML cleaning (removes Confluence-specific markup)
    2. Macro conversion (transforms Confluence macros to markdown-friendly HTML)
    3. Link and image processing
    4. Markdown generation using markdownify
    5. Post-processing for Wiki.js/BookStack compatibility
    6. Metadata tracking in page.conversion_metadata
    
    Args:
        page: ConfluencePage object with HTML content in page.content
        config: Optional configuration dictionary for converter behavior
        logger: Optional logger instance (uses module logger if not provided)
        
    Returns:
        bool: True if conversion succeeded, False otherwise
        
    Example:
        >>> from converters import convert_page
        >>> from models import ConfluencePage
        >>> page = ConfluencePage(id='123', title='Test', content='<html>...', space_key='DEMO')
        >>> success = convert_page(page)
        >>> if success:
        ...     print(page.markdown_content)
    """
    if logger is None:
        logger = logging.getLogger('confluence_markdown_migrator.converters')
    
    converter = MarkdownConverter(logger=logger, config=config)
    return converter.convert_page(page)


__all__ = [
    'convert_page',
    'MarkdownConverter',
    'HtmlCleaner',
    'MacroHandler',
    'LinkProcessor'
]
