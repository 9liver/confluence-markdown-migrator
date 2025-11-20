"""Tests for markdown conversion fixes using real Confluence HTML."""

import pytest
from pathlib import Path
from converters.markdown_converter import MarkdownConverter
from converters.macro_handler import MacroHandler


class TestCodeBlockConversion:
    """Test code block extraction and conversion."""
    
    def test_simple_bash_code_block(self):
        """Test basic bash code block conversion."""
        html = '''
        <div class="code panel pdl">
            <div class="codeContent panelContent pdl">
                <pre class="syntaxhighlighter-pre" data-syntaxhighlighter-params="brush: bash; gutter: false; theme: RDark">$ sudo apt update && sudo apt install python3 python3-pip git</pre>
            </div>
        </div>
        '''
        
        converter = MarkdownConverter()
        result = converter.convert(html)
        
        # Should contain the command
        assert '$ sudo apt update' in result
        assert '```bash' in result
        assert '```' in result
    
    def test_code_block_with_header(self):
        """Test code block with file header."""
        html = '''
        <div class="code panel pdl">
            <div class="codeHeader panelHeader pdl"><b>~/.profile</b></div>
            <div class="codeContent panelContent pdl">
                <pre class="syntaxhighlighter-pre" data-syntaxhighlighter-params="brush: bash; gutter: false; theme: RDark"># set PATH so it includes user's private bin if it exists
if [ -d "$HOME/.local/bin" ] ; then
    PATH="$HOME/.local/bin:$PATH"
fi</pre>
            </div>
        </div>
        '''
        
        converter = MarkdownConverter()
        result = converter.convert(html)
        
        # Should contain header as comment
        assert '~/.profile' in result
        # Should contain code
        assert 'set PATH' in result
        assert '```bash' in result
    
    def test_multiline_code_block(self):
        """Test multiline configuration file."""
        html = '''
        <div class="code panel pdl">
            <div class="codeHeader panelHeader pdl"><b>~/.ansible/ansible.cfg</b></div>
            <div class="codeContent panelContent pdl">
                <pre class="syntaxhighlighter-pre" data-syntaxhighlighter-params="brush: text; gutter: true; theme: RDark">[defaults]
forks = 10
timeout = 20
vault_password_file = $HOME/.vault_pass
remote_user = <username></pre>
            </div>
        </div>
        '''
        
        converter = MarkdownConverter()
        result = converter.convert(html)
        
        # Should contain all lines
        assert '[defaults]' in result
        assert 'forks = 10' in result
        assert 'vault_password_file' in result
        # Should have header
        assert 'ansible.cfg' in result


class TestListConversion:
    """Test nested list conversion."""
    
    def test_nested_ordered_list_with_code(self):
        """Test nested list containing code blocks."""
        html = '''
        <ol>
            <li>First item
                <ol>
                    <li>Nested item with code:
                        <div class="code panel pdl">
                            <div class="codeContent panelContent pdl">
                                <pre class="syntaxhighlighter-pre" data-syntaxhighlighter-params="brush: bash">$ mkdir ~/.ssh</pre>
                            </div>
                        </div>
                    </li>
                </ol>
            </li>
        </ol>
        '''
        
        converter = MarkdownConverter()
        result = converter.convert(html)
        
        # Should have proper list structure
        assert '1. First item' in result
        # Should have nested item (with letter marker)
        assert 'a. Nested item' in result or 'i. Nested item' in result
        # Should have code block
        assert '$ mkdir ~/.ssh' in result
        # Should NOT have literal \n
        assert '\\n' not in result
    
    def test_no_literal_newlines(self):
        """Ensure no literal \n characters in output."""
        html = '''
        <ol>
            <li>Item one</li>
            <li>Item two
                <ol>
                    <li>Nested</li>
                </ol>
            </li>
        </ol>
        '''
        
        converter = MarkdownConverter()
        result = converter.convert(html)
        
        # Should NOT contain literal backslash-n
        assert '\\n' not in result
        # Should have actual newlines
        assert '\n' in result


class TestAdmonitionConversion:
    """Test info/warning box conversion."""
    
    def test_info_macro_conversion(self):
        """Test info macro to admonition."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-information">
            <span class="aui-icon aui-icon-small aui-iconfont-info confluence-information-macro-icon"></span>
            <div class="confluence-information-macro-body">
                <p>This is important information</p>
            </div>
        </div>
        '''
        
        converter = MarkdownConverter()
        result = converter.convert(html)
        
        # Should be admonition format
        assert '> [!info]' in result.lower() or '> [!note]' in result.lower()
        assert 'important information' in result
    
    def test_consecutive_admonitions(self):
        """Test multiple admonitions have proper spacing."""
        html = '''
        <div class="confluence-information-macro confluence-information-macro-information">
            <div class="confluence-information-macro-body"><p>First info</p></div>
        </div>
        <div class="confluence-information-macro confluence-information-macro-warning">
            <div class="confluence-information-macro-body"><p>Second warning</p></div>
        </div>
        '''
        
        converter = MarkdownConverter()
        result = converter.convert(html)
        
        # Should have both admonitions
        assert 'First info' in result
        assert 'Second warning' in result
        # Should have blank line between them
        lines = result.split('\n')
        # Find the end of first admonition and start of second
        # There should be at least one blank line between
        assert result.count('\n\n') >= 1


class TestFullPageConversion:
    """Test conversion of the full Ansible page."""
    
    def test_full_page_has_all_sections(self):
        """Test that full page conversion includes all major sections."""
        # Load the actual HTML file
        html_path = Path(__file__).parent.parent / 'raw_html_244744731.html'
        if not html_path.exists():
            pytest.skip("Raw HTML file not found")
        
        html = html_path.read_text(encoding='utf-8')
        
        converter = MarkdownConverter()
        result = converter.convert(html)
        
        # Check for major sections
        assert 'Schritt-für-Schritt-Anleitung' in result
        assert 'Verwandte Artikel' in result
        
        # Check for code blocks
        assert '$ sudo apt update' in result
        assert '$ mkdir ~/.ssh' in result
        assert '$ chmod 700 ~/.ssh' in result
        
        # Check for config files
        assert '[defaults]' in result
        assert 'ansible.cfg' in result or 'ansible/ansible.cfg' in result
        
        # Check no literal newlines
        assert '\\n' not in result
        
        # Check content length (should be substantial)
        assert len(result) > 3000, f"Result too short: {len(result)} chars"
