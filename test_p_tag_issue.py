#!/usr/bin/env python3
"""Test the p tag issue with newlines."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from bs4 import BeautifulSoup
from converters.markdown_converter import MarkdownConverter
from converters.html_list_fixer import HtmlListFixer

# HTML similar to Confluence export
html = '''
<ol>
<li><p>Item 1</p></li>
<li><p>Item 2</p><ol><li><p>Sub 1</p></li><li><p>Sub 2</p></li></ol></li>
<li><p>Item 3</p></li>
</ol>
'''

print("Input HTML:")
print(html)
print()

# Apply fixer
list_fixer = HtmlListFixer()
fixed = list_fixer.fix_html(html)

print("After HtmlListFixer:")
print(fixed)
print()

# Convert
converter = MarkdownConverter()
markdown = converter.convert(fixed)

print("Final Markdown:")
print(markdown)
print("\nRaw repr:")
print(repr(markdown))

# Now let's check what causes the extra newlines
print("\n=== Debugging the p tags ===")
soup = BeautifulSoup(fixed, 'html.parser')

for li in soup.find_all('li'):
    print(f"\nList item with parent {li.parent.name}:")
    inner_html = ''.join(str(child) for child in li.children)
    print(f"Inner HTML: {repr(inner_html[:80])}")
    
    # Check if it has nested lists
    nested = li.find(['ol', 'ul'])
    if nested:
        print("Has nested list!")
        # The issue: p tags create newlines and then the nested list
        p = li.find('p')
        if p:
            print(f"p tag text: {repr(p.get_text())}")
    else:
        print("No nested list")