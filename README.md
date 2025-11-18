# Confluence to Markdown Migration Tool

A standalone tool for migrating Confluence content to Markdown format with support for Wiki.js and BookStack as export targets.

## Overview

This tool provides a robust pipeline for migrating Confluence content while maintaining 1:1 content fidelity. It supports dual-mode fetching (Confluence REST API or HTML export parsing) and multiple export targets (local markdown files, Wiki.js, and BookStack).

### Key Features

- **Dual-Mode Fetching**: Confluence REST API or HTML export parsing
- **High-Fidelity HTML to Markdown Conversion**: Preserves formatting, macros, and structure
- **Confluence Macro Support**: Converts info, warning, note, tip, code, expand, panel, toc, and more
- **Comprehensive Link Resolution**: Handles internal Confluence links and converts them appropriately
- **Attachment Handling**: Downloads and references attachments with filtering options
- **Interactive TUI**: Terminal-based interface using Textual framework for visual space and page selection with tree view, tri-state checkboxes (✓/~/[ ]), real-time search filtering, destination structure preview (Wiki.js paths or BookStack hierarchy based on export target), selection statistics (page count, attachments, size estimate), and keyboard shortcuts (m=migrate, a=select all, d=select, /=search, escape=clear, q=quit, ?=help)
- **Smart Integrity Verification**: Comprehensive validation with checksums, hierarchy checks, and local backups
- **Multiple Export Targets**: Export to local markdown files, Wiki.js, or BookStack
- **Comprehensive Logging**: Structured logging with verbosity levels and progress tracking
- **Dry-Run Mode**: Test migrations without making changes
- **Resumable Migrations**: Track progress and resume interrupted migrations
- **Batch Processing**: Process multiple pages in parallel for efficiency

## Architecture

The migration pipeline follows these phases:

```
Confluence Source
    ↓
┌─────────────────────────────────────┐
│  Phase 1: Fetch                     │
│  - API mode: REST API calls         │
│  - HTML mode: Parse export files    │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Phase 2: Convert                   │
│  - HTML → Markdown conversion       │
│  - Macro processing                 │
│  - Link resolution                  │
│  - Attachment handling              │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Phase 3: Export                    │
│  - Local files: Write to disk       │
│  - Wiki.js: GraphQL API import      │
│  - BookStack: REST API import       │
└─────────────────────────────────────┘
    ↓
Export Target (Markdown Files / Wiki.js / BookStack)
```

## CLI Usage

The tool provides a comprehensive command-line interface for orchestrating migrations:

```bash
# Basic usage - export to markdown files
python migrate.py --config config.yaml

# Interactive mode with TUI for page selection
python migrate.py --interactive

# Direct import to Wiki.js
python migrate.py --export-target wikijs

# Direct import to BookStack
python migrate.py --export-target bookstack

# Import to both Wiki.js and BookStack
python migrate.py --export-target both_wikis

# Dry-run mode (preview without changes)
python migrate.py --dry-run --export-target wikijs

# Filter by spaces
python migrate.py --spaces "ENG,HR,DOC"

# Single page migration (includes children)
python migrate.py --page-id 123456

# Filter by date (pages modified after date)
python migrate.py --since-date 2024-01-01

# Verbose logging
python migrate.py -vv  # DEBUG level
```

### CLI Arguments

- `--config PATH`: Path to configuration YAML file (default: config.yaml)
- `--mode {api,html}`: Fetch mode - API or HTML export (default: api)
- `--export-target {markdown_files,wikijs,bookstack,both_wikis}`: Export destination (default: markdown_files)
- `--spaces KEYS`: Comma-separated space keys to migrate (e.g., ENG,HR)
- `--page-id ID`: Single page ID to migrate (includes all children)
- `--since-date DATE`: ISO date to filter pages modified after (e.g., 2024-01-01)
- `--dry-run`: Preview migration without making changes
- `-i, --interactive`: Launch interactive TUI for content selection
- `-v, --verbose`: Increase verbosity (-v for INFO, -vv for DEBUG)
- `--version`: Show version and exit

### Migration Workflows

The tool supports three distinct workflows:

**1. Export to Markdown Files Only**
```bash
python migrate.py --export-target markdown_files
```
- Fetches content from Confluence
- Converts HTML to Markdown
- Exports to local filesystem with attachments
- Generates README.md index files
- Useful for: version control, offline review, custom processing

**2. Direct Import to Wiki**
```bash
python migrate.py --export-target wikijs
# or
python migrate.py --export-target bookstack
```
- Fetches content from Confluence
- Converts HTML to Markdown
- Imports directly to target wiki via API
- Uploads attachments as wiki assets
- No local files created (except logs/reports)
- Useful for: one-time migrations, automated syncs

**3. Import to Both Wikis**
```bash
python migrate.py --export-target both_wikis
```
- Fetches content from Confluence
- Converts HTML to Markdown
- Imports to Wiki.js via GraphQL API
- Imports to BookStack via REST API
- Useful for: multi-platform deployments, redundancy

### Migration Reports

After each migration, the tool generates:

**Console Report** - Displayed in terminal with:
- Summary statistics (pages, attachments, duration, success rate)
- Phase breakdown (conversion, export/import)
- Error summary by phase
- Space-level breakdown

**JSON Report** - Saved to `migration_report.json` (configurable) with:
- Complete statistics for all phases
- Detailed error information
- Per-space metrics
- Timestamp and configuration snapshot

**Example Console Report:**
```
============================================================
MIGRATION REPORT
============================================================

Summary:
  Spaces:      3
  Pages:       127
  Attachments: 45
  Export:      Wiki.js
  Duration:    2m 34s
  Success:     98.4%

Phase Breakdown:
  Content Conversion:
    Pages processed: 127
    Success: 125
    Failed: 0
    Partial: 2

  Wiki.js Import:
    Created: 120
    Updated: 5
    Skipped: 2
    Failed: 0
    Attachments: 45

Space Breakdown:
  Space: Engineering (ENG)
    Pages:       85/85
    Attachments: 32
  Space: HR (HR)
    Pages:       42/42
    Attachments: 13

============================================================
```


## Integrity Verification

The tool includes comprehensive integrity verification to ensure all content is correctly fetched and saved locally before conversion. This minimizes data loss and catches issues early.

### What is Verified

- **Attachments**: All referenced images and files are downloaded and checksummed
- **Hierarchy**: Page parent-child relationships are valid with no orphans or cycles
- **Links**: Internal Confluence links point to existing pages
- **Checksums**: SHA256 hashes computed for all pages and attachments
- **Backup**: Complete local backup created with raw HTML and metadata

### Configuration

Enable in `config.yaml`:

```yaml
advanced:
  integrity_verification:
    enabled: true
    verification_depth: "standard"  # basic, standard, or full
    create_backup: true
    backup_directory: "./integrity-backup"
    halt_on_failure: false  # Stop migration if critical issues found
```

### Verification Modes

- **Basic**: Checks attachments and hierarchy only (fastest)
- **Standard**: Adds page checksums and internal link validation (recommended)
- **Full**: Includes external link HTTP validation (slowest, thorough)

### Reports

Verification generates detailed reports with:
- Integrity score (0-100%)
- Missing attachments with page context
- Orphan pages and circular references
- Broken internal/external links
- Actionable fix recommendations

Reports saved to:
- Console output (summary)
- `{backup_directory}/integrity_report.json` (full details)
- `{output_directory}/integrity_issues.csv` (issue list)

### Performance Impact

- **Basic/Standard**: Minimal overhead (~5-10% increase in runtime)
- **Full**: Moderate overhead (~20-30% increase due to external link checks)
- Checksum computation parallelized using `checksum_workers` setting
- Leverages existing cache to avoid redundant API calls

