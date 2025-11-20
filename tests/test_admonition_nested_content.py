"""Tests for nested content preservation in admonitions."""

import unittest
from bs4 import BeautifulSoup
from converters.markdown_converter import MarkdownConverter
from converters.macro_handler import MacroHandler


class TestAdmonitionNestedContent(unittest.TestCase):
    def setUp(self):
        self.converter = MarkdownConverter()
        self.macro_handler = MacroHandler()
    
    def test_admonition_with_nested_list(self):
        """Test admonitions preserve nested list structure."""
        html = '''
        <blockquote class="is-info" data-callout="info">
            <p><strong>Important Notes</strong></p>
            <ul>
                <li>First item</li>
                <li>Second item with sub-items:
                    <ul>
                        <li>Sub-item 1</li>
                        <li>Sub-item 2</li>
                    </ul>
                </li>
                <li>Third item</li>
            </ul>
        </blockquote>
        '''
        
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Should have admonition marker
        self.assertIn('[!info]', markdown)
        self.assertIn('Important Notes', markdown)
        
        # Should preserve the nested list structure
        # The list should be indented within the admonition
        lines = markdown.strip().split('\n')
        list_lines = [l for l in lines if l.strip().startswith('> -')]
        self.assertEqual(len(list_lines), 3, "Should have 3 main list items")
        
        # Check for nested sub-items with proper indentation
        nested_lines = [l for l in lines if 'Sub-item' in l]
        for line in nested_lines:
            self.assertTrue(line.startswith('> '), "All admonition lines should start with '> '")
            self.assertIn('Sub-item', line)
    
    def test_admonition_with_code_block(self):
        """Test admonitions preserve code blocks."""
        html = '''
        <blockquote class="is-info" data-callout="info">
            <p><strong>Setup Instructions</strong></p>
            <pre><code>sudo apt update
sudo apt install python3</code></pre>
            <p>Run these commands carefully.</p>
        </blockquote>
        '''
        
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Should have admonition marker
        self.assertIn('[!info]', markdown)
        self.assertIn('Setup Instructions', markdown)
        
        # Should preserve the code block
        self.assertIn('```', markdown)
        self.assertIn('sudo apt update', markdown)
        self.assertIn('Run these commands carefully', markdown)
        
        # Check that code block is properly indented within admonition
        lines = markdown.strip().split('\n')
        code_fence_line = [i for i, l in enumerate(lines) if '```' in l][0]
        self.assertTrue(lines[code_fence_line].startswith('> '), "Code block should be inside admonition")
    
    def test_info_macro_with_nested_content(self):
        """Test that info macros with nested lists/code are handled correctly."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-information">
            <div class="confluence-information-macro-body">
                <p>Configuration steps:</p>
                <ol>
                    <li>Edit the config file:
                        <div class="code panel">
                            <pre data-syntaxhighlighter-params="brush: yaml">
server:
  port: 8080
                            </pre>
                        </div>
                    </li>
                    <li>Restart the service</li>
                </ol>
                <p>Verify it's working.</p>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        soup, stats, warnings = self.macro_handler.convert(soup, 'export')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should use admonition syntax
        self.assertIn('[!info]', markdown)
        
        # Should preserve ordered list
        self.assertIn('1.', markdown)
        self.assertIn('2.', markdown)
        
        # Should preserve YAML code block with comment header
        self.assertIn('# config file', markdown)
        self.assertIn('```yaml', markdown)
        self.assertIn('port: 8080', markdown)
        
        # Should preserve final paragraph
        self.assertIn('Verify it's working', markdown)
    
    def test_admonition_with_multiple_paragraphs(self):
        """Test admonitions preserve multiple paragraphs."""
        html = '''
        <blockquote class="is-warning" data-callout="warning">
            <p><strong>Warning</strong></p>
            <p>This is the first paragraph with important information.</p>
            <p>This is the second paragraph with more details.</p>
            <ul>
                <li>A list item</li>
            </ul>
            <p>Final paragraph.</p>
        </blockquote>
        '''
        
        markdown = self.converter.convert_standalone_html(html, 'export')
        
        # Should have admonition marker
        self.assertIn('[!warning]', markdown)
        self.assertIn('Warning', markdown)
        
        # Should preserve all content
        self.assertIn('first paragraph', markdown)
        self.assertIn('second paragraph', markdown)
        self.assertIn('list item', markdown)
        self.assertIn('Final paragraph', markdown)
    
    def test_deeply_nested_structure_in_admonition(self):
        """Test very deeply nested structures are preserved."""
        html = '''
        <blockquote class="is-info" data-callout="info">
            <p><strong>Complex Example</strong></p>
            <ol>
                <li>Level 1 item
                    <ul>
                        <li>Level 2 bullet
                            <ol>
                                <li>Level 3 numbered
                                    <div class="code panel">
                                        <pre data-syntaxhighlighter-params="brush: bash">
echo "Deep nesting"
                                        </pre>
                                    </div>
                                </li>
                            </ol>
                        </li>
                    </ul>
                </li>
            </ol>
        </blockquote>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have admonition
        self.assertIn('[!info]', markdown)
        
        # Should have complex nested content
        self.assertIn('Level 1 item', markdown)
        self.assertIn('Level 2 bullet', markdown)
        self.assertIn('Level 3 numbered', markdown)
        self.assertIn('# Deep Example', markdown)
        self.assertIn('```bash', markdown)
        self.assertIn('echo "Deep nesting"', markdown)


if __name__ == '__main__':
    unittest.main()