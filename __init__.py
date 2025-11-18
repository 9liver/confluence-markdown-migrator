"""
Confluence to Markdown Migration Tool

A standalone tool for migrating Confluence content to Markdown format with
support for both Wiki.js and BookStack as export targets.

Features:
- Dual-mode fetching: Confluence REST API or HTML export parsing
- High-fidelity HTML to Markdown conversion
- Confluence macro conversion (info, warning, code, expand, panel, etc.)
- Attachment handling with filtering and size limits
- Internal link resolution and anchor preservation
- Interactive TUI for space/page selection
- Export to local markdown files, Wiki.js, or BookStack
- Comprehensive logging and progress tracking
- Dry-run mode for safe testing
- Resumable migrations with status tracking

Basic Usage:
    1. Copy config.yaml.example to config.yaml
    2. Fill in your Confluence credentials and target system settings
    3. Run: python migrate.py --mode api --export-target markdown_files
    4. For interactive mode: python migrate.py --interactive

Example Configuration (config.yaml):
    confluence:
        base_url: "https://confluence.example.com"
        auth_type: "basic"
        username: "your-username"
        password: ${CONFLUENCE_PASSWORD}
    
    export:
        output_directory: "./confluence-export"
        markdown_flavor: "gfm"
"""

"""Confluence to Markdown Migration Tool

A standalone tool for migrating Confluence content to Markdown format with
support for both Wiki.js and BookStack as export targets.
"""

__version__ = "1.0.0"
__author__ = "Your Name"
__description__ = "Confluence to Markdown migration tool with Wiki.js and BookStack support"

# Import and expose key classes for public API
from .models import (
    ConfluenceAttachment,
    ConfluencePage,
    ConfluenceSpace,
    DocumentationTree,
    ExportTarget,
    MigrationStatus
)
from .config_loader import ConfigLoader, get_nested
from .logger import setup_logging, ProgressTracker, log_section, log_config

# Expose main entry point for CLI
from .migrate import main as cli_main

__all__ = [
    # Version info
    '__version__',
    '__author__',
    '__description__',
    
    # Core data models
    'ConfluenceAttachment',
    'ConfluencePage',
    'ConfluenceSpace',
    'DocumentationTree',
    'ExportTarget',
    'MigrationStatus',
    
    # Configuration
    'ConfigLoader',
    'get_nested',
    
    # Logging
    'setup_logging',
    'ProgressTracker',
    'log_section',
    'log_config',
    
    # CLI entry point
    'cli_main',
]
