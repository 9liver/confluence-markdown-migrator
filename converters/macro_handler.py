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
        
        if format_type == 'storage':
            # Find ac:structured-macro elements
            for element in soup.find_all('ac:structured-macro'):
                macro_name = self._get_macro_name(element, format_type)
                if macro_name:
                    macros.append((element, macro_name))
        else:  # export
            # Find elements with data-macro-name attribute
            for element in soup.find_all(attrs={'data-macro-name': True}):
                macro_name = element.get('data-macro-name')
                if macro_name:
                    macros.append((element, macro_name))
        
        return macros
    
    def _get_macro_name(self, element: Tag, format_type: str) -> Optional[str]:
        """Extract macro name from element."""
        if format_type == 'storage':
            return element.get('ac:name')
        else:
            return element.get('data-macro-name')
    
    def _convert_info_macro(self, element: Tag, format_type: str) -> None:
        """Convert info macro to blockquote with info callout class."""
        title = self._extract_parameter(element, 'title', format_type) or 'Note'
        body = self._extract_body(element, format_type, plain_text=False)
        
        # Create blockquote structure
        self._create_blockquote(element, callout_type='info', title=title, body=body)
    
    def _convert_warning_macro(self, element: Tag, format_type: str) -> None:
        """Convert warning macro to blockquote with warning callout class."""
        title = self._extract_parameter(element, 'title', format_type) or 'Warning'
        body = self._extract_body(element, format_type, plain_text=False)
        
        # Create blockquote structure
        self._create_blockquote(element, callout_type='warning', title=title, body=body)
    
    def _convert_note_macro(self, element: Tag, format_type: str) -> None:
        """Convert note macro to blockquote (maps to warning)."""
        title = self._extract_parameter(element, 'title', format_type) or 'Note'
        body = self._extract_body(element, format_type, plain_text=False)
        
        # Note maps to warning in Wiki.js
        self._create_blockquote(element, callout_type='warning', title=title, body=body)
    
    def _convert_tip_macro(self, element: Tag, format_type: str) -> None:
        """Convert tip macro to blockquote with success callout class."""
        title = self._extract_parameter(element, 'title', format_type) or 'Tip'
        body = self._extract_body(element, format_type, plain_text=False)
        
        self._create_blockquote(element, callout_type='success', title=title, body=body)
    
    def _convert_code_macro(self, element: Tag, format_type: str) -> None:
        """Convert code macro to pre > code block with language detection."""
        language = self._extract_parameter(element, 'language', format_type) or 'text'
        collapse = self._extract_parameter(element, 'collapse', format_type) or 'false'
        theme = self._extract_parameter(element, 'theme', format_type)
        
        code = self._extract_body(element, format_type, plain_text=True)
        
        # Create pre > code block
        new_soup = BeautifulSoup('', 'lxml')
        pre = new_soup.new_tag('pre')
        code_tag = new_soup.new_tag('code')
        
        # Add language class
        if language and language != 'text':
            code_tag['class'] = f'language-{language}'
        
        code_tag.string = code or ''
        pre.append(code_tag)
        
        # Add title if available
        title = self._extract_parameter(element, 'title', format_type)
        if title:
            title_p = new_soup.new_tag('p')
            title_strong = new_soup.new_tag('strong')
            title_strong.string = title
            title_p.append(title_strong)
            element.replace_with(title_p)
            title_p.insert_after(pre)
        else:
            element.replace_with(pre)
    
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
                    return str(cdata) if cdata else body.get_text(strip=True)
            else:
                body = element.find('ac:rich-text-body')
                if body:
                    # Include the rich text body content
                    return body.decode_contents(formatter="html") or ''
        else:  # export
            # Look for data-macro-body attribute or child elements
            body = element.get('data-macro-body')
            if body:
                return body
            # Return inner HTML if no specific body format
            return element.decode_contents(formatter="html") or ''
        
        return ''
    
    def _create_blockquote(self, element: Tag, callout_type: str, title: str, body: str) -> None:
        """Create blockquote structure for macro conversion."""
        new_soup = BeautifulSoup('', 'lxml')
        blockquote = new_soup.new_tag('blockquote')
        
        if callout_type:
            blockquote['class'] = f'is-{callout_type}'
        
        # Add title
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
