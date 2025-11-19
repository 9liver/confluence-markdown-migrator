# Feature: Alphanumeric List Support

## Overview
The Confluence Markdown Migrator now supports alphabetic and roman numeral list numbering from Confluence content.

## Supported List Types

### Numeric (Default)
- Input: `<ol>` with no style or numeric style
- Output: `1., 2., 3., ...`

### Lowercase Alphabetic
- Input: `<ol style="list-style-type: lower-alpha;">`
- Output: `a., b., c., ...`

### Uppercase Alphabetic
- Input: `<ol style="list-style-type: upper-alpha;">`
- Output: `A., B., C., ...`

### Lowercase Roman Numerals
- Input: `<ol style="list-style-type: lower-roman;">`
- Output: `i., ii., iii., iv., ...`

### Uppercase Roman Numerals
- Input: `<ol style="list-style-type: upper-roman;">`
- Output: `I., II., III., IV., ...`

## Implementation Details

### Components Modified

1. **html_list_fixer.py**
   - Added `_preserve_list_style_types()` method
   - Parses CSS `list-style-type` attributes
   - Stores as `data-list-type` attribute

2. **markdown_converter.py**
   - Added `ListTypeMarkers` helper class
   - Modified `convert_li()` to check `data-list-type`
   - Generates appropriate list markers

### Example Usage

From Confluence HTML:
```html
<ol>
<li>Main item</li>
<li>Main item with sublist
  <ol style="list-style-type: lower-alpha;">
    <li>Sub item a</li>
    <li>Sub item b</li>
  </ol>
</li>
</ol>
```

Generated Markdown:
```markdown
1. Main item
2. Main item with sublist
   a. Sub item a
   b. Sub item b
```

## Testing

Run tests with:
```bash
python3 test_list_styles.py
python3 debug_simple.py
```

## Backward Compatibility

This feature is fully backward compatible. Lists without style attributes continue to use numeric numbering as before.
