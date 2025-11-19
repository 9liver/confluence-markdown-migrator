#!/usr/bin/env python3
"""Test the complete pipeline with alpha lists."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from converters.markdown_converter import MarkdownConverter
from converters.html_list_fixer import HtmlListFixer
from bs4 import BeautifulSoup

# Test with alpha list
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

print("=== TEST: Alpha list conversion ===")
print("Input HTML:")
print(html_alpha)
print()

# Apply list fixer
list_fixer = HtmlListFixer()
fixed = list_fixer.fix_html(html_alpha)

print("After HtmlListFixer:")
print(fixed)
print()

# Check data attributes
soup = BeautifulSoup(fixed, 'html.parser')
for i, ol in enumerate(soup.find_all('ol')):
    data_type = ol.get('data-list-type')
    style = ol.get('style')
    print(f"OL #{i+1}: style={repr(style)}, data-list-type={repr(data_type)}")

# Convert to markdown
converter = MarkdownConverter()
markdown = converter.convert(fixed)

print("\nFinal Markdown:")
print(markdown)
print("\nRaw repr:")
print(repr(markdown))