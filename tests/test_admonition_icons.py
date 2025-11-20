"""Tests for icon text in admonitions."""

import unittest
from bs4 import BeautifulSoup
from converters.markdown_converter import MarkdownConverter
from converters.macro_handler import MacroHandler


class TestAdmonitionIcons(unittest.TestCase):
    def setUp(self):
        self.converter = MarkdownConverter()
        self.macro_handler = MacroHandler()
    
    def test_info_macro_has_info_icon(self):
        """Test info macro is rendered with info icon."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-information">
            <div class="confluence-information-macro-body">
                <p>This is an informational message.</p>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have admonition with info icon
        # The icon should be prepended to the title or content
        self.assertIn('[!info]', markdown)
        # The ℹ️ icon should be present
        self.assertIn('ℹ️', markdown)
        self.assertIn('informational message', markdown)
    
    def test_warning_macro_has_warning_icon(self):
        """Test warning macro is rendered with warning icon."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-warning">
            <div class="confluence-information-macro-body">
                <p>This is a warning message.</p>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have admonition with warning icon
        self.assertIn('[!warning]', markdown)
        # The ⚠️ icon should be present
        self.assertIn('⚠️', markdown)
        self.assertIn('warning message', markdown)
    
    def test_note_macro_warning_icon(self):
        """Test note macro uses warning icon (maps to warning)."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-note">
            <div class="confluence-information-macro-body">
                <p>This is a note.</p>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Note maps to warning
        self.assertIn('[!warning]', markdown)
        self.assertIn('⚠️', markdown)
        self.assertIn('This is a note', markdown)
    
    def test_tip_macro_success_icon(self):
        """Test tip macro uses success icon."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-tip">
            <div class="confluence-information-macro-body">
                <p>This is a tip.</p>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Tip uses success which gets info icon in Wiki.js but we add the ✔️ icon
        self.assertIn('[!info]', markdown)  # Wiki.js maps success to info
        self.assertIn('✔️', markdown)
        self.assertIn('This is a tip', markdown)
    
    def test_macro_with_title_has_icon(self):
        """Test macro with custom title still gets icon."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-information">
            <p class="title">Custom Title</p>
            <div class="confluence-information-macro-body">
                <p>Message content.</p>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have title with icon
        self.assertIn('[!info]', markdown)
        self.assertIn('ℹ️', markdown)
        self.assertIn('Custom Title', markdown)
        self.assertIn('Message content', markdown)
    
    def test_multiple_macros_with_different_icons(self):
        """Test multiple macros with different icon types."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-information">
            <div class="confluence-information-macro-body"><p>Info message</p></div>
        </div>
        <div class="confluence-information-macro confluence-information-macro-warning">
            <div class="confluence-information-macro-body"><p>Warning message</p></div>
        </div>
        <div class="confluence-information-macro confluence-information-macro-tip">
            <div class="confluence-information-macro-body"><p>Tip message</p></div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have all three admonitions with their icons
        self.assertIn('ℹ️', markdown)
        self.assertIn('⚠️', markdown)
        self.assertIn('✔️', markdown)
        
        # Should have different callout markers
        self.assertIn('[!info]', markdown)
        self.assertIn('[!warning]', markdown)
        
        # Should have content
        self.assertIn('Info message', markdown)
        self.assertIn('Warning message', markdown)
        self.assertIn('Tip message', markdown)


if __name__ == '__main__':
    unittest.main()