### When to Use

- **Production migrations**: Always enable to catch issues before conversion
- **Large spaces**: Use "standard" mode to balance speed and thoroughness
- **Offline work**: Create backup for later processing without API access
- **Compliance**: Checksums provide tamper detection for audit trails

### CLI Usage Examples

```bash
# Run migration with integrity verification
python migrate.py --mode api --spaces DEV --verify-integrity

# Verify only (no conversion/export) - not yet implemented
# python migrate.py --mode api --spaces DEV --verify-only
```

### Troubleshooting Integrity Issues

**Problem**: Integrity score below 50%

**Solutions**:
1. Check `integrity_report.json` for specific issues
2. Re-run fetch with `--force-refresh` to bypass cache
3. Verify Confluence permissions for attachments
4. Review broken link recommendations in report
5. Use `--halt-on-failure false` to continue despite issues


### Fetcher System

The tool implements a dual-mode fetching system with a consistent interface:

**ConfluenceClient**: Enhanced REST API client with robust error handling, retry logic, and content fidelity focus. Supports both Basic and Bearer authentication, with exponential backoff for attachment downloads and proper error categorization (transient vs permanent failures).

**BaseFetcher**: Abstract interface that defines the contract for all fetcher implementations. Provides common functionality including filter validation, date parsing, and logging utilities.

**ApiFetcher**: Implements `BaseFetcher` for direct API access. Key features:
- Uses `body.export_view` expansion for highest fidelity HTML (rendered with all macros expanded)
- Implements caching for spaces and pages to avoid redundant API calls
- Applies attachment exclusion rules (file type and size filters)
- Supports CQL search for efficient date-based filtering
- Tracks conversion metadata for quality reporting

**HtmlFetcher**: Implements `BaseFetcher` for HTML export parsing. Key features:
- Parses Confluence HTML export files without API access
- Robust file matching with chunked scanning and BeautifulSoup fallback
- Extracts metadata from HTML structure
- Identifies attachments from content references
- Perfect for offline migrations or when API access is restricted

### Content Fidelity Strategy

To achieve 1:1 content fidelity, the API fetcher specifically uses `body.export_view` instead of `body.storage`. This critical difference ensures:
- Macros are rendered and expanded (not left as wiki markup)
- Dynamic content is resolved
- Templates are processed
- Formatting is preserved exactly as users see it in Confluence

The system tracks conversion quality through the `conversion_metadata` dictionary in each `ConfluencePage`, enabling detailed reporting on:
- Conversion success (pending, success, partial, failed)
- Macros detected and converted
- Links resolved (internal vs external)
- Images processed
- Warnings encountered

## Markdown Conversion

The converter module provides high-fidelity HTML to Markdown conversion with full Confluence macro support and quality tracking:

### Components

**HtmlCleaner**: Removes Confluence-specific markup (classes, data attributes, wrapper divs) without losing content. Handles both `storage` and `export_view` HTML formats.

**MacroHandler**: Converts Confluence macros to markdown structures:
- `info`, `warning`, `note`, `tip` → Markdown blockquotes or Wiki.js admonitions
- `code` → Fenced code blocks with language detection
- `expand` → Collapsible `<details>/<summary>` elements
- `panel` → Blockquotes with optional titles

**LinkProcessor**: Smart link handling:
- Preserves internal Confluence links for exporter rewriting
- Converts attachment references to relative paths
- Validates external links and tracks broken links
- Processes images with alt text preservation

**MarkdownConverter**: Main orchestrator using markdownify with custom handlers for tables, nested lists, callouts, code blocks, and images. Post-processes for Wiki.js/BookStack compatibility.

**Features:**
- Confluence macro conversion with parameter extraction
- Table preservation with proper markdown syntax
- Code block language detection
- Smart link and attachment reference handling
- Image reference conversion with alt text
- Nested list support with proper indentation
- Wiki.js and BookStack compatibility modes
- Comprehensive metadata tracking

**Usage:**
```python
from converters import convert_page
from models import ConfluencePage

# Convert a page
page = ConfluencePage(id='123', title='Example', content='<html>...</html>', space_key='DEMO')
success = convert_page(page, config={'target_wiki': 'wikijs'})

if success:
    print(page.markdown_content)
    print(f"Macros converted: {page.conversion_metadata.get('macros_converted', 0)}")
    print(f"Links: {page.conversion_metadata.get('links_internal', 0)} internal, {page.conversion_metadata.get('links_external', 0)} external")
```

**Supported Confluence Macros:**

| Macro | Output |
|-------|--------|
| `info` | `> **Note:** content` or `> [!INFO]` |
| `warning`, `note` | `> **Warning:** content` or `> [!WARNING]` |
| `tip` | `> **Tip:** content` or `> [!SUCCESS]` |
| `code` | ` ```python\ncode\n``` ` |
| `expand` | `<details><summary>Title</summary>content</details>` |
| `panel` | `> content` with optional title |

**Conversion Metadata:**
Each converted page tracks comprehensive quality metrics:
- `conversion_status`: success, partial, or failed
- `macros_found/converted/failed`: Macro conversion statistics
- `links_internal/external`: Link type counts
- `images_count/with_alt`: Image statistics
- `conversion_warnings`: List of warning messages
- `conversion_timestamp`: ISO timestamp
- `format_detected`: storage or export

**Configuration:**
Converter behavior can be customized via `config.yaml`:
```yaml
converter:
  target_wiki: wikijs      # wikijs, bookstack, or both
  preserve_html: false
  strict_markdown: true
  heading_offset: 0        # Adjust heading levels
```

### Error Handling & Reliability

**Attachment Download Robustness**:
- Exponential backoff retry (`backoff_factor * (2 ** attempt)`)
- Distinguishes transient errors (retry): connection errors, timeouts, 429, 500, 502, 503, 504
- Fails fast on permanent errors (no retry): 401, 403, 404
- Configurable retry attempts and backoff factor

**Rate Limiting**:
- Configurable minimum delay between requests
- Respects `Retry-After` headers from 429 responses
- Prevents overwhelming Confluence servers

**Caching**:
- In-memory caching: Spaces and pages are cached during fetch to avoid redundant API calls
- Disk-based full content caching for resumable migrations (e.g., after interruptions) is planned for Phase 2
- Current `advanced.cache_enabled` controls in-memory caching only

## Markdown Export

The markdown exporter converts the DocumentationTree to local markdown files with proper directory structure, attachment management, and navigation indexes:

### Directory Structure

The exporter creates organized directory structures for each Confluence space:

```
confluence-export/
├── DEV/
│   ├── README.md                              # Space index with navigation
│   ├── attachments/                           # All space attachments
│   │   ├── architecture-diagram.png
│   │   └── api-reference.pdf
│   ├── getting-started.md                     # Root-level page
│   └── api-reference/
│       ├── api-reference.md                   # Parent page
│       └── authentication.md                  # Child page
└── OPS/
    ├── README.md
    └── runbooks/
        ├── runbooks.md
        └── deployment/
            ├── deployment.md
            └── rollback-procedures.md
```

### Configuration

Configure export behavior in the `export` section of `config.yaml`:

```yaml
export:
  output_directory: "./confluence-export"     # Base output directory
  create_index_files: true                    # Generate README.md navigation files
  organize_by_space: true                     # Create subdirectories per space
  
  attachment_handling:
    download_attachments: true                # Enable attachment downloads
    max_file_size: 52428800                   # 50MB size limit
    skip_file_types: [".exe", ".dll", ".zip"]  # File extensions to skip
    attachment_directory: "attachments"       # Attachments subdirectory name
```

### Attachment Handling

