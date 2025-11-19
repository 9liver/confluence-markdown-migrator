#!/usr/bin/env python3
"""Debug style attribute parsing."""

import re
from bs4 import BeautifulSoup

TEST_HTML = '''
<div>
<ol>
<li>Main item 1</li>
<li>Main item 2
  <ol style="list-style-type: lower-alpha;">
    <li>Sub item</li>
    <li>Sub item</li>
  </ol>
</li>
<li>Main item 3</li>
</ol>
</div>
'''

def debug_style_parsing():
    soup = BeautifulSoup(TEST_HTML, 'lxml')
    
    print("DEBUGGING STYLE PARSING")
    print("=" * 80)
    
    for i, ol in enumerate(soup.find_all('ol')):
        print(f"\n<ol> #{i}:")
        print(f"  HTML: {str(ol)[:100]}")
        print(f"  Attributes: {ol.attrs}")
        
        style = ol.get('style', '')
        print(f"  style attribute: '{style}'")
        
        if style:
            # Try different regex patterns
            pattern1 = r'list-style-type:\s*([^;]+)'
            match1 = re.search(pattern1, style, re.IGNORECASE)
            print(f"  Pattern 1 match: {match1.group(1) if match1 else 'None'}")
            
            pattern2 = r'list-style-type.*:.*([^;]+)'
            match2 = re.search(pattern2, style, re.IGNORECASE)
            print(f"  Pattern 2 match: {match2.group(1) if match2 else 'None'}")
            
            # Simple split approach
            if 'lower-alpha' in style:
                print("  Detected: lower-alpha (via simple string search)")
            elif 'lower-roman' in style:
                print("  Detected: lower-roman (via simple string search)")
            
    print("\nFinding nested <ol>:")
    main_ol = soup.find('ol')
    nested_ol = main_ol.find('ol')
    if nested_ol:
        print(f"Nested <ol> found")
        print(f"  Attributes: {nested_ol.attrs}")
        print(f"  Parent: {nested_ol.parent.name}")
        style = nested_ol.get('style')
        print(f"  Style: '{style}'")
        
        # Test the find_previous_sibling approach
        prev_sib = nested_ol.find_previous_sibling()
        print(f"  Previous sibling: {prev_sib}")
        
        prev_li = nested_ol.find_previous_sibling('li')
        print(f"  Previous <li>: {prev_li}")

if __name__ == '__main__':
    debug_style_parsing()
