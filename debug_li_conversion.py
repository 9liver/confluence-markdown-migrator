#!/usr/bin/env python3
"""Debug the convert_li method to see what's happening."""

import logging
from converters.markdown_converter import MarkdownConverter

# Real Confluence HTML - shorter version
TEST_HTML = '''
<div id="main-content" class="wiki-content">
<h2>Schritt-für-Schritt-Anleitung</h2>
<ol>
<li><p>Item 1</p></li>
<li><p>Item 2</p>
<ol><li><p>Nested 1</p></li>
<li><p>Nested 2</p></li>
<li><p>Nested 3</p></li>
</ol></li>
<li><p>Item 3</p></li>
</ol>
</div>
'''

# Override convert_li to add debugging
original_convert_li = None

def debug_convert_li(self, el, text, parent_tags=None, **kwargs):
    print(f"\n=== convert_li called ===")
    print(f"Element tag: {el.name}")
    print(f"Element text: '{text.strip()[:30]}'")
    
    parent = el.parent
    if parent:
        print(f"Parent tag: {parent.name}")
        
        # Get all siblings that are li elements
        siblings = [child for child in parent.children if hasattr(child, 'name') and child.name == 'li']
        print(f"Found {len(siblings)} <li> siblings in parent:")
        for i, sib in enumerate(siblings):
            sib_text = sib.get_text().strip().replace('\n', ' ')[:30]
            marker = " <-- THIS" if sib == el else ""
            print(f"  [{i}] {sib_text}{marker}")
        
        try:
            index = siblings.index(el)
            print(f"Current element index: {index}")
        except ValueError:
            index = 0
            print(f"Current element NOT FOUND in siblings, using index 0")
    else:
        print("ERROR: No parent found")
    
    # Call the original method
    return original_convert_li(self, el, text, parent_tags, **kwargs)

def main():
    # Monkey patch to add debug output
    global original_convert_li
    original_convert_li = MarkdownConverter.convert_li
    MarkdownConverter.convert_li = debug_convert_li
    
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s - %(message)s')
    
    config = {
        'target_wiki': 'wikijs',
        'confluence': {
            'base_url': 'https://confluence.oediv.lan'
        }
    }
    converter = MarkdownConverter(config=config)
    
    print("BEFORE CONVERSION")
    print("=" * 80)
    
    markdown = converter.convert_standalone_html(TEST_HTML, 'storage')
    
    print("\n" + "=" * 80)
    print("AFTER CONVERSION")
    print("=" * 80)
    print(markdown)

if __name__ == '__main__':
    main()