**Deduplication Strategy**:
- Downloads attachments to `{space-key}/attachments/` directory
- Deduplicates by SHA256 content hash
- Renames duplicates with counter suffix (e.g., `image_1.png`)
- Updates ConfluenceAttachment.local_path with saved location

**Exclusion Rules**:
- File size limits (configurable max_file_size)
- Blocked file extensions (skip_file_types)
- Supports multi-part extensions (`.tar.gz` handled correctly)
- Already excluded attachments preserved

**Download Modes**:
- **API Mode**: Downloads via Confluence REST API with exponential backoff retry
- **HTML Mode**: Extracts from local HTML export directory

### Link Rewriting

**Attachment References**:
- Finds markdown links `[text](url)` and images `![alt](url)`
- Matches against ConfluenceAttachment metadata
- Calculates relative paths based on page hierarchy depth:
  - Root page (depth 0): `./attachments/file.png`
  - Nested page (depth 1): `../attachments/file.png`
  - Deep nesting (depth N): `../` repeated N times + `attachments/file.png`
- Handles URL encoding, case-insensitive matching, and basename extraction

**Internal Page Links** (placeholder):
- Identifies Confluence internal links (`/pages/viewpage.action?pageId=123`)
- Logs TODO warning (future enhancement will map to relative markdown paths)
- Preserves original URLs to avoid broken navigation

### Index Files

Each space directory contains a `README.md` with:

**Frontmatter**:
```yaml
---
confluence_space_key: DEV
space_name: Development
page_count: 42
attachment_count: 156
generated_at: 2024-01-15T10:30:00Z
---
```

**Navigation Features**:
- Hierarchical table of contents from page structure
- Status indicators (❌ failed, ⚠️ partial, ✅ success, ⏳ pending)
- Relative markdown links to all pages
- Space description and metadata

**Warning Sections**:
- Pages without markdown content
- Conversion failures and errors
- Broken link references
- Attachment processing issues

**Footer**:
- Export timestamp and tool information
- Statistics summary

### Usage Example

Export Confluence content to markdown files:

```bash
# Export specific spaces to markdown
python migrate.py --mode api --export-target markdown_files --spaces DEV OPS

# Interactive selection with export
python migrate.py --interactive --export-target markdown_files

# Custom output directory
python migrate.py --export-target markdown_files --config config.production.yaml
```

### Progress Tracking

The exporter provides comprehensive progress monitoring:

- **Space-level progress**: Via ProgressTracker for each space
- **Page-level progress**: Via tqdm progress bars for attachment downloads
- **Detailed logging**: Per-page export status, attachment processing results
- **Statistics**: Export summary with page counts, attachment counts, error tallies

### Error Handling

**Graceful Degradation**:
- Pages without markdown_content are logged and skipped (not exported)
- Attachment download failures are tracked but don't halt export
- Broken links are preserved as-is with warnings logged
- All errors stored in page.conversion_metadata['export_errors']

**Retry Logic**:
- Exponential backoff for attachment downloads (3 attempts default)
- Configurable retry attempts and backoff factors
- Distinguishes permanent vs transient errors

**Validation**:
- File size validation after download
- Content hash verification for deduplication
- URL accessibility checks (future enhancement)

### Integration with Wiki.js and BookStack

The markdown files generated by this exporter serve as input for:

- **Wiki.js Importer**: Consumes markdown with frontmatter and relative paths
- **BookStack Importer**: Processes markdown structure and attachment links
- **Manual Import**: Files can be manually uploaded to any markdown-compatible platform

The exporter architecture (AttachmentManager, LinkRewriter, IndexGenerator) provides reusable components for subsequent importers.

## Installation

### Prerequisites

- Python 3.8 or higher
- Access to Confluence (Server or Cloud)
- (Optional) Wiki.js instance with API access
- (Optional) BookStack instance with API access

### Setup

1. Clone or download this tool to your local machine

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Copy the example configuration file:
   ```bash
   cp config.yaml.example config.yaml
   ```

4. Edit `config.yaml` and fill in your credentials and settings:
   - Confluence URL and authentication
   - Target system settings (Wiki.js and/or BookStack)
   - Export preferences

## Configuration

The configuration file (`config.yaml`) supports extensive customization. Key sections:

### Confluence Source Settings

```yaml
confluence:
  base_url: "https://confluence.example.com"
  auth_type: "basic"  # or "bearer" for API tokens
  username: "your-username"
  password: ${CONFLUENCE_PASSWORD}  # Use environment variables for secrets
  verify_ssl: true
```

### Export Target Settings

Configure one or more export targets:

```yaml
migration:
  export_target: "markdown_files"  # or "wikijs", "bookstack", "both_wikis"

# Wiki.js settings (if using wikijs export target)
wikijs:
  base_url: "https://wiki.example.com"
  api_key: ${WIKIJS_API_KEY}

# BookStack settings (if using bookstack export target)
bookstack:
  base_url: "https://bookstack.example.com"
  token_id: ${BOOKSTACK_TOKEN_ID}
  token_secret: ${BOOKSTACK_TOKEN_SECRET}
```

See `config.yaml.example` for all available options and detailed documentation.

### Confluence Settings - Reference

| Setting | Required | Description |
|---------|----------|-------------|
| `confluence.base_url` | Yes (API) | Confluence Server/Cloud URL |
| `confluence.auth_type` | Yes (API) | "basic" or "bearer" |
| `confluence.username` | Yes (Basic) | Username |
| `confluence.password` | Yes (Basic) | Password (use env var) |
| `confluence.api_token` | Yes (Bearer) | API token for Cloud |
| `confluence.verify_ssl` | No | SSL verification (default: true) |
| `confluence.html_export_path` | Yes (HTML) | Path to HTML export |

### Advanced Settings

#### Cache Configuration

The tool supports intelligent caching to minimize API calls and improve performance:

##### Cache Modes

- **`validate`** (recommended): Checks with Confluence if cached content is still current using HTTP cache headers (ETag, Last-Modified). Only downloads full content if changed. Best balance of performance and freshness.
- **`always_use`**: Offline mode. Uses cached data without validation, even if expired. Useful for working without network access or testing. May use stale data.
- **`disable`**: Always fetches fresh data from API. Use when cache is causing issues or when guaranteed latest content is required. Slowest but most reliable.

##### Configuration Example

```yaml
advanced:
  cache:
    enabled: true
    mode: "validate"  # or "always_use", "disable"
    directory: "./.cache"
    ttl_seconds: 86400  # 1 day
    validate_with_headers: true
    cache_attachments: true
    verify_checksums: true
```

##### Cache Statistics

After migration, the tool reports cache performance in the migration report:

```
Cache Statistics:
Mode:        validate
Hits:        450
Misses:      50
Hit Rate:    90.0%
API Saved:   450 calls
Validations: 50
Cache Size:  125.34 MB
Entries:     1200
```

**Cache Metrics Explained:**
- **Hit Rate**: Percentage of requests served from cache
- **API Saved**: Number of API requests avoided
- **Validations**: Number of cache validation checks performed (304 responses)
- **Invalidated**: Number of cache entries that were stale and refetched (200 responses)

##### Cache Troubleshooting

**Problem**: Stale or incorrect content in migration
- **Solution**: Clear cache and re-run with `cache.mode: "disable"` or delete `.cache` directory

**Problem**: Slow performance despite caching enabled
- **Solution**: Check cache hit rate in report. If low, increase `ttl_seconds` or use `validate` mode for better cache reuse

**Problem**: Cache validation errors
- **Solution**: Ensure Confluence server returns proper ETag/Last-Modified headers. Set `validate_with_headers: false` to disable validation and use TTL-only caching

