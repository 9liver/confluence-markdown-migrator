import unittest
import re
from bs4 import BeautifulSoup
from converters.markdown_converter import MarkdownConverter
from converters.macro_handler import MacroHandler
from converters.html_cleaner import HtmlCleaner

class TestMarkdownConversion(unittest.TestCase):
    def setUp(self):
        self.converter = MarkdownConverter()
        self.macro_handler = MacroHandler()
        self.html_cleaner = HtmlCleaner()
    
    def test_code_block_with_header(self):
        """Test code blocks with headers are properly converted."""
        html = '''
        <div class="code panel pdl">
            <div class="codeHeader panelHeader pdl"><b>~/.profile</b></div>
            <div class="codeContent panelContent pdl">
                <pre class="syntaxhighlighter-pre" data-syntaxhighlighter-params="brush: bash; gutter: false; theme: RDark">
# set PATH so it includes user's private bin if it exists
if [ -d "$HOME/.local/bin" ] ; then
    PATH="$HOME/.local/bin:$PATH"
fi
                </pre>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Verify header appears as bash comment
        self.assertIn('# ~/.profile', markdown)
        # Verify code block with proper language tag
        self.assertIn('```bash', markdown)
        self.assertIn('$HOME/.local/bin', markdown)
    
    def test_code_block_with_language_detection(self):
        """Test code blocks with language detection from syntaxhighlighter params."""
        html = '''
        <div class="code panel pdl" style="border-width: 1px;">
            <div class="codeContent panelContent pdl">
                <pre class="syntaxhighlighter-pre" data-syntaxhighlighter-params="brush: python; gutter: true; theme: RDark">
