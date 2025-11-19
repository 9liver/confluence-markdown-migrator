#!/usr/bin/env python3
"""Test script for real Confluence HTML to see markdown conversion issues."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from converters.markdown_converter import MarkdownConverter
from converters.html_list_fixer import HtmlListFixer
from bs4 import BeautifulSoup

# Load real Confluence HTML
with open('test_real_confluence.html', 'r') as f:
    html_content = f.read()

print("=== STEP 1: Original HTML ===")
print(html_content)
print()

# Parse with BeautifulSoup
soup = BeautifulSoup(html_content, 'html.parser')
content_div = soup.find('div', {'id': 'main-content'})
if content_div:
    html_content = str(content_div)

print("=== STEP 2: After extracting main-content ===")
print(html_content)
print()

# Apply list fixer
list_fixer = HtmlListFixer()
html_content = list_fixer.fix_html(html_content)

print("=== STEP 3: After HtmlListFixer ===")
print(html_content)
print()

# Convert to markdown
converter = MarkdownConverter()
markdown = converter.convert(html_content)

print("=== STEP 4: Final Markdown ===")
print(markdown)
print()

print("=== STEP 5: Show raw markdown (repr) ===")
print(repr(markdown))