##### Legacy Cache Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `advanced.cache_enabled` | false | Replaced by `cache.enabled` (deprecated) |
| `advanced.cache_directory` | "./.cache" | Replaced by `cache.directory` (deprecated) |
| `advanced.cache_ttl_seconds` | 86400 | Replaced by `cache.ttl_seconds` (deprecated) |

##### Advanced HTTP & Network Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `advanced.request_timeout` | 30s | HTTP timeout |
| `advanced.max_retries` | 3 | Retry attempts |
| `advanced.retry_backoff_factor` | 2.0 | Exponential backoff |
| `advanced.rate_limit` | 0.0s | Minimum delay between requests |

**Tip**: Increase `rate_limit` and reduce `batch_size` for slow networks or large Confluence instances.

## Quick Start

### Basic Usage

**Export to local markdown files:**
```bash
python migrate.py --mode api --export-target markdown_files
```

**Interactive mode (select spaces/pages):**
```bash
python migrate.py --interactive
```

**Export specific spaces:**
```bash
python migrate.py --spaces DEV OPS DOC --export-target markdown_files
```

**Test migration (dry run):**
```bash
python migrate.py --dry-run --export-target wikijs
```

### Command Line Options

```
--mode {api,html}              Fetch mode (default: api)
--export-target {markdown_files,wikijs,bookstack,both_wikis}
                               Export destination (default: markdown_files)
--spaces SPACES [SPACES ...]   Specific space keys to migrate
--page-id PAGE_ID             Single page ID to migrate (for testing)
--since-date DATE             Filter pages modified after date (ISO format)
--dry-run                     Perform dry run without making changes
--interactive                 Enable interactive TUI mode
--batch-size N                Number of pages to process in parallel (default: 5)
--output-dir DIR              Output directory for markdown files
--verbose, -v                 Increase verbosity (use -vv for debug)
--config PATH                 Path to config file (default: config.yaml)
```

## Interactive Mode

The TUI provides a visual interface for selecting Confluence content with the following features:

**Tree Navigation:**
- Use arrow keys (↑↓←→) to navigate the Confluence hierarchy
- Press SPACE or ENTER to toggle selection on focused node
- Tri-state checkboxes: [✓] fully selected (green), [~] partially selected (yellow), [ ] not selected (dim)

**Search Filtering:**
- Press `/` to focus search input
- Type to filter in real-time (matches page/space names)
- Press ESCAPE to clear search and return to full tree

**Preview Pane:**
- Shows destination structure based on export target:
  - `wikijs`: Flat path structure (e.g., `/DEV/Architecture/Overview.md`)
  - `bookstack`: Hierarchical layout (Shelf→Book→Chapter→Page)
  - `both_wikis`: Shows both Wiki.js and BookStack previews
  - `markdown_files`: Preview not available (files written to disk)

**Statistics Panel:**
- Real-time counts of selected pages, spaces, attachments
- Estimated migration size (pages + attachments)
- Updates automatically as selection changes

**Keyboard Shortcuts:**
- `m`: Migrate (validate selection and exit with result)
- `q`: Quit without migrating
- `a`: Select all visible pages
- `d`: Deselect all pages
- `?`: Show help with all shortcuts

**Usage Example:**
```bash
# Launch interactive mode with Wiki.js target
python migrate.py --interactive --export-target wikijs

# Launch with BookStack target
python migrate.py --interactive --export-target bookstack

# Launch with dual-wiki target (shows both previews)
python migrate.py --interactive --export-target both_wikis
```

The preview pane adapts automatically to show the appropriate destination structure based on your configured export target.

## Export Targets

### Markdown Files

Exports content to local markdown files with structured directories:

```
confluence-export/
├── space-key-1/
│   ├── index.md (space overview)
│   ├── page-1-title.md
│   ├── page-2-title.md
│   └── attachments/
│       ├── image1.png
│       └── document.pdf
├── space-key-2/
│   └── ...
└── migration-report.json
```

**Features:**
- Preserves page hierarchy with directory structure
- Downloads and references attachments
- Generates index files for navigation
- Creates JSON report with migration statistics

### Wiki.js

Directly imports content to Wiki.js via GraphQL API:

**Features:**
- Creates pages with hierarchical paths (e.g., /SPACE/parent/child)
- Preserves page hierarchy and parent-child relationships
- Uploads attachments to Wiki.js assets with link rewriting
- Converts Confluence labels to Wiki.js tags
- Handles conflict resolution (skip, overwrite, versioned paths)
- Supports multi-language content
- Dry-run mode for safe previews

---

### Wiki.js Import Configuration

The Wiki.js importer provides flexible configuration for handling Confluence to Wiki.js migrations:

#### Overview

The importer translates Confluence's hierarchical structure into Wiki.js flat paths while preserving content relationships:
- **Hierarchy → Paths**: Confluence spaces with parent/child pages become `/space-key/parent-page/child-page`
- **Attachments**: Uploaded to Wiki.js assets folder and linked in markdown
- **Labels**: Converted to Wiki.js tags for categorization
- **Conflicts**: Multiple strategies for handling existing pages

Enable by setting `migration.export_target: wikijs` or `both_wikis` in your config.

#### Configuration Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `conflict_resolution` | string | `'skip'` | How to handle existing pages: `'skip'` (ignore), `'overwrite'` (replace), `'version'` (append `-2`, `-3` suffixes) |
| `preserve_labels` | boolean | `true` | Convert Confluence labels to Wiki.js tags |
| `include_space_in_path` | boolean | `true` | Include space key in paths (`/SPACE/...`); set `false` for flat `/...` paths |
| `asset_upload.enabled` | boolean | `true` | Enable attachment uploads to Wiki.js assets |
| `asset_upload.folder` | string | `'/confluence-assets'` | Target folder in Wiki.js (must start with `/`) |
| `asset_upload.max_workers` | integer | `3` | Parallel upload threads (1-10 recommended) |
| `asset_upload.rewrite_links` | boolean | `true` | Replace local attachment paths with asset URLs in markdown |

**Example Configuration:**

```yaml
wikijs:
  base_url: "https://wiki.example.com"
  api_key: ${WIKIJS_API_KEY}
  verify_ssl: true
  
  # Conflict resolution strategy
  conflict_resolution: 'version'  # Use versioned paths to avoid overwrites
  
  # Preserve Confluence labels as tags
  preserve_labels: true
  
  # Include space key in paths (false for unified wiki)
  include_space_in_path: true
  
  # Asset upload settings
  asset_upload:
    enabled: true
    folder: '/confluence-assets'
    max_workers: 5
    rewrite_links: true
```

#### Usage Examples

**Dry-run preview:**
```bash
# Preview conflicts and paths without making changes
python migrate.py --export-target wikijs --dry-run
```

**Interactive migration:**
```bash
# Use TUI to select pages before import
python migrate.py --interactive --export-target wikijs
```

**Import specific spaces:**
```bash
# Only import DEV and DOC spaces
python migrate.py --export-target wikijs --spaces DEV DOC
```

#### Conflict Resolution Strategies

-  **`skip`**  : Do not import if page exists (default, safe for incremental)
-  **`overwrite`**  : Replace existing content (use for full syncs)
-  **`version`**  : Create new page with numeric suffix (`/page`, `/page-2`, `/page-3`)

Use `version` when preserving history is important or for incremental updates.

#### Attachments and Assets

Attachments are:
1. Uploaded to the configured Wiki.js asset folder (e.g., `/confluence-assets`)
2. Processed in parallel using `max_workers` threads
3. Referenced in markdown via rewritten URLs (e.g., `![img](/assets/file.png)`)
4. Deduplicated by content hash to avoid duplicates

#### Troubleshooting

**Invalid Configuration:**
- Check validation errors on startup - all settings are type-checked
- Ensure `asset_upload.folder` starts with `/` (absolute path required)
- `max_workers` must be a positive integer

