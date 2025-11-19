"""
Wiki.js Importer Orchestrator for Confluence to Wiki.js Migration.

Main entry point for importing Confluence content to Wiki.js using GraphQL API.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from collections import defaultdict

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

from models import ConfluencePage, ConfluenceSpace, DocumentationTree
from .wikijs_client import WikiJsClient, WikiJsApiError, WikiJsConnectionError
from .hierarchy_mapper import ConfluenceHierarchyMapper
from .asset_uploader import AssetUploader


logger = logging.getLogger('confluence_markdown_migrator.importers.wikijs_importer')


class WikiJsImporter:
    """
    Orchestrates import of Confluence content to Wiki.js.
    
    This importer:
    1. Maps Confluence hierarchies to Wiki.js flat paths
    2. Handles page creation, updates, and conflict resolution
    3. Uploads attachments as Wiki.js assets
    4. Preserves Confluence labels as Wiki.js tags
    5. Supports dry-run mode for safe previews
    """

    def __init__(
        self,
        config: Dict[str, Any],
        tree: DocumentationTree,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the Wiki.js importer.
        
        Args:
            config: Configuration dictionary
            tree: DocumentationTree with converted pages
            logger: Logger instance
        """
        self.config = config
        self.tree = tree
        self.logger = logger or logging.getLogger('confluence_markdown_migrator.importers.wikijs_importer')
        
        # Extract Wiki.js configuration
        self.wikijs_config = config.get('wikijs', {})
        self.conflict_resolution = self.wikijs_config.get('conflict_resolution', 'skip')
        self.preserve_labels = self.wikijs_config.get('preserve_labels', True)
        self.include_space = self.wikijs_config.get('include_space_in_path', True)
        
        # Initialize components
        self.client = WikiJsClient.from_config(config)
        self.mapper = ConfluenceHierarchyMapper()
        self.asset_uploader = AssetUploader(config, self.client, self.logger)
        
        # Import statistics
        self.stats = {
            'total_pages': 0,
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'failed': 0,
            'attachments_uploaded': 0,
            'errors': []
        }
        
        self.logger.info("WikiJsImporter initialized")
        
        # Track created resources for rollback
        self.created_resources = {
            'pages': [],
            'attachments': []
        }
    
    def import_pages(
        self,
        selected_page_ids: Optional[Set[str]] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Import pages to Wiki.js.
        
        Args:
            selected_page_ids: Set of page IDs to import (None for all)
            dry_run: If True, only log intended actions without API calls
            
        Returns:
            Statistics dictionary with import results
        """
        self.logger.info(f"Starting Wiki.js import (dry_run={dry_run})")
        
        # Reset statistics for each import run
        self._reset_stats()
        
        # Get pages to import
        if selected_page_ids:
            pages_to_import = []
            for page_id in selected_page_ids:
                page = self.tree.get_page_by_id(page_id)
                if page and page.markdown_content:
                    pages_to_import.append(page)
        else:
            pages_to_import = [p for p in self.tree.get_all_pages() if p.markdown_content]
        
        self.stats['total_pages'] = len(pages_to_import)
        
        if not pages_to_import:
            self.logger.warning("No pages to import")
            return self.stats.copy()
        
        # Import pages
        iterable = pages_to_import
        if self._should_show_progress():
            iterable = tqdm(pages_to_import, desc="Importing to Wiki.js")
        
        for page in iterable:
            try:
                success = self._import_single_page(page, dry_run)
                if success:
                    if dry_run:
                        self.logger.info(f"[DRY RUN] Would import: {page.title}")
                else:
                    self.stats['failed'] += 1
            except Exception as e:
                self.logger.error(f"Error importing page '{page.title}': {e}", exc_info=True)
                self.stats['failed'] += 1
                self.stats['errors'].append({
                    'page_id': page.id,
                    'page_title': page.title,
                    'error': str(e)
                })
        
        # Log summary
        self._log_import_summary(dry_run)
        
        # Check if rollback is needed
        rollback_on_failure = self.config.get('migration', {}).get('rollback_on_failure', True)
        if self.stats['failed'] > 0 and not dry_run and rollback_on_failure:
            self.logger.warning(f"Import failed with {self.stats['failed']} errors. Executing rollback...")
            rollback_stats = self.rollback()
            self.stats['rollback_executed'] = rollback_stats['rollback_executed']
            self.stats['rollback_deleted'] = rollback_stats['pages_deleted'] + rollback_stats['attachments_deleted']
        else:
            self.stats['rollback_executed'] = False
            self.stats['rollback_deleted'] = 0
        
        return self.stats.copy()
    
    def _import_single_page(
        self,
        page: ConfluencePage,
        dry_run: bool = False
    ) -> bool:
        """
        Import a single page to Wiki.js.
        
        Args:
            page: ConfluencePage to import
            dry_run: If True, only simulate the import
            
        Returns:
            True on success, False on failure
        """
        # Get space for this page
        space = self.tree.get_space(page.space_key)
        if not space:
            self.logger.error(f"Space not found for page: {page.space_key}")
            return False
        
        # Generate Wiki.js path
        wikijs_path = self.mapper.generate_path(page, space, self.tree, include_space=self.include_space)
        self.logger.debug(f"Generated path for '{page.title}': {wikijs_path}")
        
        # Check for existing page (always check, even in dry-run, to accurately preview conflicts)
        existing_page = None
        try:
            existing_page = self.client.get_page_by_path(wikijs_path)
            if dry_run and existing_page:
                self.logger.debug(f"[DRY RUN] Found existing page at: {wikijs_path}")
        except Exception as e:
            self.logger.warning(f"Error checking for existing page: {e}")
            if dry_run:
                # In dry-run, treat errors as "no existing page" for conservative simulation
                self.logger.debug(f"[DRY RUN] Could not check existence, assuming new page: {e}")
                existing_page = None
        
        # Handle conflict based on strategy
        if existing_page:
            action = self._handle_conflict(existing_page, page, wikijs_path)
            
            if action == 'skip':
                self.logger.info(f"Skipping existing page: {wikijs_path}")
                self.stats['skipped'] += 1
                self._update_page_metadata(page, 'skipped', wikijs_path, existing_page.get('id'))
                return True
            
            elif action == 'overwrite':
                # Update existing page
                if not dry_run:
                    return self._update_page(existing_page['id'], page, wikijs_path)
                else:
                    self.logger.info(f"[DRY RUN] Would update: {wikijs_path}")
                    self.stats['updated'] += 1
                    return True
            
            elif action == 'version':
                # Generate unique path and create new page
                unique_path = self.mapper.generate_unique_path(wikijs_path, self.client)
                if not dry_run:
                    return self._create_page(page, unique_path)
                else:
                    self.logger.info(f"[DRY RUN] Would create at unique path: {unique_path}")
                    self.stats['created'] += 1
                    return True
        else:
            # No conflict - create new page
            if not dry_run:
                return self._create_page(page, wikijs_path)
            else:
                self.logger.info(f"[DRY RUN] Would create: {wikijs_path}")
                self.stats['created'] += 1
                return True
    
    def _create_page(self, page: ConfluencePage, path: str) -> bool:
        """Create a new page in Wiki.js."""
        try:
            # Handle attachments
            markdown_content = page.markdown_content or ""
            
            if page.attachments and self.asset_uploader.enabled:
                self.logger.debug(f"Uploading {len(page.attachments)} attachments for '{page.title}'")
                
                # Upload attachments
                attachment_map = self.asset_uploader.upload_attachments_batch(page.attachments)
                
                # Update stats
                self.stats['attachments_uploaded'] += len(attachment_map)
                
                # Rewrite markdown content to use asset URLs
                markdown_content = self.asset_uploader.rewrite_attachment_links(
                    markdown_content,
                    attachment_map
                )
            
            # Extract tags from Confluence labels
            tags = self._extract_tags(page) if self.preserve_labels else []
            
            # Prepare metadata
            metadata = self._prepare_page_metadata(page)
            
            # Create page via API
            created_page = self.client.create_page(
                path=path,
                title=page.title,
                content=markdown_content,
                description=metadata.get('description', ''),
                editor=self.client.default_editor,
                is_published=True,
                tags=tags
            )
            
            if created_page:
                self.stats['created'] += 1
                self._update_page_metadata(
                    page,
                    'imported',
                    path,
                    created_page['id']
                )
                # Track for rollback
                self.created_resources['pages'].append({
                    'id': created_page['id'],
                    'path': path
                })
                self.logger.info(f"Created page: {path}")
                return True
            else:
                self.logger.error(f"Failed to create page: {path}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error creating page '{page.title}': {e}", exc_info=True)
            return False
    
    def _update_page(self, page_id: int, page: ConfluencePage, path: str) -> bool:
        """Update an existing page in Wiki.js."""
        try:
            # Handle attachments
            markdown_content = page.markdown_content or ""
            
            if page.attachments and self.asset_uploader.enabled:
                self.logger.debug(f"Uploading {len(page.attachments)} attachments for '{page.title}'")
                
                # Upload attachments
                attachment_map = self.asset_uploader.upload_attachments_batch(page.attachments)
                
                # Update stats
                self.stats['attachments_uploaded'] += len(attachment_map)
                
                # Rewrite markdown content to use asset URLs
                markdown_content = self.asset_uploader.rewrite_attachment_links(
                    markdown_content,
                    attachment_map
                )
            
            # Extract tags from Confluence labels
            tags = self._extract_tags(page) if self.preserve_labels else []
            
            # Prepare metadata
            metadata = self._prepare_page_metadata(page)
            
            # Update page via API
            updated_page = self.client.update_page(
                page_id=page_id,
                content=markdown_content,
                title=page.title,
                description=metadata.get('description', ''),
                tags=tags
            )
            
            if updated_page:
                self.stats['updated'] += 1
                self._update_page_metadata(page, 'updated', path, page_id)
                self.logger.info(f"Updated page: {path}")
                return True
            else:
                self.logger.error(f"Failed to update page: {path}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error updating page '{page.title}': {e}", exc_info=True)
            return False
    
    def _handle_conflict(self, existing_page: Dict[str, Any], page: ConfluencePage, path: str) -> str:
        """
        Handle page conflicts based on configured strategy.
        
        Args:
            existing_page: Existing Wiki.js page
            page: Confluence page being imported
            path: Generated Wiki.js path
            
        Returns:
            Action to take: 'skip', 'overwrite', or 'version'
        """
        strategy = self.conflict_resolution
        
        self.logger.info(
            f"Conflict detected for '{page.title}' at path: {path}. "
            f"Resolution strategy: {strategy}"
        )
        
        if strategy == 'skip':
            return 'skip'
        
        elif strategy == 'overwrite':
            # Check if content is actually different
            existing_content = existing_page.get('content', '')
            new_content = page.markdown_content or ''
            
            if existing_content.strip() == new_content.strip():
                self.logger.debug(f"Content unchanged, skipping: {path}")
                return 'skip'
            
            return 'overwrite'
        
        elif strategy == 'version':
            return 'version'
        
        else:
            self.logger.warning(f"Unknown conflict strategy '{strategy}', defaulting to 'skip'")
            return 'skip'
    
    def _extract_tags(self, page: ConfluencePage) -> List[str]:
        """
        Extract tags from Confluence page labels.
        
        Args:
            page: ConfluencePage to extract tags from
            
        Returns:
            List of tag strings
        """
        tags = []
        
        # Add Confluence labels
        labels = page.metadata.get('labels', [])
        if labels:
            tags.extend(labels)
        
        # Add Confluence page ID as tag if preserve_page_ids is enabled
        if self.config.get('migration', {}).get('preserve_page_ids', False):
            tags.append(f"confluence-id-{page.id}")
        
        # Filter out system/internal labels
        filtered_tags = []
        for tag in tags:
            if not tag.startswith('confluence:'):  # Skip system labels
                filtered_tags.append(tag)
        
        return filtered_tags
    
    def _prepare_page_metadata(self, page: ConfluencePage) -> Dict[str, Any]:
        """
        Prepare metadata for Wiki.js page creation.
        
        Args:
            page: ConfluencePage to extract metadata from
            
        Returns:
            Dictionary with metadata fields
        """
        metadata = {}
        
        # Description (could be excerpt or first paragraph)
        metadata['description'] = page.metadata.get('description', '')
        
        # Author info
        author = page.metadata.get('author')
        if author:
            metadata['author'] = author
        
        # Last modified
        last_modified = page.metadata.get('last_modified')
        if last_modified:
            metadata['last_modified'] = last_modified
        
        return metadata
    
    def _update_page_metadata(self, page: ConfluencePage, status: str, path: str, wikijs_page_id: Optional[int] = None):
        """
        Update page metadata with import results.
        
        Args:
            page: ConfluencePage to update
            status: Import status ('imported', 'updated', 'skipped', 'failed')
            path: Wiki.js path
            wikijs_page_id: Wiki.js page ID if available
        """
        # Use flat structure - no nested 'conversion_metadata' key
        page.conversion_metadata['wikijs_import'] = {
            'status': status,
            'path': path,
            'wikijs_page_id': wikijs_page_id,
            'import_timestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    def _reset_stats(self) -> None:
        """Reset statistics for a new import run."""
        self.stats = {
            'total_pages': 0,
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'failed': 0,
            'attachments_uploaded': 0,
            'errors': []
        }
    
    def _log_import_summary(self, dry_run: bool):
        """Log import statistics summary."""
        mode = "DRY RUN" if dry_run else "IMPORT"
        
        self.logger.info("=" * 60)
        self.logger.info(f"WIKI.JS {mode} SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"Total pages processed: {self.stats['total_pages']}")
        self.logger.info(f"Pages created: {self.stats['created']}")
        self.logger.info(f"Pages updated: {self.stats['updated']}")
        self.logger.info(f"Pages skipped: {self.stats['skipped']}")
        self.logger.info(f"Pages failed: {self.stats['failed']}")
        self.logger.info(f"Attachments uploaded: {self.stats['attachments_uploaded']}")
        
        if self.stats['errors']:
            self.logger.info(f"Errors encountered: {len(self.stats['errors'])}")
            for error in self.stats['errors'][:5]:  # Show first 5 errors
                self.logger.error(f"  - {error['page_title']}: {error['error']}")
        
        self.logger.info("=" * 60)
    
    def _should_show_progress(self) -> bool:
        """Check if progress bars should be displayed."""
        return tqdm is not None and self.config.get('export', {}).get('progress_bars', True)

    def rollback(self) -> Dict[str, Any]:
        """
        Rollback the import by deleting created pages and attachments.

        Returns:
            Dictionary with rollback statistics
        """
        rollback_stats = {
            'rollback_executed': True,
            'pages_deleted': 0,
            'attachments_deleted': 0,
            'errors': []
        }

        # Delete created pages
        for page_info in self.created_resources['pages']:
            try:
                page_id = page_info['id'] if isinstance(page_info, dict) else page_info
                self.client.delete_page(page_id)
                rollback_stats['pages_deleted'] += 1
                self.logger.debug(f"Deleted page: {page_id}")
            except Exception as e:
                self.logger.error(f"Failed to delete page {page_id}: {e}")
                rollback_stats['errors'].append({
                    'type': 'page',
                    'id': page_id,
                    'error': str(e)
                })

        # Delete created attachments
        for att_id in self.created_resources['attachments']:
            try:
                self.client.delete_attachment(att_id)
                rollback_stats['attachments_deleted'] += 1
                self.logger.debug(f"Deleted attachment: {att_id}")
            except Exception as e:
                self.logger.error(f"Failed to delete attachment {att_id}: {e}")
                rollback_stats['errors'].append({
                    'type': 'attachment',
                    'id': att_id,
                    'error': str(e)
                })

        self.logger.info(
            f"Rollback completed: {rollback_stats['pages_deleted']} pages deleted, "
            f"{rollback_stats['attachments_deleted']} attachments deleted"
        )

        # Reset tracking
        self.created_resources = {'pages': [], 'attachments': []}

        return rollback_stats


# Export importer for easy access
__all__ = ['WikiJsImporter']