#!/usr/bin/env python3
"""Debug why nested list indentation might fail."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from bs4 import BeautifulSoup
from converters.markdown_converter import MarkdownConverter
from converters.html_list_fixer import HtmlListFixer

# Simple nested list - should work
html = '''
<ol>
<li>Item 1</li>
<li>Item 2
<ol>
<li>Sub 2.1</li>
<li>Sub 2.2</li>
</ol>
</li>
<li>Item 3</li>
</ol>
'''

print("=== Test 1: Simple nested list ===")
soup = BeautifulSoup(html, 'html.parser')
list_fixer = HtmlListFixer()
fixed = list_fixer.fix_html(html)

converter = MarkdownConverter()
markdown = converter.convert(fixed)
print(markdown)
print()

# Confluence-style with <p> tags
html2 = '''
<ol>
<li><p>Item 1</p></li>
<li><p>Item 2</p>
<ol>
<li><p>Sub 2.1</p></li>
<li><p>Sub 2.2</p></li>
</ol>
</li>
<li><p>Item 3</p></li>
</ol>
'''

print("=== Test 2: Confluence style with <p> tags ===")
soup2 = BeautifulSoup(html2, 'html.parser')
fixed2 = list_fixer.fix_html(html2)
markdown2 = converter.convert(fixed2)
print(markdown2)
print()

# Check what's happening
print("=== Debug: Check structure of Test 2 ===")
ss = BeautifulSoup(fixed2, 'html.parser')
for i, li in enumerate(ss.find_all('li')):
    print(f"li[{i}]: parent={li.parent.name}, content={repr(li.get_text()[:30])}")
    
    # Check depth calculation
    depth = 0
    ancestor = li.parent
    while ancestor:
        if ancestor.name in ['ol', 'ul']:
            depth += 1
        ancestor = ancestor.parent
    print(f"  Depth: {depth}")
    
    # Check what markdownify base does
    import markdownify
    base_converter = markdownify.MarkdownConverter()
    base_result = base_converter.convert(str(li))
    print(f"  Base markdownify: {repr(base_result)}")
print()

# Let's trace the actual convert_li calls
print("=== Debug: Tracing convert_li calls ===")
# Monkey patch to trace
original_convert_li = MarkdownConverter.convert_li

def traced_convert_li(self, el, text, parent_tags=None, **kwargs):
    result = original_convert_li(self, el, text, parent_tags, **kwargs)
    print(f"convert_li: text={repr(text)[:50]}, result={repr(result)[:50]}")
    return result

MarkdownConverter.convert_li = traced_convert_li

converter2 = MarkdownConverter()
markdown3 = converter2.convert(fixed2)
print("=== Final output with tracing ===")
print(markdown3)