#!/usr/bin/env python3
"""Debug the full pipeline to see where list types are lost."""

import logging
from bs4 import BeautifulSoup
from converters.html_list_fixer import HtmlListFixer
from converters.markdown_converter import MarkdownConverter

# Test HTML
TEST_HTML = '''
<div>
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
</div>
'''

def debug_pipeline():
    print("="*80)
    print("STEP 1: Original HTML")
    print("="*80)
    print(TEST_HTML)
    
    print("\n" + "="*80)
    print("STEP 2: After HtmlListFixer")
    print("="*80)
    
    fixer = HtmlListFixer()
    fixed_html = fixer.fix_html(TEST_HTML)
    print(fixed_html)
    
    # Check if data attributes were set
    soup = BeautifulSoup(fixed_html, 'lxml')
    nested_ol = soup.find_all('ol')[1]  # The nested one
    print(f"\nNested <ol> after fixer:")
    print(f"  data-list-type: {nested_ol.get('data-list-type')}")
    print(f"  All attributes: {nested_ol.attrs}")
    
    print("\n" + "="*80)
    print("STEP 3: During Markdown Conversion")
    print("="*80)
    
    # Monkey patch convert_ol to see what's happening
    original_convert_ol = MarkdownConverter.convert_ol
    original_convert_li = MarkdownConverter.convert_li
    
    def debug_convert_ol(self, el, text, parent_tags=None, **kwargs):
        print(f"convert_ol called on <ol> with attributes: {el.attrs}")
        print(f"  data-list-type: {el.get('data-list-type')}")
        return original_convert_ol(self, el, text, parent_tags, **kwargs)
    
    def debug_convert_li(self, el, text, parent_tags=None, **kwargs):
        parent = el.parent
        if parent and parent.name == 'ol':
            list_type = parent.get('data-list-type')
            if list_type:
                print(f"convert_li: Parent <ol> has data-list-type={list_type}")
        return original_convert_li(self, el, text, parent_tags, **kwargs)
    
    MarkdownConverter.convert_ol = debug_convert_ol
    MarkdownConverter.convert_li = debug_convert_li
    
    config = {'target_wiki': 'wikijs'}
    converter = MarkdownConverter(config=config)
    markdown = converter.convert_standalone_html(fixed_html, 'export')
    
    print("\n" + "="*80)
    print("STEP 4: Final Markdown")
    print("="*80)
    print(markdown)

if __name__ == '__main__':
    debug_pipeline()
