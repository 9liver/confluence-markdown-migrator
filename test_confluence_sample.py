#!/usr/bin/env python3
"""Test script for Confluence HTML to Markdown conversion."""

import logging
from converters.markdown_converter import MarkdownConverter

# Sample Confluence HTML (excerpt from the Ansible setup guide)
SAMPLE_HTML = '''
<p>Diese Anleitung beschreibt, wie unsere Ansible-Umgebung für die Entwicklung und Tests lokal eingerichtet werden kann.</p>
<div class="confluence-information-macro confluence-information-macro-information conf-macro output-block" data-hasbody="true" data-macro-name="info">
    <span class="aui-icon aui-icon-small aui-iconfont-info confluence-information-macro-icon"> </span>
    <div class="confluence-information-macro-body">
        <p>Alle Pfade in dieser Anleitung sind natürlich als persönliche Vorlieben anzusehen und frei nach belieben anzupassen</p>
    </div>
</div>
<div class="confluence-information-macro confluence-information-macro-information conf-macro output-block" data-hasbody="true" data-macro-name="info">
    <p class="title">Changelog</p>
    <span class="aui-icon aui-icon-small aui-iconfont-info confluence-information-macro-icon"> </span>
    <div class="confluence-information-macro-body">
        <p>2024-10-31: Anpassung von Links und Configs an das neue GitLab</p>
    </div>
</div>
<h2 id="Ansiblelokaleinrichten-Schritt-für-Schritt-Anleitung">Schritt-für-Schritt-Anleitung</h2>
<ol>
    <li>
        <p class="auto-cursor-target">Für diese Anleitung notwendige Pakete installieren</p>
        <div class="code panel pdl conf-macro output-block" style="border-width: 1px;" data-hasbody="true" data-macro-name="code">
            <div class="codeContent panelContent pdl">
                <pre class="syntaxhighlighter-pre" data-syntaxhighlighter-params="brush: bash; gutter: false; theme: RDark" data-theme="RDark">$ sudo apt update &amp;&amp; sudo apt install python3 python3-pip git</pre>
            </div>
        </div>
    </li>
    <li>
        <p class="auto-cursor-target">Da die Ansible Version aus den offiziellen repos zu alt ist installieren wir <a href="https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html#pip-install" class="external-link" rel="nofollow">Ansible über pip</a></p>
        <ol>
            <li>
                <p class="auto-cursor-target">Sofern Ansible bereits über die Paketverwaltung installiert wurde:</p>
                <div class="code panel pdl conf-macro output-block" style="border-width: 1px;" data-hasbody="true" data-macro-name="code">
                    <div class="codeContent panelContent pdl">
                        <pre class="syntaxhighlighter-pre" data-syntaxhighlighter-params="brush: bash; gutter: false; theme: RDark" data-theme="RDark">$ sudo apt remove ansible</pre>
                    </div>
                </div>
            </li>
            <li>
                <p class="auto-cursor-target">Ansible installieren</p>
                <div class="code panel pdl conf-macro output-block" style="border-width: 1px;" data-hasbody="true" data-macro-name="code">
                    <div class="codeContent panelContent pdl">
                        <pre class="syntaxhighlighter-pre" data-syntaxhighlighter-params="brush: bash; gutter: false; theme: RDark" data-theme="RDark">$ python3 -m pip install --proxy http://127.0.0.1:3128 --user ansible</pre>
                    </div>
                </div>
            </li>
            <li>
                <p class="auto-cursor-target">Pfad zum Ansible binary bekannt machen in <code>~/.profile</code></p>
                <div class="code panel pdl conf-macro output-block" style="border-width: 1px;" data-hasbody="true" data-macro-name="code">
                    <div class="codeHeader panelHeader pdl" style="border-bottom-width: 1px;"><b>~/.profile</b></div>
                    <div class="codeContent panelContent pdl">
                        <pre class="syntaxhighlighter-pre" data-syntaxhighlighter-params="brush: bash; gutter: false; theme: RDark" data-theme="RDark"># set PATH so it includes user's private bin if it exists
if [ -d "$HOME/.local/bin" ] ; then
    PATH="$HOME/.local/bin:$PATH"
fi</pre>
                    </div>
                </div>
                <div class="confluence-information-macro confluence-information-macro-note conf-macro output-block" data-hasbody="true" data-macro-name="note">
                    <span class="aui-icon aui-icon-small aui-iconfont-warning confluence-information-macro-icon"> </span>
                    <div class="confluence-information-macro-body">
                        <p>Eventuell bereits in der standard <code>.profile</code> vorhanden, bitte prüfen</p>
                    </div>
                </div>
            </li>
        </ol>
    </li>
    <li>
        <p class="auto-cursor-target">Das SSH-Keypair auf der VDI und im GitLab hinterlegen<span class="confluence-anchor-link conf-macro output-inline" id="Ansiblelokaleinrichten-3" data-hasbody="false" data-macro-name="anchor"> </span></p>
    </li>
</ol>
'''

def main():
    # Setup logging
    logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')
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
    markdown = converter.convert_standalone_html(SAMPLE_HTML, 'export')

    print("=" * 80)
    print("CONVERTED MARKDOWN:")
    print("=" * 80)
    print(markdown)
    print("=" * 80)

if __name__ == '__main__':
    main()
