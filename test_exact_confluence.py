#!/usr/bin/env python3
"""Test with exact Confluence HTML structure."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from converters.markdown_converter import MarkdownConverter
from converters.html_list_fixer import HtmlListFixer
from bs4 import BeautifulSoup

# Exact structure from Confluence export
html_content = '''
<ol>
<li><p class="auto-cursor-target">Für diese Anleitung notwendige Pakete installieren</p>
<div class="code panel pdl conf-macro output-block">
<pre>$ sudo apt update</pre>
</div></li>
<li><p class="auto-cursor-target">Ansible installieren</p>
<ol>
<li><p class="auto-cursor-target">Sofern Ansible bereits installiert wurde:</p>
<div class="code panel pdl conf-macro output-block">
<pre>$ sudo apt remove ansible</pre>
</div></li>
<li><p class="auto-cursor-target">Ansible installieren</p>
<div class="code panel pdl conf-macro output-block">
<pre>$ python3 -m pip install ansible</pre>
</div></li>
</ol></li>
<li><p class="auto-cursor-target">Fertig</p></li>
</ol>
'''

print("=== HTML Input ===")
print(html_content)
print()

# Apply list fixer
list_fixer = HtmlListFixer()
html_fixed = list_fixer.fix_html(html_content)

print("=== After HtmlListFixer ===")
print(html_fixed)
print()

# Parse and debug
soup = BeautifulSoup(html_fixed, 'html.parser')

def debug_structure(el, indent=0):
    prefix = "  " * indent
    if hasattr(el, 'name') and el.name:
        attrs = {k: v for k, v in el.attrs.items() if k != 'style'}
        attr_str = f" {attrs}" if attrs else ""
        print(f"{prefix}<{el.name}{attr_str}>")
        
        for child in el.children:
            debug_structure(child, indent + 1)
        
        print(f"{prefix}</{el.name}>")
    elif hasattr(el, 'strip') and el.strip():
        print(f"{prefix}'{el.strip()}'")

print("=== Structure Analysis ===")
for i, ol in enumerate(soup.find_all('ol')):
    print(f"=== Ordered List #{i+1} ===")
    for j, li in enumerate(ol.find_all('li', recursive=False)):
        print(f"  List Item #{j+1}:")
        # Check depth
        depth = 0
        ancestor = li.parent
        while ancestor:
            if ancestor.name in ['ol', 'ul']:
                depth += 1
            ancestor = ancestor.parent
        
        # Check children
        children = [c for c in li.children if hasattr(c, 'name') and c.name]
        child_names = [c.name for c in children]
        print(f"    Depth: {depth}")
        print(f"    Children: {child_names}")
        
        # Check for nested lists
        nested = li.find(['ol', 'ul'])
        if nested:
            print(f"    Has nested list: {nested.name}")
    print()

print("=== Converting to Markdown ===")
converter = MarkdownConverter()
markdown = converter.convert(html_fixed)

print("=== Final Markdown ===")
print(markdown)
print()

print("=== Raw (repr) ===")
print(repr(markdown))