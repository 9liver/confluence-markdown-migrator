#!/usr/bin/env python3
"""Test with the real Confluence HTML to see nested list issues."""

import logging
from converters.markdown_converter import MarkdownConverter

# Real Confluence HTML (first part with nested lists)
REAL_HTML = '''<div id="main-content" class="wiki-content">
<ol>
<li><p class="auto-cursor-target">Für diese Anleitung notwendige Pakete installieren</p>
<div class="code panel pdl conf-macro output-block" style="border-width: 1px;" data-hasbody="true" data-macro-name="code">
<div class="codeContent panelContent pdl">
<pre class="syntaxhighlighter-pre">$ sudo apt update && sudo apt install python3 python3-pip git</pre>
</div></div></li>
<li><p class="auto-cursor-target">Da die Ansible Version aus den offiziellen repos zu alt ist ...</p>
<ol><li><p class="auto-cursor-target">Sofern Ansible bereits über die Paketverwaltung installiert wurde:</p>
<div class="code panel pdl conf-macro output-block">
<div class="codeContent panelContent pdl">
<pre class="syntaxhighlighter-pre">$ sudo apt remove ansible</pre>
</div></div></li>
<li><p class="auto-cursor-target">Ansible installieren</p>
<div class="code panel pdl conf-macro output-block">
<div class="codeContent panelContent pdl">
<pre class="syntaxhighlighter-pre">$ python3 -m pip install --proxy http://127.0.0.1:3128 --user ansible</pre>
</div></div></li>
<li><p class="auto-cursor-target">Pfad zum Ansible binary bekannt machen...</p></li>
</ol></li>
<li><p class="auto-cursor-target">Das SSH-Keypair auf der VDI und im GitLab hinterlegen</p></li>
</ol>
</div>'''

def main():
    # Setup logging
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')
    logger = logging.getLogger('test')
    
    # Create converter
    config = {
        'target_wiki': 'wikijs',
        'confluence': {
            'base_url': 'https://confluence.oediv.lan'
        }
    }
    converter = MarkdownConverter(logger=logger, config=config)
    
    # Convert HTML to markdown
    markdown = converter.convert_standalone_html(REAL_HTML, 'storage')
    
    print("=" * 80)
    print("CONVERTED MARKDOWN:")
    print("=" * 80)
    print(markdown)
    print("=" * 80)

if __name__ == '__main__':
    main()
