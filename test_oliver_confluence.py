#!/usr/bin/env python3
"""Test with Oliver's actual Confluence export HTML structure."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from converters.markdown_converter import MarkdownConverter
from converters.html_list_fixer import HtmlListFixer
from bs4 import BeautifulSoup

# Extract the problematic section from Oliver's export
html = '''
<ol>
<li><p class="auto-cursor-target">Für diese Anleitung notwendige Pakete installieren</p></li>
<li><p class="auto-cursor-target">Da die Ansible Version aus den offiziellen repos zu alt ist und einige module fehlen installieren wir <a href="https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html#pip-install" class="external-link" rel="nofollow">Ansible über pip</a></p>
<ol>
<li><p class="auto-cursor-target">Sofern Ansible bereits über die Paketverwaltung installiert wurde:</p></li>
<li><p class="auto-cursor-target">Ansible installieren</p></li>
</ol>
</li>
</ol>
'''

print("=== Input HTML ===")
print(html)
print()

# Apply list fixer
list_fixer = HtmlListFixer()
fixed = list_fixer.fix_html(html)

print("=== After HtmlListFixer ===")
print(fixed)
print()

# Convert to markdown
converter = MarkdownConverter()
markdown = converter.convert(fixed)

print("=== Final Markdown ===")
print(markdown)
print()

print("=== Comparison: Before vs After Fix ===")
print("BEFORE (with extra newlines):")
print("2. Item 2\n\n   1. Sub 1\n   2. Sub 2")
print()
print("AFTER (correct indentation, no extra newlines):")
print("2. Item 2\n   1. Sub 1\n   2. Sub 2")
print()

print("=== Raw repr ===")
print(repr(markdown))