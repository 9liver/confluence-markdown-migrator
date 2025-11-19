#!/usr/bin/env python3
"""Debug script to trace what the list fixer does."""

import logging
from bs4 import BeautifulSoup
from converters.html_list_fixer import HtmlListFixer

# Shortened HTML for debugging
DEBUG_HTML = '''
<ol>
<li>Item 1</li>
</ol>
<pre><code>code 1</code></pre>
<ol start="2">
<li>Item 2</li>
</ol>
<pre><code>code 2</code></pre>
<ol start="3">
<li>Item 3</li>
</ol>
'''

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')
    logger = logging.getLogger('debug')
    
    print("BEFORE:")
    print("=" * 80)
    soup = BeautifulSoup(DEBUG_HTML, 'lxml')
    print(str(soup.body))
    print("=" * 80)
    
    print("\\nFINDING OLS:")
    for i, ol in enumerate(soup.find_all('ol')):
        print(f"OL #{i}: start={ol.get('start')}")
        print(f"  Prev sibling: {ol.previous_sibling}")
        print(f"  Next sibling: {ol.next_sibling}")
        print(f"  Next element sibling: {ol.find_next_sibling()}")
    
    fixer = HtmlListFixer(logger)
    fixed = fixer.fix_html(DEBUG_HTML)
    
    print("\n\\nAFTER:")
    print("=" * 80)
    soup = BeautifulSoup(fixed, 'lxml')
    print(str(soup.body))
    print("=" * 80)

if __name__ == '__main__':
    main()
