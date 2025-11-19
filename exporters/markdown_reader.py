"""Markdown reader for importing local markdown files back into DocumentationTree.

This module provides functionality to read exported markdown files with YAML frontmatter
and reconstruct a DocumentationTree for import into Wiki.js or BookStack.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from tqdm import tqdm

from models import (
    ConfluenceAttachment,
    ConfluencePage,
    ConfluenceSpace,
    DocumentationTree
)


class MarkdownReader:
    """
    Reads local markdown files and reconstructs a DocumentationTree from frontmatter.

    This reader enables the import_from_markdown workflow by:
    1. Scanning directories for .md files
    2. Parsing YAML frontmatter for metadata
    3. Reconstructing ConfluencePage objects
    4. Building parent-child relationships
    5. Creating ConfluenceSpace containers
    """

    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the markdown reader.

        Args:
            config: Configuration dictionary
            logger: Logger instance
        """
        self.config = config
        self.logger = logger or logging.getLogger('confluence_markdown_migrator.exporters.markdown_reader')

        # Statistics tracking
        self.stats = {
            'files_scanned': 0,
            'files_parsed': 0,
            'files_skipped': 0,
            'files_failed': 0,
            'pages_loaded': 0,
            'attachments_loaded': 0,
            'spaces_created': 0,
            'orphan_pages': 0,
            'errors': []
        }

        self.logger.info("MarkdownReader initialized")

    def read_export_directory(self, export_dir: Path) -> DocumentationTree:
        """
        Main entry point to scan directory and build DocumentationTree.

        Args:
            export_dir: Path to exported markdown directory

        Returns:
            Reconstructed DocumentationTree
        """
        self.logger.info(f"Reading markdown files from {export_dir}")

        if not export_dir.exists():
            raise ValueError(f"Export directory does not exist: {export_dir}")

        if not export_dir.is_dir():
            raise ValueError(f"Export path is not a directory: {export_dir}")

        # Scan for markdown files
        md_files = self._scan_markdown_files(export_dir)
        self.stats['files_scanned'] = len(md_files)

        if not md_files:
            self.logger.warning(f"No markdown files found in {export_dir}")
            return DocumentationTree()

        self.logger.info(f"Found {len(md_files)} markdown files to process")

        # Parse all markdown files
        pages = []
        with tqdm(total=len(md_files), desc="Parsing markdown files", unit="file") as pbar:
            for file_path in md_files:
                try:
                    page = self._parse_and_reconstruct_page(file_path, export_dir)
                    if page:
                        pages.append(page)
                        self.stats['files_parsed'] += 1
                        self.stats['pages_loaded'] += 1
                        self.stats['attachments_loaded'] += len(page.attachments)
                    else:
                        self.stats['files_skipped'] += 1
                except Exception as e:
                    self.logger.error(f"Failed to parse {file_path}: {e}")
                    self.stats['files_failed'] += 1
                    self.stats['errors'].append({
                        'file': str(file_path),
                        'error': str(e)
                    })
                finally:
                    pbar.update(1)

        # Build tree from pages
        tree = self._build_tree_from_pages(pages)

        # Log summary
        self._log_read_summary()

        return tree

    def _scan_markdown_files(self, export_dir: Path) -> List[Path]:
        """
        Recursively find all .md files in directory.

        Args:
            export_dir: Root directory to scan

        Returns:
            List of markdown file paths
        """
        md_files = []

        for file_path in export_dir.rglob("*.md"):
            # Skip index files (README.md)
            if file_path.name.lower() == "readme.md":
                self.logger.debug(f"Skipping index file: {file_path}")
                continue

            md_files.append(file_path)

        # Sort by path for consistent processing order
        md_files.sort()

        return md_files

    def _parse_and_reconstruct_page(
        self,
        file_path: Path,
        export_dir: Path
    ) -> Optional[ConfluencePage]:
        """
        Parse a markdown file and reconstruct a ConfluencePage.

        Args:
            file_path: Path to markdown file
            export_dir: Root export directory for relative path calculation

        Returns:
            Reconstructed ConfluencePage or None if parsing fails
        """
        try:
            content = file_path.read_text(encoding='utf-8')
        except Exception as e:
            self.logger.error(f"Failed to read file {file_path}: {e}")
            return None

        # Extract frontmatter and markdown content
        frontmatter, markdown_content = self._extract_frontmatter(content)

        if not frontmatter:
            self.logger.warning(f"No valid frontmatter in {file_path}")
            return None

        # Validate required fields
        required_fields = ['confluence_page_id', 'title', 'space_key']
        missing_fields = [f for f in required_fields if f not in frontmatter]

        if missing_fields:
            self.logger.warning(
                f"Missing required fields in {file_path}: {missing_fields}"
            )
            return None

        # Reconstruct page
        page = self._reconstruct_page(frontmatter, markdown_content, file_path)

        # Reconstruct attachments
        attachments = self._reconstruct_attachments(frontmatter, file_path)
        for att in attachments:
            page.add_attachment(att)

        return page

    def _extract_frontmatter(self, content: str) -> Tuple[Dict[str, Any], str]:
        """
        Extract YAML frontmatter from markdown content.

        Args:
            content: Full file content

        Returns:
            Tuple of (frontmatter dict, markdown content)
        """
        # Match YAML frontmatter between --- delimiters
        pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(pattern, content, re.DOTALL)

        if not match:
            return {}, content

        yaml_str = match.group(1)
        markdown_content = match.group(2).strip()

        try:
            frontmatter = yaml.safe_load(yaml_str)
            if not isinstance(frontmatter, dict):
                self.logger.warning("Frontmatter is not a dictionary")
                return {}, content
            return frontmatter, markdown_content
        except yaml.YAMLError as e:
            self.logger.warning(f"Failed to parse YAML frontmatter: {e}")
            return {}, content

    def _reconstruct_page(
        self,
        frontmatter: Dict[str, Any],
        markdown_content: str,
        file_path: Path
    ) -> ConfluencePage:
        """
        Create a ConfluencePage from frontmatter and content.

        Args:
            frontmatter: Parsed YAML frontmatter
            markdown_content: Markdown content without frontmatter
            file_path: Source file path

        Returns:
            Reconstructed ConfluencePage
        """
        # Extract core fields
        page_id = str(frontmatter['confluence_page_id'])
        title = frontmatter['title']
        space_key = frontmatter['space_key']

        # Extract optional parent info
        parent_id = frontmatter.get('parent_id')
        if parent_id:
            parent_id = str(parent_id)

        # Extract URL
        url = frontmatter.get('confluence_url')

        # Build metadata dict
        metadata = {
            'author': frontmatter.get('author'),
            'last_modified': frontmatter.get('last_modified'),
            'version': frontmatter.get('version', 1),
            'labels': frontmatter.get('labels', []),
            'content_type': 'page',
            'content_source': 'markdown_import',
            'content_checksum': frontmatter.get('content_checksum'),
            # Preserve import metadata
            'import_source_file': str(file_path),
            'parent_chain': frontmatter.get('parent_chain', []),
            'parent_titles': frontmatter.get('parent_titles', []),
            'hierarchy_depth': frontmatter.get('hierarchy_depth', 0),
            'relative_path': frontmatter.get('relative_path'),
            'filesystem_depth': frontmatter.get('filesystem_depth', 0),
            'export_timestamp': frontmatter.get('export_timestamp'),
            'space_name': frontmatter.get('space_name')
        }

        # Create page with empty HTML content (we have markdown)
        # Let __post_init__ create default conversion_metadata
        page = ConfluencePage(
            id=page_id,
            title=title,
            content='',  # Original HTML not available from markdown
            space_key=space_key,
            parent_id=parent_id,
            url=url,
            metadata=metadata,
            markdown_content=markdown_content,
            integrity_status=frontmatter.get('integrity_status', 'imported')
        )

        # Update conversion_metadata in-place with values from frontmatter
        # This ensures we inherit any future default fields from ConfluencePage.__post_init__
        if frontmatter.get('conversion_status'):
            page.conversion_metadata['conversion_status'] = frontmatter['conversion_status']
        else:
            page.conversion_metadata['conversion_status'] = 'imported'

        if frontmatter.get('conversion_warnings'):
            page.conversion_metadata['conversion_warnings'] = frontmatter['conversion_warnings']

        if frontmatter.get('macros_converted'):
            page.conversion_metadata['macros_converted'] = frontmatter['macros_converted']

        if frontmatter.get('macros_failed'):
            page.conversion_metadata['macros_failed'] = frontmatter['macros_failed']

        if frontmatter.get('markdown_checksum'):
            page.conversion_metadata['markdown_checksum'] = frontmatter['markdown_checksum']

        return page

    def _reconstruct_attachments(
        self,
        frontmatter: Dict[str, Any],
        file_path: Path
    ) -> List[ConfluenceAttachment]:
        """
        Recreate attachment objects from frontmatter metadata.

        Args:
            frontmatter: Parsed YAML frontmatter
            file_path: Markdown file path for relative path resolution

        Returns:
            List of ConfluenceAttachment objects
        """
        attachments = []
        attachment_data = frontmatter.get('attachments', [])

        if not attachment_data:
            return attachments

        page_id = str(frontmatter['confluence_page_id'])

        for att_data in attachment_data:
            try:
                # Resolve local path relative to markdown file
                local_path = att_data.get('local_path')
                resolved_path = None

                if local_path:
                    # Try to resolve relative to markdown file directory
                    potential_path = file_path.parent / local_path
                    if potential_path.exists():
                        resolved_path = str(potential_path)
                    else:
                        self.logger.debug(
                            f"Attachment file not found: {potential_path}"
                        )

                attachment = ConfluenceAttachment(
                    id=str(att_data.get('id', '')),
                    title=att_data.get('title', ''),
                    media_type=att_data.get('media_type', 'application/octet-stream'),
                    file_size=att_data.get('file_size', 0),
                    download_url='',  # Not available for import
                    page_id=page_id,
                    local_path=resolved_path or local_path,
                    content_checksum=att_data.get('checksum')
                )

                attachments.append(attachment)

            except Exception as e:
                self.logger.warning(
                    f"Failed to reconstruct attachment from {att_data}: {e}"
                )

        return attachments

    def _build_tree_from_pages(self, pages: List[ConfluencePage]) -> DocumentationTree:
        """
        Build a DocumentationTree from a list of pages.

        Args:
            pages: List of reconstructed ConfluencePage objects

        Returns:
            Organized DocumentationTree
        """
        tree = DocumentationTree()

        # Update tree metadata
        tree.metadata.update({
            'fetch_mode': 'markdown_import',
            'total_pages_fetched': len(pages),
            'total_attachments_fetched': sum(len(p.attachments) for p in pages)
        })

        # Group pages by space
        pages_by_space: Dict[str, List[ConfluencePage]] = {}
        for page in pages:
            space_key = page.space_key
            if space_key not in pages_by_space:
                pages_by_space[space_key] = []
            pages_by_space[space_key].append(page)

        # Create spaces and organize pages
        for space_key, space_pages in pages_by_space.items():
            # Create space (use first page's metadata for space name if available)
            space_name = space_key
            for page in space_pages:
                # Check if space_name was stored in frontmatter
                if page.metadata.get('space_name'):
                    space_name = page.metadata['space_name']
                    break

            space = ConfluenceSpace(
                key=space_key,
                name=space_name,
                id=f"imported_{space_key}",
                description=f"Imported from markdown files"
            )

            # Build page index for linking
            page_index: Dict[str, ConfluencePage] = {p.id: p for p in space_pages}

            # Link parent-child relationships
            self._link_parent_child_relationships(space_pages, page_index)

            # Add root pages (no parent or parent not in this space) to space
            for page in space_pages:
                if page.parent_id is None or page.parent_id not in page_index:
                    space.add_page(page)
                    if page.parent_id and page.parent_id not in page_index:
                        self.stats['orphan_pages'] += 1
                        self.logger.debug(
                            f"Page '{page.title}' (ID: {page.id}) has parent_id "
                            f"{page.parent_id} not found in space - treated as root"
                        )

            tree.add_space(space)
            self.stats['spaces_created'] += 1

            self.logger.info(
                f"Space '{space_key}': {len(space_pages)} pages, "
                f"{len(space.pages)} root pages"
            )

        return tree

    def _link_parent_child_relationships(
        self,
        pages: List[ConfluencePage],
        page_index: Dict[str, ConfluencePage]
    ) -> None:
        """
        Rebuild parent-child links between pages.

        Args:
            pages: List of pages to link
            page_index: Dictionary mapping page IDs to pages
        """
        # Sort by hierarchy depth to process parents before children
        sorted_pages = sorted(
            pages,
            key=lambda p: p.metadata.get('hierarchy_depth', 0)
        )

        for page in sorted_pages:
            if page.parent_id and page.parent_id in page_index:
                parent = page_index[page.parent_id]
                # Avoid duplicates
                if page not in parent.children:
                    parent.add_child(page)

    def _log_read_summary(self) -> None:
        """Log summary of markdown reading operation."""
        self.logger.info("=" * 60)
        self.logger.info("MARKDOWN READER SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Files scanned: {self.stats['files_scanned']}")
        self.logger.info(f"Files parsed: {self.stats['files_parsed']}")
        self.logger.info(f"Files skipped: {self.stats['files_skipped']}")
        self.logger.info(f"Files failed: {self.stats['files_failed']}")
        self.logger.info(f"Pages loaded: {self.stats['pages_loaded']}")
        self.logger.info(f"Attachments loaded: {self.stats['attachments_loaded']}")
        self.logger.info(f"Spaces created: {self.stats['spaces_created']}")
        self.logger.info(f"Orphan pages: {self.stats['orphan_pages']}")

        if self.stats['errors']:
            self.logger.warning(f"Total errors: {len(self.stats['errors'])}")
            for error in self.stats['errors'][:5]:  # Show first 5 errors
                self.logger.warning(f"  - {error['file']}: {error['error']}")
            if len(self.stats['errors']) > 5:
                self.logger.warning(
                    f"  ... and {len(self.stats['errors']) - 5} more errors"
                )

        self.logger.info("=" * 60)

    def get_stats(self) -> Dict[str, Any]:
        """Return current statistics."""
        return self.stats.copy()


__all__ = ['MarkdownReader']