def hello_world():
    print("Hello, World!")
                </pre>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should detect Python language
        self.assertIn('```python', markdown)
        self.assertIn('def hello_world():', markdown)
    
    def test_simple_code_block(self):
        """Test simple code blocks without headers."""
        html = '''
        <div class="code panel pdl">
            <div class="codeContent panelContent pdl">
                <pre class="syntaxhighlighter-pre" data-syntaxhighlighter-params="brush: bash; gutter: false">
$ sudo apt update && sudo apt install python3 python3-pip git
                </pre>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have code fence
        self.assertIn('```bash', markdown)
        # Should not have header text (comments or bold)
        lines_before_fence = markdown.split('```')[0]
        self.assertNotIn('**', lines_before_fence)
        self.assertNotIn('~/.profile', lines_before_fence)
    
    def test_info_macro_conversion(self):
        """Test info macros convert to admonition syntax."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-information">
            <span class="aui-icon aui-icon-small aui-iconfont-info confluence-information-macro-icon"></span>
            <div class="confluence-information-macro-body">
                <p>Alle Pfade in dieser Anleitung sind natürlich als persönliche Vorlieben anzusehen.</p>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should use admonition syntax
        self.assertTrue('> [!info]' in markdown or '> [!warning]' in markdown)
    
    def test_warning_macro_conversion(self):
        """Test warning macros convert to warning admonition syntax."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-note">
            <span class="aui-icon aui-icon-small aui-iconfont-warning confluence-information-macro-icon"></span>
            <div class="confluence-information-macro-body">
                <p>Eventuell bereits in der standard .profile vorhanden, bitte prüfen</p>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should use warning admonition
        self.assertIn('[!warning]', markdown)
    
    def test_macro_with_title(self):
        """Test macros with titles include the title in output."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-information">
            <p class="title">Changelog</p>
            <span class="aui-icon aui-icon-small aui-iconfont-info confluence-information-macro-icon"></span>
            <div class="confluence-information-macro-body">
                <p>2024-10-31: Anpassung von Links und Configs an das neue GitLab</p>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should preserve the title
        self.assertIn('Changelog', markdown)
        # Should use admonition syntax
        self.assertIn('[!info]', markdown)
    
    def test_nested_ordered_lists(self):
        """Test proper indentation of nested ordered lists."""
        html = '''
        <ol>
            <li>First main item
                <ol>
                    <li>First nested item</li>
                    <li>Second nested item</li>
                </ol>
            </li>
            <li>Second main item</li>
        </ol>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Check proper nesting structure
        lines = markdown.strip().split('\n')
        top_level_items = [l for l in lines if re.match(r'^\d+\.', l.strip())]
        nested_items = [l for l in lines if re.match(r'^\s+\d+\.', l.strip())]
        
        self.assertGreaterEqual(len(top_level_items), 2)
        self.assertGreaterEqual(len(nested_items), 2)
        
        # Check proper indentation (4 spaces per level)
        for item in nested_items:
            self.assertTrue(item.startswith('    '), f"Nested item should be indented with 4 spaces: {item}")
    
    def test_list_with_code_blocks(self):
        """Test list items containing code blocks."""
        html = '''
        <ol>
            <li>Install package:
                <div class="code panel pdl">
                    <div class="codeContent panelContent pdl">
                        <pre class="syntaxhighlighter-pre">$ sudo apt update</pre>
                    </div>
                </div>
            </li>
        </ol>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have list item
        self.assertIn('1.', markdown)
        # Should have code block
        self.assertIn('```', markdown)
        # Should have the command
        self.assertIn('sudo apt update', markdown)
    
    def test_list_with_paragraphs(self):
        """Test list items containing paragraphs."""
        html = '''
        <ol>
            <li><p>First paragraph</p><p>Second paragraph</p></li>
            <li><p>Another item with single paragraph</p></li>
        </ol>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have list items
        self.assertIn('1.', markdown)
        self.assertIn('2.', markdown)
        # Should have paragraph content
        self.assertIn('First paragraph', markdown)
        self.assertIn('Second paragraph', markdown)
    
    def test_emoticon_conversion(self):
        """Test emoticon images are converted to text format."""
        html = '''
        <p>Great work <img class="emoticon emoticon-smile" src="/images/icons/emoticons/smile.svg" alt="(smile)" /></p>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup = self.html_cleaner.clean(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should convert to !(smile) format
        self.assertIn('!(smile)', markdown)
        # Should not have img tag
        self.assertNotIn('<img', markdown)
    
    def test_anchor_preservation(self):
        """Test confluence anchors are preserved."""
        html = '''
        <p>Step 3<span class="confluence-anchor-link" id="Ansiblelokaleinrichten-3"></span></p>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should preserve the anchor immediately after the content
        self.assertIn('<a id="Ansiblelokaleinrichten-3"></a>', markdown)
        # Should not duplicate the anchor
        self.assertEqual(markdown.count('<a id="Ansiblelokaleinrichten-3"></a>'), 1)
    
    def test_multiple_anchors_preserved(self):
        """Test that multiple anchors in sequence render consistently."""
        html = '''
        <h2>Heading 1<span class="confluence-anchor-link" id="section-1"></span></h2>
        <p>Paragraph 1 <span class="confluence-anchor-link" id="paragraph-1"></span></p>
        <h3>Subheading 1<span class="confluence-anchor-link" id="subsection-1"></span></h3>
        '''
        
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Each anchor should appear exactly once and be properly placed
        self.assertIn('<a id="section-1"></a>', markdown)
        self.assertIn('<a id="paragraph-1"></a>', markdown)
        self.assertIn('<a id="subsection-1"></a>', markdown)
        
        # No duplicates
        self.assertEqual(markdown.count('<a id="section-1"></a>'), 1)
        self.assertEqual(markdown.count('<a id="paragraph-1"></a>'), 1)
        self.assertEqual(markdown.count('<a id="subsection-1"></a>'), 1)
    
    def test_content_by_label_conversion(self):
        """Test content-by-label lists convert to simple bullet lists."""
        html = '''
        <ul class="content-by-label">
            <li>
                <div>
                    <span class="icon aui-icon content-type-page" title="Page">Page:</span>
                </div>
                <div class="details">
                    <a href="/pages/viewpage.action?pageId=123456">Related Page 1</a>
                </div>
            </li>
            <li>
                <div>
                    <span class="icon aui-icon content-type-page" title="Page">Page:</span>
                </div>
                <div class="details">
                    <a href="/pages/viewpage.action?pageId=789012">Related Page 2</a>
                </div>
            </li>
        </ul>
        '''
        
        # Test through public conversion API - pre-processing happens internally
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Should be converted to simple bullet list
        self.assertIn('-', markdown)
        # Should preserve links
        self.assertIn('Related Page 1', markdown)
        self.assertIn('Related Page 2', markdown)
        # Should not have icon spans
        self.assertNotIn('icon aui-icon', markdown)
    
    def test_comprehensive_conversion(self):
        """Test a comprehensive snippet with multiple elements."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-information">
            <span class="aui-icon aui-icon-small aui-iconfont-info confluence-information-macro-icon"></span>
            <div class="confluence-information-macro-body">
                <p>Setup instructions <img class="emoticon emoticon-smile" src="/images/icons/emoticons/smile.svg" alt="(smile)" /></p>
            </div>
        </div>
        
        <ol>
            <li>First step
                <div class="code panel pdl"><div class="codeContent panelContent pdl">
                    <pre class="syntaxhighlighter-pre">echo "Hello World"</pre>
                </div></div>
            </li>
            <li>Second step <span class="confluence-anchor-link" id="step-2"></span>
                <div class="confluence-information-macro confluence-information-macro-note">
                    <span class="aui-icon aui-icon-small aui-iconfont-warning confluence-information-macro-icon"></span>
                    <div class="confluence-information-macro-body">
                        <p>Be careful with this step</p>
                    </div>
                </div>
            </li>
        </ol>
        '''
        
        # Test through public conversion API - pre-processing happens internally       
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Check for admonitions
        self.assertIn('[!', markdown)
        # Check for emoticon
        self.assertIn('!(smile)', markdown)
        # Check for code block
        self.assertIn('```', markdown)
        # Check for list
        self.assertIn('1.', markdown)
        self.assertIn('2.', markdown)
        # Check for anchor
        self.assertTrue('<a id="step-2"></a>' in markdown or '{#step-2}' in markdown)

    def test_three_level_list_nesting(self):
        """Test proper indentation for three levels of nested lists."""
        html = '''
        <ol>
            <li>First main item
                <ol>
                    <li>First nested item
                        <ol>
                            <li>Deeply nested item 1</li>
                            <li>Deeply nested item 2</li>
                        </ol>
                    </li>
                    <li>Second nested item</li>
                </ol>
            </li>
            <li>Second main item</li>
        </ol>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Check proper nesting structure
        lines = markdown.strip().split('\n')
        
        # Top level should be numbered 1., 2.
        top_level_items = [l for l in lines if re.match(r'^\d+\.\s+', l.strip())]
        self.assertGreaterEqual(len(top_level_items), 2)
        
        # Second level should be letters a., b.
        second_level_items = [l for l in lines if re.match(r'^\s+[a-z]\.\s+', l)]
        self.assertGreaterEqual(len(second_level_items), 2)
        
        # Third level should be roman numerals i., ii.
        third_level_items = [l for l in lines if re.match(r'^\s+[ivx]\.\s+', l)]
        self.assertGreaterEqual(len(third_level_items), 2)
        
        # Check indentation at each level
        for item in top_level_items:
            self.assertFalse(item.startswith(' '), "Top level should have no indentation")
        
        for item in second_level_items:
            self.assertTrue(item.startswith('    '), f"Second level should have 4 spaces: {item}")
        
        for item in third_level_items:
            self.assertTrue(item.startswith('        '), f"Third level should have 8 spaces: {item}")

    def test_list_item_with_text_and_admonition(self):
        """Test list item containing both descriptive text and inner admonition."""
        html = '''
        <ol>
            <li>Step with admonition:
                <div class="confluence-information-macro confluence-information-macro-information">
                    <div class="confluence-information-macro-body">
                        <p>Important note about this step</p>
                    </div>
                </div>
            </li>
            <li>Another step with code:
                <div class="code panel pdl">
                    <div class="codeContent panelContent pdl">
                        <pre class="syntaxhighlighter-pre">echo "test"</pre>
                    </div>
                </div>
            </li>
        </ol>
        '''
        
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Should have both list items
        self.assertIn('1.', markdown)
        self.assertIn('2.', markdown)
        # Should have admonition content
        self.assertIn('[!', markdown)
        self.assertIn('Important note', markdown)
        # Should have code block
        self.assertIn('```', markdown)
        # Should preserve text before admonition/code
        self.assertIn('Step with admonition', markdown)
        self.assertIn('Another step with code', markdown)

    def test_callout_with_list_content(self):
        """Test callout/admonition transformation preserving list structure."""
        html = '''
        <blockquote class="is-info">
            <p><strong>Important Note</strong></p>
            <ul>
                <li>First important point</li>
                <li>Second important point</li>
            </ul>
        </blockquote>
        '''
        
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Should convert to admonition syntax
        self.assertIn('[!info]', markdown)
        # Should preserve the title
        self.assertIn('Important Note', markdown)
        # Should preserve the list structure
        self.assertIn('-', markdown)
        self.assertIn('First important point', markdown)
        self.assertIn('Second important point', markdown)
    
    def test_callout_with_nested_blockquote(self):
        """Test callout/admonition with nested blockquotes preserves structure."""
        html = '''
        <blockquote class="is-warning">
            <p><strong>Nested Content</strong></p>
            <blockquote>
            <p>Inner quote content</p>
            </blockquote>
        </blockquote>
        '''
        
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Should convert to admonition syntax
        self.assertIn('[!warning]', markdown)
        # Should preserve the title
        self.assertIn('Nested Content', markdown)
        # Should preserve inner blockquote markers
        self.assertIn('> ', markdown)
        self.assertIn('Inner quote content', markdown)


if __name__ == '__main__':
    unittest.main()
