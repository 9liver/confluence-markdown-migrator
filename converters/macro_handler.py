"""Confluence macro handler for converting macros to markdown-friendly HTML."""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup, Tag

logger = logging.getLogger('confluence_markdown_migrator.converters.macrohandler')


class MacroHandler:
    """Converts Confluence macros to markdown-friendly HTML structures."""
    
    def __init__(self, logger: logging.Logger = None):
        """Initialize macro handler with optional logger."""
        self.logger = logger or logging.getLogger('confluence_markdown_migrator.converters.macrohandler')
        
        # Register macro converters
        self.macro_converters = {
            'info': self._convert_info_macro,
            'warning': self._convert_warning_macro,
            'note': self._convert_note_macro,
            'tip': self._convert_tip_macro,
            'code': self._convert_code_macro,
            'expand': self._convert_expand_macro,
            'panel': self._convert_panel_macro,
        }
        
        # Icon mapping for callout types
        self._icon_map = {
            'info': 'ℹ️',
            'warning': '⚠️',
            'success': '✔️',
            'danger': '❗',
            'note': '📝',
            'tip': '💡'
        }
    
    def convert(self, soup: BeautifulSoup, format_type: str = 'export') -> Tuple[BeautifulSoup, Dict[str, Any], List[str]]:
        """
        Convert all Confluence macros in the HTML.
        
        Args:
            soup: BeautifulSoup object with Confluence HTML
            format_type: 'export' or 'storage' format
            
        Returns:
            Tuple of (cleaned soup, conversion stats, warnings)
        """
        self.logger.debug(f"Converting macros (format: {format_type})")
        
        stats = {
            'macros_found': 0,
            'macros_converted': 0,
            'macros_failed': [],
            'by_type': {}
        }
        warnings = []
        
        # Find all macros
        macros = self._find_macros(soup, format_type)
        
        # Process depth-first (handle nested macros from inside out)
        for element, macro_name in reversed(macros):
            stats['macros_found'] += 1
            
            self.logger.debug(f"Converting macro: {macro_name}")
            
            try:
                if macro_name in self.macro_converters:
                    self.macro_converters[macro_name](element, format_type)
                    stats['macros_converted'] += 1
                    stats['by_type'][macro_name] = stats['by_type'].get(macro_name, 0) + 1
                else:
                    # Convert unknown macro
                    self._convert_unknown_macro(element, macro_name, format_type)
                    warnings.append(f"Unsupported macro type: {macro_name}")
                    stats['macros_failed'].append(macro_name)
            except Exception as e:
                self.logger.error(f"Failed to convert macro {macro_name}: {str(e)}")
                warnings.append(f"Failed to convert {macro_name}: {str(e)}")
                stats['macros_failed'].append(macro_name)
        
        self.logger.info(f"Macro conversion: {stats['macros_converted']}/{stats['macros_found']} succeeded")
        return soup, stats, warnings
    
    def _find_macros(self, soup: BeautifulSoup, format_type: str) -> List[Tuple[Tag, str]]:
        """Find all macro elements in the HTML."""
        macros = []
        processed_elements = set()

        if format_type == 'storage':
            # Find ac:structured-macro elements
            for element in soup.find_all('ac:structured-macro'):
                macro_name = self._get_macro_name(element, format_type)
                if macro_name:
                    macros.append((element, macro_name))
                    processed_elements.add(id(element))
        else:  # export
            # Find elements with data-macro-name attribute
            for element in soup.find_all(attrs={'data-macro-name': True}):
                macro_name = element.get('data-macro-name')
                if macro_name and id(element) not in processed_elements:
                    macros.append((element, macro_name))
                    processed_elements.add(id(element))

            # Also find confluence-information-macro elements (info, warning, note, tip boxes)
            # Only match div elements with the main macro class, not icons/spans
            for element in soup.find_all('div', class_=True):
                # Skip if already processed
                if id(element) in processed_elements:
                    continue

                classes = element.get('class', [])
                if isinstance(classes, str):
                    classes = classes.split()

                # Check if this is an information macro (has exactly 'confluence-information-macro' class)
                if 'confluence-information-macro' not in classes:
                    continue

                # Skip icon spans and body divs
                if 'confluence-information-macro-icon' in classes:
                    continue
                if 'confluence-information-macro-body' in classes:
                    continue

                # Determine macro type from class - check more specific types first
                class_str = ' '.join(classes)
                macro_name = 'info'  # default

                if 'confluence-information-macro-warning' in class_str:
                    macro_name = 'warning'
                elif 'confluence-information-macro-note' in class_str:
                    macro_name = 'note'
                elif 'confluence-information-macro-tip' in class_str:
                    macro_name = 'tip'
                elif 'confluence-information-macro-information' in class_str:
                    macro_name = 'info'

                macros.append((element, macro_name))
                processed_elements.add(id(element))

            # Also find code panel divs that might not have data-macro-name
            # Must have both "code" and "panel" as separate class names (not substrings)
            for element in soup.find_all('div'):
                if id(element) in processed_elements:
                    continue
                classes = element.get('class', [])
                if isinstance(classes, str):
                    classes = classes.split()
                # Check for actual "code" class and "panel" class (not codeHeader or panelHeader)
                has_code = any(cls == 'code' for cls in classes)
                has_panel = any(cls == 'panel' or cls == 'pdl' for cls in classes)
                if has_code and has_panel:
                    macros.append((element, 'code'))
                    processed_elements.add(id(element))

        return macros
    
    def _get_macro_name(self, element: Tag, format_type: str) -> Optional[str]:
        """Extract macro name from element."""
        if format_type == 'storage':
            return element.get('ac:name')
        else:
            return element.get('data-macro-name')
    
    def _convert_info_macro(self, element: Tag, format_type: str) -> None:
        """Convert info macro to blockquote with info callout class."""
        # Try multiple ways to extract title
        title = self._extract_parameter(element, 'title', format_type)
        if not title:
            title = self._extract_title_from_info_macro(element)
        # Don't use default title if none found - let the content speak for itself
        body = self._extract_body(element, format_type, plain_text=False)

        # Create blockquote structure
        self._create_blockquote(element, callout_type='info', title=title, body=body)
    
    def _convert_warning_macro(self, element: Tag, format_type: str) -> None:
        """Convert warning macro to blockquote with warning callout class."""
        title = self._extract_parameter(element, 'title', format_type)
        if not title:
            title = self._extract_title_from_info_macro(element)
        body = self._extract_body(element, format_type, plain_text=False)

        # Create blockquote structure
        self._create_blockquote(element, callout_type='warning', title=title, body=body)
    
    def _convert_note_macro(self, element: Tag, format_type: str) -> None:
        """Convert note macro to blockquote (maps to warning)."""
        title = self._extract_parameter(element, 'title', format_type)
        if not title:
            title = self._extract_title_from_info_macro(element)
        body = self._extract_body(element, format_type, plain_text=False)

        # Note maps to warning in Wiki.js
        self._create_blockquote(element, callout_type='warning', title=title, body=body)
    
    def _convert_tip_macro(self, element: Tag, format_type: str) -> None:
        """Convert tip macro to blockquote with success callout class."""
        title = self._extract_parameter(element, 'title', format_type)
        if not title:
            title = self._extract_title_from_info_macro(element)
        body = self._extract_body(element, format_type, plain_text=False)

        self._create_blockquote(element, callout_type='success', title=title, body=body)
    
    def _convert_code_macro(self, element: Tag, format_type: str) -> None:
        """Convert code macro to pre > code block with language detection."""
        language = self._extract_parameter(element, 'language', format_type)

        # Try to extract language from syntaxhighlighter params
        if not language:
            language = self._extract_language_from_syntaxhighlighter(element)

        language = language or ''
        collapse = self._extract_parameter(element, 'collapse', format_type) or 'false'
        theme = self._extract_parameter(element, 'theme', format_type)

        # Extract title from parameter or codeHeader div - prioritize codeHeader
        title = self._extract_parameter(element, 'title', format_type)
        if not title:
            # Check for codeHeader div (Confluence export format)
            code_header = element.find(class_='codeHeader')
            if not code_header:
                # Also check for panelHeader as fallback
                code_header = element.find(class_='panelHeader')
            if code_header:
                title = code_header.get_text(strip=True)
                # Store this for later deletion to avoid duplication
                code_header['data-processed'] = 'true'

        # ENHANCED: Extract code content with multiple fallbacks
        code = ''
        # First check for pre element with syntaxhighlighter
        pre_elem = element.find('pre', class_='syntaxhighlighter-pre')
        # If not found, look for any pre element
        if not pre_elem:
            pre_elem = element.find('pre')
        # If still not found, look for codeContent div
        if not pre_elem:
            code_content = element.find(class_='codeContent')
            if code_content:
                pre_elem = code_content.find('pre')
        
        if pre_elem:
            # ENHANCED: Use get_text() to ensure we get all text content
            code = pre_elem.get_text()
            # Also try to get language from this element if not yet found
            if not language:
                params = pre_elem.get('data-syntaxhighlighter-params', '')
                if params:
                    language = self._extract_language_from_syntaxhighlighter_params(params)
        else:
            # ENHANCED: Multiple fallback strategies
            # Try codeContent div
            code_content = element.find(class_='codeContent')
            if code_content:
                code = code_content.get_text()
            else:
                # Last resort: get all text from the element
                code = element.get_text()
        
        # ENHANCED: Validate code content
        if not code or not code.strip():
            self.logger.warning(f"Empty code block detected in macro conversion")
            # Try one more time with stripped_strings
            code = '\n'.join(element.stripped_strings)

        # Get the actual pre element from the DOM that we'll be modifying
        actual_pre_elem = pre_elem or element.find('pre')
        
        # Create pre > code block structure
        new_soup = BeautifulSoup('', 'lxml')
        pre = new_soup.new_tag('pre')
        code_tag = new_soup.new_tag('code')
        
        # Add language class
        if language:
            code_tag['class'] = f'language-{language}'
        
        # ENHANCED: Ensure code is never empty
        code_tag.string = code if code else '# Empty code block'
        pre.append(code_tag)
        
        # Store code header in data attribute on pre element for later use
        if title:
            pre['data-code-header'] = title
        
        # Store any syntaxhighlighter params on the pre element
        if actual_pre_elem and actual_pre_elem.get('data-syntaxhighlighter-params'):
            pre['data-syntaxhighlighter-params'] = actual_pre_elem.get('data-syntaxhighlighter-params')
        
        # Replace the original element with the new pre>code structure
        element.replace_with(pre)
        
        # Clean up any header elements that were marked as processed
        for header in element.find_all(attrs={'data-processed': 'true'}):
            header.decompose()
    
    def _convert_expand_macro(self, element: Tag, format_type: str) -> None:
        """Convert expand macro to details > summary collapsible structure."""
        title = self._extract_parameter(element, 'title', format_type) or 'Click to expand'
        body = self._extract_body(element, format_type, plain_text=False)
        
        # Create details > summary structure
        new_soup = BeautifulSoup('', 'lxml')
        details = new_soup.new_tag('details')
        summary = new_soup.new_tag('summary')
        summary.string = title
        details.append(summary)
        
        # Add body content
        if body:
            body_p = new_soup.new_tag('div')
            body_p.append(BeautifulSoup(body, 'lxml'))
            details.append(body_p)
        
        element.replace_with(details)
    
    def _convert_panel_macro(self, element: Tag, format_type: str) -> None:
        """Convert panel macro to blockquote with optional title."""
        title = self._extract_parameter(element, 'title', format_type) or None
        border_color = self._extract_parameter(element, 'borderColor', format_type)
        bg_color = self._extract_parameter(element, 'bgColor', format_type)
        
        body = self._extract_body(element, format_type, plain_text=False)
        
        # Create blockquote structure
        new_soup = BeautifulSoup('', 'lxml')
        blockquote = new_soup.new_tag('blockquote')
        
        # Add title if available
        if title:
            title_p = new_soup.new_tag('p')
            title_strong = new_soup.new_tag('strong')
            title_strong.string = title
            title_p.append(title_strong)
            blockquote.append(title_p)
        
        # Add body content
        if body:
            body_div = new_soup.new_tag('div')
            body_div.append(BeautifulSoup(body, 'lxml'))
            blockquote.append(body_div)
        
        element.replace_with(blockquote)
    
    def _convert_unknown_macro(self, element: Tag, macro_name: str, format_type: str) -> None:
        """Convert unknown macro to blockquote with warning."""
        self.logger.warning(f"Converting unknown macro: {macro_name}")
        
        body = self._extract_body(element, format_type, plain_text=False)
        
        # Create blockquote structure with warning
        new_soup = BeautifulSoup('', 'lxml')
        blockquote = new_soup.new_tag('blockquote')
        
        warning_p = new_soup.new_tag('p')
        warning_strong = new_soup.new_tag('strong')
        warning_strong.string = f"[Confluence Macro: {macro_name}]"
        warning_p.append(warning_strong)
        warning_p.append(" (content below)")
        blockquote.append(warning_p)
        
        if body:
            body_div = new_soup.new_tag('div')
            body_div.append(BeautifulSoup(body, 'lxml'))
            blockquote.append(body_div)
        
        element.replace_with(blockquote)
    
    def _extract_parameter(self, element: Tag, param_name: str, format_type: str) -> Optional[str]:
        """Extract parameter value from macro element."""
        if format_type == 'storage':
            # Look for ac:parameter with ac:name
            param = element.find('ac:parameter', {'ac:name': param_name})
            return param.get_text(strip=True) if param else None
        else:  # export
            # Look for data-macro-param-* attribute
            attr_name = f'data-macro-param-{param_name}'
            return element.get(attr_name)
    
    def _extract_body(self, element: Tag, format_type: str, plain_text: bool = False) -> str:
        """Extract macro body content."""
        if format_type == 'storage':
            # Look for various body types
            if plain_text:
                body = element.find('ac:plain-text-body')
                if body:
                    # Extract CDATA if present
                    if body.string:
                        return body.get_text(strip=True)
                    cdata = body.find(string=lambda text: isinstance(text, type(BeautifulSoup('', 'lxml').__class__)))
                    body_text = str(cdata) if cdata else body.get_text(strip=True)
                    # Return plain text without emoticon processing
                    return body_text
            else:
                body = element.find('ac:rich-text-body')
                if body:
                    # Include the rich text body content
                    body_html = body.decode_contents(formatter="html") or ''
                    return body_html
        else:  # export
            # Look for data-macro-body attribute or child elements
            body = element.get('data-macro-body')
            if body:
                return body

            # Check for confluence-information-macro-body class
            body_div = element.find(class_='confluence-information-macro-body')
            if body_div:
                if plain_text:
                    return body_div.get_text() or ''
                body_html = body_div.decode_contents(formatter="html") or ''
                return body_html

            # Return content based on plain_text flag
            if plain_text:
                return element.get_text() or ''
            
            body_html = element.decode_contents(formatter="html") or ''
            return body_html

        return ''

    def _extract_title_from_info_macro(self, element: Tag) -> Optional[str]:
        """Extract title from info macro element (from p.title class)."""
        title_elem = element.find('p', class_='title')
        if title_elem:
            return title_elem.get_text(strip=True)
        return None

    def _extract_language_from_syntaxhighlighter(self, element: Tag) -> Optional[str]:
        """Extract language from Confluence syntaxhighlighter params."""
        # Check element itself
        params = element.get('data-syntaxhighlighter-params', '')
        if not params:
            # Check pre elements inside
            pre = element.find('pre')
            if pre:
                params = pre.get('data-syntaxhighlighter-params', '')

        if params:
            return self._extract_language_from_syntaxhighlighter_params(params)
        
        return None
        
    def _extract_language_from_syntaxhighlighter_params(self, params: str) -> Optional[str]:
        """Extract language from params string like 'brush: bash; gutter: false; theme: RDark'.
        
        Args:
            params: The syntaxhighlighter parameters string
            
        Returns:
            Language string or None
        """
        # Parse "brush: bash; gutter: false" format
        for param in params.split(';'):
            param = param.strip()
            if param.startswith('brush:'):
                language = param.replace('brush:', '').strip()
                # Map common Confluence language names
                language_map = {
                    # Shell scripting
                    'bash': 'bash',
                    'shell': 'bash',
                    'sh': 'bash',
                    'zsh': 'bash',
                    'ksh': 'bash',
                    'csh': 'bash',
                    'tcsh': 'bash',
                    
                    # Python
                    'python': 'python',
                    'py': 'python',
                    
                    # JavaScript
                    'javascript': 'javascript',
                    'js': 'javascript',
                    
                    # Java & related
                    'java': 'java',
                    'scala': 'scala',
                    'kotlin': 'kotlin',
                    'groovy': 'groovy',
                    
                    # Web technologies
                    'html': 'html',
                    'xml': 'xml',
                    'css': 'css',
                    'less': 'less',
                    'sass': 'sass',
                    'scss': 'scss',
                    
                    # Data formats
                    'json': 'json',
                    'yaml': 'yaml',
                    'yml': 'yaml',
                    'toml': 'toml',
                    'ini': 'ini',
                    
                    # SQL
                    'sql': 'sql',
                    'mysql': 'sql',
                    'postgresql': 'sql',
                    'plsql': 'sql',
                    'tsql': 'sql',
                    
                    # Configuration & markup
                    'text': 'text',
                    'plain': 'text',
                    'properties': 'text',
                    'conf': 'text',
                    'config': 'text',
                    'markdown': 'markdown',
                    'md': 'markdown',
                    'rst': 'rst',
                    'asciidoc': 'asciidoc',
                    
                    # Systems languages
                    'c': 'c',
                    'cpp': 'cpp',
                    'c++': 'cpp',
                    'cc': 'cpp',
                    'cxx': 'cpp',
                    'h': 'c',
                    'hpp': 'cpp',
                    
                    # Other languages
                    'php': 'php',
                    'ruby': 'ruby',
                    'rb': 'ruby',
                    'perl': 'perl',
                    'pl': 'perl',
                    'go': 'go',
                    'golang': 'go',
                    'rust': 'rust',
                    'rs': 'rust',
                    'swift': 'swift',
                    'r': 'r',
                    'matlab': 'matlab',
                    'sql': 'sql',
                    
                    # Template languages
                    'jinja': 'jinja',
                    'jinja2': 'jinja',
                    'twig': 'twig',
                    
                    # Build tools
                    'make': 'make',
                    'cmake': 'cmake',
                    'docker': 'docker',
                    'dockerfile': 'docker',
                    'terraform': 'hcl',
                    'hcl': 'hcl',
                    
                    # Other formats
                    'diff': 'diff',
                    'patch': 'diff',
                }
                return language_map.get(language.lower(), language)

        return None
    
    def _create_blockquote(self, element: Tag, callout_type: str, title: str, body: str) -> None:
        """Create blockquote structure for macro conversion with admonition support."""
        new_soup = BeautifulSoup('', 'lxml')
        blockquote = new_soup.new_tag('blockquote')

        if callout_type:
            blockquote['class'] = f'is-{callout_type}'
            # Add data attribute for easier admonition detection by MarkdownConverter
            blockquote['data-callout'] = callout_type

        # Add title with icon if available
        if title:
            title_p = new_soup.new_tag('p')
            title_strong = new_soup.new_tag('strong')
            
            # Prepend icon if we have one for this callout type
            icon = self._icon_map.get(callout_type, '')
            if icon:
                title_strong.string = f"{icon} {title}"
            else:
                title_strong.string = title
            
            title_p.append(title_strong)
            blockquote.append(title_p)

        # Add body content - parse and extract just the content, not wrapper elements
        if body:
            # Parse the body HTML
            body_soup = BeautifulSoup(body, 'lxml')
            # Get the body content, stripping html/body wrapper tags that lxml adds
            body_content = body_soup.find('body')
            if body_content:
                # Move all children to the blockquote, but skip empty/title elements
                for child in list(body_content.children):
                    # Skip NavigableStrings that are just whitespace
                    if not hasattr(child, 'name') or child.name is None:
                        text = str(child).strip()
                        if not text:
                            continue
                        # Create a text node
                        blockquote.append(text)
                        continue

                    # Skip empty elements (no text content)
                    child_text = child.get_text(strip=True) if hasattr(child, 'get_text') else ''
                    if not child_text:
                        continue

                    # Skip if this child is just the title text repeated
                    if title and child_text == title:
                        continue

                    blockquote.append(child.extract() if hasattr(child, 'extract') else child)
            else:
                # Fallback: just append the text
                text = body_soup.get_text(strip=True)
                if text and text != title:  # Don't duplicate title
                    p = new_soup.new_tag('p')
                    p.string = text
                    blockquote.append(p)

        element.replace_with(blockquote)