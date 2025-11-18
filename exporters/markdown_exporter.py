"""Main markdown exporter orchestrator for Confluence to Markdown migration."""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

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
    
    def __init__(self, config: Dict[str, Any], logger: Optional[logging.Logger] = None):
        """
        Initialize the markdown exporter.
        
        Args:
            config: Configuration dictionary with export settings
            logger: Logger instance
        """
        self.config = config
        self.logger = logger or logging.getLogger('confluence_markdown_migrator.exporters.markdown_exporter')
        
        # Extract export configuration
        export_config = config.get('export', {})
        self.output_directory = Path(export_config.get('output_directory', './confluence-export'))
        self.create_index_files = export_config.get('create_index_files', True)
        self.organize_by_space = export_config.get('organize_by_space', True)
        
        # Initialize helper components
        self.link_rewriter = LinkRewriter(logger=self.logger)
        self.index_generator = IndexGenerator(logger=self.logger)
        
        # Initialize statistics
        self.stats = {
            'total_pages_exported': 0,
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
        
        # Process root pages
        space_stats = {
            'pages_exported': 0,
            'attachments_saved': 0,
            'attachments_skipped': 0,
            'attachments_failed': 0,
            'errors': []
        }
        
        for page in space.pages:
            try:
                page_stats = self._export_page_recursive(
                    page=page,
                    parent_dir=space_dir,
                    space_dir=space_dir,
                    attachment_manager=attachment_manager,
                    depth=0,
                    fs_depth=0
                )
                
                # Update space stats
                space_stats['pages_exported'] += page_stats['pages_exported']
                space_stats['attachments_saved'] += page_stats['attachments_saved']
                space_stats['attachments_skipped'] += page_stats['attachments_skipped']
                space_stats['attachments_failed'] += page_stats['attachments_failed']
                space_stats['errors'].extend(page_stats['errors'])
                
            except Exception as e:
                self.logger.error(f"Error exporting page '{page.title}': {e}", exc_info=True)
                space_stats['errors'].append({
                    'page_id': page.id,
                    'page_title': page.title,
                    'error': str(e)
                })
        
        # Generate index file
        if self.create_index_files:
            try:
                readme_path = self.index_generator.generate_space_index(space, space_dir)
                self.logger.info(f"Generated index: {readme_path}")
            except Exception as e:
                self.logger.error(f"Failed to generate index for space '{space.key}': {e}")
        
        # Update global stats
        self.stats['total_pages_exported'] += space_stats['pages_exported']
        self.stats['total_attachments_saved'] += space_stats['attachments_saved']
        self.stats['total_attachments_skipped'] += space_stats['attachments_skipped']
        self.stats['total_attachments_failed'] += space_stats['attachments_failed']
        
        # Update attachment manager stats
        att_stats = attachment_manager.get_stats()
        self.stats['total_attachments_size_bytes'] += att_stats['total_size_bytes']
        
        self.logger.info(
            f"Space '{space.key}' export complete: "
            f"{space_stats['pages_exported']} pages, "
            f"{space_stats['attachments_saved']} attachments saved"
        )
        
        return space_stats
    
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
                attachment_stats = attachment_manager.process_attachments(page)
                page_stats['attachments_saved'] = attachment_stats['downloaded']
                page_stats['attachments_skipped'] = attachment_stats['skipped']
                page_stats['attachments_failed'] = attachment_stats['failed']
            
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
    
    def _generate_frontmatter(self, page: ConfluencePage) -> str:
        """
        Generate YAML frontmatter for markdown file.
        
        Args:
            page: ConfluencePage instance
            
        Returns:
            Formatted frontmatter string
        """
        lines = ["---"]
        
        # Core metadata
        lines.append(f"confluence_page_id: {page.id}")
        lines.append(f"title: {page.title}")
        lines.append(f"space_key: {page.space_key}")
        
        # Last modified
        last_modified = page.metadata.get('last_modified')
        if last_modified:
            lines.append(f"last_modified: {last_modified}")
        
        # Author
        author = page.metadata.get('author')
        if author:
            lines.append(f"author: {author}")
        
        # Labels
        labels = page.metadata.get('labels', [])
        if labels:
            labels_str = ', '.join(labels)
            lines.append(f"labels: [{labels_str}]")
        
        # Version
        version = page.metadata.get('version', 1)
        lines.append(f"version: {version}")
        
        # Conversion status
        conversion_status = page.conversion_metadata.get('conversion_status', 'pending')
        lines.append(f"conversion_status: {conversion_status}")
        
        # Attachments count
        if page.attachments:
            lines.append(f"attachments_count: {len(page.attachments)}")
        
        lines.append("---")
        
        return '\n'.join(lines)
    
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