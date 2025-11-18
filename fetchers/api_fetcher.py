"""API fetcher implementation for retrieving Confluence content via REST API."""

import fnmatch
import hashlib
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from confluence_client import ConfluenceClient
from models import (
    ConfluenceAttachment,
    ConfluencePage,
    ConfluenceSpace,
    DocumentationTree
)
from .base_fetcher import BaseFetcher, FetcherError
from .cache_manager import CacheManager, CacheMode

logger = logging.getLogger('confluence_markdown_migrator.fetcher.api')


class ApiFetcher(BaseFetcher):
    """Fetches Confluence content via REST API for highest content fidelity."""
    
    def __init__(self, config: Dict[str, Any], logger=None):
        """
        Initialize API fetcher with configuration.
        
        Args:
            config: Configuration dictionary with confluence and advanced settings
            logger: Logger instance (optional)
        """
        super().__init__(config, logger)
        
        # Extract Confluence configuration
        confluence_config = config.get('confluence', {})
        advanced_config = config.get('advanced', {})
        
        # Required parameters
        base_url = confluence_config.get('base_url')
        if not base_url:
            raise ValueError("confluence.base_url is required for API fetcher")
        
        auth_type = confluence_config.get('auth_type', 'basic')
        
        # Optional parameters with defaults
        self.timeout = int(advanced_config.get('request_timeout', 30))
        self.max_retries = int(advanced_config.get('max_retries', 3))
        self.retry_backoff_factor = float(advanced_config.get('retry_backoff_factor', 2.0))
        self.rate_limit = float(advanced_config.get('rate_limit', 0.0))
        
        # Cache mode from config
        cache_config = advanced_config.get('cache', {})
        cache_mode = cache_config.get('mode', 'validate') if cache_config.get('enabled', False) else 'disable'
        
        # Initialize Confluence client
        client_kwargs = {
            'base_url': base_url,
            'auth_type': auth_type,
            'verify_ssl': confluence_config.get('verify_ssl', True),
            'timeout': self.timeout,
            'max_retries': self.max_retries,
            'retry_backoff_factor': self.retry_backoff_factor,
            'rate_limit': self.rate_limit
        }
        
        if auth_type == 'basic':
            client_kwargs.update({
                'username': confluence_config.get('username'),
                'password': confluence_config.get('password')
            })
        else:  # bearer
            client_kwargs.update({
                'api_token': confluence_config.get('api_token')
            })
        
        self.client = ConfluenceClient(**client_kwargs)
        
        # Initialize caches
        self._space_cache: Dict[str, ConfluenceSpace] = {}
        self._page_cache: Dict[str, ConfluencePage] = {}
        self._page_fetch_counter = 0
        self._last_progress_log_time = 0
        self._api_calls_made = 0
        
        # Initialize cache manager with mode
        self.cache_manager = CacheManager(config, mode=cache_mode)
        self.cache_stats = {
            'api_calls': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'validations': 0,
            'invalidations': 0
        }
        
        logger.info(f"Initialized ApiFetcher for {base_url} with auth_type={auth_type}, cache_mode={cache_mode}")
    
    def fetch_spaces(self, space_keys: Optional[List[str]] = None) -> List[ConfluenceSpace]:
        """
        Fetch Confluence spaces via API.
        
        Args:
            space_keys: Optional list of space keys to filter
            
        Returns:
            List of ConfluenceSpace objects (pages not loaded)
        """
        logger.info(f"Fetching spaces from Confluence API")
        
        # Check cache for spaces list
        cache_key = CacheManager.generate_cache_key('spaces_list')
        if space_keys:
            cache_key = CacheManager.generate_cache_key('spaces_list', space_keys=','.join(sorted(space_keys)))
        
        api_spaces = None
        validation_metadata = None
        
        # Use validation callback for VALIDATE mode if header validation is enabled
        if (self.cache_manager.mode == CacheMode.VALIDATE and 
            self.cache_manager.enabled and 
            self.cache_manager.validate_with_headers):
            def validate_spaces(cached_meta):
                url = f"{self.client.base_url}/rest/api/space"
                return self.client.validate_cache(
                    url,
                    etag=cached_meta.get('etag'),
                    last_modified=cached_meta.get('last_modified')
                )
            
            cached_data = self.cache_manager.get_with_validation(cache_key, validate_spaces)
        else:
            cached_data = self.cache_manager.get(cache_key)
        
        if cached_data:
            logger.info(f"Using cached spaces list")
            api_spaces = cached_data
            self.cache_stats['cache_hits'] += 1
        else:
            logger.info(f"Cache miss - fetching spaces from API")
            self.cache_stats['cache_misses'] += 1
            self.cache_stats['api_calls'] += 1
            
            api_spaces, validation_metadata = self.client.get_spaces(return_metadata=True)
            self.cache_manager.set(cache_key, api_spaces, validation_metadata=validation_metadata)
        
        spaces = []
        
        for api_space in api_spaces:
            space_key = api_space.get('key')
            
            # Filter if space_keys specified
            if space_keys and space_key not in space_keys:
                logger.debug(f"Skipping space '{space_key}' - not in filter list")
                continue
            
            space_model = self._convert_api_space_to_model(api_space)
            spaces.append(space_model)
            
            # Cache space
            self._space_cache[space_key] = space_model
        
        logger.info(f"Fetched {len(spaces)} spaces")
        return spaces
    
    def fetch_space_content(
        self,
        space_key: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> ConfluenceSpace:
        """
        Fetch complete space content with all pages and hierarchy.
        
        Args:
            space_key: Confluence space key
            filters: Optional filters (page_id, since_date)
            
        Returns:
            Populated ConfluenceSpace with pages
        """
        logger.info(f"Fetching space content for '{space_key}'")
        
        # Get space from cache or fetch
        if space_key in self._space_cache:
            space = self._space_cache[space_key]
            logger.debug(f"Using cached space '{space_key}'")
        else:
            try:
                # Fetch all spaces and filter in Python (space_keys param not supported)
                all_spaces, _ = self.client.get_spaces(return_metadata=True)
                matching_spaces = [s for s in all_spaces if s.get('key') == space_key]
                if not matching_spaces:
                    raise ValueError(f"Space '{space_key}' not found")
                space = self._convert_api_space_to_model(matching_spaces[0])
                self._space_cache[space_key] = space
            except Exception as e:
                logger.error(f"Failed to fetch space '{space_key}': {str(e)}")
                raise FetcherError(f"Space '{space_key}' not found: {str(e)}")
        
        # Handle page_id filter (fetch single page tree)
        if filters and 'page_id' in filters and filters['page_id']:
            page_id = filters['page_id']
            logger.info(f"Fetching single page tree for page_id={page_id}")
            
            try:
                root_page = self._fetch_page_recursive(page_id)
                
                # Validate page belongs to space
                if root_page.space_key != space_key:
                    raise ValueError(
                        f"Page {page_id} found in space '{root_page.space_key}', "
                        f"not in specified space '{space_key}'"
                    )
                
                space.pages = [root_page]
            except Exception as e:
                logger.error(f"Failed to fetch page tree for {page_id}: {str(e)}")
                raise FetcherError(f"Failed to fetch page {page_id}: {str(e)}")
        
        # Handle since_date filter (use CQL search)
        elif filters and 'since_date' in filters and filters['since_date']:
            logger.info(f"Fetching pages modified since {filters['since_date']}")
            pages = self._search_pages_by_date(space_key, filters['since_date'])
            space.pages = self._build_hierarchy_from_flat_list(pages)
        
        # Default: fetch all top-level pages recursively (optimized path)
        else:
            logger.info(f"Fetching all pages in space '{space_key}'")
            
            # Check cache for space content
            cache_key = CacheManager.generate_cache_key('space_content', space_key=space_key)
            all_pages_api = None
            validation_metadata = None
            
            # Use validation callback for VALIDATE mode if header validation is enabled
            if (self.cache_manager.mode == CacheMode.VALIDATE and 
                self.cache_manager.enabled and 
                self.cache_manager.validate_with_headers):
                def validate_space_content(cached_meta):
                    url = f"{self.client.base_url}/rest/api/content?spaceKey={space_key}"
                    return self.client.validate_cache(
                        url,
                        etag=cached_meta.get('etag'),
                        last_modified=cached_meta.get('last_modified')
                    )
                
                cached_data = self.cache_manager.get_with_validation(cache_key, validate_space_content)
            else:
                cached_data = self.cache_manager.get(cache_key)
            
            if cached_data:
                logger.info(f"Using cached space content for '{space_key}'")
                all_pages_api = cached_data
                self.cache_stats['cache_hits'] += 1
            else:
                logger.info(f"Cache miss - fetching from API")
                self.cache_stats['cache_misses'] += 1
                self.cache_stats['api_calls'] += 1
                
                all_pages_api, validation_metadata = self.client.get_space_content(
                    space_key, 
                    return_metadata=True
                )
                
                # Verify content is present in first few pages
                if all_pages_api and len(all_pages_api) > 0:
                    sample_page = all_pages_api[0]
                    has_body = 'body' in sample_page
                    has_export_view = has_body and 'export_view' in sample_page.get('body', {})
                    has_view = has_body and 'view' in sample_page.get('body', {})
                    logger.debug(f"Sample page {sample_page.get('id')}: has_body={has_body}, has_export_view={has_export_view}, has_view={has_view}")
                
                # Cache the API response
                self.cache_manager.set(cache_key, all_pages_api, validation_metadata=validation_metadata)
            
            # Log progress every 500 pages
            page_models = []
            logger.info(f"Converting {len(all_pages_api)} API responses to page models...")
            
            for idx, api_page in enumerate(all_pages_api):
                if idx % 500 == 0 and idx > 0:
                    logger.info(f"Converted {idx}/{len(all_pages_api)} page models...")
                page_model = self._convert_api_page_to_model(api_page)
                page_models.append(page_model)
            
            # Build hierarchy from flat list (much faster than recursive fetching)
            logger.info("Building page hierarchy from flat list...")
            space.pages = self._build_hierarchy_from_flat_list(page_models)
            logger.info(f"Built hierarchy with {len(space.pages)} root pages")
        
        # Apply filters and return
        if filters:
            space.pages = self._apply_filters(space.pages, filters)
        
        logger.info(f"Space '{space_key}' fetched: {len(space.pages)} root pages, "
                   f"{len(space.get_all_pages())} total pages")
        return space
    
    def fetch_page_tree(self, page_id: str) -> ConfluencePage:
        """
        Fetch specific page and all descendants recursively.
        
        Args:
            page_id: Confluence page ID
            
        Returns:
            Root ConfluencePage with children populated
        """
        logger.info(f"Fetching page tree for page_id={page_id}")
        return self._fetch_page_recursive(page_id)
    
    def fetch_page_content(self, page_id: str) -> ConfluencePage:
        """
        Fetch single page content without children.
        
        Args:
            page_id: Confluence page ID
            
        Returns:
            ConfluencePage without children loaded
        """
        # Check runtime cache first
        if page_id in self._page_cache:
            logger.debug(f"Using runtime cached page {page_id}")
            return self._page_cache[page_id]
        
        # Check persistent cache
        cache_key = CacheManager.generate_cache_key('page_content', page_id=page_id)
        cached_data = None
        validation_metadata = None
        
        # Use validation callback for VALIDATE mode if header validation is enabled
        if (self.cache_manager.mode == CacheMode.VALIDATE and 
            self.cache_manager.enabled and 
            self.cache_manager.validate_with_headers):
            def validate_page(cached_meta):
                url = f"{self.client.base_url}/rest/api/content/{page_id}"
                return self.client.validate_cache(
                    url,
                    etag=cached_meta.get('etag'),
                    last_modified=cached_meta.get('last_modified')
                )
            
            cached_data = self.cache_manager.get_with_validation(cache_key, validate_page)
        else:
            cached_data = self.cache_manager.get(cache_key)
        
        if cached_data:
            logger.debug(f"Using persistent cached page {page_id}")
            page_model = self._convert_api_page_to_model(cached_data)
            self._page_cache[page_id] = page_model
            self.cache_stats['cache_hits'] += 1
            return page_model
        
        logger.debug(f"Cache miss - fetching page content for {page_id} from API")
        self.cache_stats['cache_misses'] += 1
        self.cache_stats['api_calls'] += 1
        
        # CRITICAL: Use body.export_view for highest fidelity HTML (not body.storage)
        expand_fields = 'body.export_view,body.view,ancestors,space,version,metadata.labels,history'
        
        try:
            api_response, validation_metadata = self.client.get_page(
                page_id, 
                expand=expand_fields,
                return_metadata=True
            )
            logger.debug(f"API response for page {page_id}: {type(api_response)}")
        except Exception as e:
            logger.error(f"Failed to fetch page {page_id}: {str(e)}")
            raise
        
        # Cache the API response with validation metadata
        self.cache_manager.set(cache_key, api_response, validation_metadata=validation_metadata)
        
        page_model = self._convert_api_page_to_model(api_response)
        
        # Cache the page in runtime cache
        self._page_cache[page_id] = page_model
        
        return page_model
    
    def build_documentation_tree(
        self,
        space_keys: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> DocumentationTree:
        """
        Build complete documentation tree for specified spaces.
        
        Args:
            space_keys: Optional list of space keys to fetch
            filters: Optional filters to apply
            
        Returns:
            Populated DocumentationTree
        """
        logger.info(f"Building documentation tree{f' for spaces {space_keys}' if space_keys else ''}")
        
        # Validate filters
        self._validate_filters(filters)
        
        # Create tree with metadata
        tree = DocumentationTree()
        tree.metadata['fetch_mode'] = 'api'
        tree.metadata['fetch_timestamp'] = datetime.utcnow().isoformat()
        tree.metadata['confluence_base_url'] = self.config.get('confluence', {}).get('base_url')
        tree.metadata['filters_applied'] = filters or {}
        
        # Add cache statistics tracking
        tree.metadata['cache_stats'] = {
            'enabled': self.cache_manager.enabled,
            'mode': self.cache_manager.mode.value if hasattr(self.cache_manager, 'mode') else 'unknown',
            'cache_dir': self.cache_manager.cache_dir if hasattr(self.cache_manager, 'cache_dir') else None
        }
        
        # Handle page_id filter early: fetch page to determine space
        if filters and 'page_id' in filters and filters['page_id']:
            page_id = filters['page_id']
            logger.info(f"Fetching single page tree for page_id={page_id}")
            
            # Fetch page first to get space key
            page = self.fetch_page_content(page_id)
            space_key = page.space_key
            
            # Fetch space and attach page
            space = self.fetch_space_content(space_key=space_key, filters=filters)
            tree.add_space(space)
            
            # Update metadata
            tree.metadata['total_pages_fetched'] = len(space.get_all_pages())
            tree.metadata['total_attachments_fetched'] = len([
                att for page in space.get_all_pages() 
                for att in page.attachments if not att.excluded
            ])
            
            # Final cache stats for this path
            self._update_tree_cache_stats(tree)
            
            return tree
        
        # Standard path: fetch spaces
        spaces = self.fetch_spaces(space_keys)
        total_pages = 0
        total_attachments = 0
        
        for space in spaces:
            logger.info(f"Processing space '{space.key}'")
            
            # Fetch full content for space
            populated_space = self.fetch_space_content(space.key, filters)
            tree.add_space(populated_space)
            
            # Update counts
            space_pages = populated_space.get_all_pages()
            total_pages += len(space_pages)
            total_attachments += len([
                att for page in space_pages 
                for att in page.attachments if not att.excluded
            ])
        
        # Final metadata
        tree.metadata['total_pages_fetched'] = total_pages
        tree.metadata['total_attachments_fetched'] = total_attachments
        
        # Add final cache statistics
        self._update_tree_cache_stats(tree)
        
        # Log summary
        logger.info(f"Documentation tree built: {len(spaces)} spaces, "
                   f"{total_pages} pages, {total_attachments} attachments")
        logger.info(f"Cache statistics: mode={self.cache_manager.mode.value}, "
                   f"hits={self.cache_stats['cache_hits']}, misses={self.cache_stats['cache_misses']}, "
                   f"api_calls_saved={self.cache_stats['cache_hits']}")
        
        return tree
    
    def _update_tree_cache_stats(self, tree: DocumentationTree) -> None:
        """Update tree metadata with final cache statistics."""
        manager_stats = self.cache_manager.get_stats()
        
        # Calculate total requests and include api_calls made
        total_requests = manager_stats['hits'] + manager_stats['misses']
        
        tree.metadata['cache_stats'].update({
            'hits': manager_stats['hits'],
            'misses': manager_stats['misses'],
            'validations': manager_stats['validations'],
            'invalidations': manager_stats['invalidations'],
            'hit_rate': manager_stats['hit_rate'],
            'api_calls_saved': manager_stats['api_calls_saved'],
            'api_calls_made': self.cache_stats['api_calls'],
            'total_requests': total_requests,
            'total_entries': manager_stats['total_entries'],
            'total_size_mb': manager_stats['total_size_mb']
        })
    
    def _fetch_page_recursive(self, page_id: str, depth: int = 0, max_depth: int = 50) -> ConfluencePage:
        """
        Recursively fetch page with children.
        
        Args:
            page_id: Confluence page ID
            depth: Current recursion depth
            max_depth: Maximum recursion depth to prevent infinite loops
            
        Returns:
            Populated ConfluencePage with children
        """
        if depth > max_depth:
            logger.error(f"Maximum recursion depth {max_depth} exceeded for page {page_id}")
            raise FetcherError(f"Page hierarchy too deep or cyclic reference detected")
        
        # Check cache
        if page_id in self._page_cache:
            logger.debug(f"Cache hit for page {page_id}")
            return self._page_cache[page_id]
        
        logger.debug(f"Fetching page {page_id} (depth={depth})")
        self._log_fetch_progress(page_id, depth)
        
        # Fetch page with expansions
        expand_fields = 'body.export_view,body.view,ancestors,space,version,metadata.labels,history'
        
        try:
            api_response, validation_metadata = self.client.get_page(
                page_id, 
                expand=expand_fields,
                return_metadata=True
            )
            self.cache_stats['api_calls'] += 1
        except Exception as e:
            logger.error(f"Failed to fetch page {page_id}: {str(e)}")
            raise
        
        # Cache the page
        cache_key = CacheManager.generate_cache_key('page_content', page_id=page_id)
        self.cache_manager.set(cache_key, api_response, validation_metadata=validation_metadata)
        
        # Convert to model
        page_model = self._convert_api_page_to_model(api_response)
        
        # Cache page
        self._page_cache[page_id] = page_model
        
        # Recursively fetch children
        try:
            child_responses, child_metadata = self.client.get_page_children(
                page_id, 
                return_metadata=True
            )
            self.cache_stats['api_calls'] += 1
            
            # Cache children list
            children_cache_key = CacheManager.generate_cache_key(f"page_{page_id}_children")
            self.cache_manager.set(children_cache_key, child_responses, validation_metadata=child_metadata)
            
            for child_response in child_responses:
                child_model = self._fetch_page_recursive(child_response['id'], depth + 1, max_depth)
                page_model.add_child(child_model)
        except Exception as e:
            logger.warning(f"Failed to fetch children for page {page_id}: {str(e)}")
        
        # Fetch attachments
        try:
            attachments = self._fetch_attachments_for_page(page_id)
            page_model.attachments = attachments
        except Exception as e:
            logger.warning(f"Failed to fetch attachments for page {page_id}: {str(e)}")
        
        return page_model
    
    def _convert_api_page_to_model(self, api_response: Dict[str, Any]) -> ConfluencePage:
        """
        Convert API page response to ConfluencePage model with conversion metadata.
        
        Args:
            api_response: API JSON response
            
        Returns:
            ConfluencePage model
        """
        page_id = str(api_response['id'])
        title = api_response.get('title', 'Untitled')
        
        # Get export_view HTML (highest fidelity)
        content_html = ''
        if 'body' in api_response and 'export_view' in api_response['body']:
            content_html = api_response['body']['export_view'].get('value', '')
        elif 'body' in api_response and 'view' in api_response['body']:
            # Fallback to view if export_view not available
            content_html = api_response['body']['view'].get('value', '')
            logger.warning(f"Page {page_id} used 'view' mode instead of 'export_view'")
        else:
            logger.warning(f"Page {page_id} has no content in export_view or view mode")
        
        space_key = api_response.get('space', {}).get('key', 'UNKNOWN')
        
        # Extract parent_id from ancestors
        parent_id = None
        ancestors = api_response.get('ancestors', [])
        if ancestors:
            # Parent is the ancestor closest to this page (last in list)
            parent_id = str(ancestors[-1]['id'])
        
        # Build metadata dict
        version = api_response.get('version', {}).get('number', 1)
        history = api_response.get('history', {})
        last_modified = history.get('lastUpdated', {}).get('when')
        creator = history.get('created', {}).get('by', {}).get('displayName')
        author = creator  # For simplicity, use creator as author
        
        # Extract labels
        labels = []
        metadata = api_response.get('metadata', {})
        if 'labels' in metadata:
            labels = [label.get('name') for label in metadata['labels'].get('results', [])]
        
        # Determine content type
        content_type = 'page'  # Default
        if '/blog/' in api_response.get('_links', {}).get('webui', ''):
            content_type = 'blogpost'
        
        page_metadata = {
            'author': author,
            'last_modified': last_modifier,
            'version': version,
            'labels': labels,
            'content_type': content_type,
            'content_source': 'api'
        }
        
        # Initialize conversion metadata for quality tracking
        conversion_metadata = {
            'status': 'fetched',
            'macros_detected': [],
            'links_resolved': 0,
            'images_processed': 0,
            'warnings': [],
            'fetch_timestamp': datetime.utcnow().isoformat()
        }
        
        # Check for empty content and add warning
        if not content_html or len(content_html.strip()) < 50:  # Minimal HTML check
            conversion_metadata['warnings'].append("Page has very little or no content")
        
        # Create page model
        page = ConfluencePage(
            id=page_id,
            title=title,
            content=content_html,
            space_key=space_key,
            parent_id=parent_id,
            metadata=page_metadata
        )
        
        # Set conversion metadata
        page.conversion_metadata = conversion_metadata
        logger.debug(f"Initialized conversion_metadata for page {page_id}")
        
        return page
    
    def _convert_api_space_to_model(self, api_response: Dict[str, Any]) -> ConfluenceSpace:
        """
        Convert API space response to ConfluenceSpace model.
        
        Args:
            api_response: API JSON response
            
        Returns:
            ConfluenceSpace model
        """
        space_id = str(api_response['id'])
        key = api_response.get('key', 'UNKNOWN')
        name = api_response.get('name', key)
        description = api_response.get('description', {}).get('plain', {}).get('value', '')
        
        # Extract metadata
        homepage_id = None
        if 'homepage' in api_response:
            homepage_id = str(api_response['homepage'].get('id'))
        
        space_type = api_response.get('type', 'global')
        
        space_metadata = {
            'homepage_id': homepage_id,
            'type': space_type,
            'permissions': {}
        }
        
        return ConfluenceSpace(
            key=key,
            name=name,
            id=space_id,
            description=description,
            metadata=space_metadata
        )
    
    def _convert_api_attachment_to_model(self, api_response: Dict[str, Any], page_id: str) -> ConfluenceAttachment:
        """
        Convert API attachment response to ConfluenceAttachment model.
        
        Args:
            api_response: API JSON response
            page_id: Parent page ID
            
        Returns:
            ConfluenceAttachment model
        """
        attachment_id = str(api_response['id'])
        title = api_response.get('title', 'Untitled')
        media_type = api_response.get('metadata', {}).get('mediaType', 'application/octet-stream')
        file_size = api_response.get('extensions', {}).get('fileSize', 0)
        
        # Build download URL
        download_path = api_response.get('_links', {}).get('download', '')
        if download_path:
            # Handle both full URL and relative path
            if download_path.startswith('http'):
                download_url = download_path
            else:
                download_url = self.client.base_url + download_path.lstrip('/')
        else:
            # Fallback download URL
            download_url = f"{self.client.base_url}/download/attachments/{page_id}/{title}"
        
        return ConfluenceAttachment(
            id=attachment_id,
            title=title,
            media_type=media_type,
            file_size=file_size,
            download_url=download_url,
            page_id=page_id
        )
    
    def _fetch_attachments_for_page(self, page_id: str) -> List[ConfluenceAttachment]:
        """
        Fetch attachments for page and apply exclusion rules, with caching.
        
        Args:
            page_id: Confluence page ID
            
        Returns:
            List of ConfluenceAttachment models (some may be excluded)
        """
        logger.debug(f"Fetching attachments for page {page_id}")
        
        # Check cache for attachments list
        attachments_cache_key = CacheManager.generate_cache_key(f"page_{page_id}_attachments")
        api_attachments = None
        attachments_meta = None
        
        # Use validation callback for VALIDATE mode if header validation is enabled
        if (self.cache_manager.mode == CacheMode.VALIDATE and 
            self.cache_manager.enabled and 
            self.cache_manager.validate_with_headers):
            def validate_attachments(cached_meta):
                url = f"{self.client.base_url}/rest/api/content/{page_id}/child/attachment"
                return self.client.validate_cache(
                    url,
                    etag=cached_meta.get('etag'),
                    last_modified=cached_meta.get('last_modified')
                )
            
            cached_attachments = self.cache_manager.get_with_validation(attachments_cache_key, validate_attachments)
        else:
            cached_attachments = self.cache_manager.get(attachments_cache_key)
        
        if cached_attachments:
            logger.debug(f"Using cached attachments list for page {page_id}")
            api_attachments = cached_attachments
            self.cache_stats['cache_hits'] += 1
        else:
            logger.debug(f"Cache miss - fetching attachments for page {page_id} from API")
            self.cache_stats['cache_misses'] += 1
            self.cache_stats['api_calls'] += 1
            
            api_attachments, attachments_meta = self.client.get_attachments(
                page_id, 
                return_metadata=True
            )
            self.cache_manager.set(attachments_cache_key, api_attachments, validation_metadata=attachments_meta)
        
        export_config = self.config.get('export', {})
        attachment_config = export_config.get('attachment_handling', {})
        
        max_file_size = attachment_config.get('max_file_size', 52428800)  # 50MB default
        skip_file_types = attachment_config.get('skip_file_types', [])
        attachments_dir = attachment_config.get('attachments_dir', './attachments')
        
        attachments = []
        
        for api_attachment in api_attachments:
            attachment = self._convert_api_attachment_to_model(api_attachment, page_id)
            
            # Generate cache key for binary data
            att_cache_key = CacheManager.generate_cache_key(
                'attachment',
                page_id=page_id,
                att_id=attachment.id,
                att_title=attachment.title
            )
            
            # Try to get cached binary data
            cached_binary = None
            if not attachment.excluded:
                cached_binary = self.cache_manager.get_binary(att_cache_key)
            
            if cached_binary is not None:
                # Use cached attachment
                attachment.local_path = os.path.join(attachments_dir, attachment.title)
                attachment.cached = True
                logger.debug(f"Using cached attachment: {attachment.title}")
                self.cache_stats['cache_hits'] += 1
            else:
                # Download attachment if not excluded
                if not attachment.excluded:
                    try:
                        logger.debug(f"Downloading attachment: {attachment.title}")
                        self.cache_stats['api_calls'] += 1
                        
                        binary_data, download_meta = self.client.download_attachment(
                            attachment.download_url,
                            return_metadata=True
                        )
                        
                        # Cache binary data
                        self.cache_manager.set_binary(
                            att_cache_key,
                            binary_data,
                            metadata={
                                'media_type': attachment.media_type,
                                'file_size': attachment.file_size,
                                'page_id': page_id,
                                'etag': download_meta.get('etag'),
                                'last_modified': download_meta.get('last_modified')
                            }
                        )
                        
                        attachment.local_path = os.path.join(attachments_dir, attachment.title)
                        attachment.cached = False
                        self.cache_stats['cache_misses'] += 1
                        
                    except Exception as e:
                        logger.warning(f"Failed to download attachment {attachment.title}: {str(e)}")
                        attachment.excluded = True
                        attachment.exclusion_reason = f"download_failed: {str(e)}"
            
            # Apply exclusion rules
            if skip_file_types and not attachment.excluded:
                file_ext = os.path.splitext(attachment.title)[1].lower()
                if file_ext:
                    # Check against patterns (e.g., "*.exe", ".exe")
                    for pattern in skip_file_types:
                        pattern = pattern.strip()
                        if fnmatch.fnmatch(file_ext, pattern) or fnmatch.fnmatch(attachment.title, f"*{pattern}"):
                            attachment.excluded = True
                            attachment.exclusion_reason = f"blocked_extension: {file_ext}"
                            logger.debug(f"Excluding attachment '{attachment.title}' (blocked extension)")
                            break
            
            # Check file size
            if not attachment.excluded and attachment.file_size > max_file_size:
                attachment.excluded = True
                size_mb = attachment.file_size / (1024 * 1024)
                max_mb = max_file_size / (1024 * 1024)
                attachment.exclusion_reason = f"exceeds_size_limit: {size_mb:.1f}MB > {max_mb:.1f}MB"
                logger.debug(f"Excluding attachment '{attachment.title}' (size limit)")
            
            attachments.append(attachment)
        
        logger.debug(f"Fetched {len(attachments)} attachments for page {page_id} "
                    f"({len([a for a in attachments if a.excluded])} excluded)")
        
        return attachments
    
    def _search_pages_by_date(self, space_key: str, since_date: str) -> List[ConfluencePage]:
        """
        Search for pages modified since date using CQL.
        
        Args:
            space_key: Confluence space key
            since_date: ISO date string
            
        Returns:
            List of ConfluencePage models
        """
        # Build CQL query
        cql = f'space = "{space_key}" AND lastModified >= "{since_date}"'
        
        logger.info(f"Searching for pages with CQL: {cql}")
        
        expand_fields = 'body.export_view,body.view,ancestors,space,version,metadata.labels,history'
        
        try:
            search_results = self.client.search_content(cql, expand=expand_fields)
            self.cache_stats['api_calls'] += 1
        except Exception as e:
            logger.error(f"CQL search failed: {str(e)}")
            raise
        
        pages = []
        for result in search_results:
            if result.get('type') == 'page':
                page = self._convert_api_page_to_model(result)
                pages.append(page)
        
        logger.info(f"CQL search returned {len(pages)} pages")
        return pages
    
    def _build_hierarchy_from_flat_list(self, pages: List[ConfluencePage]) -> List[ConfluencePage]:
        """
        Reconstruct parent-child relationships from flat list of pages.
        
        Args:
            pages: List of pages with parent_id references
            
        Returns:
            List of root pages with children populated
        """
        if not pages:
            return []
        
        # Build lookup dict for fast access
        page_dict = {page.id: page for page in pages}
        
        # Reset children lists
        for page in pages:
            page.children = []
        
        # Build hierarchy
        root_pages = []
        for page in pages:
            if page.parent_id is None:
                root_pages.append(page)
            elif page.parent_id in page_dict:
                parent = page_dict[page.parent_id]
                parent.add_child(page)
            else:
                # Parent not in list, treat as root
                logger.warning(f"Parent {page.parent_id} not found for page {page.id}, treating as root")
                root_pages.append(page)
        
        logger.debug(f"Built hierarchy from {len(pages)} pages: {len(root_pages)} root pages")
        return root_pages
    
    def _log_fetch_progress(self, page_id: str, depth: int):
        """Log progress every 50 pages and every 10 seconds."""
        self._page_fetch_counter += 1
        current_time = time.time()
        
        # Log every 50 pages or every 10 seconds, whichever comes first
        if (self._page_fetch_counter % 50 == 0 or 
            (current_time - self._last_progress_log_time) > 10):
            self._last_progress_log_time = current_time
            logger.info(f"Fetched {self._page_fetch_counter} pages so far (current: {page_id}, depth: {depth})")
