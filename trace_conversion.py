#!/usr/bin/env python3
"""Trace the conversion process to understand the newline issue."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from bs4 import BeautifulSoup

# Test HTML
html = '''
<ol>
<li><p>Item 2</p>
<ol>
<li><p>Sub 2.1</p></li>
<li><p>Sub 2.2</p></li>
</ol>
</li>
</ol>
'''

print("=== Original HTML ===")
print(html)
print()

# Parse it and see structure
soup = BeautifulSoup(html, 'html.parser')

for i, li in enumerate(soup.find_all('li')):
    print(f"=== LI #{i+1} ===")
    print(f"Parent: {li.parent.name}")
    
    # Show children
    print("Children:")
    for j, child in enumerate(li.children):
        if hasattr(child, 'name'):
            print(f"  {j}: {child.name} - {repr(child.get_text()[:40])}")
        else:
            print(f"  {j}: text - {repr(str(child)[:40])}")
    
    # Check for nested lists
    nested = li.find(['ol', 'ul'])
    print(f"Has nested list: {nested is not None}")
    
    print()

# Now let's see what markdownify does to each element
print("=== What each child becomes ===")
import markdownify

for i, li in enumerate(soup.find_all('li')):
    print(f"=== LI #{i+1} with markdownify ===")
    converter = markdownify.MarkdownConverter()
    result = converter.convert_li(li, "")
    print(f"Result: {repr(result)}")
    
    # Let's see what the recursive conversion produces
    text = ""
    for child in li.children:
        if hasattr(child, 'name'):
            child_result = converter.convert_tag(child, None, None)
            print(f"  {child.name}: {repr(child_result)}")
            text += child_result
        else:
            text += str(child)
    
    print(f"Combined text: {repr(text)}")
    print()