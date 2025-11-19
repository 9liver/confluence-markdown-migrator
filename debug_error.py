#!/usr/bin/env python3
"""Debug the NoneType error in html_list_fixer."""

import logging
from converters.html_list_fixer import HtmlListFixer

# Create test HTML that should trigger the error
TEST_HTML = '''
<h2>Test Überschrift</h2>
<p>Some text</p>
<ol>
<li>Item 1</li>
</ol>
<div class="confluence-information-macro">
<p>Info box</p>
</div>
<pre class="syntaxhighlighter-pre"><code>test code</code></pre>
'''

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(levelname)s - %(message)s')
    logger = logging.getLogger('debug')
    
    print("Testing HtmlListFixer...")
    
    fixer = HtmlListFixer()
    
    try:
        result = fixer.fix_html(TEST_HTML)
        print("✓ Success!")
        print("Result:", result)
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()
