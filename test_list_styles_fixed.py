#!/usr/bin/env python3
"""Test the list type detection with actual Confluence format."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from converters.markdown_converter import MarkdownConverter
from converters.html_list_fixer import HtmlListFixer
from bs4 import BeautifulSoup

# Test 1: Alpha lower list
html_alpha = '''<ol>
<li>Main item 1</li>
<li>Main item 2
  <ol style="list-style-type: lower-alpha;">
    <li>Sub item a</li>
    <li>Sub item b</li>
  </ol>
</li>
<li>Main item 3</li>
</ol>'''

print("=" * 80)
print("TESTING: ALPHA LOWERCASE LIST (a., b., c.)")
print("=" * 80)

# Parse and check if style is detected
soup = BeautifulSoup(html_alpha, 'html.parser')
for i, ol in enumerate(soup.find_all('ol')):
    style = ol.get('style', '')
    print(f"OL #{i+1} style: {repr(style)}")

# Test the detection logic directly
list_fixer = HtmlListFixer()
detected = list_fixer._detect_list_type(soup.find('ol').find('ol'))
print(f"Detected list type: {detected}")

fixed = list_fixer.fix_html(html_alpha)
print("\nFixed HTML:")
print(fixed)

# Check data attributes
soup2 = BeautifulSoup(fixed, 'html.parser')
for i, ol in enumerate(soup2.find_all('ol')):
    data_type = ol.get('data-list-type')
    print(f"OL #{i+1} data-list-type: {repr(data_type)}")

converter = MarkdownConverter()
markdown = converter.convert(fixed)
print("\nMarkdown output:")
print(markdown)
print("\n" + "=" * 80)