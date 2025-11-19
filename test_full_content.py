#!/usr/bin/env python3
"""Test with the FULL real Confluence HTML to check list numbering."""

import logging
from converters.markdown_converter import MarkdownConverter

REAL_FULL_HTML = '''
<div id="main-content" class="wiki-content">
<h2 id="Ansiblelokaleinrichten-Schritt-für-Schritt-Anleitung">Schritt-für-Schritt-Anleitung</h2>
<ol>
<li><p class="auto-cursor-target">Für diese Anleitung notwendige Pakete installieren</p>
<div class="code panel pdl conf-macro output-block"><div class="codeContent panelContent pdl">
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
<li><p class="auto-cursor-target">Pfad zum Ansible binary bekannt machen</p></li>
<li><p class="auto-cursor-target">Ansible version prüfen</p></li>
<li><p class="auto-cursor-target">Optional: Ansible updaten</p></li>
</ol></li>
<li><p class="auto-cursor-target">Das SSH-Keypair auf der VDI und im GitLab hinterlegen</p>
<ol><li><p class="auto-cursor-target">SSH-Verzeichnis erstellen:</p></li>
<li><p class="auto-cursor-target">Rechte setzen</p></li>
<li><p class="auto-cursor-target">Private-Key ablegen</p></li>
<li><p class="auto-cursor-target">Rechte setzen</p></li>
<li><p class="auto-cursor-target">Public-Key im GitLab hinterlegen</p></li>
</ol></li>
<li><p class="auto-cursor-target">Konfigurationsdateien anlegen</p>
<ol><li><p class="auto-cursor-target">ansible config anlegen</p></li>
<li><p class="auto-cursor-target">git config anlegen</p></li>
<li><p class="auto-cursor-target">ssh config anlegen</p></li>
<li><p class="auto-cursor-target">Umgebungsvariablen setzen</p></li>
</ol></li>
</ol>
</div>
'''

def main():
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s - %(message)s')
    
    config = {
        'target_wiki': 'wikijs',
        'confluence': {
            'base_url': 'https://confluence.oediv.lan'
        }
    }
    converter = MarkdownConverter(config=config)
    
    markdown = converter.convert_standalone_html(REAL_FULL_HTML, 'storage')
    
    print("=" * 80)
    print("CONVERTED MARKDOWN:")
    print("=" * 80)
    print(markdown)
    print("\n" + "=" * 80)
    print("CHECKING LIST NUMBERING:")
    print("=" * 80)
    
    lines = markdown.split('\n')
    for i, line in enumerate(lines):
        if re.match(r'^\s*\d+\.', line):
            print(f"Line {i}: {line}")

if __name__ == '__main__':
    import re
    main()
