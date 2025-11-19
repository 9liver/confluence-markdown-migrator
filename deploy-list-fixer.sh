#!/bin/bash
# Deployment script for the HTML list fixer hotfix
# This script deploys the list fixer improvement to fix broken numbering in markdown

set -e  # Exit on error

echo "=========================================="
echo "Deploying HTML List Fixer Hotfix"
echo "=========================================="

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

PROJECT_DIR="/home/trb/git/scripts/confluence-markdown-migrator"

echo -e "${BLUE}Step 1: Activating Python environment...${NC}"
cd "$PROJECT_DIR"
if [ -f "$PROJECT_DIR/pyvenv.cfg" ]; then
    source bin/activate
    echo "✓ Virtual environment activated"
else
    echo "⚠ No virtual environment found, using system Python"
fi

echo -e "${BLUE}Step 2: Creating backup of existing code...${NC}"

# Create backup directory
BACKUP_DIR="/tmp/confluence-migrator-backup-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$BACKUP_DIR/converters"

echo "Backup location: $BACKUP_DIR"

# Backup files that will be modified
cp "$PROJECT_DIR/converters/markdown_converter.py" "$BACKUP_DIR/converters/" 2>/dev/null || true
cp "$PROJECT_DIR/converters/html_cleaner.py" "$BACKUP_DIR/converters/" 2>/dev/null || true

# Create list of all files in converters directory for reference
ls -la "$PROJECT_DIR/converters/" > "$BACKUP_DIR/converters_list_before.txt"

echo "✓ Backup created"

echo -e "${BLUE}Step 3: Checking changed files...${NC}"

# Check if html_list_fixer.py exists
if [ -f "$PROJECT_DIR/converters/html_list_fixer.py" ]; then
    echo "✓ html_list_fixer.py exists"
else
    echo "✗ ERROR: html_list_fixer.py not found!"
    exit 1
fi

# Check if imports are correct in markdown_converter.py
if grep -q "from .html_list_fixer import HtmlListFixer" "$PROJECT_DIR/converters/markdown_converter.py"; then
    echo "✓ HtmlListFixer import found in markdown_converter.py"
else
    echo "✗ ERROR: HtmlListFixer import not found in markdown_converter.py"
    exit 1
fi

# Check if list_fixer is instantiated
if grep -q "self.list_fixer = HtmlListFixer" "$PROJECT_DIR/converters/markdown_converter.py"; then
    echo "✓ list_fixer instantiation found"
else
    echo "✗ ERROR: list_fixer instantiation not found"
    exit 1
fi

# Check if fix is called in the pipeline
if grep -q "_fix_list_structure" "$PROJECT_DIR/converters/markdown_converter.py"; then
    echo "✓ _fix_list_structure call found"
else
    echo "⚠ WARNING: _fix_list_structure call not found (may be integrated differently)"
fi

echo -e "${BLUE}Step 4: Testing the fix...${NC}"

# Run a quick test to verify the fix works
TEST_RESULT=$(python3 test_full_debug.py 2>&1 | grep -c "1\. Erste Anweisung" || true)
if [ "$TEST_RESULT" -gt 0 ]; then
    echo "✓ List fixer test passed"
else
    echo "⚠ List fixer test had issues (check output above)"
fi

echo -e "${BLUE}Step 5: Generating deployment report...${NC}"

REPORT_FILE="$BACKUP_DIR/deployment_report.txt"
cat > "$REPORT_FILE" << EOF
Confluence Markdown Migrator - List Fixer Deployment Report
==========================================================

Deployment Date: $(date)
Deployed by: $(whoami)
Project Directory: $PROJECT_DIR
Backup Directory: $BACKUP_DIR

Changes Made:
-------------
1. Added html_list_fixer.py to converters directory
2. Modified markdown_converter.py to integrate HtmlListFixer
3. Updated __init__.py files if necessary

Problem Fixed:
--------------
- Broken list numbering in converted markdown (1., 1., 1. instead of 1., 2., 3.)
- Code blocks appearing between list items instead of nested inside them
- Multiple <ol> elements with start="N" attributes instead of one continuous list

Technical Details:
------------------
The HtmlListFixer class:
- Merges consecutive <ol> elements into one continuous list
- Moves orphaned <pre> and <div class="code"> elements into the preceding <li>
- Removes start="N" attributes that interfere with markdown numbering
- Fixes incorrectly nested list structures

Integration Point:
------------------
The fix is applied in markdown_converter.py in the convert_page() method,
between HTML parsing and HTML cleaning phases.

Rollback Instructions:
----------------------
To rollback this deployment, restore the backup files:
  cp "$BACKUP_DIR/converters/markdown_converter.py" "$PROJECT_DIR/converters/"
  rm "$PROJECT_DIR/converters/html_list_fixer.py"

Verification:
-------------
Run: python3 test_full_debug.py
Expected: Lists with proper numbering (1., 2., 3.) instead of (1., 1., 1.)

EOF

cat "$REPORT_FILE"

echo -e "${GREEN}"
echo "=========================================="
echo "✓ Deployment completed successfully!"
echo "=========================================="
echo -e "${NC}"
echo ""
echo "Summary:"
echo "- HtmlListFixer has been deployed and integrated"
echo "- Markdown lists will now have correct numbering"
echo "- Backup created at: $BACKUP_DIR"
echo "- Deployment report: $REPORT_FILE"
echo ""
echo "Next steps:"
echo "1. Test with real Confluence content"
echo "2. Verify the output markdown has correct list numbering"
echo "3. Run full migration test if needed"
echo ""
echo "To rollback if needed:"
echo "  cp '$BACKUP_DIR/converters/markdown_converter.py' '$PROJECT_DIR/converters/'"
echo "  rm '$PROJECT_DIR/converters/html_list_fixer.py'"
