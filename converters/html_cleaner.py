"""HTML cleaner for removing Confluence-specific markup without losing content."""

import logging
import re
from typing import Any

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger('confluence_markdown_migrator.converters.htmlcleaner')


class HtmlCleaner:
    """Removes Confluence-specific HTML markup for cleaner markdown conversion."""
    
    def __init__(self, logger: logging.Logger = None):
        """Initialize HTML cleaner with optional logger."""
        self.logger = logger or logging.getLogger('confluence_markdown_migrator.converters.htmlcleaner')
    
    def clean(self, soup: BeautifulSoup, format_type: str = 'export') -> BeautifulSoup:
        """
        Main entry point to clean HTML based on format type.
        
        Args:
            soup: BeautifulSoup object with Confluence HTML
            format_type: 'export' or 'storage' format
            
        Returns:
            Cleaned BeautifulSoup object
        """
        self.logger.debug(f"Cleaning HTML (format: {format_type})")
        
        if format_type == 'export':
            self._clean_export_html(soup)
        elif format_type == 'storage':
            self._clean_storage_format(soup)
        else:
            self.logger.warning(f"Unknown format type: {format_type}, treating as export")
            self._clean_export_html(soup)
        
        self.logger.debug("HTML cleaning completed")
        return soup
    
    def _clean_export_html(self, soup: BeautifulSoup) -> None:
        """Clean export HTML (rendered HTML with all macros expanded)."""
        # Remove Confluence-specific classes
        confluence_classes = [
            'confluenceTable', 'confluenceTh', 'confluenceTd',
            'confluence-embedded-image', 'confluence-embedded-file',
            'wiki-content', 'page-content', 'table-wrap'
        ]
        
        for cls in confluence_classes:
            for element in soup.find_all(class_=cls):
                self._remove_classes(element, [cls])
                if self._is_structural_wrapper(element):
                    self._unwrap_element(element)
        
        # Remove data attributes from images and other elements
        data_attrs = ['data-linked-resource-id', 'data-linked-resource-type', 
                     'data-linked-resource-default-alias', 'data-base-url', 
                     'data-image-src', 'data-macro-name', 'data-macro-id']
        
        for attr in data_attrs:
            for element in soup.find_all(attrs={attr: True}):
                del element[attr]
        
        # Remove navigation and header elements
        for selector in ['#header', '#navigation', '#footer', '.page-metadata']:
            for element in soup.select(selector):
                element.decompose()
        
        # Remove wrapper divs that contain no structural content
        for div in soup.find_all('div'):
            if self._is_structural_wrapper(div):
                self._unwrap_element(div)
        
        # Clean up empty elements
        self._remove_empty_elements(soup)
    
    def _clean_storage_format(self, soup: BeautifulSoup) -> None:
        """Clean storage format (wiki markup with ac:namespace elements)."""
        # For storage format, we keep ac:structured-macro elements for macro handler
        # Only remove wrapper divs and navigation
        
        # Remove navigation and header elements
        for selector in ['#header', '#navigation', '#footer']:
            for element in soup.select(selector):
                element.decompose()
        
        # Remove wrapper divs but preserve macro elements
        for div in soup.find_all('div'):
            if self._is_structural_wrapper(div) and not div.find(['ac:structured-macro', 'ri:attachment']):
                self._unwrap_element(div)
        
        # Clean up empty elements
        self._remove_empty_elements(soup)
    
    def _remove_classes(self, element: Tag, classes: list) -> None:
        """Remove specified CSS classes from element."""
        if not element.get('class'):
            return
        
        current_classes = element.get('class', [])
        remaining_classes = [c for c in current_classes if c not in classes]
        
        if remaining_classes:
            element['class'] = remaining_classes
        else:
            del element['class']
    
    def _remove_attributes(self, element: Tag, patterns: list) -> None:
        """Remove attributes matching wildcard patterns from element."""
        if not element.attrs:
            return
        
        attrs_to_remove = []
        for attr in element.attrs:
            for pattern in patterns:
                if pattern.endswith('*'):
                    prefix = pattern[:-1]
                    if attr.startswith(prefix):
                        attrs_to_remove.append(attr)
                        break
                elif attr == pattern:
                    attrs_to_remove.append(attr)
                    break
        
        for attr in attrs_to_remove:
            del element[attr]
    
    def _unwrap_element(self, element: Tag) -> None:
        """Safely unwrap element while preserving child content."""
        self.logger.debug(f"Unwrapping element: {element.name} {element.get('class', '')}")
        element.unwrap()
    
    def _is_structural_wrapper(self, element: Tag) -> bool:
        """
        Check if element is a structural wrapper that can be safely unwrapped.
        
        A wrapper is structural if it contains tables, lists, code blocks, or images.
        """
        if not element.name or element.name not in ['div', 'span']:
            return False
        
        # Check for attributes that might be important
        important_attrs = ['id', 'class', 'data-*']
        if element.attrs:
            has_important_attrs = any(
                attr in ['id', 'name', 'style'] or attr.startswith('data-')
                for attr in element.attrs
            )
            if has_important_attrs:
                return False
        
        # Check for structural content
        structural_selectors = ['table', 'ul', 'ol', 'pre', 'img', 'code', 'blockquote']
        if element.find(structural_selectors):
            self.logger.debug(f"Preserving wrapper with structural content: {element.name}")
            return False
        
        # Check for text content beyond whitespace
        text = element.get_text(strip=True)
        if len(text) > 1000:  # Large text blocks likely need wrapper
            self.logger.debug(f"Preserving wrapper with large text block: {len(text)} chars")
            return False
        
        return True
    
    def _remove_empty_elements(self, soup: BeautifulSoup) -> None:
        """Remove empty elements that serve no purpose."""
        removed_count = 0
        
        for element in soup.find_all(['div', 'span', 'p', 'br']):
            # Skip elements with children
            if element.find():
                continue
            
            # Check if element has non-whitespace text
            text = element.get_text(strip=True)
            has_text = len(text) > 0
            
            # Check if element has important attributes
            has_attrs = bool(element.attrs)
            
            # Remove if completely empty
            if not has_text and not has_attrs:
                element.decompose()
                removed_count += 1
        
        if removed_count > 0:
            self.logger.debug(f"Removed {removed_count} empty elements")
