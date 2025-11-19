"""
HTML List Fixer for repairing broken Confluence/Wiki.js HTML list structures.

This module fixes common issues when Confluence HTML has been rendered through
Wiki.js or other intermediate systems, causing broken list numbering and
incorrect code block placement.
"""

import logging
from bs4 import BeautifulSoup, Tag


class HtmlListFixer:
    """Repairs broken HTML list structures to ensure proper Markdown conversion."""

    def __init__(self, logger: logging.Logger = None):
        """Initialize with optional logger."""
        self.logger = logger or logging.getLogger(__name__)

    def fix_html(self, html_content: str) -> str:
        """Main entry point - repair broken HTML list structures."""
        if not html_content:
            return html_content

        soup = BeautifulSoup(html_content, 'lxml')

        # Fix consecutive OL elements (the main issue)
        self._fix_consecutive_ordered_lists(soup)

        # Move orphaned code blocks into list items
        self._fix_orphaned_code_blocks(soup)

        # Remove start attributes that interfere with markdown numbering
        self._remove_start_attributes(soup)

        # Fix incorrectly nested lists
        self._fix_nested_list_nesting(soup)

        return str(soup)

    def _fix_consecutive_ordered_lists(self, soup: BeautifulSoup) -> None:
        """
        Fix multiple consecutive <ol> lists that should be one continuous list.
        
        Handles patterns like:
        <ol><li>item 1</li></ol>
        <pre>code block</pre>
        <ol start="2"><li>item 2</li></ol>
        """
        # Find all ordered list elements
        ordered_lists = soup.find_all('ol')
        
        for current_ol in ordered_lists:
            # Skip if already removed/merged
            if not current_ol.parent:
                continue
                
            self._process_list_and_merge_next(current_ol)

    def _process_list_and_merge_next(self, current_ol: Tag) -> None:
        """Process a list and merge all following list elements into it."""
        # Get the next sibling of this list
        next_sibling = current_ol.find_next_sibling()
        
        while next_sibling is not None:
            self.logger.debug(f"Processing sibling: {type(next_sibling).__name__}")
            
            # If it's another ordered list, merge it
            if isinstance(next_sibling, Tag) and next_sibling.name == 'ol':
                self.logger.debug("Merging consecutive <ol> elements")
                
                # Move all list items from next_sibling to current_ol
                for li in list(next_sibling.find_all('li', recursive=False)):
                    li.extract()
                    current_ol.append(li)
                
                # Remove the now-empty ol
                to_remove = next_sibling
                next_sibling = to_remove.find_next_sibling()
                to_remove.decompose()
                continue
                
            # If it's a code block, move it into the last list item
            elif self._is_code_element(next_sibling):
                self._append_to_last_list_item(current_ol, next_sibling)
                next_sibling = current_ol.find_next_sibling()
                continue
                
            # If it's empty or whitespace, skip it
            elif isinstance(next_sibling, Tag):
                # Tag element - check if it has meaningful content
                if not next_sibling.get_text(strip=True):
                    empty = next_sibling
                    next_sibling = empty.find_next_sibling()
                    empty.decompose()
                    continue
            else:
                # NavigableString or similar text node
                text = str(next_sibling)
                if not text.strip():
                    empty = next_sibling
                    next_sibling = empty.find_next_sibling()
                    if empty and empty.extract:
                        empty.extract()
                    continue
                
            # Stop at any other element type
            break
        
        return

    def _is_code_element(self, element) -> bool:
        """Check if an element is a code block that belongs in a list item."""
        if not isinstance(element, Tag):
            return False
            
        # Match <pre> elements
        if element.name == 'pre':
            return True
            
        # Match <div class="code ..."> elements
        if element.name == 'div':
            classes = element.get('class', [])
            if isinstance(classes, list):
                return any('code' in cls.lower() for cls in classes)
                
        return False

    def _append_to_last_list_item(self, ol: Tag, element: Tag) -> None:
        """Append an element to the last list item in the ordered list."""
        list_items = ol.find_all('li', recursive=False)
        if list_items:
            last_li = list_items[-1]
            # Move the element into the last list item
            last_li.append(element.extract())
            self.logger.debug("Moved code block into last list item")

    def _fix_orphaned_code_blocks(self, soup: BeautifulSoup) -> None:
        """
        Find code blocks that are direct children of lists but not inside list items,
        and move them into the preceding list item.
        """
        # Find all elements that might be code blocks
        candidates = soup.find_all(['pre', 'div'])
        
        for element in candidates:
            if not self._is_code_element(element):
                continue
                
            # Check if this element is a direct child of a list
            parent = element.parent
            if parent and parent.name in ['ol', 'ul']:
                # Find the previous list item sibling
                prev_li = element.find_previous_sibling('li')
                if prev_li:
                    prev_li.append(element.extract())
                    self.logger.debug("Fixed orphaned code block in list")

    def _remove_start_attributes(self, soup: BeautifulSoup) -> None:
        """Remove start attributes from ordered lists that interfere with markdown numbering."""
        for ol in soup.find_all('ol'):
            if ol.has_attr('start'):
                del ol['start']
                self.logger.debug("Removed start attribute from <ol>")

    def _fix_nested_list_nesting(self, soup: BeautifulSoup) -> None:
        """
        Fix lists that are direct children of other lists (invalid HTML).
        They should be nested inside the preceding <li> element.
        """
        # Fix ordered lists
        for ol in soup.find_all('ol'):
            parent = ol.parent
            if parent and parent.name in ['ol', 'ul']:
                # Find the preceding list item
                prev_li = ol.find_previous_sibling('li')
                if prev_li:
                    prev_li.append(ol.extract())
                    self.logger.debug("Fixed nested ordered list structure")

        # Fix unordered lists
        for ul in soup.find_all('ul'):
            parent = ul.parent
            if parent and parent.name in ['ol', 'ul']:
                prev_li = ul.find_previous_sibling('li')
                if prev_li:
                    prev_li.append(ul.extract())
                    self.logger.debug("Fixed nested unordered list structure")


def fix_list_html(html_content: str, logger: logging.Logger = None) -> str:
    """Convenience function to fix HTML list structures."""
    fixer = HtmlListFixer(logger)
    return fixer.fix_html(html_content)
