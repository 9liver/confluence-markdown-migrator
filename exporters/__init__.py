"""Markdown export package for Confluence to Markdown migration pipeline.

This package provides functionality to export converted Confluence content to local
markdown files with proper directory structure, attachment handling, and navigation
indexes.

Package Structure:
- markdown_exporter: Main orchestrator for exporting DocumentationTree to filesystem
- attachment_manager: Downloads, deduplicates, and saves attachments per space
- link_rewriter: Rewrites markdown links/images to use relative paths
- index_generator: Creates README.md navigation files for each space

Key Features:
- Preserves Confluence space organization with space-key directories
- Handles attachment deduplication by content hashing
- Rewrites markdown links to relative filesystem paths
- Generates hierarchical navigation indexes
- Integrates with existing models (ConfluencePage, DocumentationTree)
- Supports both API and HTML export modes for attachment downloads

Models Referenced:
- ConfluenceAttachment: local_path field tracks saved file location
- ConfluencePage: markdown_content and conversion_metadata fields
- DocumentationTree: Export input structure with spaces hierarchy

Configuration Referenced:
- export.output_directory: Base output path for exported files
- export.create_index_files: Enable/disable README.md generation
- export.attachment_handling: Size limits, exclusions, directory naming
"""

from .markdown_exporter import MarkdownExporter
from .markdown_reader import MarkdownReader
from .attachment_manager import AttachmentManager
from .link_rewriter import LinkRewriter
from .index_generator import IndexGenerator

__all__ = [
    'MarkdownExporter',
    'MarkdownReader',
    'AttachmentManager',
    'LinkRewriter',
    'IndexGenerator'
]