**Path Conflicts:**
- Use `conflict_resolution: version` to avoid overwrites
- For multiple spaces, use `include_space_in_path: true` to isolate paths
- Check `page.conversion_metadata['wikijs_import']['path']` in reports

**Attachment Upload Failures:**
- Verify Wiki.js API permissions (Admin > API Access)
- Check folder permissions in Wiki.js (Admin > Storage)
- Reduce `max_workers` if hitting rate limits
- Review logs for specific upload errors

**Rate Limiting:**
- Increase `advanced.rate_limit` to slow down requests
- Reduce `max_workers` for attachment uploads
- Check Wiki.js server logs for throttling

**GraphQL API Errors:**
- Verify Wiki.js version compatibility (v2.x recommended)
- Check API key permissions (read/write pages and assets)
- Review Wiki.js logs for detailed error messages

### Migration Orchestration Issues

**Problem:** Migration fails during conversion phase
- **Cause:** Invalid HTML content, unsupported macros
- **Solution:** Check conversion_metadata in report, enable fallback_to_raw in config, review specific page content

**Problem:** Dry-run shows different results than actual run
- **Cause:** API state changes between runs, network issues
- **Solution:** Run dry-run immediately before actual migration, check for concurrent Confluence edits

**Problem:** Import fails after successful conversion
- **Cause:** Target wiki API issues, authentication problems, rate limiting
- **Solution:** Check target wiki credentials, enable rate limiting in config, review API logs

**Problem:** Both wikis import partially succeeds
- **Cause:** One wiki fails while other succeeds
- **Solution:** Review report for per-target errors, re-run with single target to isolate issue

#### Rollback and Error Recovery

**Rollback Behavior:**
The tool does **not** perform automatic rollback on import failures. This is by design for several reasons:
- **Idempotent operations**: Rerunning the importer will update existing content rather than creating duplicates
- **Granular control**: Users can review the migration report and selectively re-run failed items
- **Partial success**: Even if some items fail, successfully imported content remains available
- **Target system differences**: Wiki.js and BookStack have different deletion APIs and permission models

**Manual Rollback Options:**

1. **For Wiki.js:**
   - Use the admin UI to delete imported pages/spaces
   - Or use the GraphQL API to programmatically delete content
   - Example: Use the `pages.delete` mutation with page IDs from the migration report

2. **For BookStack:**
   - Shelves, Books, Chapters, and Pages can be deleted via the web UI
   - API deletion is available via DELETE endpoints
   - Use IDs from the migration report to identify what to delete

3. **For Markdown Files:**
   - Simply delete the export directory: `rm -rf ./confluence-export`
   - Or use version control to revert: `git checkout -- ./confluence-export`

**Best Practices:**

- **Always run with `--dry-run` first** to preview changes
- **Start with a single space or page** using `--spaces` or `--page-id`
- **Use `--export-target markdown_files`** first to verify conversion quality
- **Review the migration report** before deciding whether to re-run or rollback
- **Test imports on a staging instance** before production migrations

**Performance Optimization with Caching:**

- **Enable smart caching** for large migrations to minimize API calls:
  ```yaml
  advanced:
    cache:
      enabled: true
      mode: "validate"  # Smart validation mode
      ttl_seconds: 86400
  ```
- **Monitor cache statistics** in migration report - aim for hit rate >70%
- **Use `validate` mode** (recommended) for most migrations - balances performance with freshness
- **Use `always_use` mode** for offline testing or when Confluence is slow (may use stale cache)
- **Clear cache before major migrations** if you've made significant changes in Confluence
- **Cache attachments** to avoid re-downloading large files (set `cache_attachments: true`)
- **Increase TTL** for stable content that doesn't change frequently

**Cache-Specific Best Practices:**

- **First migration**: Use default cache settings, let cache populate automatically
- **Subsequent migrations**: Enable caching to benefit from previous fetch
- **Testing/debugging**: Use `always_use` mode for fast, repeatable tests without API calls
- **Production runs**: Use `validate` mode to ensure fresh content while minimizing API usage
- **Monitor disk space**: Large attachment caches can grow quickly - monitor `./.cache` directory
- **Clear stale cache**: Periodically clear cache: `rm -rf ./.cache/*` or use CLI `--clear-cache`

**Re-running Failed Migrations:**

If a migration fails partially:
1. Review the `migration_report.json` to identify failed items
2. Fix the underlying issue (credentials, network, target system)
3. Re-run the importer - it will skip already-successful items and retry failures
4. Use `--verbose` to see detailed progress

**Example: Re-running after a failure**
```bash
# Initial run with failures
python migrate.py --export-target wikijs --spaces ENG

# Fix the issue (e.g., increase rate limits in config)

# Re-run - will skip successful items and retry failures
python migrate.py --export-target wikijs --spaces ENG --verbose
```

**Incremental Migrations:**

- Use `--since-date` to process only recently modified pages
- Combine with caching for optimal performance on recurring migrations
- Example: Weekly sync of only changed content
  ```bash
  python migrate.py --since-date 2024-01-01 --export-target wikijs
  ```

#### Additional Resources

