"""Main markdown exporter orchestrator for Confluence to Markdown migration."""

import hashlib
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from models import DocumentationTree, ConfluenceSpace, ConfluencePage
from logger import ProgressTracker
from .attachment_manager import AttachmentManager
from .link_rewriter import LinkRewriter
from .index_generator import IndexGenerator


class MarkdownExporter:
    """
    Orchestrates export of DocumentationTree to local markdown files.
    
    This exporter:
    1. Creates space directories with proper hierarchy
    2. Downloads and saves attachments (with deduplication)
    3. Rewrites markdown links to relative paths
    4. Writes markdown files with frontmatter
    5. Generates navigation index files (README.md)
    """
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None, output_dir: Optional[str] = None):
        """
        Initialize the markdown exporter.

        Args:
            config: Configuration dictionary with export settings
            logger: Logger instance
            output_dir: Optional output directory override (takes precedence over config)
        """
        self.config = config
        self.logger = logger or logging.getLogger('confluence_markdown_migrator.exporters.markdown_exporter')

        # Extract export configuration
        export_config = config.get('export', {})
        self.output_directory = Path(output_dir) if output_dir else Path(export_config.get('output_directory', './confluence-export'))
        self.create_index_files = export_config.get('create_index_files', True)
        self.organize_by_space = export_config.get('organize_by_space', True)
        
        # Initialize helper components
        self.link_rewriter = LinkRewriter(logger=self.logger)
        self.index_generator = IndexGenerator(logger=self.logger)
        
        # Initialize statistics
        self.stats = {
            'total_pages_exported': 0,
            'total_pages_unchanged': 0,
            'total_attachments_saved': 0,
            'total_attachments_skipped': 0,
            'total_attachments_failed': 0,
            'total_attachments_size_bytes': 0,
            'total_errors': 0,
            'spaces_processed': 0
        }
        
        self.logger.info("MarkdownExporter initialized")
        
        # Track exported files for rollback
        self.exported_files = []
    
    def export_tree(self, tree: DocumentationTree) -> Dict[str, Any]:
        """
        Export entire documentation tree to markdown files.
        
        Args:
            tree: DocumentationTree instance with converted pages
            
        Returns:
            Statistics dictionary with export results
        """
        self.logger.info(f"Starting markdown export to {self.output_directory}")
        
        # Validate/create output directory
        try:
            self.output_directory.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Output directory ready: {self.output_directory}")
        except Exception as e:
            self.logger.error(f"Failed to create output directory: {e}")
            raise
        
        # Process all spaces
        total_spaces = len(tree.spaces)
        with ProgressTracker(total_items=total_spaces, item_type='spaces') as tracker:
            for space_key, space in tree.spaces.items():
                try:
                    self._export_space(space)
                    tracker.increment(success=True)
                    self.stats['spaces_processed'] += 1
                except Exception as e:
                    self.logger.error(f"Failed to export space '{space_key}': {e}", exc_info=True)
                    tracker.increment(success=False)
                    self.stats['total_errors'] += 1
        
        # Log summary
        self._log_export_summary()
        
        return self.stats.copy()
    
    def _export_space(self, space: ConfluenceSpace) -> Dict[str, Any]:
        """
        Export a single Confluence space.
        
        Args:
            space: ConfluenceSpace instance
            
        Returns:
            Space-level statistics
        """
        self.logger.info(f"Exporting space '{space.key}' - {space.name}")
        
        # Create space directory
        if self.organize_by_space:
            space_dir = self.output_directory / space.key
        else:
            space_dir = self.output_directory
        
        space_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize attachment manager for this space
        attachment_manager = AttachmentManager(
            config=self.config,
            space_key=space.key,
            output_dir=space_dir,
            logger=self.logger
        )
        
        # Pre-export validation
        all_space_pages = space.get_all_pages()
        if not all_space_pages:
            self.logger.warning(f"Space '{space.key}' has no pages to export")
            return {
                'pages_exported': 0,
                'attachments_saved': 0,
                'attachments_skipped': 0,
                'attachments_failed': 0,
                'errors': []
            }
        
        pages_with_content = sum(1 for p in all_space_pages if p.markdown_content)
        self.logger.info(
            f"Space '{space.key}' has {pages_with_content}/{len(all_space_pages)} pages with markdown content"
        )
        self.logger.debug(f"Collected {len(all_space_pages)} total pages from space '{space.key}'")
        
        # Track exported pages to avoid duplicates
        exported_page_ids = set()

        # Initialize space stats
        space_stats = {
            'pages_exported': 0,
            'pages_unchanged': 0,
            'attachments_saved': 0,
            'attachments_skipped': 0,
            'attachments_failed': 0,
            'errors': []
        }
        
        # Process all pages (flat iteration instead of recursive root-only)
        for idx, page in enumerate(all_space_pages):
            # Skip if already exported
            if page.id in exported_page_ids:
                self.logger.debug(f"Skipping duplicate page ID {page.id}")
                continue
            
            # Skip if no markdown content
            if not page.markdown_content:
                self.logger.info(
                    f"Skipping page '{page.title}' (ID: {page.id}) - no markdown content (page {idx+1}/{len(all_space_pages)})"
                )
                if 'export_errors' not in page.conversion_metadata:
                    page.conversion_metadata['export_errors'] = []
                page.conversion_metadata['export_errors'].append("No markdown content available")
                continue
            
            try:
                page_stats = self._export_page_flat(
                    page=page,
                    space_dir=space_dir,
                    attachment_manager=attachment_manager,
                    space=space
                )
                
                # Update space stats
                space_stats['pages_exported'] += page_stats['pages_exported']
                space_stats['pages_unchanged'] += page_stats.get('pages_unchanged', 0)
                space_stats['attachments_saved'] += page_stats['attachments_saved']
                space_stats['attachments_skipped'] += page_stats['attachments_skipped']
                space_stats['attachments_failed'] += page_stats['attachments_failed']
                space_stats['errors'].extend(page_stats['errors'])
                
                # Track exported page
                if page_stats['pages_exported'] > 0:
                    exported_page_ids.add(page.id)
                
            except Exception as e:
                self.logger.error(f"Error exporting page '{page.title}': {e}", exc_info=True)
                space_stats['errors'].append({
                    'page_id': page.id,
                    'page_title': page.title,
                    'error': str(e)
                })
        
        # Validate stats
        assert space_stats['pages_exported'] <= len(all_space_pages)
        
        # Warn if no pages exported
        if space_stats['pages_exported'] == 0:
            self.logger.warning(
                f"No pages exported from space '{space.key}' despite {len(all_space_pages)} pages available"
            )
        
        # Generate index file
        if self.create_index_files:
            try:
                readme_path = self.index_generator.generate_space_index(space, space_dir)
                self.logger.info(f"Generated index: {readme_path}")
            except Exception as e:
                self.logger.error(f"Failed to generate index for space '{space.key}': {e}")
        
        # Update global stats
        self.stats['total_pages_exported'] += space_stats['pages_exported']
        self.stats['total_pages_unchanged'] += space_stats['pages_unchanged']
        self.stats['total_attachments_saved'] += space_stats['attachments_saved']
        self.stats['total_attachments_skipped'] += space_stats['attachments_skipped']
        self.stats['total_attachments_failed'] += space_stats['attachments_failed']
        
        # Update attachment manager stats
        att_stats = attachment_manager.get_stats()
        self.stats['total_attachments_size_bytes'] += att_stats['total_size_bytes']
        
        # Calculate export rate
        export_rate = (space_stats['pages_exported'] / len(all_space_pages) * 100) if all_space_pages else 0
        if export_rate < 100:
            self.logger.warning(
                f"Only {export_rate:.1f}% of pages exported - check logs for skipped pages"
            )
        
        self.logger.info(
            f"Space '{space.key}' export complete: "
            f"{space_stats['pages_exported']}/{len(all_space_pages)} pages exported, "
            f"{space_stats['attachments_saved']} attachments saved"
        )
        
        return space_stats
    
    # DEPRECATED: Use _export_page_flat() instead. Kept for backward compatibility.
    # The preferred approach is flat iteration via _export_page_flat() for better performance
    # and simpler logic. This method remains for compatibility with external callers.
    def _export_page_recursive(
        self,
        page: ConfluencePage,
        parent_dir: Path,
        space_dir: Path,
        attachment_manager: AttachmentManager,
        depth: int = 0,
        fs_depth: int = 0
    ) -> Dict[str, Any]:
        """
        Recursively export a page and its children.
        
        Args:
            page: ConfluencePage instance
            parent_dir: Parent directory path
            attachment_manager: AttachmentManager instance for this space
            depth: Current depth in page hierarchy (logical Confluence depth)
            fs_depth: Current depth in filesystem relative to space root
            
        Returns:
            Page-level statistics
        """
        page_stats = {
            'pages_exported': 0,
            'attachments_saved': 0,
            'attachments_skipped': 0,
            'attachments_failed': 0,
            'errors': []
        }
        
        # Skip if no markdown content
        if not page.markdown_content:
            self.logger.warning(
                f"Page '{page.title}' (ID: {page.id}) has no markdown content - skipping"
            )
            if 'export_errors' not in page.conversion_metadata:
                page.conversion_metadata['export_errors'] = []
            page.conversion_metadata['export_errors'].append("No markdown content available")
            return page_stats
        
        # Calculate page directory and file paths
        sanitized_title = self._sanitize_filename(page.title)
        
        # Calculate filesystem depth for this page
        # If page has children, create subdirectory
        if page.children:
            page_dir = parent_dir / sanitized_title
            page_dir.mkdir(parents=True, exist_ok=True)
            page_file = page_dir / f"{sanitized_title}.md"
            page_fs_depth = fs_depth + 1  # File is inside new subdirectory
            child_fs_depth = page_fs_depth  # Children at same depth as this page
        else:
            # Leaf page - write directly to parent
            page_dir = parent_dir
            page_file = parent_dir / f"{sanitized_title}.md"
            page_fs_depth = fs_depth  # No increment for leaf pages
            child_fs_depth = fs_depth  # No children
        
        self.logger.debug(f"Exporting page '{page.title}' to {page_file}")
        
        try:
            # Process attachments
            if page.attachments:
                self.logger.debug(f"Processing {len(page.attachments)} attachments for page '{page.title}' (ID: {page.id})")
                attachment_stats = attachment_manager.process_attachments(page)
                page_stats['attachments_saved'] = attachment_stats['downloaded']
                page_stats['attachments_skipped'] = attachment_stats['skipped']
                page_stats['attachments_failed'] = attachment_stats['failed']
                
                self.logger.debug(f"Completed attachments for '{page.title}': {attachment_stats['downloaded']} saved, {attachment_stats['skipped']} skipped, {attachment_stats['failed']} failed")
            
            # Rewrite links
            rewritten_markdown = self.link_rewriter.rewrite_links(
                page=page,
                attachment_manager=attachment_manager,
                page_depth=page_fs_depth
            )
            
            # Generate frontmatter
            frontmatter = self._generate_frontmatter(page)
            
            # Write markdown file
            full_content = f"{frontmatter}\n\n{rewritten_markdown}"
            page_file.write_text(full_content, encoding='utf-8')
            
            page_stats['pages_exported'] += 1
            
            # Update page metadata
            if 'export_metadata' not in page.conversion_metadata:
                page.conversion_metadata['export_metadata'] = {}
            
            export_timestamp = datetime.utcnow().isoformat() + 'Z'
            
            page.conversion_metadata['export_metadata'].update({
                'exported_path': str(page_file.relative_to(space_dir)),
                'export_timestamp': export_timestamp,
                'attachments_processed': page_stats['attachments_saved'],
                'errors': page_stats['errors']
            })
            
        except Exception as e:
            self.logger.error(f"Error exporting page '{page.title}': {e}", exc_info=True)
            page_stats['errors'].append({
                'page_id': page.id,
                'error': str(e)
            })
            if 'export_errors' not in page.conversion_metadata:
                page.conversion_metadata['export_errors'] = []
            page.conversion_metadata['export_errors'].append(str(e))
        
        # Recursively export children
        for child in page.children:
            try:
                child_stats = self._export_page_recursive(
                    page=child,
                    parent_dir=page_dir,
                    space_dir=space_dir,
                    attachment_manager=attachment_manager,
                    depth=depth + 1,
                    fs_depth=child_fs_depth
                )
                
                # Merge child stats
                for key in page_stats:
                    if key != 'errors':  # Keep parent's errors separate
                        page_stats[key] += child_stats[key]
                page_stats['errors'].extend(child_stats['errors'])
                
            except Exception as e:
                self.logger.error(f"Error exporting child page '{child.title}': {e}", exc_info=True)
                page_stats['errors'].append({
                    'page_id': child.id,
                    'page_title': child.title,
                    'error': str(e)
                })
        
        return page_stats
    
    def _export_page_flat(
        self,
        page: ConfluencePage,
        space_dir: Path,
        attachment_manager: AttachmentManager,
        space: ConfluenceSpace
    ) -> Dict[str, Any]:
        """
        Export a single page without recursion (flat iteration approach).
        
        Calculates page directory based on parent chain for proper hierarchy.
        
        Args:
            page: ConfluencePage instance
            space_dir: Root directory for the space
            attachment_manager: AttachmentManager instance for this space
            
        Returns:
            Page-level statistics
        """
        page_stats = {
            'pages_exported': 0,
            'pages_unchanged': 0,
            'attachments_saved': 0,
            'attachments_skipped': 0,
            'attachments_failed': 0,
            'errors': []
        }

        # Calculate page directory based on parent chain
        page_dir, page_file = self._get_page_path(page, space_dir, space)
        
        # Compute actual filesystem depth for correct relative links
        if page_dir == space_dir:
            page_depth = 0
        else:
            try:
                relative_dir = page_dir.relative_to(space_dir)
                page_depth = len(relative_dir.parts)
            except ValueError:
                # page_dir not under space_dir (shouldn't happen with current logic)
                self.logger.warning(
                    f"Page directory {page_dir} is not under space directory {space_dir}, "
                    f"using depth=0 for page '{page.title}' (ID: {page.id})"
                )
                page_depth = 0
        
        self.logger.debug(f"Computed page_depth={page_depth} for '{page.title}' (dir: {page_dir})")
        self.logger.debug(f"Exporting page '{page.title}' (ID: {page.id}) to {page_file}")
        
        try:
            # Create parent directories with better error handling
            try:
                page_dir.mkdir(parents=True, exist_ok=True)
            except PermissionError as e:
                parent_exists = page_dir.parent.exists()
                parent_is_dir = page_dir.parent.is_dir() if parent_exists else False
                parent_writable = os.access(str(page_dir.parent), os.W_OK) if parent_exists else False
                self.logger.error(
                    f"Permission denied creating directory {page_dir}: {e}. "
                    f"Parent exists: {parent_exists}, "
                    f"is dir: {parent_is_dir}, "
                    f"writable: {parent_writable}"
                )
                raise
            except OSError as e:
                self.logger.error(f"OS error creating directory {page_dir}: {e}")
                raise
            
            # Process attachments
            if page.attachments:
                self.logger.debug(f"Processing {len(page.attachments)} attachments for page '{page.title}' (ID: {page.id})")
                attachment_stats = attachment_manager.process_attachments(page)
                page_stats['attachments_saved'] = attachment_stats['downloaded']
                page_stats['attachments_skipped'] = attachment_stats['skipped']
                page_stats['attachments_failed'] = attachment_stats['failed']
            
            # Rewrite links
            rewritten_markdown = self.link_rewriter.rewrite_links(
                page=page,
                attachment_manager=attachment_manager,
                page_depth=page_depth  # Use computed depth for correct relative paths
            )

            # Calculate relative path for frontmatter
            try:
                relative_path = str(page_file.relative_to(space_dir))
            except ValueError:
                relative_path = page_file.name

            # Generate frontmatter with comprehensive metadata
            frontmatter = self._generate_frontmatter(
                page=page,
                space=space,
                relative_path=relative_path,
                filesystem_depth=page_depth
            )
            
            # Write markdown file with comprehensive error handling
            full_content = f"{frontmatter}\n\n{rewritten_markdown}"
            try:
                # Check if file exists and content is unchanged
                if page_file.exists():
                    try:
                        existing_content = page_file.read_text(encoding='utf-8')
                        if existing_content == full_content:
                            # Content is byte-identical, skip writing
                            self.logger.debug(
                                f"Markdown unchanged for page '{page.title}' (ID: {page.id}), skipping write"
                            )
                            page_stats['pages_unchanged'] += 1
                            return page_stats
                    except Exception as e:
                        # If we can't read existing file, proceed with write
                        self.logger.debug(f"Could not read existing file {page_file}: {e}, proceeding with write")

                page_file.write_text(full_content, encoding='utf-8')
                page_stats['pages_exported'] += 1
                self.logger.debug(f"Successfully wrote {len(full_content)} bytes to {page_file}")
                
                # Update page metadata only on successful write
                if 'export_metadata' not in page.conversion_metadata:
                    page.conversion_metadata['export_metadata'] = {}
                
                export_timestamp = datetime.utcnow().isoformat() + 'Z'
                
                page.conversion_metadata['export_metadata'].update({
                    'exported_path': str(page_file.relative_to(space_dir)),
                    'export_timestamp': export_timestamp,
                    'attachments_processed': page_stats['attachments_saved'],
                    'errors': page_stats['errors']
                })
            except PermissionError as e:
                self.logger.error(f"Permission denied writing to {page_file}: {e}", exc_info=True)
                page_stats['errors'].append({
                    'page_id': page.id,
                    'error': f"Permission denied: {e}"
                })
            except (OSError, IOError) as e:
                self.logger.error(f"IO error writing to {page_file}: {e}", exc_info=True)
                page_stats['errors'].append({
                    'page_id': page.id,
                    'error': f"IO error: {e}"
                })
            
        except Exception as e:
            self.logger.error(f"Error exporting page '{page.title}' (ID: {page.id}, Space: {space.key}): {e}", exc_info=True)
            page_stats['errors'].append({
                'page_id': page.id,
                'error': str(e)
            })
            if 'export_errors' not in page.conversion_metadata:
                page.conversion_metadata['export_errors'] = []
            page.conversion_metadata['export_errors'].append(str(e))
        
        return page_stats
    
    def _generate_frontmatter(
        self,
        page: ConfluencePage,
        space: Optional[ConfluenceSpace] = None,
        relative_path: Optional[str] = None,
        filesystem_depth: int = 0
    ) -> str:
        """
        Generate comprehensive YAML frontmatter for markdown file with Confluence metadata.

        Args:
            page: ConfluencePage instance
            space: ConfluenceSpace instance for parent chain traversal
            relative_path: Relative path from space root
            filesystem_depth: Depth in exported filesystem structure

        Returns:
            YAML frontmatter string
        """
        frontmatter = {}

        # Core metadata
        frontmatter['confluence_page_id'] = page.id
        frontmatter['title'] = page.title
        frontmatter['space_key'] = page.space_key

        # Space name if available
        if space:
            frontmatter['space_name'] = space.name

        # Parent chain information for hierarchy reconstruction
        parent_id = page.parent_id
        parent_chain = []
        parent_titles = []

        if space and parent_id:
            frontmatter['parent_id'] = parent_id

            # Build parent chain by traversing up
            current_parent_id = parent_id
            while current_parent_id:
                parent_page = space.get_page_by_id(current_parent_id)
                if parent_page:
                    parent_chain.insert(0, parent_page.id)
                    parent_titles.insert(0, parent_page.title)
                    current_parent_id = parent_page.parent_id
                else:
                    break

            if parent_chain:
                frontmatter['parent_chain'] = parent_chain
                frontmatter['parent_titles'] = parent_titles

        # Hierarchy depth (distance from root)
        hierarchy_depth = len(parent_chain)
        frontmatter['hierarchy_depth'] = hierarchy_depth

        # Path reconstruction metadata
        if page.url:
            frontmatter['confluence_url'] = page.url

        if relative_path:
            frontmatter['relative_path'] = relative_path

        frontmatter['filesystem_depth'] = filesystem_depth

        # Last modified
        last_modified = page.metadata.get("last_modified")
        if last_modified:
            frontmatter['last_modified'] = last_modified

        # Author
        author = page.metadata.get("author")
        if author:
            frontmatter['author'] = author

        # Labels - ensure it's a list
        labels = page.metadata.get("labels", [])
        # Ensure labels is always a list for proper YAML formatting
        if labels:
            frontmatter['labels'] = list(labels)  # Force list type
        else:
            frontmatter['labels'] = []

        # Version
        frontmatter['version'] = page.metadata.get("version", 1)

        # Attachment metadata - ensure it's always an array
        if page.attachments:
            attachments_list = []
            for att in page.attachments:
                att_data = {
                    'id': att.id,
                    'title': att.title,
                    'media_type': att.media_type,
                    'file_size': att.file_size
                }
                if att.local_path:
                    att_data['local_path'] = str(att.local_path)
                if att.content_checksum:
                    att_data['checksum'] = att.content_checksum
                attachments_list.append(att_data)

            frontmatter['attachments'] = attachments_list  # Will be formatted as YAML array
            frontmatter['attachment_count'] = len(page.attachments)
        else:
            frontmatter['attachments'] = []  # Explicitly empty array
            frontmatter['attachment_count'] = 0

        # Conversion metadata
        conversion_status = page.conversion_metadata.get("conversion_status", "pending")
        frontmatter['conversion_status'] = conversion_status

        conversion_warnings = page.conversion_metadata.get("conversion_warnings", [])
        if conversion_warnings:
            frontmatter['conversion_warnings'] = conversion_warnings

        macros_converted = page.conversion_metadata.get("macros_converted", [])
        if macros_converted:
            frontmatter['macros_converted'] = macros_converted

        macros_failed = page.conversion_metadata.get("macros_failed", [])
        if macros_failed:
            frontmatter['macros_failed'] = macros_failed

        # Integrity metadata
        content_checksum = page.metadata.get("content_checksum")
        if content_checksum:
            frontmatter['content_checksum'] = content_checksum

        markdown_checksum = page.conversion_metadata.get("markdown_checksum")
        if markdown_checksum:
            frontmatter['markdown_checksum'] = markdown_checksum

        if page.integrity_status and page.integrity_status != 'pending':
            frontmatter['integrity_status'] = page.integrity_status

        # Export timestamp
        frontmatter['export_timestamp'] = datetime.utcnow().isoformat() + 'Z'

        # Use yaml.dump for proper escaping and formatting
        # default_flow_style=False ensures arrays and lists are formatted in block style (with - prefixes)
        yaml_str = yaml.dump(
            frontmatter,
            default_flow_style=False,  # Forces block style for lists/arrays
            allow_unicode=True,
            sort_keys=False,
            width=1000  # Prevent line wrapping
        )

        return f"---\n{yaml_str}---"
    def _get_page_path(self, page: ConfluencePage, space_dir: Path, space: ConfluenceSpace) -> Tuple[Path, Path]:
        """
        Calculate page directory and file path based on parent chain.
        
        Args:
            page: ConfluencePage instance
            space_dir: Root directory for the space
            space: ConfluenceSpace instance
            
        Returns:
            Tuple of (page_directory, page_file_path)
        """
        # Start with space directory
        page_dir = space_dir
        
        # Build path by traversing parent chain
        parent_titles = []
        current_page = page
        
        # Traverse up the parent chain until we reach a root page
        while current_page.parent_id:
            parent = space.get_page_by_id(current_page.parent_id)
            if parent:
                # Add parent's sanitized title to the path (in reverse order)
                parent_titles.insert(0, self._sanitize_filename(parent.title))
                current_page = parent
            else:
                # Orphan page - parent not found, stop traversal
                self.logger.warning(
                    f"Page '{page.title}' (ID: {page.id}) has parent_id {page.parent_id} "
                    f"but parent page not found in space '{space.key}'"
                )
                break
        
        # Apply parent titles to directory path
        for parent_title in parent_titles:
            page_dir = page_dir / parent_title
        
        # Add current page's title to get the final file path
        sanitized_title = self._sanitize_filename(page.title)
        
        # For pages with children, create subdirectory to match legacy behavior
        if page.children:
            page_dir = page_dir / sanitized_title
        
        page_file = page_dir / f"{sanitized_title}.md"
        
        return page_dir, page_file
    
    def _sanitize_filename(self, title: str) -> str:
        """
        Convert page title to filesystem-safe filename.
        
        Args:
            title: Page title
            
        Returns:
            Sanitized filename
        """
        if not title:
            return "untitled"
        
        # Convert to lowercase
        sanitized = title.lower()
        
        # Replace spaces and special characters with hyphens
        sanitized = re.sub(r'[^a-z0-9\-_]', '-', sanitized)
        
        # Remove consecutive hyphens
        sanitized = re.sub(r'-+', '-', sanitized)
        
        # Remove leading/trailing hyphens
        sanitized = sanitized.strip('-')
        
        # Truncate to reasonable length
        max_len = 100
        if len(sanitized) > max_len:
            sanitized = sanitized[:max_len]
        
        # Ensure it's not empty
        if not sanitized:
            sanitized = "untitled"
        
        return sanitized
    
    def _log_export_summary(self) -> None:
        """Log final export statistics."""
        self.logger.info("=" * 60)
        self.logger.info("MARKDOWN EXPORT SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Spaces processed: {self.stats['spaces_processed']}")
        self.logger.info(f"Pages exported: {self.stats['total_pages_exported']}")
        if self.stats['total_pages_unchanged'] > 0:
            self.logger.info(f"Pages unchanged: {self.stats['total_pages_unchanged']}")
        self.logger.info(f"Attachments saved: {self.stats['total_attachments_saved']}")
        self.logger.info(f"Attachments skipped: {self.stats['total_attachments_skipped']}")
        self.logger.info(f"Attachments failed: {self.stats['total_attachments_failed']}")
        self.logger.info(f"Total attachments size: {self._format_bytes(self.stats['total_attachments_size_bytes'])}")
        self.logger.info(f"Total errors: {self.stats['total_errors']}")
        self.logger.info(f"Output directory: {self.output_directory}")
        self.logger.info("=" * 60)
    
    def _format_bytes(self, bytes_val: int) -> str:
        """Format bytes to human-readable string."""
        if bytes_val == 0:
            return "0 B"
        
        for unit in ['B', 'KB', 'MB', 'GB']:
            if bytes_val < 1024.0:
                return f"{bytes_val:.1f} {unit}"
            bytes_val /= 1024.0
        
        return f"{bytes_val:.1f} TB"