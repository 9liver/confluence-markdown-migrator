#!/usr/bin/env python3
"""Simple debug to see if list types are being preserved."""

import logging
from bs4 import BeautifulSoup
from converters.html_list_fixer import HtmlListFixer
from converters.markdown_converter import MarkdownConverter

TEST_HTML = '''
<ol>
<li>Main item 1</li>
<li>Main item 2
  <ol style="list-style-type: lower-alpha;">
    <li>Sub item a</li>
    <li>Sub item b</li>
  </ol>
</li>
<li>Main item 3</li>
</ol>
'''

def main():
    print("STEP 1: Applying HtmlListFixer")
    fixer = HtmlListFixer()
    fixed_html = fixer.fix_html(TEST_HTML)
    
    print("Fixed HTML:")
    print(fixed_html)
    
    print("\nChecking data attributes in fixed HTML:")
    soup = BeautifulSoup(fixed_html, 'lxml')
    nested_ol = soup.find_all('ol')[1]
    print(f"  data-list-type: {nested_ol.get('data-list-type')}")
    print(f"  All attrs: {nested_ol.attrs}")
    
    print("\nSTEP 2: Converting to Markdown")
    config = {'target_wiki': 'wikijs'}
    converter = MarkdownConverter(config=config)
    
    # Monkey patch convert_li to show the list type
    original_convert_li = MarkdownConverter.convert_li
    
    def debug_convert_li(self, el, text, parent_tags=None, **kwargs):
        parent = el.parent
        if parent and parent.name == 'ol':
            list_type = parent.get('data-list-type')
            print(f"convert_li called, parent data-list-type={list_type}")
        return original_convert_li(self, el, text, parent_tags, **kwargs)
    
    MarkdownConverter.convert_li = debug_convert_li
    
    markdown = converter.convert_standalone_html(fixed_html, 'export')
    
    print("\nFinal Markdown:")
    print(markdown)

if __name__ == '__main__':
    main()
