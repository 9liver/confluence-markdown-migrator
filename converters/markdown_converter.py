"""Markdown converter orchestrator for high-fidelity HTML to Markdown conversion."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional, List

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter as MarkdownifyConverter

from .html_cleaner import HtmlCleaner
from .link_processor import LinkProcessor
from .macro_handler import MacroHandler

logger = logging.getLogger('confluence_markdown_migrator.converters.markdownconverter')


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
    
    def convert_html(self, html_content: str, format_type: str = 'export') -> str:
        """Convert raw HTML string to markdown."""
        self.logger.debug("Converting HTML to markdown")
        
        soup = self._parse_html(html_content)
        format_type = self._detect_format(html_content) if not format_type else format_type
        
        # Clean and convert
        soup = self.html_cleaner.clean(soup, format_type)
        soup, _, _ = self.macro_handler.convert(soup, format_type)
        
        return self._convert_to_markdown(soup)
    
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
    
    def _convert_to_markdown(self, soup: BeautifulSoup) -> str:
        """Convert BeautifulSoup to markdown using the subclassed converter."""
        self.logger.debug("Converting to markdown")
        
        # Use the inherited convert method from MarkdownifyConverter
        # This will use our custom convert_* methods
        return super().convert(str(soup))
    
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
        
        # Process links and store stats
        if self.link_processor:
            markdown, link_stats = self.link_processor.process_links(markdown, page)
            self._last_link_stats = link_stats  # Store for later use
        
        # Convert callouts to admonition syntax if needed
        if self.target_wiki in ['wikijs', 'both']:
            markdown = self._convert_callouts_to_admonitions(markdown)
        
        return markdown
    
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
        # Remove trailing whitespace from lines
        lines = [line.rstrip() for line in markdown.split('\n')]
        
        # Reduce multiple consecutive blank lines (max 2)
        cleaned_lines = []
        blank_count = 0
        
        for line in lines:
            if line.strip() == '':
                blank_count += 1
                if blank_count <= 2:  # Keep max 2 consecutive blank lines
                    cleaned_lines.append('')
            else:
                blank_count = 0
                cleaned_lines.append(line)
        
        # Ensure single trailing newline
        markdown = '\n'.join(cleaned_lines).rstrip() + '\n'
        
        return markdown
    
    def _convert_callouts_to_admonitions(self, markdown: str) -> str:
        """Convert blockquote callouts to Wiki.js admonition syntax."""
        import re
        lines = markdown.split('\n')
        result = []
        
        for line in lines:
            # Check if line is a blockquote with callout class
            if re.match(r'> \{\.is-(info|warning|success|danger)\}', line):
                callout_match = re.match(r'> \{\.is-(info|warning|success|danger)\}', line)
                callout_type = callout_match.group(1)
                
                # Map to Wiki.js admonition types
                admonition_types = {
                    'info': 'INFO',
                    'warning': 'WARNING',
                    'success': 'SUCCESS',
                    'danger': 'DANGER'
                }
                wiki_type = admonition_types.get(callout_type, 'NOTE')
                result.append(f"> [!{wiki_type}]")
            else:
                result.append(line)
        
        return '\n'.join(result)
    
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
    def convert_table(self, el, text, convert_as_inline):
        """Custom table converter to ensure proper markdown table syntax."""
        from bs4 import BeautifulSoup
        if convert_as_inline:
            return text
        
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
        header_row = '| ' + ' | '.join(cell.get_text(strip=True) for cell in header_cells) + ' |'
        markdown_rows.append(header_row)
        
        # Separator row
        separator = '| ' + ' | '.join('---' for _ in header_cells) + ' |'
        markdown_rows.append(separator)
        
        # Data rows
        for row in rows[1:]:
            cells = row.find_all('td')
            if cells:
                data_row = '| ' + ' | '.join(cell.get_text(strip=True) for cell in cells) + ' |'
                markdown_rows.append(data_row)
        
        result = '\\n'.join(markdown_rows) + '\\n\\n'
        return result
    
    def convert_blockquote(self, el, text, convert_as_inline):
        """Handle blockquotes, check for callout classes."""
        if convert_as_inline:
            return text
        
        # Check for callout classes
        classes = el.get('class', [])
        for cls in classes:
            if cls.startswith('is-'):
                callout_type = cls.replace('is-', '')
                return f'> {{.{cls}}}\\n' + super().convert_blockquote(el, text, convert_as_inline)
        
        return super().convert_blockquote(el, text, convert_as_inline)
    
    def convert_code(self, el, text, convert_as_inline):
        """Handle inline code and code blocks."""
        language = self._extract_code_language(el)
        if language and not convert_as_inline:
            return f"```{language}\\n{text.strip()}\\n```\\n\\n"
        return f"`{text}`"
    
    def convert_img(self, el, text, convert_as_inline):
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