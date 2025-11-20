"""Tests for language-specific comment headers in code blocks."""

import unittest
from bs4 import BeautifulSoup
from converters.markdown_converter import MarkdownConverter
from converters.macro_handler import MacroHandler


class TestCommentHeaders(unittest.TestCase):
    def setUp(self):
        self.converter = MarkdownConverter()
        self.macro_handler = MacroHandler()
    
    def test_bash_comment_header(self):
        """Test code blocks with bash use # for comments."""
        html = '''
        <div class="code panel">
            <div class="codeHeader"><b>~/.profile</b></div>
            <div class="codeContent">
                <pre data-syntaxhighlighter-params="brush: bash">
export PATH="$HOME/.local/bin:$PATH"
                </pre>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have bash comment
        self.assertIn('# ~/.profile', markdown)
        # Should have code fence
        self.assertIn('```bash', markdown)
    
    def test_python_comment_header(self):
        """Test code blocks with python use # for comments."""
        html = '''
        <div class="code panel">
            <div class="codeHeader"><b>hello.py</b></div>
            <div class="codeContent">
                <pre data-syntaxhighlighter-params="brush: python">
print("Hello, World!")
                </pre>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have python comment
        self.assertIn('# hello.py', markdown)
        # Should have code fence
        self.assertIn('```python', markdown)
    
    def test_javascript_comment_header(self):
        """Test code blocks with javascript use // for comments."""
        html = '''
        <div class="code panel">
            <div class="codeHeader"><b>app.js</b></div>
            <div class="codeContent">
                <pre data-syntaxhighlighter-params="brush: javascript">
console.log("Hello World");
                </pre>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have javascript comment
        self.assertIn('// app.js', markdown)
        # Should have code fence
        self.assertIn('```javascript', markdown)
    
    def test_css_comment_header(self):
        """Test code blocks with CSS use /* */ for comments."""
        html = '''
        <div class="code panel">
            <div class="codeHeader"><b>styles.css</b></div>
            <div class="codeContent">
                <pre data-syntaxhighlighter-params="brush: css">
body { margin: 0; }
                </pre>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have CSS block comment
        self.assertIn('/* styles.css */', markdown)
        # Should have code fence
        self.assertIn('```css', markdown)
    
    def test_sql_comment_header_uses_dashes(self):
        """Test code blocks with SQL use -- for comments."""
        html = '''
        <div class="code panel">
            <div class="codeHeader"><b>query.sql</b></div>
            <div class="codeContent">
                <pre data-syntaxhighlighter-params="brush: sql">
SELECT * FROM users;
                </pre>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have SQL comment
        self.assertIn('-- query.sql', markdown)
        # Should have code fence
        self.assertIn('```sql', markdown)
    
    def test_ini_comment_header_uses_semicolon(self):
        """Test code blocks with INI use ; for comments."""
        html = '''
        <div class="code panel">
            <div class="codeHeader"><b>config.ini</b></div>
            <div class="codeContent">
                <pre data-syntaxhighlighter-params="brush: ini">
[section]
key=value
                </pre>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have INI comment
        self.assertIn('; config.ini', markdown)
        # Should have code fence
        self.assertIn('```ini', markdown)
    
    def test_unknown_language_defaults_to_hash(self):
        """Test unknown language defaults to # for comments."""
        html = '''
        <div class="code panel">
            <div class="codeHeader"><b>unknown.xyz</b></div>
            <div class="codeContent">
                <pre data-syntaxhighlighter-params="brush: xyz">
content
                </pre>
            </div>
        </div>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Unknown language should default to # comment
        self.assertIn('# unknown.xyz', markdown)
        # Should have code fence (language will be xyz as-is)
        self.assertIn('```', markdown)
    
    def test_comment_header_in_nested_lists(self):
        """Test comment headers are preserved when code blocks are nested in lists."""
        html = '''
        <ol>
            <li>Step 1:
                <div class="code panel">
                    <div class="codeHeader"><b>install.sh</b></div>
                    <div class="codeContent">
                        <pre data-syntaxhighlighter-params="brush: bash">
sudo apt update
                        </pre>
                    </div>
                </div>
            </li>
        </ol>
        '''
        
        soup = BeautifulSoup(html, 'lxml')
        markdown = self.converter.convert_standalone_html(str(soup), 'export')
        
        # Should have list item
        self.assertIn('1.', markdown)
        # Should have bash comment header
        self.assertIn('# install.sh', markdown)
        # Should have code block
        self.assertIn('```bash', markdown)


if __name__ == '__main__':
    unittest.main()