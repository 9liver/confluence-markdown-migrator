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
    
    # Language to comment prefix mapping
    LANGUAGE_COMMENT_MAP = {
        # Shell/scripting languages
        'bash': '#',
        'sh': '#',
        'shell': '#',
        'zsh': '#',
        'ksh': '#',
        'csh': '#',
        'tcsh': '#',
        'fish': '#',
        'powershell': '#',
        'ps1': '#',
        'cmd': 'rem',
        'batch': 'rem',
        
        # Configuration formats
        'yaml': '#',
        'yml': '#',
        'ini': ';',
        'toml': '#',
        'properties': '#',
        'config': '#',
        'conf': '#',
        'env': '#',
        'dockerfile': '#',
        
        # Other formats that use #
        'python': '#',
        'ruby': '#',
        'r': '#',
        'rscript': '#',
        'make': '#',
        'cmake': '#',
        'perl': '#',
        'pl': '#',
        'docker': '#',
        'terraform': '#',
        'hcl': '#',
        
        # Languages that use different comment styles
        'javascript': '//',
        'js': '//',
        'typescript': '//',
        'ts': '//',
        'jsx': '//',
        'tsx': '//',
        'css': '/*',
        'scss': '//',
        'sass': '//',
        'less': '//',
        'java': '//',
        'c': '//',
        'cpp': '//',
        'c++': '//',
        'cc': '//',
        'cxx': '//',
        'h': '//',
        'hpp': '//',
        'csharp': '//',
        'cs': '//',
        'go': '//',
        'golang': '//',
        'swift': '//',
        'php': '//',
        'kotlin': '//',
        'kt': '//',
        'scala': '//',
        'groovy': '//',
        'rust': '//',
        'rs': '//',
        'objectivec': '//',
        'objc': '//',
        'dart': '//',
        'elixir': '#',
        'erlang': '%',
        'matlab': '%',
        'sql': '--',
        'mysql': '--',
        'postgresql': '--',
        'sqlite': '--',
        'plsql': '--',
        'tsql': '--',
        'html': '<!--',
        'xml': '<!--',
        'xhtml': '<!--',
        'svg': '<!--',
        'text': '#',
        'plain': '#',
        'markdown': '#',
        'md': '#',
        'json': '#',
        'diff': '#',
        'patch': '#',
    }
    
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
        # Find and process code panel divs that weren't handled by macros
        # Only process panels without data-macro-name
        self._process_remaining_code_panels(soup)
        # Preprocess content-by-label lists
        # Note: This is a stub - content by label conversion is handled elsewhere
        pass
    
    def _process_remaining_code_panels(self, soup: BeautifulSoup) -> None:
        """Process code panel divs that weren't handled by MacroHandler."""
        for div in soup.find_all('div', class_=True):
            # Skip if this was already processed by MacroHandler
            if div.get('data-macro-name'):
                continue
                
            classes = div.get('class', [])
            has_code = any(cls == 'code' for cls in classes)
            has_panel = any(cls == 'panel' or cls == 'pdl' for cls in classes)
            
            if has_code and has_panel:
                # Extract header if present
                header_elem = div.find(class_='codeHeader') or div.find(class_='panelHeader')
                header_text = ''
                if header_elem:
                    header_text = header_elem.get_text(strip=True)
                    header_elem.decompose()
                
                # Ensure the pre element has a code child
                pre_elem = div.find('pre')
                if pre_elem and not pre_elem.find('code'):
                    code_elem = soup.new_tag('code')
                    code_elem.string = pre_elem.get_text()
                    pre_elem.clear()
                    pre_elem.append(code_elem)
                
                # Store header text in data attribute for later use
                if pre_elem and header_text:
                    pre_elem['data-code-header'] = header_text
                
                # Unwrap the div - keep the pre>code structure
                div.unwrap()
    
    def _get_comment_prefix(self, language: str) -> str:
        """Get the appropriate comment prefix for a programming language."""
        if not language:
            return '#'
        
        # Look up in the language map
        prefix = self.LANGUAGE_COMMENT_MAP.get(language.lower())
        if prefix:
            return prefix
        
        # Default to '#' for unknown languages
        return '#'
    
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
        
        # Preserve anchors from confluence-anchor-link spans
        markdown = self._preserve_anchors(markdown)

        # Convert callouts to admonition syntax BEFORE indentation
        if self.target_wiki in ['wikijs', 'both']:
            markdown = self._convert_callouts_to_admonitions(markdown)

        # Indent code blocks that are part of list items
        markdown = self._indent_code_blocks_in_lists(markdown)
        return markdown
    
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
        # Also handles nested content better
        pattern = re.compile(
            r'(?:> \{\.is-(info|warning|success|danger)\}\n)?'  # Optional class marker
            r'(?:> \[data-callout=(info|warning|success|danger)\]\n)?'  # Optional data attribute marker
            r'> \*\*([^*].*?)\*\*\n'  # Title line (non-greedy)
            r'(?:(?:>\s*\n)*)'  # Optional empty blockquote lines
            r'((?:> [^>].*(?:\n|$))*)'  # Content lines (non-greedy)
        )
        
        def replace_admonition(match):
            # Determine callout type (from class, data attribute, or infer from title)
            callout_type = match.group(1) or match.group(2)
            title = match.group(3) or 'Info'
            content = match.group(4) or ''
            
            # Map title to callout type if not already set
            if not callout_type:
                title_lower = title.lower()
                if 'info' in title_lower or 'information' in title_lower:
                    callout_type = 'info'
                elif 'warn' in title_lower:
                    callout_type = 'warning'
                elif 'tip' in title_lower or 'success' in title_lower or 'note' in title_lower:
                    callout_type = 'info'  # Wiki.js uses [!info] for tips and notes
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
                # Add content lines, ensuring they're properly indented
                content_lines = content.split('\n')
                for line in content_lines:
                    line_strip = line.strip()
                    if line_strip:
                        if line.startswith('> '):
                            result += f"> {line[2:]}\n"  # Remove '> ' prefix
                        else:
                            result += f"> {line_strip}\n"
                    # Don't add empty lines as they break list continuation
            
            return result + "\n"
        
        # Apply the transformation repeatedly to handle all matches
        previous_markdown = ''
        current_markdown = markdown
        while previous_markdown != current_markdown:
            previous_markdown = current_markdown
            current_markdown = pattern.sub(replace_admonition, current_markdown)
        
        return current_markdown

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
        
        # Use markdownify for content, then wrap in admonition
        from bs4 import BeautifulSoup
        
        if callout_type:
            # Map to Wiki.js admonition syntax
            admonition_map = {
                'info': '[!info]',
                'warning': '[!warning]',
                'success': '[!info]',
                'danger': '[!warning]'
            }
            admon_type = admonition_map.get(callout_type, '[!info]')
            
            # Get inner content as markdown
            content_html = ''.join(str(child) for child in el.children)
            if content_html:
                content_soup = BeautifulSoup(content_html, 'lxml')
                # Process it recursively with our converter
                content = self.convert(str(content_soup))
            else:
                content = ''
            
            # Build the admonition
            result = f"> {admon_type}\n"
            if content:
                content_lines = content.strip().split('\n')
                for line in content_lines:
                    result += f"> {line}\n"
            result += "\n"
            return result
        else:
            # Regular blockquote
            content = ''.join(str(child) for child in el.children)
            if content:
                content_soup = BeautifulSoup(content, 'lxml')
                content_md = self.convert(str(content_soup))
                result = ""
                for line in content_md.strip().split('\n'):
                    result += f"> {line}\n"
                return result + "\n"
            else:
                return "\n"
    
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
        """Normalize list bullet characters while preserving indentation."""
        lines = markdown.split('\n')
        normalized_lines = []
        
        for line in lines:
            # Check if this is a list item
            list_match = re.match(r'([ \t]*)([-*+][ \t]+|\d+\.[ \t]+)(.*)', line)
            if list_match:
                leading_spaces = list_match.group(1)
                bullet = list_match.group(2)
                content = list_match.group(3)
                
                # Normalize bullet to '-' for unordered, keep numbers for ordered
                if bullet.lstrip()[:1] in ['*', '+']:  # Check first non-space char
                    # Replace first character with '-' but preserve spacing
                    normalized_bullet = bullet.replace(bullet.lstrip()[:1], '-', 1)
                else:
                    normalized_bullet = bullet
                
                normalized_line = f"{leading_spaces}{normalized_bullet}{content}"
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
                # Don't add <br> elements to empty parts list
                if result == '<br>':
                    if parts:
                        parts.append(result)
                else:
                    parts.append(result)

        # Join all parts
        full_text = ''.join(parts)
        
        # Clean up: normalize multiple <br> and trim
        full_text = re.sub(r'(<br>)+', '<br>', full_text)
        full_text = full_text.strip()
        full_text = re.sub(r'^<br>|<br>$', '', full_text)
        
        return full_text

    # Custom markdownify converters for specific HTML elements
    def convert_table(self, el, text, parent_tags=None, **kwargs):
        """Convert table to markdown with proper spacing."""
        from markdownify import markdownify
        
        # Use parent converter but ensure proper spacing
        table_markdown = super().convert_table(el, text, parent_tags, **kwargs)
        
        # Ensure table is separated from surrounding text with blank lines
        if table_markdown.strip():
            if not table_markdown.startswith('\n\n'):
                table_markdown = '\n\n' + table_markdown
            if not table_markdown.endswith('\n'):
                table_markdown += '\n\n'
        
        return table_markdown
    
    def _get_comment_prefix(self, language: str) -> str:
        """Get the appropriate comment prefix for a programming language."""
        if not language:
            return '#'
        
        # Look up in the language map
        prefix = self.LANGUAGE_COMMENT_MAP.get(language.lower())
        if prefix:
            return prefix
        
        # Default to '#' for unknown languages
        return '#'
    
    def convert_pre(self, el, text, parent_tags=None, **kwargs):
        """Handle pre elements, especially for code blocks."""
        # Check for syntaxhighlighter params
        params = el.get('data-syntaxhighlighter-params', '')
        header = el.get('data-code-header', '')
        
        # Check for code child element
        code_el = el.find('code')
        if code_el:
            language = self._extract_code_language(code_el)
            code_text = code_el.get_text()
        else:
            language = self._parse_syntaxhighlighter_language(params) if params else ''
            code_text = text
        
        # Format the code block with proper language
        if language and language != 'text':
            fenced_code = f"```{language}\n{code_text.rstrip('\n')}\n```\n\n"
        else:
            fenced_code = f"```\n{code_text.rstrip('\n')}\n```\n\n"
        
        # Add header if present - use language-appropriate comment prefix
        if header:
            comment_prefix = self._get_comment_prefix(language)
            # For block comments (CSS, HTML, etc.), we need to handle closing
            if comment_prefix == '/*':
                return f"{comment_prefix} {header} */\n\n{fenced_code}"
            elif comment_prefix == '<!--':
                return f"{comment_prefix} {header} -->\n\n{fenced_code}"
            else:
                return f"{comment_prefix} {header}\n\n{fenced_code}"
        
        return fenced_code
    
    def convert_div(self, el, text, parent_tags=None, **kwargs):
        """Handle div elements, with special handling for code panels."""
        classes = el.get('class', [])
        
        # Check if this is a code panel (has both 'code' and 'panel' classes)
        # If the code panel was already processed by MacroHandler, it will have pre>code
        has_code = any(cls == 'code' for cls in classes)
        has_panel = any(cls == 'panel' or cls == 'pdl' for cls in classes)
        
        if has_code and has_panel:
            # This should be handled by convert_pre on the inner pre element
            # If no pre element exists, just extract text content
            pre_elem = el.find('pre')
            if not pre_elem:
                return text + '\n\n' if text.strip() else ''
            # If pre exists, it will be processed by convert_pre
            # Just return the text content
            return text
        
        # Regular div - return text content
        return text + '\n\n' if text.strip() else ''
    
    def convert_ul(self, el, text, parent_tags=None, **kwargs):
        """Convert unordered list with consistent indentation."""
        # Track nesting depth
        depth = kwargs.get('depth', 0)
        indent = '    ' * depth  # 4 spaces per level
        
        result = ''
        # Process each list item
        for child in el.children:
            if child.name == 'li':
                # Get the text of the list item
                item_text = self._process_list_item_content(child, depth + 1)
                
                # Add the list item with proper indentation
                result += f"{indent}- {item_text}\n"
                
                # Process nested lists
                for nested_child in child.children:
                    if nested_child.name in ['ul', 'ol']:
                        nested_result = self._convert_nested_list(nested_child, depth + 1)
                        if nested_result:
                            result += nested_result + '\n'
                
                # If this is the last item, don't add extra newline
        
        return result.rstrip() + '\n' if result else ''
    
    def convert_ol(self, el, text, parent_tags=None, **kwargs):
        """Convert ordered list with consistent numbering and indentation."""
        # Track nesting depth
        depth = kwargs.get('depth', 0)
        indent = '    ' * depth  # 4 spaces per level
        
        result = ''
        # Process each list item
        for idx, child in enumerate(el.children):
            if child.name == 'li':
                # Get the text of the list item
                item_text = self._process_list_item_content(child, depth + 1)
                
                # Use correct numbering (depth 0 gets 1, 2, 3; depth 1 gets a, b, c)
                if depth == 0:
                    number = idx + 1
                elif depth == 1:
                    number = ListTypeMarkers.get_alpha_marker(idx)
                else:
                    number = ListTypeMarkers.get_roman_marker(idx)
                
                result += f"{indent}{number}. {item_text}\n"
                
                # Process nested lists
                for nested_child in child.children:
                    if nested_child.name in ['ul', 'ol']:
                        nested_result = self._convert_nested_list(nested_child, depth + 1)
                        if nested_result:
                            result += nested_result + '\n'
        
        return result.rstrip() + '\n' if result else ''
    
    def _convert_nested_list(self, el, depth):
        """Convert nested list recursively."""
        if el.name == 'ul':
            return self.convert_ul(el, '', depth=depth)
        elif el.name == 'ol':
            return self.convert_ol(el, '', depth=depth)
        return ''
    
    def _process_list_item_content(self, li, depth):
        """Process content within a list item."""
        from bs4 import BeautifulSoup
        
        # Convert the li element to HTML and process it
        li_html = str(li)
        li_soup = BeautifulSoup(li_html, 'lxml')
        
        # Get direct text and inline elements
        content = ''
        for child in li_soup.find('li').children:
            if not hasattr(child, 'name') or child.name is None:
                # Text node
                text = str(child).strip()
                if text:
                    content += text + ' '
            elif child.name in ['p', 'span', 'strong', 'em', 'b', 'i', 'code', 'a']:
                # Inline elements - convert recursively
                from bs4 import BeautifulSoup
                child_html = str(child)
                child_md = self.convert(child_html)
                if child_md:
                    content += child_md.strip() + ' '
        
        return content.strip()
    
    def convert_code(self, el, text, parent_tags=None, **kwargs):
        """Handle inline code and code blocks."""
        # Check if this is a code block (inside pre) or inline code
        parent = el.parent
        if parent and parent.name == 'pre':
            # This will be handled by convert_pre, just return the text
            return text

        # Inline code - preserve whitespace and escape backticks
        if '`' in text:
            # Use double backticks if content contains backticks
            return f'``{text}``'
        return f'`{text}`'
    
    def convert_img(self, el, text, parent_tags=None, **kwargs):
        """Handle image conversion."""
        alt = el.get('alt', '')
        src = el.get('src', '')
        title = el.get('title', '')
        
        # Special handling for emoticons
        if 'emoticon' in el.get('class', []):
            # Return empty string - emoticons are handled by HtmlCleaner
            return ''
        
        # Regular image - use markdown syntax
        if title:
            return f'![{alt}]({src} "{title}")'
        else:
            return f'![{alt}]({src})'
    
    def convert_blockquote(self, el, text, parent_tags=None, **kwargs):
        """Handle blockquote conversion."""
        # Use our custom admonition conversion for blockquotes with callout attributes
        if el.get('data-callout') or any(cls.startswith('is-') for cls in el.get('class', [])):
            return self._convert_blockquote_to_admonition(el)
        
        # Regular blockquote
        return super().convert_blockquote(el, text, parent_tags, **kwargs)
    
    def _parse_syntaxhighlighter_language(self, params: str) -> str:
        """Parse language from syntaxhighlighter params string."""
        for param in params.split(';'):
            param = param.strip()
            if param.startswith('brush:'):
                language = param.replace('brush:', '').strip()
                # Use the comprehensive language map from _extract_language_from_syntaxhighlighter_params
                return self._extract_language_from_syntaxhighlighter_params(param.replace('brush:', 'brush: '))
        return ''
    
    def _extract_language_from_syntaxhighlighter_params(self, params: str) -> str:
        """Extract language from syntaxhighlighter params."""
        # This is a fallback method - the real implementation is in MacroHandler
        # Import it here to avoid circular dependencies
        from .macro_handler import MacroHandler
        handler = MacroHandler()
        return handler._extract_language_from_syntaxhighlighter_params(params)