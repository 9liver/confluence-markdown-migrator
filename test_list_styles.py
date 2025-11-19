#!/usr/bin/env python3
"""Test if list style types are now preserved."""

import logging
from converters.markdown_converter import MarkdownConverter

# HTML with different list types
TEST_HTML_ALPHA = '''
<div>
<ol>
<li>Main item 1</li>
<li>Main item 2
  <ol style="list-style-type: lower-alpha;">
    <li>Sub item</li>
    <li>Sub item</li>
  </ol>
</li>
<li>Main item 3</li>
</ol>
</div>
'''

TEST_HTML_ROMAN = '''
<div>
<ol>
<li>Main item 1</li>
<li>Main item 2
  <ol style="list-style-type: lower-roman;">
    <li>Sub item</li>
    <li>Sub item</li>
  </ol>
</li>
<li>Main item 3</li>
</ol>
</div>
'''

def test_conversion(html, title):
    print(f"\n{'='*80}")
    print(f"TESTING: {title}")
    print(f"{'='*80}")
    
    config = {'target_wiki': 'wikijs'}
    converter = MarkdownConverter(config=config)
    markdown = converter.convert_standalone_html(html, 'export')
    
    print(markdown)
    
    return markdown

def main():
    test_conversion(TEST_HTML_ALPHA, "ALPHA LOWERCASE LIST (a., b., c.)")
    test_conversion(TEST_HTML_ROMAN, "ROMAN LOWERCASE LIST (i., ii., iii.)")

if __name__ == '__main__':
    main()