- [Wiki.js GraphQL API Documentation](https://docs.requarks.io/dev/graphql-api)
- Confluence to Wiki.js Migration Guide (coming soon)
- Example configurations in `/examples/wikijs-import.yaml`

### BookStack

Directly imports content to BookStack via REST API with hierarchical structure preservation:

**Features:**
- Creates shelves, books, chapters, and pages
- **Hierarchy mapping**: Confluence Space → BookStack Shelf, Top-level page → Book, Pages with children → Chapter, Leaf pages → Page
- **Markdown to HTML conversion**: Converts markdown to HTML for BookStack storage
- **Image upload**: Uploads attachments and rewrites references in HTML content
- **Ordering preservation**: Maintains page sequence using BookStack priority values
- **Batch processing**: Efficient parallel processing for large migrations
- **Dry-run mode**: Preview import operations without making changes
- **Conflict handling**: Skip or update existing content
- **Nested page flattening**: Handles Confluence's unlimited nesting within BookStack's 3-level structure

---

### BookStack Import Configuration

The BookStack importer provides comprehensive configuration for migrating Confluence to BookStack's hierarchical structure:

#### Overview

The importer transforms Confluence's flexible hierarchy into BookStack's structured three-level system:
- **Space → Shelf**: Each Confluence space becomes a BookStack shelf
- **Top-level Page → Book**: Pages without parents become books containing collections of content
- **Page with Children → Chapter**: Intermediate pages with descendants become chapters that organize pages
- **Leaf Page → Page**: Final pages without children become content pages
- **Flattening**: Confluence pages nested beyond Page level are flattened as siblings with warnings logged

BookStack stores content as HTML (not markdown), so the importer automatically converts markdown to HTML using the `markdown` library with extensions for tables, code highlighting, and formatting.

#### Hierarchy Mapping Details

**Confluence Structure** → **BookStack Structure**:
```
Space: DEV                          → Shelf: DEV
├── Page: Architecture (top-level)  → Book: Architecture
│   ├── Page: API Design (has kids)  → Chapter: API Design
│   │   ├── Page: Authentication    → Page: Authentication
│   │   └── Page: Authorization     → Page: Authorization
│   └── Page: Database Schema       → Page: Database Schema (no chapter)
└── Page: Getting Started           → Book: Getting Started
    └── Page: Setup Instructions    → Page: Setup Instructions
```

**Nested Page Handling:**
- BookStack only supports 3 levels: Shelf → Book → Chapter → Page
- Confluence pages nested under a Page (e.g., Page → Page → Page) are flattened
- Flattened pages become siblings at the Page level with warnings logged
- This preserves all content but loses some hierarchical relationship depth

**Important Limitations:**
- No native markdown support (converted to HTML)
- Images must be uploaded after page creation (two-step process)
- Chapter and Page names have 255 character limits (truncated with warning)
- Shelves are required for Books (all Books belong to a Shelf)

#### Configuration Settings

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `bookstack.base_url` | string | - | BookStack instance URL (e.g., `https://bookstack.example.com`) |
| `bookstack.token_id` | string | - | API token ID from Settings > API Tokens |
| `bookstack.token_secret` | string | - | API token secret |
| `bookstack.default_editor` | string | `'markdown'` | Default editor for new Wiki.js pages (ignored for BookStack) |
| `advanced.verify_ssl` | boolean | `true` | Verify SSL certificates |
| `advanced.request_timeout` | integer | `30` | HTTP request timeout in seconds |
| `advanced.max_retries` | integer | `3` | Maximum retry attempts for failed API calls |
| `advanced.retry_backoff_factor` | float | `0.5` | Exponential backoff factor (0.5 = 0.5s, 1.0s, 2.0s, ...) |
| `advanced.rate_limit` | float | `0.0` | Minimum seconds between requests (0 = no limit) |
| `advanced.progress_bars` | boolean | `true` | Show tqdm progress bars |

**Example Configuration:**

```yaml
migration:
  export_target: "bookstack"  # or "both_wikis"

bookstack:
  base_url: "https://bookstack.example.com"
  token_id: ${BOOKSTACK_TOKEN_ID}    # From Settings > API Tokens
  token_secret: ${BOOKSTACK_TOKEN_SECRET}
  default_editor: "markdown"  # Optional, defaults to markdown

advanced:
  verify_ssl: true
  request_timeout: 30
  max_retries: 3
  retry_backoff_factor: 0.5
  rate_limit: 0.1  # 100ms between requests
  progress_bars: true
```

**API Token Generation:**
1. Go to BookStack → Settings → API Tokens
2. Click "Create API Token"
3. Copy the **Token ID** and **Token Secret** (secret is only shown once!)
4. Store in environment variables or config file

#### Usage Examples

**Dry-run preview:**
```bash
# Preview BookStack import without making changes
python migrate.py --export-target bookstack --dry-run
```

**Interactive migration:**
```bash
# Use TUI to select pages before import
python migrate.py --interactive --export-target bookstack
```

**Import specific spaces:**
```bash
# Only import DEV and DOC spaces
python migrate.py --export-target bookstack --spaces DEV DOC
```

**Full migration with logging:**
```bash
# Import all spaces with debug logging
python migrate.py --export-target bookstack --verbose --verbose
```

**Migrate from existing markdown export:**
```bash
# If you already converted to markdown, import directly
python migrate.py --mode local --export-target bookstack
```

#### Dry-Run Mode

The importer fully supports dry-run mode for safe preview:

**What happens in dry-run:**
- No API calls are made to BookStack
- All transformations run (markdown→HTML, hierarchy mapping, link rewriting)
- Logs show intended actions with `[DRY RUN]` prefix
- Statistics include hypothetical page counts
- Image upload and attachment processing are simulated
- Error handling paths are tested

**Example dry-run output:**
```
INFO: Starting BookStack import (dry_run=True)
INFO: [DRY RUN] Would create shelf: Development
INFO: [DRY RUN] Would create book: Architecture (parent: Development)
INFO: [DRY RUN] Would create chapter: API Design (parent: Architecture)
INFO: [DRY RUN] Would create page: Authentication
INFO: [DRY RUN] Would upload 5 images for page
INFO: BOOKSTACK IMPORT SUMMARY (Dry Run: True)
INFO: Shelves: 1, Books: 3, Chapters: 5, Pages: 42, Images: 156
```

#### Conflict Resolution

Unlike Wiki.js's flexible path system, BookStack has strict hierarchy rules:

**Shelf conflicts:** Shelves use Confluence space keys as names. If a shelf with the same name exists:
- The importer **adds books to existing shelf** (no conflict)
- Books are organized under the existing shelf
- No duplicate shelves are created

**Book conflicts:** Books are created within shelves. If a book with the same name exists in the shelf:
- The importer will **skip creation** (default behavior)
- Statistics track skipped items
- No data is overwritten

**Page conflicts:** Pages can exist in books or chapters. If a page with the same name exists:
- The importer will **create unique names** by appending numeric suffixes
- Example: `Authentication`, `Authentication-2`, `Authentication-3`
- Preserves all content without overwriting

**To handle updates:**
- Manually delete content in BookStack before re-importing, OR
- Use dry-run to preview and selectively import only new content

#### Image and Attachment Upload

Attachments are processed in a two-step workflow:

1. **Page Creation**: First create the page in BookStack to get a page ID
2. **Image Upload**: Then upload images using the page ID as `uploaded_to` parameter

**Process:**
```python
# 1. Create page
page = client.create_page(
    book_id=1,
    name="API Documentation",
    html="<p>Content with images</p>"
)

# 2. Upload images
image_map = uploader.upload_images_for_page(
    confluence_page,
    bookstack_page_id=page['id']
)

# 3. Rewrite HTML references
updated_html = uploader.rewrite_image_references(
    html_content=page['html'],
    image_map=image_map
)

# 4. Update page with rewritten HTML
client.update_page(page['id'], html=updated_html)
```

**Supported image types:**
- PNG, JPEG, JPG, GIF, SVG, WebP
- Filtered by MIME type and file extension
- Large images may be resized by BookStack automatically

**Upload behavior:**
- Failed uploads log warnings but don't stop the import
- Successfully uploaded images are logged at DEBUG level
- Image references that can't be rewritten are preserved as-is
- Duplicate images are uploaded separately (no deduplication at upload level)

#### BookStack Hierarchy Limitations

**Maximum depth:**
BookStack's three-level structure aligns well with most Confluence hierarchies but has important constraints:

```
Valid (3 levels max):
✅ Shelf → Book → Chapter → Page

Invalid (exceeds 3 levels):
❌ Shelf → Book → Chapter → Page → Page → Page  # Too deep!

Solution: Flattening
Confluence:                BookStack:
Page                       Page
└── Page       →           Page (flattened sibling)
    └── Page   →           Page (flattened sibling)
```

**Why 3 levels?**
- Shelves: Organize books (like Confluence spaces)
- Books: Contain chapters and pages (like Confluence parent pages)
- Chapters: Organize pages within books (like Confluence pages with children)
- Pages: Final content (like Confluence leaf pages)

**Flattening strategy:**
- Deterministic conversion preserves all content
- Warnings logged for each flattened page
- Parent-child relationships lost but content hierarchy flattened
- Example: `DEV/Architecture/API/Authentication` becomes a flat page at the same level as other API pages

#### Error Handling

**Retry Logic:**
- Network failures: Exponential backoff (configurable attempts)
- Rate limiting: Automatic retry after `Retry-After` header value
- Timeout errors: Configurable timeout with retry
- Temporary failures: Max retries before skipping

**Graceful Degradation:**
- Single page failures don't stop entire import
- Failed pages logged with full context (ID, title, error)
- Statistics track failed and skipped counts
- Images that fail to upload don't prevent page creation
- Continue processing remaining content

**Error Examples:**
```python
# Network error → Retry → Success
# Or: Retry → Retry → Log warning → Continue

# Page creation fails → Log error → Update stats['failed'] → Next page

# Image upload fails for 1 of 5 images → Log warning → 
#        Upload remaining 4 → Rewrite remaining references → Continue
```

**Import statistics include:**
- `shelves`, `books`, `chapters`, `pages`: Successfully created
- `images_uploaded`: Count of successfully uploaded attachments
- `skipped`: Items not processed (parent not selected, filtered out)
- `failed`: Items that failed after retries
- `errors`: Detailed error list with context (first 5 shown in summary)

#### Troubleshooting

**Authentication Errors:**
```
ERROR: Authentication failed: 401 Unauthorized
→ Check token_id and token_secret
→ Verify token hasn't been revoked
→ Ensure token has appropriate permissions (read/write)
→ Check BookStack logs for authentication details
```

**Hierarchy Errors:**
```
WARNING: Flattening nested page 'Deep Nested Page' (ID: 12345).
BookStack doesn't support pages nested under pages...
→ Normal for deep hierarchies
→ Review flattened structure in BookStack after import
→ Adjust Confluence hierarchy before migration if needed
```

**Image Upload Failures:**
```
WARNING: Failed to upload image 'diagram.png': Connection timeout
→ Check network connectivity
→ Increase timeout in config
→ Verify image file exists and is accessible
→ Try uploading manually through BookStack UI
```

**Page Creation Failures:**
```
ERROR: Failed to create page 'API Documentation': 400 Bad Request
→ Check page title length (max 255 chars)
→ Verify markdown→HTML conversion succeeded
→ Check BookStack logs for specific validation errors
→ Inspect HTML content for malformed tags
```

**Rate Limiting:**
```
WARNING: Rate limited (429). Retrying after 5s
→ Normal for large imports
→ Increase rate_limit in config to slow down
→ Monitor BookStack server resources
→ Consider importing during off-peak hours
```

**Common Solutions:**
1. **Increase timeouts** for slow networks:
   ```yaml
   advanced:
     request_timeout: 60  # Increase from 30s
   ```

2. **Reduce parallel processing** for rate-limited APIs:
   ```yaml
   migration:
     batch_size: 2  # Reduce from default 5
   ```

3. **Enable dry-run** to preview issues:
   ```bash
   python migrate.py --export-target bookstack --dry-run --verbose
   ```

4. **Check logs** for specific errors:
   ```bash
   grep -E "ERROR|WARNING" migration.log
   ```

5. **Verify BookStack API** is accessible:
   ```bash
   curl -H "Authorization: Token YOUR_ID:YOUR_SECRET" \
        https://bookstack.example.com/api/shelves
   ```

#### API Rate Limits and Performance

**BookStack API limits:**
- Default: 180 requests per minute (adjustable in BookStack settings)
- Large attachments may have per-request size limits
- Monitoring: https://bookstack.example.com/api/stats (if enabled)

**Performance tuning:**
```yaml
# For large imports
advanced:
  rate_limit: 0.1        # 100ms between requests (safe default)
  max_retries: 3
  
# For fast servers and small imports
advanced:
  rate_limit: 0.0        # No rate limiting
  max_retries: 5
```

**Batch imports:**
- Process 1 space at a time for reliability
- Each space creates 1 shelf
- Books, chapters, and pages created sequentially within each space
- Images uploaded after page creation (sequential per page)
- Parallel batch processing is supported at the space level

#### Additional Resources

- [BookStack API Documentation](https://demo.bookstackapp.com/api/docs)
- [BookStack PHP API Wrapper Examples](https://github.com/phonicx/bsapi)
- Confluence to BookStack Migration Guide (coming soon)
- Example configurations in `/examples/bookstack-import.yaml`### BookStack

Directly imports content to BookStack via REST API:

**Features:**
- Creates shelves, books, and chapters
- Maps Confluence spaces to BookStack books
- Uploads images and attachments
- Preserves page metadata and tags
- Batch processing for large migrations

## Content Processing

### Confluence Macro Conversion

The tool converts common Confluence macros to their markdown equivalents:

| Confluence Macro | Markdown Equivalent |
|-----------------|---------------------|
| Note/Info Panel | `> **Note:** content` |
| Warning Panel | `> **Warning:** content` |
| Tip Panel | `> **Tip:** content` |
| Code Block | ` ```language\ncode\n``` ` |
| Expand | HTML `<details>` block |
| TOC | Generate markdown TOC |
| Children | List of child pages |
| Anchor | HTML anchor tag |

### Link Resolution

- Internal Confluence links → Relative markdown links
- External links → Preserved as-is
- Attachments → Relative file paths or uploaded references
- Page anchors → HTML anchor tags

### Attachment Handling

- Download attachments from Confluence
- Filter by file size and type
- Organize in `attachments/` subdirectories
- Update references in markdown content

## Logging and Monitoring

### Log Levels

- `--verbose` (`-v`): INFO level (general progress)
- `--verbose --verbose` (`-vv`): DEBUG level (detailed debugging)
- Default: WARNING level (errors and warnings only)

### Progress Tracking

The tool provides detailed progress tracking:

```
Starting processing of 150 pages
Processed 10/150 pages (140 remaining) - Last: Success
Processed 20/150 pages (130 remaining) - Last: Success
...
=== Progress Summary: PAGES ===
Total: 150
Processed: 150
Successful: 148
Failed: 2
Success Rate: 98.7%
Elapsed Time: 2m 35s
```

### Migration Reports

After completion, a JSON report is generated with:
- Total pages, attachments, and spaces processed
- Conversion success rates
- Failed pages with error messages
- Processing timestamps

## Advanced Usage

### Environment Variables

Use environment variables for sensitive configuration:

```bash
export CONFLUENCE_PASSWORD="secret"
export WIKIJS_API_KEY="your-wikijs-key"
export BOOKSTACK_TOKEN_SECRET="your-token-secret"

python migrate.py --export-target both_wikis
```

### Batch Processing

Adjust batch size for performance tuning:

```bash
# For fast networks and powerful systems
python migrate.py --batch-size 10 --export-target markdown_files

# For slower connections or rate-limited APIs
python migrate.py --batch-size 2 --export-target wikijs
```

### Filtering

Migrate specific content subsets:

```bash
# Specific spaces
python migrate.py --spaces DEV DOC --export-target markdown_files

# Pages modified after date
python migrate.py --since-date "2023-01-01" --export-target wikijs

# Single page for testing
python migrate.py --page-id "123456789" --export-target markdown_files
```

## Troubleshooting

### Connection Issues

**SSL Certificate Errors**
```bash
# Test SSL connection
curl -v https://confluence.example.com

# Disable SSL verification (testing only)
confluence:
  verify_ssl: false
```

**Timeout Errors**
```bash
# Increase timeout in config
advanced:
  request_timeout: 60  # Increase from 30s
```

**Firewall/Proxy Issues**
```bash
# Set proxy environment variables
export HTTP_PROXY=http://proxy.example.com:8080
export HTTPS_PROXY=http://proxy.example.com:8080
```

### Authentication Issues

**401 Unauthorized**
- Verify credentials are correct
- Check `auth_type` matches your Confluence (basic vs bearer)
- For Confluence Cloud, use bearer with API token from https://id.atlassian.com/manage-profile/security/api-tokens
- For Confluence Server, use basic auth with username/password
- Test with `curl`:
  ```bash
  curl -u username:password https://confluence.example.com/rest/api/space
  ```

**403 Forbidden**
- Verify user has read access to spaces/pages
- Check if user is in groups with appropriate permissions
- API tokens require proper scope (read:confluence for Cloud)

### Rate Limiting & Performance

**429 Too Many Requests**
```yaml
# Increase rate limiting delay
advanced:
  rate_limit: 0.5  # Wait 0.5s between requests
  
# Or reduce batch size
migration:
  batch_size: 2  # Reduce from default 5
```

**Slow Performance**
- Enable smart caching with `validate` mode to reduce API calls while ensuring freshness
  ```yaml
  advanced:
    cache:
      enabled: true
      mode: "validate"  # Smart caching with HTTP validation
  ```
- Check cache hit rate in migration report - should be >70% for effective caching
- Increase `ttl_seconds` for better cache reuse: `ttl_seconds: 172800` (2 days)
- Reduce batch size for slower networks: `batch_size: 2`
- Use `since_date` filter to process only recent changes

### Cache Issues

**Cache Configuration Problems**

```yaml
# Recommended cache configuration
advanced:
  cache:
    enabled: true
    mode: "validate"      # Smart validation mode
    ttl_seconds: 86400    # 1 day cache lifetime
    cache_attachments: true
    verify_checksums: true
```

**Stale Content Despite Caching**
- Check migration report for cache statistics
- If hit rate is low, cache may not be working properly
- Clear cache manually: `rm -rf ./.cache/*`
- Verify cache directory permissions and disk space
- Check logs for cache read/write errors

**Cache Not Working (No Hits)**
- Verify cache is enabled: `cache.enabled: true`
- Check cache directory exists and is writable: `ls -la ./.cache`
- Look for cache initialization in logs: `grep "Cache enabled" migration.log`
- Ensure you're using API mode (HTML mode has limited caching)
- Validate Confluence returns ETag/Last-Modified headers: `curl -I ${CONFLUENCE_URL}/rest/api/space`

**Cache Validation Errors**
- Disable header validation if Confluence doesn't support it:
  ```yaml
  advanced:
    cache:
      validate_with_headers: false  # Use TTL-only validation
  ```
- Check Confluence response headers: `curl -I ${URL} | grep -E "ETag|Last-Modified"`
- Use `always_use` mode for offline testing (no validation performed)

**Offline Mode (`always_use`)**
- Uses cached data without network validation
- Best for: testing, development, or when Confluence is unavailable
- Warning: May use stale data - check cache age in stats
- Example: `mode: "always_use"` with pre-populated cache

**Cache Size & Disk Usage**
- Monitor cache directory size: `du -sh ./.cache`
- Large attachments can quickly fill cache - adjust `ttl_seconds` downward
- Cache includes both API responses (JSON) and attachments (binary)
- Clear old cache periodically: `find ./.cache -mtime +7 -delete`

### Content Fetching Issues

**API Mode - Missing Content**
- Verify `body.export_view` is being used (check logs for fallback warnings)
- Some macros may not render in export view (check Confluence macro settings)
- Increase `max_retries` for transient network issues:
  ```yaml
  advanced:
    max_retries: 5
    retry_backoff_factor: 3.0
  ```

**HTML Mode - File Not Found**
- Ensure export was extracted completely (all files, attachments subdirectory)
- Check `index.html` exists in export directory
- Verify file permissions allow reading
- Try re-exporting from Confluence (ensure "Include attachments" is checked)

**Attachment Download Failures**
- Check attachment exclusion rules (file types, size limits)
- Verify attachment still exists in Confluence (not deleted)
- For HTML mode, ensure attachments are in `attachments/{page_id}/` subdirectory
- Check logs for specific error messages and retry status

### Content Quality Issues

**Poor Macro Conversion**
- Check `conversion_metadata` in page models (use `--verbose`)
- Enable macro fallback to raw content:
  ```yaml
  content_processing:
    macro_conversion:
      fallback_to_raw: true
  ```
- Review warnings in migration report for specific macro issues

**Broken Links**
- Use `--verbose` to see link resolution attempts
- Check if target pages were excluded by filters
- Verify Confluence base URL is correct in config
- For cross-space links, ensure all spaces are migrated

**Missing Images**
- Verify images weren't excluded by size/type filters
- Check attachment download succeeded in logs
- For HTML mode, ensure images are in attachments directory
- Try downloading manually to test URL/accessibility

### Debug Mode

Enable debug logging for detailed troubleshooting:

```bash
# Debug logging with output to file
python migrate.py -vv --export-target markdown_files 2>&1 | tee debug.log

# Check specific component logs
grep "confluence_client" debug.log  # API client activity
grep "api_fetcher" debug.log        # API fetcher operations
grep "conversion_metadata" debug.log # Content conversion details
```

### Getting Help

If issues persist:

1. **Search logs** for error patterns:
   ```bash
   grep -i "error\|failed\|exception" debug.log
   ```

2. **Check common solutions**:
   - Review `/home/trb/git/scripts/confluence-to-bookstack/TROUBLESHOOTING.md` for known issues
   - Verify Python version: `python --version` (3.8+)
   - Check dependencies: `pip list | grep -E "requests|beautifulsoup|pyyaml"`

3. **Create issue report** with:
   - Full error message and stack trace
   - Relevant log excerpts (sanitized)
   - Config file (remove sensitive data)
   - Python version and OS
   - Steps to reproduce

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Areas for contribution:
- Additional Confluence macro conversions
- New export targets
- Performance improvements
- Test coverage
- Documentation

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Acknowledgments

This tool builds upon patterns and learnings from:

- [confluence-to-bookstack](https://github.com/your-org/confluence-to-bookstack) - HTML export to BookStack converter
- [bookstack_wikijs_sync](https://github.com/your-org/bookstack_wikijs_sync) - Wiki.js and BookStack synchronization tool

Special thanks to the open-source community for the libraries that make this tool possible.

## Support

For issues, feature requests, or questions:

1. Check existing issues in the repository
2. Review logs in `--verbose` mode
3. Create a new issue with:
   - Error messages and logs
   - Configuration (sanitized)
   - Steps to reproduce

## Content Fetching Modes

The tool supports two fetching modes to accommodate different migration scenarios:

### API Mode

Direct REST API access to Confluence with real-time data retrieval.

**Features:**
- **Live Data**: Always fetches current content from Confluence
- **High Fidelity**: Uses `body.export_view` for rendered HTML with expanded macros
- **Filtering**: Supports CQL search, date-range filtering (`since_date`), single-page export (`page_id`)
- **Metadata**: Extracts comprehensive metadata (version history, labels, permissions)
- **Performance**: Efficient pagination and caching

**Requirements:**
- Confluence credentials (username/password or API token)
- Network access to Confluence
- API rate limit awareness for large instances

**Best For:**
- Production migrations requiring current data
- Large-scale migrations with filtering needs
- When maximum content fidelity is critical

**Configuration:**
```yaml
migration:
  mode: "api"

confluence:
  base_url: "https://confluence.example.com"
  auth_type: "basic"  # or "bearer" for API tokens
  username: "your-username"
  password: ${CONFLUENCE_PASSWORD}
```

### HTML Export Mode

Parse Confluence HTML export files without API access.

**Features:**
- **Offline**: No network access or authentication required
- **Complete**: Exports contain all pages, attachments, and metadata
- **Compatible**: Works with all Confluence versions that support HTML export
- **Safe**: No risk of rate limiting or API changes

**Requirements:**
- Confluence HTML export files (zip extracted)
- Properly structured export directory with `index.html`

**Best For:**
- Offline migrations or air-gapped environments
- When API access is restricted or unavailable
- Backup/recovery scenarios
- Testing or development migrations

**Configuration:**
```yaml
migration:
  mode: "html"

confluence:
  html_export_path: "./confluence-export-html"  # Path to extracted HTML export
```

### Mode Comparison

| Feature | API Mode | HTML Export Mode |
|---------|----------|------------------|
| **Data Freshness** | Live | Snapshot at export time |
| **Authentication** | Required | Not required |
| **Filtering** | CQL, date, page ID | Limited (page ID only) |
| **Content Quality** | ★★★★★ (rendered HTML) | ★★★★☆ (exported HTML) |
| **Attachments** | Downloaded via API | Extracted from export |
| **Performance** | API dependent | File I/O dependent |
| **Rate Limiting** | Possible | None |
| **Best For** | Production | Offline/Testing |
