#!/usr/bin/env python3
"""Debug list counting issue."""

import logging
from bs4 import BeautifulSoup

# Test HTML that reproduces the issue
TEST_HTML = '''
<div>
<ol>
  <li>Item 1</li>
  <li>
    Item 2
    <ol>
      <li>Nested 1</li>
      <li>Nested 2</li>
      <li>Nested 3</li>
    </ol>
  </li>
  <li>Item 3</li>
</ol>
</div>
'''

def debug_lists():
    soup = BeautifulSoup(TEST_HTML, 'lxml')
    ol = soup.find('ol')
    
    print("All children of <ol>:")
    for i, child in enumerate(ol.children):
        print(f"  {i}: {type(child).__name__} - '{child.name}' - '{str(child)[:50]}'")
        
    print("\nOnly <li> children:")
    list_items = [child for child in ol.children if hasattr(child, 'name') and child.name == 'li']
    for i, li in enumerate(list_items):
        print(f"  {i}: {li.name} - '{li.get_text().strip()[:30]}'")
        
    print("\nDebugging first outer <li>:")
    outer_lis = [child for child in ol.children if hasattr(child, 'name') and child.name == 'li']
    second_li = outer_lis[1]  # The one with nested list
    
    print(f"Second outer <li> content: '{second_li.get_text().strip()[:40]}'")
    
    nested_ol = second_li.find('ol')
    if nested_ol:
        nested_lis = [child for child in nested_ol.children if hasattr(child, 'name') and child.name == 'li']
        print(f"Nested <ol> has {len(nested_lis)} <li> children:")
        for i, li in enumerate(nested_lis):
            print(f"  {i}: '{li.get_text().strip()}'")

if __name__ == '__main__':
    debug_lists()
