#!/usr/bin/env python3
"""Debug indentation issues."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from converters.markdown_converter import MarkdownConverter
from converters.html_list_fixer import HtmlListFixer
from bs4 import BeautifulSoup

html_content = '''
<ol>
<li>Main item 1</li>
<li>Main item 2
  <ol>
    <li>Sub item 1</li>
    <li>Sub item 2</li>
  </ol>
</li>
<li>Main item 3</li>
</ol>
'''

print("=== Original HTML ===")
print(html_content)
print()

# Apply list fixer
list_fixer = HtmlListFixer()
html_fixed = list_fixer.fix_html(html_content)
print("=== After HtmlListFixer ===")
print(html_fixed)
print()

# Parse and check depth
def debug_depth(el, label=""):
    depth = 0
    ancestor = el.parent
    while ancestor:
        if ancestor.name in ['ol', 'ul']:
            depth += 1
        ancestor = ancestor.parent
    print(f"{label}: depth={depth}, tag={el.name}, parent={el.parent.name if el.parent else None}")

soup = BeautifulSoup(html_fixed, 'html.parser')
for i, li in enumerate(soup.find_all('li')):
    debug_depth(li, f"li[{i}]")
    
print()

# Convert to markdown
converter = MarkdownConverter()
markdown = converter.convert(html_fixed)

print("=== Final Markdown ===")
print(markdown)
print()
print("=== Raw (repr) ===")
print(repr(markdown))