"""Tests for emoticon conversion standardization."""

import unittest
from bs4 import BeautifulSoup
from converters.markdown_converter import MarkdownConverter
from converters.macro_handler import MacroHandler
from converters.html_cleaner import HtmlCleaner


class TestEmoticonConversion(unittest.TestCase):
    def setUp(self):
        self.converter = MarkdownConverter()
        self.macro_handler = MacroHandler()
        self.html_cleaner = HtmlCleaner()
    
    def test_emoticon_from_src(self):
        """Test emoticon extraction from image src URL."""
        html = '<p>Great work <img class="emoticon emoticon-smile" src="/images/icons/emoticons/smile.svg" alt="(smile)" /></p>'
        
        soup = BeautifulSoup(html, 'lxml')
        soup = self.html_cleaner.clean(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should convert to !(smile) only once
        self.assertEqual(markdown.count('!(smile)'), 1)
        # Should not have img tag
        self.assertNotIn('<img', markdown)
    
    def test_emoticon_from_alt_fallback(self):
        """Test emoticon extraction from alt text when src isn't available."""
        html = '<p>Nice! <img class="emoticon" alt="(thumbsup)" /></p>'
        
        soup = BeautifulSoup(html, 'lxml')
        soup = self.html_cleaner.clean(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should convert to !(thumbsup)
        self.assertIn('!(thumbsup)', markdown)
        self.assertNotIn('<img', markdown)
    
    def test_multiple_emoticons(self):
        """Test multiple emoticons in same content."""
        html = '''
        <p>Great <img class="emoticon emoticon-smile" src="/images/icons/emoticons/smile.svg" alt="(smile)" />
        job! <img class="emoticon emoticon-wink" src="/images/icons/emoticons/wink.svg" alt="(wink)" />
        Keep it up! <img class="emoticon emoticon-thumbs-up" src="/images/icons/emoticons/thumbs-up.svg" alt="(thumbsup)" /></p>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup = self.html_cleaner.clean(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have each emoticon once
        self.assertEqual(markdown.count('!(smile)'), 1)
        self.assertEqual(markdown.count('!(wink)'), 1)
        self.assertEqual(markdown.count('!(thumbs-up)'), 1)
        # Should not have any img tags
        self.assertNotIn('<img', markdown)
        self.assertNotIn('emoticon', markdown)
    
    def test_emoticon_in_macro_body(self):
        """Test emoticons within macro bodies are converted by HtmlCleaner."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-information">
            <div class="confluence-information-macro-body">
                <p>Setup instructions <img class="emoticon emoticon-smile" src="/images/icons/emoticons/smile.svg" alt="(smile)" /></p>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup = self.html_cleaner.clean(soup, 'export')  # HtmlCleaner converts emoticons
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have emoticon converted
        self.assertIn('!(smile)', markdown)
        self.assertNotIn('<img', markdown)
        # Should have admonition
        self.assertIn('[!info]', markdown)
    
    def test_emoticon_only_once_in_pipeline(self):
        """Test that emoticons aren't processed multiple times in the pipeline."""
        # This tests the full pipeline
        html = '''
        <div class="page-content">
            <p>Before macro</p>
            <div class="confluence-information-macro confluence-information-macro-information">
                <div class="confluence-information-macro-body">
                    <p>Content with <img class="emoticon emoticon-smile" src="/images/icons/emoticons/smile.svg" alt="(smile)" /> emoticon</p>
                </div>
            </div>
            <p>After macro <img class="emoticon emoticon-wink" src="/images/icons/emoticons/wink.svg" alt="(wink)" /></p>
        </div>
        '''
        
        # Run full pipeline (clean -> convert macros -> convert to markdown)
        soup = BeautifulSoup(html, 'lxml')
        soup = self.html_cleaner.clean(soup, 'export')  # Emoticons converted here
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Each emoticon should appear exactly once
        self.assertEqual(markdown.count('!(smile)'), 1, "smile emoticon should appear once")
        self.assertEqual(markdown.count('!(wink)'), 1, "wink emoticon should appear once")
        
        # No img tags should remain
        self.assertNotIn('<img', markdown)
        self.assertNotIn('class="emoticon"', markdown)
    
    def test_emoticon_not_left_as_img(self):
        """Ensure emoticons are never left as <img> tags in final markdown."""
        html = '''
        <p>Various emoticons:
        <img class="emoticon emoticon-smile" src="/emoticons/smile.svg" alt="(smile)" />
        <img class="emoticon emoticon-sad" src="/emoticons/sad.svg" alt="(sad)" />
        <img class="emoticon emoticon-laugh" src="/emoticons/laugh.svg" alt="(laugh)" />
        </p>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup = self.html_cleaner.clean(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # No img tags should remain
        self.assertNotIn('<img', markdown.lower())
        self.assertNotIn('<img', markdown)
        # Should have converted emoticons
        self.assertIn('!(smile)', markdown)
        self.assertIn('!(sad)', markdown)
        self.assertIn('!(laugh)', markdown)


if __name__ == '__main__':
    unittest.main()