"""Tests for standalone .code.panel handling without MacroHandler."""

import unittest
from bs4 import BeautifulSoup
from converters.markdown_converter import MarkdownConverter


class TestStandaloneCodePanels(unittest.TestCase):
    def setUp(self):
        self.converter = MarkdownConverter()
    
    def test_code_panel_without_macro_handler(self):
        """Test that code panels work correctly without going through MacroHandler."""
        html = '''
        <div class="code panel pdl">
            <div class="codeHeader panelHeader"><b>install.sh</b></div>
            <div class="codeContent panelContent">
                <pre class="syntaxhighlighter-pre" data-syntaxhighlighter-params="brush: bash; gutter: false">
#!/bin/bash
echo "Installing..."
                </pre>
            </div>
        </div>
        '''
        
        # Convert without MacroHandler preprocessing
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Should have bash comment header
        self.assertIn('# install.sh', markdown)
        # Should have bash code fence
        self.assertIn('```bash', markdown)
        # Should have the script content
        self.assertIn('#!/bin/bash', markdown)
        self.assertIn('echo "Installing..."', markdown)
    
    def test_code_panel_without_header(self):
        """Test code panel without header still works."""
        html = '''
        <div class="code panel pdl">
            <div class="codeContent panelContent">
                <pre class="syntaxhighlighter-pre" data-syntaxhighlighter-params="brush: python">
print("Hello World")
                </pre>
            </div>
        </div>
        '''
        
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Should have python code fence
        self.assertIn('```python', markdown)
        # Should have the code
        self.assertIn('print("Hello World")', markdown)
        # Should NOT have a comment header
        lines = markdown.split('```')
        # Find the line before the first code fence
        before_fence = lines[0].strip()
        self.assertFalse(before_fence.endswith('), "Should not have comment header when no title")
    
    def test_code_panel_with_language_detection(self):
        """Test language detection from syntaxhighlighter params."""
        html = '''
        <div class="code panel">
            <pre data-syntaxhighlighter-params="brush: javascript">
console.log("test");
            </pre>
        </div>
        '''
        
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Should detect JavaScript
        self.assertIn('```javascript', markdown)
        # Should have JS comment prefix
        self.assertIn('console.log', markdown)
    
    def test_multiple_code_panels_in_sequence(self):
        """Test multiple code panels in sequence."""
        html = '''
        <div class="code panel">
            <div class="codeHeader"><b>script1.sh</b></div>
            <pre data-syntaxhighlighter-params="brush: bash">echo "script1"</pre>
        </div>
        <p>Some text between</p>
        <div class="code panel">
            <div class="codeHeader"><b>script2.sh</b></div>
            <pre data-syntaxhighlighter-params="brush: bash">echo "script2"</pre>
        </div>
        '''
        
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Should have both code blocks
        self.assertIn('# script1.sh', markdown)
        self.assertIn('# script2.sh', markdown)
        self.assertIn('echo "script1"', markdown)
        self.assertIn('echo "script2"', markdown)
        # Should have text between
        self.assertIn('Some text between', markdown)
    
    def test_code_panel_in_list_item(self):
        """Test code panel within list items (common case)."""
        html = '''
        <ol>
            <li>Setup step:
                <div class="code panel">
                    <pre data-syntaxhighlighter-params="brush: yaml">config: value</pre>
                </div>
            </li>
        </ol>
        '''
        
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Should have list item
        self.assertIn('1.', markdown)
        # Should have YAML code block
        self.assertIn('```yaml', markdown)
        self.assertIn('config: value', markdown)


if __name__ == '__main__':
    unittest.main()