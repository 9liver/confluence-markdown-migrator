"""Markdown converter orchestrator for high-fidelity HTML to Markdown conversion."""

import html
import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional, List

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter as MarkdownifyConverter

from .html_cleaner import HtmlCleaner
from .html_list_fixer import HtmlListFixer
from .link_processor import LinkProcessor
from .macro_handler import MacroHandler

logger = logging.getLogger('confluence_markdown_migrator.converters.markdownconverter')


class ListTypeMarkers:
    """Helper class for converting numeric indices to list markers (a, b, c, i, ii, etc.)"""
    
    @staticmethod
    def get_alpha_marker(index: int) -> str:
        """Convert 0-based index to lowercase letter (0=a, 1=b, 2=c, etc.)"""
        return chr(ord('a') + index)
    
    @staticmethod
    def get_upper_alpha_marker(index: int) -> str:
        """Convert 0-based index to uppercase letter (0=A, 1=B, 2=C, etc.)"""
        return chr(ord('A') + index)
    
    @staticmethod
    def get_roman_marker(index: int) -> str:
        """Convert 0-based index to lowercase roman numeral (0=i, 1=ii, 2=iii, etc.)"""
        return ListTypeMarkers._int_to_roman(index + 1).lower()
    
    @staticmethod
    def get_upper_roman_marker(index: int) -> str:
        """Convert 0-based index to uppercase roman numeral"""
        return ListTypeMarkers._int_to_roman(index + 1)
    
    @staticmethod
    def _int_to_roman(num: int) -> str:
        """Convert integer to roman numeral"""
        val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
        syms = ["M", "CM", "D", "CD", "C", "XC", "L", "XL", "X", "IX", "V", "IV", "I"]
        
        roman_num = ''
        i = 0
        while num > 0:
            for _ in range(num // val[i]):
                roman_num += syms[i]
                num -= val[i]
            i += 1
        return roman_num


class MarkdownConverter(MarkdownifyConverter):
    """
    Main orchestrator for converting Confluence HTML to high-fidelity Markdown.
    
    This class extends markdownify.MarkdownConverter to provide:
    - Custom handlers for Confluence-specific elements
    - Macro conversion
    - Link/image processing
    - Metadata tracking
    """
    
    def __init__(self, logger: logging.Logger = None, config: Dict[str, Any] = None, **kwargs):
        """Initialize markdown converter with logger and configuration."""
        # Setup converter options
        markdownify_options = {
            'heading_style': 'ATX',  # Use # for headings
            'bullets': '-',  # Use - for unordered lists
            'escape_asterisks': False,
            'escape_underscores': False,
            'wrap': True,
            'wrap_width': 120
        }
        
        # Merge with any additional options from kwargs
        markdownify_options.update(kwargs)
        
        # Initialize markdownify base class with options
        super().__init__(**markdownify_options)
        
        self.logger = logger or logging.getLogger('confluence_markdown_migrator.converters.markdownconverter')
        self.config = config or {}
        
        # Initialize helper components
        self.html_cleaner = HtmlCleaner(self.logger)
        self.list_fixer = HtmlListFixer(self.logger)
        self.macro_handler = MacroHandler(self.logger)
        self.link_processor = None  # Initialized when confluence_base_url is known
        
        # Setup converter config options
        self.target_wiki = self.config.get('target_wiki', 'wikijs')  # 'wikijs', 'bookstack', or 'both'
        self.preserve_html = self.config.get('preserve_html', False)
        self.strict_markdown = self.config.get('strict_markdown', True)
        self.heading_offset = self.config.get('heading_offset', 0)
    
    def convert_page(self, page: Any) -> bool:
        """
        Convert a ConfluencePage from HTML to Markdown with full pipeline.
        
        Args:
            page: ConfluencePage object with HTML content in page.content
            
        Returns:
            bool: True if conversion succeeded, False otherwise
        """
        self.logger.info(f"Converting page {page.id} to markdown")
        
        try:
            # Initialize link processor with base URL
            confluence_base_url = self.config.get('confluence', {}).get('base_url')
            self.link_processor = LinkProcessor(confluence_base_url, self.logger)
            
            # Step 1: Detect format
            format_type = self._detect_format(page.content)
            self.logger.debug(f"Detected format: {format_type}")
            
            # Step 2: Parse HTML
            soup = self._parse_html(page.content)
            
            # Step 2.5: Fix broken list structures (if using HTML mode or if fixing is enabled)
            soup = self._fix_list_structure(soup, format_type)
            
            # Step 3: Clean HTML
            soup = self.html_cleaner.clean(soup, format_type)
            
            # Step 4: Convert macros
            soup, macro_stats, macro_warnings = self.macro_handler.convert(soup, format_type)
            
            # Step 5: Extract links/images for metadata
            link_metadata = self.link_processor.extract_links(soup)
            image_metadata = self.link_processor.extract_images(soup)
            
            # Step 6: Convert to markdown
            raw_markdown = self._convert_to_markdown(soup)
            
            # Step 7: Post-process markdown (stores link_stats on self)
            processed_markdown = self._post_process_markdown(raw_markdown, page)
            
            # Step 8: Update page metadata
            self._update_conversion_metadata(
                page, processed_markdown, macro_stats, macro_warnings,
                link_metadata, image_metadata, format_type
            )
            
            # Set the markdown content
            page.markdown_content = processed_markdown
            
            self.logger.info(f"Page {page.id} conversion successful")
            return True
            
        except Exception as e:
            self.logger.error(f"Conversion failed for page {page.id}: {str(e)}")
            self._update_failed_conversion_metadata(page, str(e))
            return False
    
    def convert_standalone_html(self, html_content: str, format_type: str = 'export') -> str:
        """Convert standalone HTML string to markdown (not part of markdownify pipeline)."""
        self.logger.debug("Converting HTML to markdown")

        soup = self._parse_html(html_content)
        format_type = self._detect_format(html_content) if not format_type else format_type

        # Clean and convert
        soup = self.html_cleaner.clean(soup, format_type)
        soup, _, _ = self.macro_handler.convert(soup, format_type)

        # Convert to markdown
        raw_markdown = self._convert_to_markdown(soup)

        # Apply post-processing (creates a dummy page object for compatibility)
        class DummyPage:
            id = 'standalone'
        processed_markdown = self._post_process_markdown(raw_markdown, DummyPage())

        return processed_markdown
    
    def _detect_format(self, html_content: str) -> str:
        """Detect HTML format (storage or export)."""
        if not html_content:
            return 'export'
        
        # Look for ac:namespace elements (storage format)
        if 'ac:' in html_content or 'ac-' in html_content:
            return 'storage'
        
        # Look for data-macro attributes (export format)
        if 'data-macro-' in html_content:
            return 'export'
        
        # Default to export
        return 'export'
    
    def _parse_html(self, html_content: str) -> BeautifulSoup:
        """Parse HTML content with BeautifulSoup."""
        return BeautifulSoup(html_content, 'lxml')
    
    def _fix_list_structure(self, soup: BeautifulSoup, format_type: str) -> BeautifulSoup:
        """Fix broken list structures in HTML before conversion."""
        self.logger.debug("Fixing HTML list structures")
        
        # Apply list fixing using HtmlListFixer
        fixed_html = self.list_fixer.fix_html(str(soup))
        
        # Parse the fixed HTML back to soup
        return BeautifulSoup(fixed_html, 'lxml')
    
    def _convert_to_markdown(self, soup: BeautifulSoup) -> str:
        """Convert BeautifulSoup to markdown using the subclassed converter."""
        self.logger.debug("Converting to markdown")
        
        # Pre-process the soup to handle special cases
        self._pre_process_html(soup)
        
        # Use the inherited convert method from MarkdownifyConverter
        # This will use our custom convert_* methods
        return super().convert(str(soup))
    
    def _pre_process_html(self, soup: BeautifulSoup) -> None:
        """Pre-process HTML to handle edge cases before markdown conversion."""
        # Find and process code panel divs
        self._process_code_panels(soup)
    
    def _process_code_panels(self, soup: BeautifulSoup) -> None:
        """Process code panel divs to ensure proper code block conversion."""
        for div in soup.find_all('div', class_=True):
            classes = div.get('class', [])
            has_code = any(cls == 'code' for cls in classes)
            has_panel = any(cls == 'panel' or cls == 'pdl' for cls in classes)
            
            if has_code and has_panel:
                # Check if this already has a pre element with proper structure
                pre_elem = div.find('pre')
                if pre_elem and pre_elem.find('code'):
                    # Already properly structured
                    continue
                
                # Ensure the pre element has a code child
                pre_elem = div.find('pre')
                if pre_elem and not pre_elem.find('code'):
                    code_elem = soup.new_tag('code')
                    code_elem.string = pre_elem.get_text()
                    pre_elem.clear()
                    pre_elem.append(code_elem)
    
    def _convert_emoticon(self, img):
        """Convert an emoticon img to !(name) text format."""
        src = img.get('src', '')
        alt = img.get('alt', '')
        
        # Extract emoticon name from src
        emoticon_name = ''
        if src:
            match = re.search(r'/([^/]+)\.(?:svg|png|gif)$', src)
            if match:
                emoticon_name = match.group(1)
        elif alt:
            # Try to extract from alt text like "(smile)"
            match = re.search(r'\(([^)]+)\)', alt)
            if match:
                emoticon_name = match.group(1)
        
        # Use standardized !(name) format
        replacement = f'!({emoticon_name or alt or "emoticon"})'
        img.replace_with(replacement)
    
    def _post_process_markdown(self, markdown: str, page: Any) -> str:
        """Apply post-processing to generated markdown."""
        self.logger.debug("Post-processing markdown")

        link_stats = None

        # Normalize headings
        markdown = self._normalize_headings(markdown)

        # Apply heading offset if configured
        if self.heading_offset != 0:
            markdown = self._apply_heading_offset(markdown, self.heading_offset)

        # Clean up whitespace and formatting
        markdown = self._clean_markdown(markdown)

        # Apply additional normalizations
        markdown = self._normalize_tables(markdown)
        markdown = self._normalize_lists(markdown)
        markdown = self._preserve_code_blocks(markdown)

        # Convert callouts to admonition syntax BEFORE indentation
        if self.target_wiki in ['wikijs', 'both']:
            markdown = self._convert_callouts_to_admonitions(markdown)

        # Indent code blocks that are part of list items
        markdown = self._indent_code_blocks_in_lists(markdown)

        # Final cleanup - remove excessive blank lines
        markdown = self._final_cleanup(markdown)

        # Process links and store stats
        if self.link_processor:
            markdown, link_stats = self.link_processor.process_links(markdown, page)
            self._last_link_stats = link_stats  # Store for later use

        return markdown

    def _final_cleanup(self, markdown: str) -> str:
        """Final cleanup pass - remove excessive blank lines."""
        # Replace 3+ consecutive newlines with 2 newlines
        while '\n\n\n' in markdown:
            markdown = markdown.replace('\n\n\n', '\n\n')

        # Fix sub-list indentation (2 spaces -> 3 spaces for consistency)
        lines = markdown.split('\n')
        result = []
        for line in lines:
            # Check for sub-list items with 2-space indent
            if re.match(r'^  \d+\.\s+', line):
                line = ' ' + line  # Add one more space
            result.append(line)

        return '\n'.join(result)

    def _indent_code_blocks_in_lists(self, markdown: str) -> str:
        """Indent content that follows list items to keep them part of the list."""
        lines = markdown.split('\n')
        result = []
        current_indent = 0
        in_list = False
        in_code_block = False

        i = 0
        while i < len(lines):
            line = lines[i]

            # Track code block state (for non-list context)
            if line.strip().startswith('```') and not in_list:
                in_code_block = not in_code_block

            # Check if this is a list item
            list_match = re.match(r'^(\s*)([-*]|\d+\.)\s+', line)
            if list_match:
                in_list = True
                indent_spaces = len(list_match.group(1))
                # Calculate indent for content under this list item
                current_indent = indent_spaces + 3
                result.append(line)
                i += 1
                continue

            # If we're in a list context, indent various content types
            if in_list and current_indent > 0 and not in_code_block:
                indent = ' ' * current_indent
                stripped = line.strip()

                # Check if this line should end the list context
                if stripped and not stripped.startswith('>') and not stripped.startswith('```') and not stripped.startswith('**'):
                    # Check if it's a new top-level list item or non-list content
                    if re.match(r'^\d+\.\s+', stripped) and not line.startswith(' '):
                        # New top-level list item
                        in_list = False
                        current_indent = 0
                        result.append(line)
                        i += 1
                        continue

                # Handle code blocks
                if stripped.startswith('```'):
                    # Add blank line before if needed
                    if result and result[-1].strip():
                        result.append('')

                    # Indent the opening fence
                    result.append(indent + stripped)
                    i += 1

                    # Indent all lines until closing fence
                    while i < len(lines):
                        code_line = lines[i]
                        if code_line.strip().startswith('```'):
                            result.append(indent + code_line.strip())
                            i += 1
                            break
                        else:
                            result.append(indent + code_line)
                            i += 1
                    continue

                # Handle blockquotes
                elif stripped.startswith('>'):
                    # Indent blockquote
                    if result and result[-1].strip():
                        result.append('')
                    result.append(indent + stripped)
                    i += 1

                    # Continue indenting blockquote lines
                    while i < len(lines) and lines[i].strip().startswith('>'):
                        result.append(indent + lines[i].strip())
                        i += 1
                    continue

                # Handle bold titles (like **~/.profile**)
                elif stripped.startswith('**') and stripped.endswith('**'):
                    if result and result[-1].strip():
                        result.append('')
                    result.append(indent + stripped)
                    i += 1
                    continue

                # Empty lines - keep them but don't break list context yet
                elif not stripped:
                    result.append('')
                    i += 1
                    continue

            result.append(line)
            i += 1

        return '\n'.join(result)
    
    def _normalize_headings(self, markdown: str) -> str:
        """Ensure proper heading hierarchy starting from H1."""
        import re
        lines = markdown.split('\n')
        min_heading_level = None
        
        # Find the minimum heading level (smallest # count, but > 0)
        for line in lines:
            if line.startswith('#'):
                level = len(line) - len(line.lstrip('#'))
                if min_heading_level is None or level < min_heading_level:
                    min_heading_level = level
        
        # Adjust to start from H1 if minimum is > 1
        if min_heading_level is not None and min_heading_level > 1:
            adjustment = 1 - min_heading_level
            markdown = self._apply_heading_offset(markdown, adjustment)
        
        return markdown
    
    def _apply_heading_offset(self, markdown: str, offset: int) -> str:
        """Apply offset to all heading levels."""
        import re
        def replace_heading(match):
            heading_mark = match.group(1)
            level = len(heading_mark)
            new_level = max(1, min(6, level + offset))  # Keep within H1-H6
            return '#' * new_level + match.group(2)
        
        heading_pattern = re.compile(r'^(#+)(\s+.*)$', re.MULTILINE)
        return heading_pattern.sub(replace_heading, markdown)
    
    def _clean_markdown(self, markdown: str) -> str:
        """Clean up markdown formatting issues."""
        # Decode HTML entities (e.g., &amp; -> &, &lt; -> <)
        markdown = html.unescape(markdown)

        # Remove trailing whitespace from lines
        lines = [line.rstrip() for line in markdown.split('\n')]

        # Reduce multiple consecutive blank/empty lines
        cleaned_lines = []
        blank_count = 0

        for line in lines:
            # Check if line is empty or just a blockquote marker
            stripped = line.strip()
            is_blank = stripped == '' or stripped == '>'

            if is_blank:
                blank_count += 1
                # Only keep first empty line in a sequence
                if blank_count == 1:
                    # Preserve blockquote continuation if previous line was blockquote
                    if cleaned_lines and cleaned_lines[-1].strip().startswith('>'):
                        if stripped == '>':
                            cleaned_lines.append('>')
                        else:
                            cleaned_lines.append('')
                    else:
                        cleaned_lines.append(line)
            else:
                blank_count = 0
                cleaned_lines.append(line)

        # Final pass: remove consecutive empty blockquote lines
        final_lines = []
        for i, line in enumerate(cleaned_lines):
            if line.strip() == '>':
                # Skip if previous line was also empty blockquote
                if final_lines and final_lines[-1].strip() == '>':
                    continue
            final_lines.append(line)

        markdown = '\n'.join(final_lines)

        # Aggressive cleanup of empty blockquote sequences
        # Replace multiple empty blockquote lines with single one
        markdown = re.sub(r'(>\s*\n){2,}', '>\n', markdown)
        # Remove empty lines at start of blockquotes (after > {.is-xxx})
        markdown = re.sub(r'(> \{\.is-\w+\}\n)(>\s*\n)+', r'\1', markdown)
        # Remove empty lines before content in blockquotes
        markdown = re.sub(r'(>\s*\n)+(> [^>\s])', r'\1\2', markdown)

        # Ensure single trailing newline
        markdown = markdown.rstrip() + '\n'

        return markdown
    
    def _convert_callouts_to_admonitions(self, markdown: str) -> str:
        """Convert blockquotes with callout markers to admonition syntax."""
        import re
        
        # Enhanced pattern to match blockquotes with callout class markers OR data-callout attributes
        pattern = re.compile(
            r'(> \{\.is-(info|warning|success|danger)\}\n)?'  # Optional class marker
            r'(> \[data-callout=(info|warning|success|danger)\]\n)?'  # Optional data attribute marker
            r'> \*\*([^*]+)\*\*\n'  # Title line
            r'(>\n)*'  # Optional empty blockquote lines
            r'((?:> [^>].*\n?)*)'  # Content lines (non-greedy)
        )
        
        def replace_admonition(match):
            # Determine callout type (from class, data attribute, or infer from title)
            callout_type = match.group(2) or match.group(4)
            title = match.group(5)
            content = match.group(7) or ''
            
            # Map title to callout type if not already set
            if not callout_type:
                title_lower = title.lower()
                if 'info' in title_lower or 'information' in title_lower:
                    callout_type = 'info'
                elif 'warn' in title_lower:
                    callout_type = 'warning'
                elif 'tip' in title_lower or 'success' in title_lower:
                    callout_type = 'info'  # Wiki.js uses [!info] for tips
                else:
                    callout_type = 'info'
            
            # Map to Wiki.js admonition syntax
            admonition_map = {
                'info': '[!info]',
                'warning': '[!warning]',
                'success': '[!info]',  # Wiki.js doesn't have success, use info
                'danger': '[!warning]'  # Wiki.js doesn't have danger, use warning
            }
            
            admon_type = admonition_map.get(callout_type, '[!info]')
            
            # Format the admonition
            result = f"> {admon_type} {title}\n"
            if content:
                # Add content lines, ensuring they're properly prefixed
                content_lines = content.split('\n')
                for line in content_lines:
                    if line.strip():
                        result += f"> {line[2:]}\n"  # Remove '> ' prefix and re-add
                    else:
                        result += ">\n"
            
            return result + "\n"
        
        # Apply the transformation
        return pattern.sub(replace_admonition, markdown)

    def _convert_blockquote_to_admonition(self, el) -> str:
        """Convert blockquote element to admonition syntax during HTML conversion."""
        callout_type = el.get('data-callout', '')
        
        if not callout_type:
            # Fall back to class-based detection
            classes = el.get('class', [])
            for cls in classes:
                if cls.startswith('is-'):
                    callout_type = cls[3:]  # Remove 'is-' prefix
                    break
        
        # Extract content
        content = self._get_text_content(el)
        lines = content.split('\n')
        
        # Extract title (first bold line)
        title = "Info"  # Default
        content_start = 0
        
        for i, line in enumerate(lines):
            if line.strip().startswith('**') and line.strip().endswith('**'):
                title = line.strip().strip('*')
                content_start = i + 1
                break
        
        # Get remaining content
        body_content = '\n'.join(lines[content_start:]).strip()
        
        if callout_type:
            # Use Wiki.js admonition syntax
            admon_map = {
                'info': '[!info]',
                'warning': '[!warning]',
                'success': '[!info]',
                'danger': '[!warning]'
            }
            admon_type = admon_map.get(callout_type, '[!info]')
            
            result = f"> {admon_type} {title}\n"
            if body_content:
                result += f">\n"
                for line in body_content.split('\n'):
                    if line.strip():
                        result += f"> {line}\n"
                    else:
                        result += ">\n"
            return result + '\n'
        else:
            # Regular blockquote
            result = ''
            for line in lines:
                if line.strip():
                    result += f"> {line}\n"
                else:
                    result += ">\n"
            return result + '\n'

    def _get_text_content(self, el):
        """Extract text content from element, preserving some structure."""
        from bs4 import BeautifulSoup
        
        # Use markdownify to convert to markdown, but customize for our needs
        text = ''
        for child in el.children:
            if hasattr(child, 'name') and child.name:
                if child.name == 'p':
                    text += child.get_text() + '\n'
                elif child.name == 'br':
                    text += '\n'
                elif child.name in ['strong', 'b']:
                    text += f"**{child.get_text()}**"
                elif child.name in ['em', 'i']:
                    text += f"*{child.get_text()}*"
                else:
                    text += child.get_text()
            else:
                text += str(child)
        return text.strip()
    
    def _update_conversion_metadata(self, page: Any, markdown: str, macro_stats: Dict[str, Any],
                                   macro_warnings: List[str], link_metadata: List[Dict],
                                   image_metadata: List[Dict], format_type: str) -> None:
        """Update page conversion metadata with conversion statistics."""
        # Initialize if not exists
        if not hasattr(page, 'conversion_metadata') or not page.conversion_metadata:
            page.conversion_metadata = {}
        
        # Use link_stats from _last_link_stats if available
        link_stats = getattr(self, '_last_link_stats', None)
        if link_stats:
            links_internal = link_stats.get('links_internal', 0)
            links_external = link_stats.get('links_external', 0)
            links_attachment = link_stats.get('links_attachment', 0)
            images_count = link_stats.get('images_count', 0)
            images_with_alt = link_stats.get('images_with_alt', 0)
            images_with_attachment = link_stats.get('images_with_attachment', 0)
            broken_links = link_stats.get('broken_links', [])
        else:
            # Fallback to original logic
            links_internal = sum(1 for link in link_metadata if link.get('is_internal'))
            links_external = sum(1 for link in link_metadata if not link.get('is_internal'))
            links_attachment = 0
            images_count = len(image_metadata)
            images_with_alt = sum(1 for img in image_metadata if img.get('alt'))
            images_with_attachment = 0
            broken_links = []
        
        # Update conversion metadata
        page.conversion_metadata.update({
            'conversion_status': 'success' if not macro_warnings else 'partial',
            'macros_found': macro_stats.get('macros_found', 0),
            'macros_converted': macro_stats.get('macros_converted', 0),
            'macros_failed': macro_stats.get('macros_failed', []),
            'links_internal': links_internal,
            'links_external': links_external,
            'links_attachment': links_attachment,
            'images_count': images_count,
            'images_with_alt': images_with_alt,
            'images_with_attachment': images_with_attachment,
            'broken_links': broken_links,
            'conversion_warnings': macro_warnings,
            'conversion_timestamp': datetime.utcnow().isoformat(),
            'format_detected': format_type,
        })
    
    def _update_failed_conversion_metadata(self, page: Any, error_message: str) -> None:
        """Update metadata for failed conversions."""
        if not hasattr(page, 'conversion_metadata') or not page.conversion_metadata:
            page.conversion_metadata = {}
        
        page.conversion_metadata.update({
            'conversion_status': 'failed',
            'conversion_error': error_message,
            'conversion_timestamp': datetime.utcnow().isoformat()
        })
    
    def _normalize_tables(self, markdown: str) -> str:
        """Normalize table formatting for consistent markdown syntax."""
        import re
        
        # Pattern to match markdown tables
        table_pattern = re.compile(
            r'(\|.*\|\n\|\s*-{3,}\s*\|.*\|\n(?:\|.*\|\n)*)',
            re.MULTILINE
        )
        
        def normalize_table(match):
            table_text = match.group(1)
            lines = table_text.strip().split('\n')
            normalized_lines = []
            
            for line in lines:
                # Ensure consistent spacing around pipes
                line = re.sub(r'\s*\|\s*', ' | ', line)
                line = line.strip()
                normalized_lines.append(line)
            
            return '\n'.join(normalized_lines) + '\n\n'
        
        return table_pattern.sub(normalize_table, markdown)
    
    def _normalize_lists(self, markdown: str) -> str:
        """Normalize list indentation and bullet characters."""
        lines = markdown.split('\n')
        normalized_lines = []
        list_stack = []  # Track nested list levels
        
        for line in lines:
            # Check if this is a list item
            list_match = re.match(r'(\s*)([-*+]|[0-9]+\.)\s+(.*)', line)
            if list_match:
                indent = len(list_match.group(1))
                bullet = list_match.group(2)
                content = list_match.group(3)
                
                # Normalize bullet to '-' for unordered, keep numbers for ordered
                if bullet in ['*', '+']:
                    bullet = '-'
                
                # Ensure proper indentation (2 spaces per level)
                level = indent // 2
                normalized_indent = '  ' * level
                
                normalized_line = f"{normalized_indent}{bullet} {content}"
                normalized_lines.append(normalized_line)
            else:
                normalized_lines.append(line)
        
        return '\n'.join(normalized_lines)
    
    def _preserve_code_blocks(self, markdown: str) -> str:
        """Ensure code blocks are not broken by whitespace cleanup."""
        import re
        
        # Pattern to match fenced code blocks
        code_block_pattern = re.compile(
            r'(```[a-zA-Z]*\n.*?\n```)',
            re.MULTILINE | re.DOTALL
        )
        
        def preserve_block(match):
            block = match.group(1)
            # Ensure consistent fencing and no extra whitespace inside
            lines = block.split('\n')
            if len(lines) >= 3:
                # Extract language from opening fence
                opening = lines[0].strip()
                language = opening[3:].strip() if len(opening) > 3 else ''
                
                # Reconstruct with clean formatting
                code_content = '\n'.join(lines[1:-1])
                return f"```{language}\n{code_content}\n```\n\n"
            return block
        
        return code_block_pattern.sub(preserve_block, markdown)
    
    # Custom markdownify converters
    def _get_cell_text(self, cell):
        """Extract text from a table cell, preserving line breaks and formatting code blocks."""
        from bs4 import NavigableString, Tag

        # Check for cell highlighting (Confluence colored cells)
        highlight_color = cell.get('data-highlight-colour', '')
        cell_classes = cell.get('class', [])

        # Build text by processing cell contents
        parts = []

        def process_element(element):
            """Recursively process element and its children."""
            if isinstance(element, NavigableString):
                text = str(element)
                # Preserve meaningful whitespace but normalize excessive spaces
                text = re.sub(r'[ \t]+', ' ', text)
                if text.strip():
                    return text.strip()
                return ''

            if not isinstance(element, Tag):
                return ''

            # Handle <pre> tags - convert to inline code, preserve <br> tags
            if element.name == 'pre':
                code_parts = []
                for child in element.children:
                    if isinstance(child, NavigableString):
                        text = str(child)
                        # Convert actual newlines to <br> markers
                        text = text.replace('\n', '<br>')
                        code_parts.append(text)
                    elif isinstance(child, Tag) and child.name == 'br':
                        code_parts.append('<br>')
                    elif isinstance(child, Tag) and child.name == 'a':
                        # Preserve link text in pre blocks
                        code_parts.append(child.get_text())
                    elif isinstance(child, Tag):
                        text = child.get_text()
                        text = text.replace('\n', '<br>')
                        code_parts.append(text)

                # Join all parts
                full_text = ''.join(code_parts)

                # Clean up: normalize multiple <br> and trim
                full_text = re.sub(r'(<br>)+', '<br>', full_text)
                full_text = full_text.strip()
                full_text = re.sub(r'^<br>|<br>$', '', full_text)

                if not full_text:
                    return ''

                # Split by <br> to get lines - use rstrip to preserve indentation
                code_lines = [line.rstrip() for line in full_text.split('<br>')]
                code_lines = [line for line in code_lines if line.strip()]  # Remove empty lines

                if len(code_lines) == 1:
                    # Single line - use inline code
                    return f'`{code_lines[0]}`'
                else:
                    # Multi-line - join with <br> for table cell
                    return '`' + '`<br>`'.join(code_lines) + '`'

            # Handle <code> tags - preserve <br> tags and original formatting
            if element.name == 'code':
                code_parts = []
                for child in element.children:
                    if isinstance(child, NavigableString):
                        # Preserve the original text including spaces
                        text = str(child)
                        # Convert actual newlines to <br> markers
                        text = text.replace('\n', '<br>')
                        code_parts.append(text)
                    elif isinstance(child, Tag) and child.name == 'br':
                        code_parts.append('<br>')
                    elif isinstance(child, Tag):
                        # Get text from nested elements, preserve newlines
                        text = child.get_text()
                        text = text.replace('\n', '<br>')
                        code_parts.append(text)

                # Join all parts
                full_text = ''.join(code_parts)

                # Clean up: normalize multiple <br> and trim
                full_text = re.sub(r'(<br>)+', '<br>', full_text)
                full_text = full_text.strip()
                full_text = re.sub(r'^<br>|<br>$', '', full_text)

                if not full_text:
                    return ''

                # Split by <br> to get lines - use rstrip to preserve indentation
                lines = [line.rstrip() for line in full_text.split('<br>')]
                lines = [line for line in lines if line.strip()]  # Remove empty lines

                if len(lines) == 1:
                    return f'`{lines[0]}`'
                else:
                    # Multi-line code in table cell - each line as inline code with <br>
                    return '`' + '`<br>`'.join(lines) + '`'

            # Handle <br> tags
            if element.name == 'br':
                return '<br>'

            # Handle links
            if element.name == 'a':
                href = element.get('href', '')
                link_text = element.get_text().strip()
                if href:
                    # Truncate very long URLs for table readability
                    if len(href) > 60:
                        return f'[{link_text or "link"}]({href[:57]}...)'
                    return f'[{link_text or href}]({href})'
                return link_text

            # Handle <p> tags - add line break after
            if element.name == 'p':
                inner_parts = []
                for child in element.children:
                    result = process_element(child)
                    if result:
                        inner_parts.append(result)
                text = ' '.join(inner_parts)
                return text + '<br>' if text else ''

            # Handle lists inside cells
            if element.name in ['ul', 'ol']:
                list_items = []
                for li in element.find_all('li', recursive=False):
                    item_text = li.get_text().strip()
                    if item_text:
                        list_items.append(f'• {item_text}')
                return '<br>'.join(list_items)

            # Handle other elements - just get text from children
            if element.name in ['span', 'strong', 'em', 'b', 'i', 'div']:
                inner_parts = []
                for child in element.children:
                    result = process_element(child)
                    if result:
                        inner_parts.append(result)
                text = ' '.join(inner_parts)

                # Apply formatting
                if element.name in ['strong', 'b']:
                    return f'**{text}**' if text else ''
                if element.name in ['em', 'i']:
                    return f'*{text}*' if text else ''
                return text

            return ''

        # Process all direct children
        for child in cell.children:
            result = process_element(child)
            if result:
                parts.append(result)

        # Join parts
        text = ' '.join(parts)

        # Clean up multiple spaces and normalize <br> tags
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\s*<br>\s*', '<br>', text)
        text = re.sub(r'(<br>)+', '<br>', text)  # Collapse multiple <br>
        text = text.strip()
        text = text.strip('<br>')  # Remove leading/trailing <br>

        # Escape pipe characters that would break table formatting
        text = text.replace('|', '\\|')

        # Add indicator for highlighted cells (e.g., green = done)
        if highlight_color == 'green' or 'highlight-green' in ' '.join(cell_classes):
            # If cell just says "DONE", make it bold
            if text.upper().strip() == 'DONE':
                text = '**DONE** ✓'
            elif not text:
                text = '✓'
        elif highlight_color == 'red' or 'highlight-red' in ' '.join(cell_classes):
            if not text:
                text = '✗'
        elif highlight_color == 'yellow' or 'highlight-yellow' in ' '.join(cell_classes):
            if not text:
                text = '⚠'

        return text

    def convert_table(self, el, text, parent_tags=None, **kwargs):
        """Custom table converter to ensure proper markdown table syntax."""
        from bs4 import BeautifulSoup

        rows = el.find_all('tr')
        if not rows:
            return ''

        # Extract header if present
        header_cells = rows[0].find_all(['th', 'td'])
        if not header_cells:
            return ''

        # Build table
        markdown_rows = []

        # Header row
        header_row = '| ' + ' | '.join(self._get_cell_text(cell) for cell in header_cells) + ' |'
        markdown_rows.append(header_row)

        # Separator row
        separator = '| ' + ' | '.join('---' for _ in header_cells) + ' |'
        markdown_rows.append(separator)

        # Data rows
        for row in rows[1:]:
            cells = row.find_all(['td', 'th'])
            if cells:
                data_row = '| ' + ' | '.join(self._get_cell_text(cell) for cell in cells) + ' |'
                markdown_rows.append(data_row)

        result = '\n'.join(markdown_rows) + '\n\n'
        return result
    
    def convert_ol(self, el, text, parent_tags=None, **kwargs):
        """Handle ordered lists."""
        # Ensure proper spacing before and after lists
        return '\n' + text + '\n'

    def convert_ul(self, el, text, parent_tags=None, **kwargs):
        """Handle unordered lists."""
        # Ensure proper spacing before and after lists
        return '\n' + text + '\n'

    def convert_li(self, el, text, parent_tags=None, **kwargs):
        """Handle list items with proper nesting."""
        parent = el.parent
        if not parent:
            return text

        # Determine nesting level by counting parent list elements
        depth = 0
        ancestor = el.parent
        while ancestor:
            if ancestor.name in ['ol', 'ul']:
                depth += 1
            ancestor = ancestor.parent
        depth = max(0, depth - 1)  # Subtract 1 because we start from immediate parent

        # Get item index within this list
        siblings = [child for child in parent.children if hasattr(child, 'name') and child.name == 'li']
        try:
            index = siblings.index(el)
        except ValueError:
            index = 0

        # Use 3 spaces per indentation level (standard for nested lists)
        indent = '   ' * depth

        # Determine bullet/number style
        if parent.name == 'ol':
            # Check for custom list type (alpha, roman, etc.)
            list_type = parent.get('data-list-type')
            if list_type:
                # Use custom markers based on type
                markers = ListTypeMarkers()
                if list_type == 'lower-alpha':
                    bullet = f'{markers.get_alpha_marker(index)}.'
                elif list_type == 'upper-alpha':
                    bullet = f'{markers.get_upper_alpha_marker(index)}.'
                elif list_type == 'lower-roman':
                    bullet = f'{markers.get_roman_marker(index)}.'
                elif list_type == 'upper-roman':
                    bullet = f'{markers.get_upper_roman_marker(index)}.'
                else:
                    bullet = f'{index + 1}.'
            else:
                bullet = f'{index + 1}.'
        else:
            bullet = '-'

        # Clean up text - preserve internal newlines for nested content
        text = text.strip()

        # Handle nested lists - they should appear on new lines with proper indentation
        # Check if this li contains nested lists
        has_nested_list = el.find(['ol', 'ul'])
        if has_nested_list:
            # For items with nested lists, we need to combine the content properly
            # The format is typically: "Text content\n\nnested list\n\n"
            # We want to keep the text content as the list item label
            # and preserve the nested list with its own formatting
            
            # Split into lines and filter out empty lines that separate the content
            lines = text.split('\n')
            result_lines = []
            content_added = False
            
            for i, line in enumerate(lines):
                is_empty = not line.strip()
                is_list_marker = re.match(r'^\s*\d+\.', line) or re.match(r'^\s*[a-z]\.', line, re.IGNORECASE)
                
                if not content_added:
                    # This is the main content of the list item (before the nested list)
                    if is_empty:
                        # Skip empty lines between content and nested list
                        continue
                    elif is_list_marker:
                        # We've reached the nested list, add the main content bullet
                        if result_lines:
                            # Combine the accumulated content lines
                            content = ' '.join(result_lines)
                            line_with_bullet = f'{indent}{bullet} {content}'
                        else:
                            # Empty content
                            line_with_bullet = f'{indent}{bullet} '
                        
                        final_lines = [line_with_bullet]
                        # Add the remaining lines (the nested list)
                        final_lines.extend(lines[i:])
                        return '\n'.join(final_lines) + '\n'
                    else:
                        # Accumulate content lines
                        result_lines.append(line)
                
            # If we get here without finding nested list markers, just use standard formatting
            content = ' '.join(result_lines) if result_lines else ''
            return f'{indent}{bullet} {content}\n{text}\n'
        else:
            return f'{indent}{bullet} {text}\n'

    def convert_blockquote(self, el, text, parent_tags=None, **kwargs):
        """Handle blockquotes, with special handling for callouts that should become admonitions."""
        # Check for callout markers
        callout_type = el.get('data-callout', '')
        
        if not callout_type:
            # Check for callout classes as fallback
            classes = el.get('class', [])
            for cls in classes:
                if cls.startswith('is-'):
                    callout_type = cls[3:]  # Remove 'is-' prefix
                    break
        
        # If this is a callout, use the special admonition converter
        if callout_type:
            return self._convert_blockquote_to_admonition(el)
        
        # Regular blockquote processing
        text = text.strip()
        if not text:
            return ''

        # Add > prefix to each line
        lines = text.split('\n')
        quoted_lines = []
        for line in lines:
            if line.startswith('>'):
                quoted_lines.append(line)
            else:
                quoted_lines.append(f'> {line}' if line.strip() else '>')

        return '\n'.join(quoted_lines) + '\n\n'

    def convert_span(self, el, text, parent_tags=None, **kwargs):
        """Handle span elements, including Confluence anchors."""
        classes = el.get('class', [])

        # Check for Confluence anchor links
        if 'confluence-anchor-link' in classes:
            anchor_id = el.get('id', '')
            if anchor_id:
                # Return an HTML anchor that works in markdown
                return f'<a id="{anchor_id}"></a>'
            return ''

        # For other spans, just return the text content
        return text

    def convert_pre(self, el, text, parent_tags=None, **kwargs):
        """Handle pre elements, especially for code blocks."""
        # Check for syntaxhighlighter params
        params = el.get('data-syntaxhighlighter-params', '')
        if params:
            language = self._parse_syntaxhighlighter_language(params)
            if language:
                return f"```{language}\n{text.strip()}\n```\n\n"

        # Check for code child element
        code_el = el.find('code')
        if code_el:
            language = self._extract_code_language(code_el)
            code_text = code_el.get_text()
            if language and language != 'text':
                return f"```{language}\n{code_text.strip()}\n```\n\n"
            return f"```\n{code_text.strip()}\n```\n\n"

        # Plain pre without code element
        return f"```\n{text.strip()}\n```\n\n"
    
    def convert_div(self, el, text, parent_tags=None, **kwargs):
        """Handle div elements, with special handling for code panels."""
        classes = el.get('class', [])
        
        # Check if this is a code panel (has both 'code' and 'panel' classes)
        has_code = any(cls == 'code' for cls in classes)
        has_panel = any(cls == 'panel' or cls == 'pdl' for cls in classes)
        
        if has_code and has_panel:
            # This is a Confluence code panel
            # Try to extract language and code
            language = ''
            code_text = ''
            
            # Try to find pre element with syntaxhighlighter
            pre_elem = el.find('pre')
            if pre_elem:
                params = pre_elem.get('data-syntaxhighlighter-params', '')
                if params:
                    language = self._parse_syntaxhighlighter_language(params)
                code_text = pre_elem.get_text()
            else:
                # Try codeContent div
                code_content = el.find(class_='codeContent')
                if code_content:
                    code_text = code_content.get_text()
            
            # Try to extract title from panelHeader
            title = ''
            panel_header = el.find(class_='panelHeader')
            if not panel_header:
                panel_header = el.find(class_='codeHeader')
            if panel_header:
                title = panel_header.get_text(strip=True)
            
            # Format the code block
            fenced_code = f"```{language}\n{code_text.strip()}\n```\n\n"
            if title:
                return f"**{title}**\n\n{fenced_code}"
            return fenced_code
        
        # Process emoticons in the div
        if el.find('img', class_='emoticon'):
            soup = BeautifulSoup('', 'lxml')
            # Copy the div and process emoticons
            div_copy = BeautifulSoup(str(el), 'lxml').find('div')
            self._process_emoticons(div_copy)
            text = self._get_text_content(div_copy)
            return text + '\n\n'
        
        # Regular div - return text content
        return text + '\n\n' if text.strip() else ''
    
    def _process_emoticons(self, element):
        """Convert emoticon img tags to text equivalents."""
        from bs4 import BeautifulSoup
        import re
        
        for img in element.find_all('img', class_='emoticon'):
            src = img.get('src', '')
            alt = img.get('alt', '')
            
            # Extract emoticon name from src URL
            emoticon_name = ''
            if src:
                match = re.search(r'/([^/]+)\.(?:svg|png|gif)$', src)
                if match:
                    emoticon_name = match.group(1)
            
            # Common emoticon mappings
            emoticon_map = {
                'smile': '😊',
                'sad': '😢',
                'wink': '😉',
                'laugh': '😄',
                'cheeky': '😏',
                'grin': '😁',
                'wondering': '🤔',
                'cool': '😎',
                'cry': '😭',
                'information': 'ℹ️',
                'warning': '⚠️',
                'error': '❌',
                'tick': '✅',
                'cross': '❌',
                'lightbulb-on': '💡',
                'lightbulb': '💡',
                'star': '⭐',
            }
            
            replacement = emoticon_map.get(emoticon_name, alt or f':{emoticon_name}:')
            img.replace_with(replacement)

    def convert_code(self, el, text, parent_tags=None, **kwargs):
        """Handle inline code and code blocks."""
        # Check if this is a code block (inside pre) or inline code
        parent = el.parent
        if parent and parent.name == 'pre':
            # This will be handled by convert_pre, just return the text
            return text

        # Inline code - just wrap in backticks
        return f"`{text}`"
    
    def convert_img(self, el, text, parent_tags=None, **kwargs):
        """Handle images."""
        src = el.get('src', '')
        alt = el.get('alt', '')
        title = el.get('title', '')
        
        # Use title as alt if alt is missing
        if not alt and title:
            alt = title
        
        return f'![{alt}]({src})'
    
    def _extract_code_language(self, element) -> str:
        """Extract programming language from code element."""
        # Check class attribute for language hints
        classes = element.get('class', [])
        for cls in classes:
            if str(cls).startswith('language-'):
                return str(cls).replace('language-', '')
            if str(cls).startswith('lang-'):
                return str(cls).replace('lang-', '')

        # Check data-language attribute
        lang = element.get('data-language')
        if lang:
            return lang

        # Check parent pre element for syntaxhighlighter params
        parent = element.parent
        if parent and parent.name == 'pre':
            params = parent.get('data-syntaxhighlighter-params', '')
            if params:
                lang = self._parse_syntaxhighlighter_language(params)
                if lang:
                    return lang

        # Check element itself for syntaxhighlighter params
        params = element.get('data-syntaxhighlighter-params', '')
        if params:
            lang = self._parse_syntaxhighlighter_language(params)
            if lang:
                return lang

        # Common language class patterns
        language_map = {
            'python': 'python',
            'javascript': 'javascript',
            'java': 'java',
            'bash': 'bash',
            'shell': 'bash',
            'sql': 'sql',
            'yaml': 'yaml',
            'yml': 'yaml',
            'json': 'json',
            'xml': 'xml',
            'html': 'html',
            'css': 'css'
        }

        for cls in classes:
            if str(cls) in language_map:
                return language_map[str(cls)]

        return 'text'  # Default fallback

    def _parse_syntaxhighlighter_language(self, params: str) -> str:
        """Parse language from syntaxhighlighter params string."""
        for param in params.split(';'):
            param = param.strip()
            if param.startswith('brush:'):
                language = param.replace('brush:', '').strip()
                # Map common Confluence language names
                language_map = {
                    'bash': 'bash',
                    'shell': 'bash',
                    'sh': 'bash',
                    'python': 'python',
                    'py': 'python',
                    'javascript': 'javascript',
                    'js': 'javascript',
                    'java': 'java',
                    'sql': 'sql',
                    'xml': 'xml',
                    'html': 'html',
                    'css': 'css',
                    'json': 'json',
                    'yaml': 'yaml',
                    'yml': 'yaml',
                    'text': 'text',
                    'plain': 'text',
                }
                return language_map.get(language.lower(), language)
        return ''