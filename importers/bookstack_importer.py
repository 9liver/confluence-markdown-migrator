"""
BookStack importer for Confluence markdown migrator.

This module provides the main importer orchestrator for migrating
Confluence content to BookStack, preserving hierarchical structure
and managing the entire import process.
"""

import logging
import time
from typing import Dict, Any, Optional, Set, List
from pathlib import Path

try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

from .bookstack_client import BookStackClient
from .bookstack_hierarchy_mapper import BookStackHierarchyMapper
from .content_transformer import ContentTransformer
from .image_uploader import ImageUploader
from .id_mapping_tracker import IdMappingTracker
from .ordering_manager import OrderingManager
from ..models import ConfluencePage, ConfluenceSpace, DocumentationTree

logger = logging.getLogger(__name__)


class BookStackImporter:
    """Main orchestrator for importing Confluence content to BookStack."""
    
    def __init__(
        self,
        config: Dict[str, Any],
        tree: DocumentationTree,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize BookStack importer.
        
        Args:
            config: Configuration dictionary
            tree: DocumentationTree with Confluence content
            logger: Optional logger instance
        """
        self.config = config
        self.tree = tree
        self.logger = logger or logging.getLogger(__name__)
        
        # Initialize BookStack components
        self.client = BookStackClient.from_config(config)
        self.hierarchy_mapper = BookStackHierarchyMapper()
        self.content_transformer = ContentTransformer(self.logger)
        self.image_uploader = ImageUploader(config, self.client, self.logger)
        self.id_mapper = IdMappingTracker(self.logger)
        self.ordering_manager = OrderingManager(self.client, self.logger)
        
        # Initialize statistics
        self.stats = self._reset_stats()
        
        self.logger.info("Initialized BookStack importer")
        
        # Track created resources for rollback
        self.created_resources = {
            'shelves': [],
            'books': [],
            'chapters': [],
            'pages': [],
            'images': []
        }
    
    def _reset_stats(self) -> Dict[str, Any]:
        """Reset statistics for a new import run."""
        return {
            'total_pages': 0,
            'shelves': 0,
            'books': 0,
            'chapters': 0,
            'pages': 0,
            'skipped': 0,
            'failed': 0,
            'images_uploaded': 0,
            'errors': []
        }
    
    def import_pages(
        self,
        selected_page_ids: Optional[Set[str]] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Import Confluence pages to BookStack.
        
        Args:
            selected_page_ids: Optional set of Confluence page IDs to import
            dry_run: If True, simulate import without making API calls
            
        Returns:
            Statistics dictionary with import results
        """
        self.logger.info(f"Starting BookStack import (dry_run={dry_run})")
        
        # Reset stats
        self.stats = self._reset_stats()
        
        # Determine spaces to process
        spaces_to_import = []
        
        if selected_page_ids:
            # Filter to only include spaces containing selected pages
            selected_spaces = set()
            for space in self.tree.spaces.values():
                if self._space_contains_selected_pages(space, selected_page_ids):
                    selected_spaces.add(space.key)
            
            spaces_to_import = [s for s in self.tree.spaces.values() if s.key in selected_spaces]
            self.logger.info(f"Selected {len(spaces_to_import)} spaces containing target pages")
        else:
            # Import all spaces
            spaces_to_import = list(self.tree.spaces.values())
            self.logger.info(f"Importing all {len(spaces_to_import)} spaces")
        
        # Import each space
        for space in (tqdm(spaces_to_import, desc="Importing Spaces") if self._should_show_progress() else spaces_to_import):
            try:
                space_stats = self._import_space(space, selected_page_ids, dry_run)
                
                # Aggregate stats
                self.stats['shelves'] += space_stats.get('shelves', 0)
                self.stats['books'] += space_stats.get('books', 0)
                self.stats['chapters'] += space_stats.get('chapters', 0)
                self.stats['pages'] += space_stats.get('pages', 0)
                self.stats['skipped'] += space_stats.get('skipped', 0)
                self.stats['failed'] += space_stats.get('failed', 0)
                self.stats['images_uploaded'] += space_stats.get('images_uploaded', 0)
                self.stats['total_pages'] += space_stats.get('total_pages', 0)
                
                if space_stats.get('errors'):
                    self.stats['errors'].extend(space_stats['errors'])
                
            except Exception as e:
                error_msg = f"Failed to import space '{space.name}': {str(e)}"
                self.logger.error(error_msg)
                self.stats['errors'].append({
                    'type': 'space',
                    'space_key': space.key,
                    'space_name': space.name,
                    'error': str(e)
                })
        
        # Check if rollback is needed
        rollback_on_failure = self.config.get('migration', {}).get('rollback_on_failure', True)
        if self.stats['failed'] > 0 and not dry_run and rollback_on_failure:
            self.logger.warning(f"Import failed with {self.stats['failed']} errors. Executing rollback...")
            rollback_stats = self.rollback()
            self.stats['rollback_executed'] = rollback_stats['rollback_executed']
            self.stats['rollback_summary'] = rollback_stats
        else:
            self.stats['rollback_executed'] = False
            self.stats['rollback_summary'] = {}
        
        # Log summary
        self._log_import_summary(dry_run)
        
        return self.stats.copy()
    
    def _space_contains_selected_pages(
        self,
        space: ConfluenceSpace,
        selected_page_ids: Set[str]
    ) -> bool:
        """Check if space contains any selected pages."""
        if not selected_page_ids:
            return True
        
        def check_page_and_children(page: ConfluencePage) -> bool:
            if page.id in selected_page_ids:
                return True
            for child in page.children:
                if check_page_and_children(child):
                    return True
            return False
        
        return any(check_page_and_children(page) for page in space.pages)
    
    def _import_space(
        self,
        space: ConfluenceSpace,
        selected_page_ids: Optional[Set[str]] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Import a single Confluence space as a BookStack shelf."""
        self.logger.info(f"Importing space: {space.name} ({space.key})")
        
        stats = {
            'shelves': 0,
            'books': 0,
            'chapters': 0,
            'pages': 0,
            'skipped': 0,
            'failed': 0,
            'images_uploaded': 0,
            'errors': []
        }
        
        # Sanitize space name for shelf
        safe_space_name = self.content_transformer.transform_title(space.name)
        
        # Create shelf for the space
        if dry_run:
            self.logger.info(f"[DRY RUN] Would create shelf: {space.name}")
            shelf = {'id': 0, 'name': space.name}
        else:
            try:
                shelf = self.client.create_shelf(
                    name=safe_space_name,
                    description=space.description or ''
                )
                self.logger.info(f"Created shelf: {shelf['name']} (ID: {shelf['id']})")
            except Exception as e:
                error_msg = f"Failed to create shelf for space '{space.name}': {str(e)}"
                self.logger.error(error_msg)
                stats['errors'].append({
                    'type': 'shelf',
                    'space_key': space.key,
                    'error': str(e)
                })
                return stats
        
        stats['shelves'] = 1
        
        # Track for rollback if not dry run
        if not dry_run:
            self.created_resources['shelves'].append({
                'id': shelf['id'],
                'type': 'shelf',
                'name': shelf['name']
            })
        
        self.id_mapper.add_space_mapping(space.key, shelf['id'])
        
        # Identify top-level pages (will become Books)
        top_level_pages = self.hierarchy_mapper.identify_top_level_pages(space.pages)
        
        # Import each top-level page as a Book
        book_ids = []
        for priority, page in enumerate(top_level_pages):
            try:
                if selected_page_ids and not self._should_process_page(page, selected_page_ids):
                    self.logger.debug(f"Skipping page (not selected): {page.title}")
                    stats['skipped'] += 1
                    continue
                
                book_stats = self._import_as_book(
                    page=page,
                    shelf_id=shelf['id'],
                    priority=priority,
                    selected_page_ids=selected_page_ids,
                    dry_run=dry_run
                )
                
                # Aggregate stats
                stats['books'] += book_stats.get('books', 0)
                stats['chapters'] += book_stats.get('chapters', 0)
                stats['pages'] += book_stats.get('pages', 0)
                stats['skipped'] += book_stats.get('skipped', 0)
                stats['failed'] += book_stats.get('failed', 0)
                stats['images_uploaded'] += book_stats.get('images_uploaded', 0)
                stats['total_pages'] += book_stats.get('total_pages', 0)
                
                if book_stats.get('book_id'):
                    book_ids.append(book_stats['book_id'])
                
                if book_stats.get('errors'):
                    stats['errors'].extend(book_stats['errors'])
                
            except Exception as e:
                error_msg = f"Failed to import book from page '{page.title}': {str(e)}"
                self.logger.error(error_msg)
                stats['errors'].append({
                    'type': 'book',
                    'page_id': page.id,
                    'page_title': page.title,
                    'error': str(e)
                })
                stats['failed'] += 1
        
        # Update shelf with ordered book list
        if not dry_run and book_ids:
            try:
                self.client.update_shelf(shelf['id'], books=book_ids)
                self.logger.debug(f"Updated shelf with {len(book_ids)} books")
            except Exception as e:
                self.logger.warning(f"Failed to update shelf with book list: {str(e)}")
        
        return stats
    
    def _should_process_page(
        self,
        page: ConfluencePage,
        selected_page_ids: Set[str]
    ) -> bool:
        """Check if page or any descendant is in selected pages."""
        if page.id in selected_page_ids:
            return True
        
        for child in page.children:
            if self._should_process_page(child, selected_page_ids):
                return True
        
        return False
    
    def _import_as_book(
        self,
        page: ConfluencePage,
        shelf_id: int,
        priority: int,
        selected_page_ids: Optional[Set[str]] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Import a Confluence page as a BookStack Book."""
        self.logger.info(f"Importing page as Book: {page.title}")
        
        stats = {
            'books': 0,
            'chapters': 0,
            'pages': 0,
            'skipped': 0,
            'failed': 0,
            'images_uploaded': 0,
            'errors': []
        }
        
        # Convert markdown to HTML
        html_content = self.content_transformer.transform_markdown_to_html(
            page.markdown_content
        )
        
        # Calculate description
        description = self.hierarchy_mapper.calculate_description(page)
        
        # Sanitize title
        safe_title = self.content_transformer.transform_title(page.title)
        
        # Create book
        if dry_run:
            self.logger.info(f"[DRY RUN] Would create book: {page.title}")
            book = {'id': 0, 'name': page.title, 'slug': ''}
        else:
            try:
                book = self.client.create_book(
                    name=safe_title,
                    description=description
                )
                self.logger.info(f"Created book: {book['name']} (ID: {book['id']})")
            except Exception as e:
                error_msg = f"Failed to create book '{page.title}': {str(e)}"
                self.logger.error(error_msg)
                stats['errors'].append({
                    'type': 'book',
                    'page_id': page.id,
                    'page_title': page.title,
                    'error': str(e)
                })
                stats['failed'] = 1
                return stats
        
        stats['books'] = 1
        stats['total_pages'] += 1
        stats['book_id'] = book['id']
        
        # Track for rollback if not dry run
        if not dry_run:
            self.created_resources['books'].append({
                'id': book['id'],
                'type': 'book',
                'name': book['name']
            })
        
        # Store mapping
        if not dry_run:
            self.id_mapper.add_page_mapping(
                confluence_id=page.id,
                bookstack_id=book['id'],
                bookstack_type='book',
                bookstack_slug=book.get('slug', '')
            )
            
            # Update page metadata
            page.metadata['bookstack_id'] = book['id']
            page.metadata['bookstack_type'] = 'book'
        
        # Add book to shelf
        if not dry_run:
            try:
                self.client.add_book_to_shelf(book['id'], shelf_id)
                self.logger.debug(f"Added book to shelf {shelf_id}")
            except Exception as e:
                self.logger.warning(f"Failed to add book to shelf: {str(e)}")
        
        # Process children
        if page.children:
            # Categorize children
            categorized = self.hierarchy_mapper.categorize_children(page.children)
            
            chapters = categorized['chapters']
            direct_pages = categorized['pages']
            
            # Import chapters
            for chapter_priority, chapter_page in enumerate(chapters):
                try:
                    chapter_stats = self._import_as_chapter(
                        page=chapter_page,
                        book_id=book['id'],
                        priority=chapter_priority,
                        selected_page_ids=selected_page_ids,
                        dry_run=dry_run
                    )
                    
                    # Aggregate stats
                    stats['chapters'] += chapter_stats.get('chapters', 0)
                    stats['pages'] += chapter_stats.get('pages', 0)
                    stats['skipped'] += chapter_stats.get('skipped', 0)
                    stats['failed'] += chapter_stats.get('failed', 0)
                    stats['images_uploaded'] += chapter_stats.get('images_uploaded', 0)
                    stats['total_pages'] += chapter_stats.get('total_pages', 0)
                    
                    if chapter_stats.get('errors'):
                        stats['errors'].extend(chapter_stats['errors'])
                    
                except Exception as e:
                    error_msg = f"Failed to import chapter '{chapter_page.title}': {str(e)}"
                    self.logger.error(error_msg)
                    stats['errors'].append({
                        'type': 'chapter',
                        'page_id': chapter_page.id,
                        'page_title': chapter_page.title,
                        'error': str(e)
                    })
                    stats['failed'] += 1
            
            # Import direct pages (not in chapters)
            for page_priority, child_page in enumerate(direct_pages):
                try:
                    page_stats = self._import_as_page(
                        page=child_page,
                        book_id=book['id'],
                        chapter_id=None,
                        priority=page_priority,
                        selected_page_ids=selected_page_ids,
                        dry_run=dry_run
                    )
                    
                    # Aggregate stats
                    stats['pages'] += page_stats.get('pages', 0)
                    stats['skipped'] += page_stats.get('skipped', 0)
                    stats['failed'] += page_stats.get('failed', 0)
                    stats['images_uploaded'] += page_stats.get('images_uploaded', 0)
                    stats['total_pages'] += page_stats.get('total_pages', 0)
                    
                    if page_stats.get('errors'):
                        stats['errors'].extend(page_stats['errors'])
                    
                except Exception as e:
                    error_msg = f"Failed to import page '{child_page.title}': {str(e)}"
                    self.logger.error(error_msg)
                    stats['errors'].append({
                        'type': 'page',
                        'page_id': child_page.id,
                        'page_title': child_page.title,
                        'error': str(e)
                    })
                    stats['failed'] += 1
            
            # Apply ordering for book content
            if not dry_run:
                self.ordering_manager.set_book_content_order(book['id'], page.children)
        
        return stats
    
    def _import_as_chapter(
        self,
        page: ConfluencePage,
        book_id: int,
        priority: int,
        selected_page_ids: Optional[Set[str]] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Import a Confluence page as a BookStack Chapter."""
        self.logger.info(f"Importing page as Chapter: {page.title}")
        
        stats = {
            'chapters': 0,
            'pages': 0,
            'skipped': 0,
            'failed': 0,
            'images_uploaded': 0,
            'errors': []
        }
        
        # Check if this page should be processed
        if selected_page_ids and page.id not in selected_page_ids:
            # Check if any child is selected
            has_selected_child = any(
                self._should_process_page(child, selected_page_ids)
                for child in page.children
            )
            if not has_selected_child:
                self.logger.debug(f"Skipping chapter (no selected children): {page.title}")
                stats['skipped'] = 1
                return stats
        
        # Calculate description
        description = self.hierarchy_mapper.calculate_description(page)
        
        # Sanitize title
        safe_title = self.content_transformer.transform_title(page.title)
        
        # Create chapter
        if dry_run:
            self.logger.info(f"[DRY RUN] Would create chapter: {page.title}")
            chapter = {'id': 0, 'name': page.title}
        else:
            try:
                chapter = self.client.create_chapter(
                    book_id=book_id,
                    name=safe_title,
                    description=description,
                    priority=priority
                )
                self.logger.info(f"Created chapter: {chapter['name']} (ID: {chapter['id']})")
            except Exception as e:
                error_msg = f"Failed to create chapter '{page.title}': {str(e)}"
                self.logger.error(error_msg)
                stats['errors'].append({
                    'type': 'chapter',
                    'page_id': page.id,
                    'page_title': page.title,
                    'error': str(e)
                })
                stats['failed'] = 1
                return stats
        
        stats['chapters'] = 1
        stats['total_pages'] += 1
        
        # Store mapping
        if not dry_run:
            self.id_mapper.add_page_mapping(
                confluence_id=page.id,
                bookstack_id=chapter['id'],
                bookstack_type='chapter'
            )
            
            # Update page metadata
            page.metadata['bookstack_id'] = chapter['id']
            page.metadata['bookstack_type'] = 'chapter'
        
        # Process children as pages
        for child_priority, child_page in enumerate(page.children):
            try:
                page_stats = self._import_as_page(
                    page=child_page,
                    book_id=book_id,
                    chapter_id=chapter['id'],
                    priority=child_priority,
                    selected_page_ids=selected_page_ids,
                    dry_run=dry_run
                )
                
                # Aggregate stats
                stats['pages'] += page_stats.get('pages', 0)
                stats['skipped'] += page_stats.get('skipped', 0)
                stats['failed'] += page_stats.get('failed', 0)
                stats['images_uploaded'] += page_stats.get('images_uploaded', 0)
                stats['total_pages'] += page_stats.get('total_pages', 0)
                
                if page_stats.get('errors'):
                    stats['errors'].extend(page_stats['errors'])
                
            except Exception as e:
                error_msg = f"Failed to import page '{child_page.title}': {str(e)}"
                self.logger.error(error_msg)
                stats['errors'].append({
                    'type': 'page',
                    'page_id': child_page.id,
                    'page_title': child_page.title,
                    'error': str(e)
                })
                stats['failed'] += 1
        
        # Apply ordering for chapter pages
        if not dry_run and page.children:
            self.ordering_manager.set_chapter_page_order(chapter['id'], page.children)
        
        return stats
    
    def _import_as_page(
        self,
        page: ConfluencePage,
        book_id: int,
        chapter_id: Optional[int],
        priority: int,
        selected_page_ids: Optional[Set[str]] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Import a Confluence page as a BookStack Page."""
        # Check if this page should be processed
        if selected_page_ids and page.id not in selected_page_ids:
            # If this page has nested children, they need to be flattened
            if page.children:
                self.logger.warning(
                    f"Page '{page.title}' has nested children beyond BookStack's "
                    f"3-level hierarchy. Flattening {len(page.children)} children "
                    f"as sibling pages."
                )
                return self._import_flattened_pages(
                    page, book_id, chapter_id, priority,
                    selected_page_ids, dry_run
                )
            else:
                self.logger.debug(f"Skipping page (not selected): {page.title}")
                return {
                    'pages': 0,
                    'total_pages': 0,
                    'skipped': 1,
                    'failed': 0,
                    'images_uploaded': 0,
                    'errors': []
                }
        
        self.logger.info(f"Importing page: {page.title}")
        
        stats = {
            'pages': 0,
            'total_pages': 0,
            'skipped': 0,
            'failed': 0,
            'images_uploaded': 0,
            'errors': []
        }
        
        # Convert markdown to HTML
        html_content = self.content_transformer.transform_markdown_to_html(
            page.markdown_content
        )

        # Sanitize title
        safe_title = self.content_transformer.transform_title(page.title)
        
        # Create page
        if dry_run:
            self.logger.info(f"[DRY RUN] Would create page: {page.title}")
            bookstack_page = {'id': 0, 'name': page.title}
        else:
            try:
                bookstack_page = self.client.create_page(
                    book_id=book_id,
                    name=safe_title,
                    html=html_content,
                    chapter_id=chapter_id,
                    priority=priority
                )
                self.logger.info(f"Created page: {bookstack_page['name']} (ID: {bookstack_page['id']})")
            except Exception as e:
                error_msg = f"Failed to create page '{page.title}': {str(e)}"
                self.logger.error(error_msg)
                stats['errors'].append({
                    'type': 'page',
                    'page_id': page.id,
                    'page_title': page.title,
                    'error': str(e)
                })
                stats['failed'] = 1
                return stats
        
        stats['pages'] = 1
        stats['total_pages'] += 1
        page_id = bookstack_page['id']
        
        # Track for rollback if not dry run
        if not dry_run:
            self.created_resources['pages'].append({
                'id': bookstack_page['id'],
                'type': 'page',
                'name': bookstack_page['name']
            })
        
        # Store mapping
        if not dry_run:
            self.id_mapper.add_page_mapping(
                confluence_id=page.id,
                bookstack_id=page_id,
                bookstack_type='page'
            )
            
            # Update page metadata
            page.metadata['bookstack_id'] = page_id
            page.metadata['bookstack_type'] = 'page'
        
        # Upload images
        if not dry_run and hasattr(page, 'attachments') and page.attachments:
            try:
                image_map = self.image_uploader.upload_images_for_page(page, page_id)
                
                if image_map:
                    # Rewrite image references in HTML
                    updated_html = self.image_uploader.rewrite_image_references(
                        html_content,
                        image_map
                    )
                    
                    # Update page with rewritten HTML
                    if updated_html != html_content:
                        self.client.update_page(page_id, html=updated_html)
                        self.logger.debug(f"Updated page with rewritten image references")
                    
                    stats['images_uploaded'] = len(image_map)
                
            except Exception as e:
                self.logger.warning(f"Failed to upload images for page '{page.title}': {str(e)}")
        
        # Handle nested pages (flatten due to BookStack limitation)
        if page.children and not dry_run:
            self.logger.warning(
                f"Page '{page.title}' has nested children beyond BookStack's "
                f"3-level hierarchy. Flattening {len(page.children)} children "
                f"as sibling pages."
            )
            
            # Import children as sibling pages
            for child_priority, child_page in enumerate(page.children):
                child_stats = self._import_as_page(
                    page=child_page,
                    book_id=book_id,
                    chapter_id=chapter_id,
                    priority=priority + 1 + child_priority,  # Siblings after parent
                    selected_page_ids=selected_page_ids,
                    dry_run=dry_run
                )
                
                stats['pages'] += child_stats.get('pages', 0)
                stats['total_pages'] += child_stats.get('total_pages', 0)
                stats['skipped'] += child_stats.get('skipped', 0)
                stats['failed'] += child_stats.get('failed', 0)
                stats['images_uploaded'] += child_stats.get('images_uploaded', 0)
                
                if child_stats.get('errors'):
                    stats['errors'].extend(child_stats['errors'])
        
        return stats
    
    def _import_flattened_pages(
        self,
        page: ConfluencePage,
        book_id: int,
        chapter_id: Optional[int],
        priority: int,
        selected_page_ids: Optional[Set[str]] = None,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """Import nested pages as flattened siblings."""
        stats = {
            'pages': 0,
            'total_pages': 0,
            'skipped': 0,
            'failed': 0,
            'images_uploaded': 0,
            'errors': []
        }
        
        # Import parent page if selected
        if selected_page_ids and page.id in selected_page_ids:
            self.logger.info(f"Importing selected page: {page.title}")
            parent_stats = self._import_as_page(
                page, book_id, chapter_id, priority,
                selected_page_ids, dry_run
            )
            
            stats['pages'] += parent_stats.get('pages', 0)
            stats['total_pages'] += parent_stats.get('total_pages', 0)
            stats['skipped'] += parent_stats.get('skipped', 0)
            stats['failed'] += parent_stats.get('failed', 0)
            stats['images_uploaded'] += parent_stats.get('images_uploaded', 0)
            
            if parent_stats.get('errors'):
                stats['errors'].extend(parent_stats['errors'])
        else:
            stats['skipped'] = 1
        
        # Import children as sibling pages
        for child_priority, child_page in enumerate(page.children):
            child_stats = self._import_as_page(
                page=child_page,
                book_id=book_id,
                chapter_id=chapter_id,
                priority=priority + child_priority + 1,
                selected_page_ids=selected_page_ids,
                dry_run=dry_run
            )
            
            stats['pages'] += child_stats.get('pages', 0)
            stats['total_pages'] += child_stats.get('total_pages', 0)
            stats['skipped'] += child_stats.get('skipped', 0)
            stats['failed'] += child_stats.get('failed', 0)
            stats['images_uploaded'] += child_stats.get('images_uploaded', 0)
            
            if child_stats.get('errors'):
                stats['errors'].extend(child_stats['errors'])
        
        return stats
    
    def _log_import_summary(self, dry_run: bool) -> None:
        """Log import summary statistics."""
        self.logger.info("=" * 60)
        self.logger.info(f"BOOKSTACK IMPORT SUMMARY (Dry Run: {dry_run})")
        self.logger.info("=" * 60)
        self.logger.info(f"Total Confluence pages: {self.stats['total_pages']}")
        self.logger.info(f"Shelves created: {self.stats['shelves']}")
        self.logger.info(f"Books created: {self.stats['books']}")
        self.logger.info(f"Chapters created: {self.stats['chapters']}")
        self.logger.info(f"Pages created: {self.stats['pages']}")
        self.logger.info(f"Images uploaded: {self.stats['images_uploaded']}")
        self.logger.info(f"Skipped: {self.stats['skipped']}")
        self.logger.info(f"Failed: {self.stats['failed']}")
        
        if self.stats['errors']:
            self.logger.warning(f"Errors encountered: {len(self.stats['errors'])}")
            for error in self.stats['errors'][:5]:  # Show first 5 errors
                self.logger.warning(f"  - {error}")
            if len(self.stats['errors']) > 5:
                self.logger.warning(f"  ... and {len(self.stats['errors']) - 5} more errors")
        
        self.logger.info("=" * 60)
    
    def rollback(self) -> Dict[str, Any]:
        """
        Rollback created BookStack resources (pages, chapters, books, shelves) on import failure.
        
        Returns:
            Statistics about deleted resources
        """
        rollback_stats = {
            'pages_deleted': 0,
            'chapters_deleted': 0,
            'books_deleted': 0,
            'shelves_deleted': 0,
            'errors': [],
            'rollback_executed': False
        }
        
        if not any(self.created_resources.values()):
            self.logger.info("No BookStack resources to rollback")
            return rollback_stats
        
        self.logger.warning(f"Rolling back BookStack resources: {len(self.created_resources['pages'])} pages, "
                           f"{len(self.created_resources['chapters'])} chapters, "
                           f"{len(self.created_resources['books'])} books, "
                           f"{len(self.created_resources['shelves'])} shelves")
        
        # Rollback in reverse order: pages → chapters → books → shelves
        
        # Delete pages
        for page in reversed(self.created_resources['pages']):
            try:
                self.client.delete_page(page['id'])
                self.logger.info(f"Rolled back page: {page['name']}")
                rollback_stats['pages_deleted'] += 1
            except Exception as e:
                self.logger.warning(f"Failed to rollback page {page['name']}: {str(e)}")
                rollback_stats['errors'].append({'type': 'page', 'resource': page, 'error': str(e)})
        
        # Delete chapters
        for chapter in reversed(self.created_resources['chapters']):
            try:
                self.client.delete_chapter(chapter['id'])
                self.logger.info(f"Rolled back chapter: {chapter['name']}")
                rollback_stats['chapters_deleted'] += 1
            except Exception as e:
                self.logger.warning(f"Failed to rollback chapter {chapter['name']}: {str(e)}")
                rollback_stats['errors'].append({'type': 'chapter', 'resource': chapter, 'error': str(e)})
        
        # Delete books
        for book in reversed(self.created_resources['books']):
            try:
                self.client.delete_book(book['id'])
                self.logger.info(f"Rolled back book: {book['name']}")
                rollback_stats['books_deleted'] += 1
            except Exception as e:
                self.logger.warning(f"Failed to rollback book {book['name']}: {str(e)}")
                rollback_stats['errors'].append({'type': 'book', 'resource': book, 'error': str(e)})
        
        # Delete shelves
        for shelf in reversed(self.created_resources['shelves']):
            try:
                self.client.delete_shelf(shelf['id'])
                self.logger.info(f"Rolled back shelf: {shelf['name']}")
                rollback_stats['shelves_deleted'] += 1
            except Exception as e:
                self.logger.warning(f"Failed to rollback shelf {shelf['name']}: {str(e)}")
                rollback_stats['errors'].append({'type': 'shelf', 'resource': shelf, 'error': str(e)})
        
        # Reset tracked resources
        self.created_resources = {'shelves': [], 'books': [], 'chapters': [], 'pages': [], 'images': []}
        rollback_stats['rollback_executed'] = (rollback_stats['pages_deleted'] > 0 or 
                                              rollback_stats['chapters_deleted'] > 0 or 
                                              rollback_stats['books_deleted'] > 0 or 
                                              rollback_stats['shelves_deleted'] > 0)
        
        return rollback_stats
    
    def _should_show_progress(self) -> bool:
        """Check if progress bars should be shown."""
        if not HAS_TQDM:
            return False
        
        # Check config for progress_bars setting
        advanced_config = self.config.get('advanced', {})
        return advanced_config.get('progress_bars', True)