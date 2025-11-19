#!/usr/bin/env python3
"""Full debug test with logging."""

import logging
from converters.html_list_fixer import HtmlListFixer
from converters.markdown_converter import MarkdownConverter

# Kurzer Abschnitt zum Debuggen
TEST_HTML = '''
<ol>
<li>Erste Anweisung</li>
</ol>
<pre class="prismjs"><code>code 1</code></pre>
<ol start="2">
<li>Zweite Anweisung</li>
</ol>
<pre class="prismjs"><code>code 2</code></pre>
<ol start="3">
<li>Dritte Anweisung</li>
</ol>
'''

def main():
    # Setup logging
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')
    
    print("=" * 80)
    print("TESTING HTML LIST FIXER")
    print("=" * 80)
    
    fixer = HtmlListFixer()
    fixed_html = fixer.fix_html(TEST_HTML)
    
    print("\nORIGINAL HTML:")
    print(TEST_HTML)
    
    print("\nFIXED HTML:")
    print(fixed_html)
    
    print("\n" + "=" * 80)
    print("TESTING MARKDOWN CONVERTER")
    print("=" * 80)
    
    config = {'target_wiki': 'wikijs', 'confluence': {'base_url': 'https://confluence.oediv.lan'}}
    logger = logging.getLogger('markdown')
    logger.setLevel(logging.DEBUG)
    converter = MarkdownConverter(logger=logger, config=config)
    
    markdown = converter.convert_standalone_html(TEST_HTML, 'export')
    
    print("\nCONVERTED MARKDOWN:")
    print(markdown)
    
    print("\n" + "=" * 80)
    print("TESTING WITH FIXER IN PIPELINE")
    print("=" * 80)
    
    markdown_fixed = converter.convert_standalone_html(fixed_html, 'export')
    
    print("\nCONVERTED MARKDOWN (nach Fixer):")
    print(markdown_fixed)

if __name__ == '__main__':
    main()
