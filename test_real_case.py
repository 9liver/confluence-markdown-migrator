#!/usr/bin/env python3
"""Test script for the real Confluence HTML case provided by user."""

import logging
from converters.markdown_converter import MarkdownConverter

# The raw HTML from the user's message
SAMPLE_HTML = '''<p>Diese Anleitung beschreibt, wie unsere Ansible-Umgebung für die Entwicklung und Tests lokal eingerichtet werden kann.</p>
<blockquote>
<p>[!INFO]<br>
Alle Pfade in dieser Anleitung sind natürlich als persönliche Vorlieben anzusehen und frei nach belieben anzupassen<br>
<img src="https://confluence.oediv.lan/s/t1v677/8703/51k4y0/_/images/icons/emoticons/smile.svg" alt="(smile)"></p>
</blockquote>
<p>Diese Anleitung setzt vorraus, dass die VDI bereits eingerichtet ist, da hier mindestens der lokale squid für den<br>
Zugriff von pip benötigt wird!</p>
<p>Ab&nbsp;<a href="https://confluence.oediv.lan/pages/viewpage.action?pageId=244744731" class="is-external-link">Punkt 3</a> kann diese Anleitung auch verwendet<br>
werden, um Ansible auf der sys-oed-103-u zu konfigurieren</p>
<p>Changelog</p>
<p>2024-10-31: Anpassung von Links und Configs an das neue GitLab</p>
<h2 id="schritt-für-schritt-anleitung" class="toc-header"><a class="toc-anchor" href="#schritt-für-schritt-anleitung">¶</a> Schritt-für-Schritt-Anleitung</h2>
<ol>
<li>Für diese Anleitung notwendige Pakete installieren</li>
</ol>
<pre class="prismjs line-numbers" v-pre="true"><code class="language-bash">$ sudo apt update &amp;&amp; sudo apt install python3 python3-pip git</code></pre>
<ol start="2">
<li>
<p>Da die Ansible Version aus den offiziellen repos zu alt ist und einige module fehlen installieren wir <a href="https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html#pip-install" class="is-external-link">Ansi (https://s2swiki.oediv.lan/_assets/favicons/apple-touch-icon.png)ble über<br>
pip</a></p>
</li>
<li>
<p>Sofern Ansible bereits über die Paketverwaltung installiert wur (https://s2swiki.oediv.lan/_assets/favicons/android-chrome-192x192.png)de:<code>&nbsp;</code></p>
</li>
</ol>
<pre class="prismjs line-numbers" v-pre="true"><code (https://s2swiki.oediv.lan/_assets/favicons/favicon-32x32.png) class="language-bash">$ sudo apt remove ansible</code></pre>
<ol start="2">
<li>Ansible i (https://s2swiki.oediv.lan/_assets/favicons/favicon-16x16.png)nstallieren</li>
</ol>
<pre class="prismjs line-numbers" v-pre="true" (https://s2swiki.oediv.lan/_assets/favicons/safari-pinned-tab.svg)><code class="language-bash">$ python3 -m pip install --proxy http: (https://s2swiki.oediv.lan/_assets/manifest.json)//127.0.0.1:3128 --user ansible</code></pre>
<ol start="3">
<li>Pfad zum Ansible binary bekannt machen in <code>~/.profile</code></li>
</ol>
<p><strong>~/.profile</strong></p>
<pre class="prismjs line-numbers" v-pre="true"><code class="language-bash"># set PATH so it includes user\'s private bin if it exists
if [ -d "$HOME/.local/bin" ] ; then
    PATH="$HOME/.local/bin: (https://use.fontawesome.com/releases/v5.10.0/css/all.css)$PATH"
fi</code></pre>
<blockquote>
<p>[!WARNING]<br>
Eventuell bereits in der standard (https://s2swiki.oediv.lan/_assets/css/app.2144b7acef37b4a5cc2e.css) <code>.profile</code> vorhanden, bitte prüfen</p>
<p><code>.profile</c (https://s2swiki.oediv.lan/_assets/js/runtime.js?1755069093)ode> wird beim Login einmalig eingelesen. Falls <code>.local/bin</code> nich (https://s2swiki.oediv.lan/_assets/js/app.js?1755069093)t bereits vorher existierte ist ein relogin<br>
notwendig. Da ein relogin mit Citrix so meines Wissens nicht möglich ist, wäre hier ein reboot notwendig.</p>
<p>Alternativ vorerst zur Laufzeit</p>
<pre class="prismjs line-numbers" v-pre="true"><code class="language-bash">export PATH="$HOME/.local/bin:$PATH"</code></pre>
</blockquote>
<ol start="4">
<li>Ansible version prüfen</li>
</ol>
<pre class="prismjs line-numbers" v-pre="true"><code class="language-">
bash
$ ansible --version
</code></pre>'''

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
