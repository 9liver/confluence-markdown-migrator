"""HTML fetcher implementation for parsing Confluence HTML export files."""

import fnmatch
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bs4 import BeautifulSoup

from models import (
    ConfluenceAttachment,
    ConfluencePage,
    ConfluenceSpace,
    DocumentationTree
)
from .base_fetcher import BaseFetcher, FetcherError
from .cache_manager import CacheManager, CacheMode

logger = logging.getLogger('confluence_markdown_migrator.fetcher.html')


class HtmlFetcher(BaseFetcher):
    """Fetches Confluence content by parsing HTML export files."""
    
    def __init__(self, config: Dict[str, Any], logger=None):
        """
        Initialize HTML fetcher with configuration.
        
        Args:
            config: Configuration dictionary with confluence.html_export_path
            logger: Logger instance (optional)
        """
        super().__init__(config, logger)
        
        # Extract HTML export path
        confluence_config = config.get('confluence', {})
        html_export_path = confluence_config.get('html_export_path')
        
        if not html_export_path:
            raise ValueError("confluence.html_export_path is required for HTML fetcher")
        
        self.html_export_path = Path(html_export_path).resolve()
        self.index_path = self.html_export_path / 'index.html'
        
        # Validate paths
        if not self.html_export_path.exists():
            raise FileNotFoundError(f"HTML export path not found: {self.html_export_path}")
        
        if not self.index_path.exists():
            raise FileNotFoundError(f"index.html not found in export path: {self.index_path}")
        
        # Initialize basic cache manager for file-based caching (TTL only)
        self.cache_manager = CacheManager(config)
        self._cache_stats = {
            'hits': 0,
            'misses': 0
        }
        
        logger.info(f"Initialized HtmlFetcher for path: {self.html_export_path}")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics for HTML mode."""
        # Calculate total requests
        total_requests = self._cache_stats['hits'] + self._cache_stats['misses']
        hit_rate = self._cache_stats['hits'] / total_requests if total_requests > 0 else 0.0
        
        return {
            **self._cache_stats,
            'enabled': self.cache_manager.enabled,
            'mode': 'TTL_only',  # HTML mode doesn't support validation
            'validations': 0,  # Not applicable for HTML mode
            'invalidations': 0,  # Not applicable for HTML mode
            'hit_rate': hit_rate,
            'api_calls_saved': self._cache_stats['hits'],  # Parse time savings
            'total_entries': 0,  # Not tracked for HTML mode
            'total_size_mb': 0,  # Not tracked for HTML mode
            'api_calls_made': 0  # Not applicable for HTML mode
        }
    
    def fetch_spaces(self, space_keys: Optional[List[str]] = None) -> List[ConfluenceSpace]:
        """
        Parse spaces from HTML export index file.
        
        Args:
            space_keys: Optional list of space keys to filter
            
        Returns:
            List of ConfluenceSpace objects (pages not loaded)
        """
        logger.info(f"Parsing spaces from {self.index_path}")
        
        # Try to cache space metadata parse
        cache_key = CacheManager.generate_cache_key('html_space_metadata', export_path=str(self.html_export_path))
        cached_metadata = self.cache_manager.get(cache_key)
        
        if cached_metadata and self.cache_manager.enabled:
            logger.debug("Using cached space metadata")
            space_metadata = cached_metadata
            self._cache_stats['hits'] += 1
        else:
            logger.debug("Parsing space metadata from HTML")
            space_metadata = self._parse_index_html()
            if self.cache_manager.enabled:
                self.cache_manager.set(cache_key, space_metadata)
            self._cache_stats['misses'] += 1
        
        spaces = []
        if space_metadata:
            space_key = space_metadata.get('key', 'EXPORT')
            
            # Filter if space_keys specified
            if space_keys and space_key not in space_keys:
                logger.info(f"Skipping space '{space_key}' - not in filter list")
                return []
            
            space = ConfluenceSpace(
                key=space_key,
                name=space_metadata.get('name', space_key),
                id=space_metadata.get('id', 'export'),
                description=space_metadata.get('description', ''),
                metadata={
                    'homepage_id': space_metadata.get('homepage_id'),
                    'type': 'global',
                    'permissions': {}
                }
            )
            spaces.append(space)
        
        logger.info(f"Parsed {len(spaces)} spaces from HTML export")
        return spaces
    
    def fetch_space_content(
        self,
        space_key: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> ConfluenceSpace:
        """
        Parse space content from HTML export.
        
        Args:
            space_key: Confluence space key
            filters: Optional filters (page_id, since_date)
            
        Returns:
            Populated ConfluenceSpace with pages
        """
        logger.info(f"Fetching space content for '{space_key}' from HTML export")
        
        # Try to cache page tree structure parse
        tree_cache_key = CacheManager.generate_cache_key('html_page_tree', export_path=str(self.html_export_path))
        cached_tree = self.cache_manager.get(tree_cache_key)
        
        if cached_tree and self.cache_manager.enabled:
            logger.debug("Using cached page tree structure")
            page_tree_structure = cached_tree
            self._cache_stats['hits'] += 1
        else:
            logger.debug("Parsing page tree structure from HTML")
            page_tree_structure = self._parse_page_tree_structure()
            if self.cache_manager.enabled:
                # Include file modification times for basic validation
                file_stats = {
                    'index_mtime': self.index_path.stat().st_mtime,
                    'export_path': str(self.html_export_path)
                }
                self.cache_manager.set(tree_cache_key, page_tree_structure, 
                                     validation_metadata=file_stats)
            self._cache_stats['misses'] += 1
        
        # Parse space metadata
        space_metadata = self._parse_index_html()
        
        # Create space
        space = ConfluenceSpace(
            key=space_key,
            name=space_metadata.get('name', space_key),
            id=space_metadata.get('id', 'export'),
            description=space_metadata.get('description', ''),
            metadata={
                'homepage_id': space_metadata.get('homepage_id'),
                'type': 'global',
                'permissions': {}
            }
        )
        
        # Build pages from tree structure
        if page_tree_structure:
            space.pages = self._build_pages_from_tree(page_tree_structure, space_key)
        
        # Apply filters
        if filters:
            space.pages = self._apply_filters(space.pages, filters)
        
        # Note: date filtering is limited in HTML mode since metadata may be incomplete
        if filters and 'since_date' in filters:
            logger.warning("Date filtering is limited in HTML mode and may not filter all pages correctly")
        
        logger.info(f"Space '{space_key}' parsed: {len(space.pages)} root pages, "
                   f"{len(space.get_all_pages())} total pages")
        return space
    
    def fetch_page_tree(self, page_id: str) -> ConfluencePage:
        """
        Fetch specific page and descendants from HTML export.
        
        Args:
            page_id: Page ID
            
        Returns:
            Root ConfluencePage with children populated
        """
        # Try to cache page tree structure parse
        tree_cache_key = CacheManager.generate_cache_key('html_page_tree', export_path=str(self.html_export_path))
        cached_tree = self.cache_manager.get(tree_cache_key)
        
        if cached_tree and self.cache_manager.enabled:
            logger.debug("Using cached page tree structure")
            page_tree_structure = cached_tree
            self._cache_stats['hits'] += 1
        else:
            logger.debug("Parsing page tree structure from HTML")
            page_tree_structure = self._parse_page_tree_structure()
            if self.cache_manager.enabled:
                file_stats = {
                    'index_mtime': self.index_path.stat().st_mtime,
                    'export_path': str(self.html_export_path)
                }
                self.cache_manager.set(tree_cache_key, page_tree_structure,
                                     validation_metadata=file_stats)
            self._cache_stats['misses'] += 1
        
        # Find page in tree
        page_info = self._find_page_in_tree(page_id, page_tree_structure)
        if not page_info:
            raise FetcherError(f"Page {page_id} not found in HTML export")
        
        # Build with children
        return self._build_page_with_children(page_info, page_info.get('space_key', 'EXPORT'))
    
    def fetch_page_content(self, page_id: str) -> ConfluencePage:
        """
        Fetch single page content from HTML export.
        
        Args:
            page_id: Page ID
            
        Returns:
            ConfluencePage without children
        """
        # Try to cache page tree structure parse
        tree_cache_key = CacheManager.generate_cache_key('html_page_tree', export_path=str(self.html_export_path))
        cached_tree = self.cache_manager.get(tree_cache_key)
        
        if cached_tree and self.cache_manager.enabled:
            logger.debug("Using cached page tree structure")
            page_tree_structure = cached_tree
            self._cache_stats['hits'] += 1
        else:
            logger.debug("Parsing page tree structure from HTML")
            page_tree_structure = self._parse_page_tree_structure()
            if self.cache_manager.enabled:
                file_stats = {
                    'index_mtime': self.index_path.stat().st_mtime,
                    'export_path': str(self.html_export_path)
                }
                self.cache_manager.set(tree_cache_key, page_tree_structure,
                                     validation_metadata=file_stats)
            self._cache_stats['misses'] += 1
        
        # Find page in tree
        page_info = self._find_page_in_tree(page_id, page_tree_structure)
        if not page_info:
            raise FetcherError(f"Page {page_id} not found in HTML export")
        
        # Parse page file - _parse_page_file handles caching internally
        page_file = self._find_page_file(page_id, page_info.get('title', ''))
        space_key = page_info.get('space_key', 'EXPORT')
        page = self._parse_page_file(page_file, page_info, space_key)
        
        return page
    
    def build_documentation_tree(
        self,
        space_keys: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None
    ) -> DocumentationTree:
        """
        Build documentation tree from HTML export.
        
        Args:
            space_keys: Optional space keys to filter
            filters: Optional filters to apply
            
        Returns:
            Populated DocumentationTree
        """
        logger.info(f"Building documentation tree from HTML export")
        
        # Validate filters
        self._validate_filters(filters)
        
        # Create tree
        tree = DocumentationTree()
        tree.metadata['fetch_mode'] = 'html'
        tree.metadata['fetch_timestamp'] = datetime.utcnow().isoformat()
        tree.metadata['confluence_base_url'] = None  # Not available in HTML mode
        tree.metadata['filters_applied'] = filters or {}
        
        # Add cache statistics for HTML mode
        tree.metadata['cache_stats'] = self.get_cache_stats()
        
        # Fetch spaces (usually just one from HTML export)
        spaces = self.fetch_spaces(space_keys)
        total_pages = 0
        total_attachments = 0
        
        # Parse full content for each space
        for space in spaces:
            logger.info(f"Processing space '{space.key}' from HTML export")
            
            # Fetch full content
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
        
        # Update final cache stats
        tree.metadata['cache_stats'].update(self.get_cache_stats())
        
        logger.info(f"Documentation tree built: {len(spaces)} spaces, "
                   f"{total_pages} pages, {total_attachments} attachments from HTML export")
        logger.info(f"HTML cache statistics: hits={self._cache_stats['hits']}, "
                   f"misses={self._cache_stats['misses']}")
        
        return tree
    
    def _parse_index_html(self) -> Dict[str, Any]:
        """
        Parse main index.html file to extract space metadata.
        
        Returns:
            Dictionary with space metadata
        """
        with open(self.index_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'lxml')
        
        metadata = {}
        
        # Try to extract space key from various sources
        title = soup.title.string if soup.title else ''
        space_key = self._extract_space_key(soup, title)
        metadata['key'] = space_key
        
        # Extract space name
        h1 = soup.find('h1')
        if h1:
            metadata['name'] = h1.get_text().strip()
        elif title:
            metadata['name'] = title.strip()
        else:
            metadata['name'] = space_key
        
        # Extract space ID from meta tags
        metadata['id'] = self._extract_space_id(soup)
        
        # Try to extract description
        meta_desc = soup.find('meta', {'name': 'description'})
        if meta_desc and meta_desc.get('content'):
            metadata['description'] = meta_desc['content']
        
        # Try to extracthomepage ID
        home_link = soup.find('a', href=True, text=lambda t: t and 'Home' in t)
        if home_link:
            homepage_id = self._extract_page_id_from_href(home_link['href'], 'Home')
            if homepage_id:
                metadata['homepage_id'] = homepage_id
        
        return metadata
    
    def _parse_page_tree_structure(self) -> List[Dict[str, Any]]:
        """
        Parse page tree structure from index.html.
        
        Returns:
            List of page info dictionaries with hierarchy
        """
        with open(self.index_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'lxml')
        
        # Try multiple selectors for page tree container
        selectors = [
            '#page-tree',  # ID selector
            '.page-tree',  # Class selector
            '#content',    # Generic content
            'body'         # Fallback to body
        ]
        
        tree_container = None
        for selector in selectors:
            tree_container = soup.select_one(selector)
            if tree_container:
                logger.debug(f"Found page tree container with selector: {selector}")
                break
        
        if not tree_container:
            logger.warning("No page tree container found in index.html")
            return []
        
        # Find the main navigation list
        nav_list = tree_container.find('ul')
        if not nav_list:
            logger.warning("No <ul> navigation list found in tree container")
            return []
        
        # Parse nested list structure
        return self._parse_list_items(nav_list)
    
    def _parse_list_items(self, ul_element, parent_id: Optional[str] = None, depth: int = 0) -> List[Dict[str, Any]]:
        """
        Recursively parse <li> elements from navigation list.
        
        Args:
            ul_element: <ul> BeautifulSoup element
            parent_id: Parent page ID (optional)
            depth: Current recursion depth
            
        Returns:
            List of page info dictionaries
        """
        pages = []
        
        for li in ul_element.find_all('li', recursive=False):
            # Extract link
            link = li.find('a', href=True)
            if not link:
                continue
            
            href = link['href']
            title = link.get_text().strip()
            
            # Extract page ID
            page_id = self._extract_page_id_from_href(href, title)
            if not page_id:
                # Create ID from title and parent info
                page_id = f"page_{depth}_{len(pages)}"
                logger.debug(f"Generated ID for page '{title}': {page_id}")
            
            # Build page info
            page_info = {
                'id': page_id,
                'title': title,
                'href': href,
                'space_key': 'EXPORT',  # Hardcoded for HTML export
                'parent_id': parent_id,
                'depth': depth
            }
            
            # Recursively process children
            child_ul = li.find('ul')
            if child_ul:
                children = self._parse_list_items(child_ul, page_id, depth + 1)
                page_info['children'] = children
            
            pages.append(page_info)
        
        return pages
    
    def _extract_space_key(self, soup: Any, title: str) -> str:
        """
        Extract space key from HTML.
        
        Args:
            soup: BeautifulSoup object
            title: Page title
            
        Returns:
            Space key string
        """
        # Try meta tags
        space_key_meta = soup.find('meta', {'name': 'confluence-space-key'})
        if space_key_meta and space_key_meta.get('content'):
            return space_key_meta['content']
        
        # Try to extract from URL patterns
        for link in soup.find_all('a', href=True):
            href = link['href']
            # Look for patterns like /display/SPACEKEY/ or /spaces/SPACEKEY/
            if '/display/' in href:
                parts = href.split('/')
                for i, part in enumerate(parts):
                    if part == 'display' and i + 1 < len(parts):
                        return parts[i + 1]
            elif '/spaces/' in href:
                parts = href.split('/')
                for i, part in enumerate(parts):
                    if part == 'spaces' and i + 1 < len(parts):
                        return parts[i + 1]
        
        # Fallback to title or default
        if title:
            # Extract first word or use title
            return title.split()[0].upper()[:10]
        
        return 'EXPORT'
    
    def _extract_space_id(self, soup: Any) -> str:
        """
        Extract space ID from HTML.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Space ID string
        """
        space_id_meta = soup.find('meta', {'name': 'confluence-space-id'})
        if space_id_meta and space_id_meta.get('content'):
            return space_id_meta['content']
        
        return 'export'
    
    def _extract_page_id_from_href(self, href: str, title: str) -> Optional[str]:
        """
        Extract page ID from href.
        
        Args:
            href: Link href
            title: Page title
            
        Returns:
            Page ID string or None
        """
        # Try multiple patterns
        patterns = [
            r'/pages/viewpage.action\?pageId=(\d+)',  # ?pageId=12345
            r'/display/[^/]+/(\d+)',                     # /display/SPACE/12345
            r'/download/attachments/(\d+)/',             # /download/attachments/12345/
            r'(\d+)\.html$',                           # 12345.html
            r'pages/(\d+)/'                             # pages/12345/
        ]
        
        for pattern in patterns:
            match = re.search(pattern, href)
            if match:
                return match.group(1)
        
        return None
    
    def _find_page_file(self, page_id: str, page_title: str) -> Path:
        """
        Find page HTML file in export directory.
        
        Args:
            page_id: Page ID
            page_title: Page title
            
        Returns:
            Path to page file
            
        Raises:
            FileNotFoundError: If page file not found
        """
        # Try direct filename patterns
        patterns = [
            f"{page_id}.html",
            f"{page_title}.html",
            page_title.replace(' ', '_') + '.html',
            page_title.replace(' ', '-').replace('/', '_') + '.html',
            page_title.replace(' ', '').replace('/', '_') + '.html'
        ]
        
        for pattern in patterns:
            file_path = self.html_export_path / pattern
            if file_path.exists():
                logger.debug(f"Found page file: {file_path}")
                return file_path
        
        # Fallback: chunked scan of all HTML files
        logger.debug(f"Direct pattern match failed for page {page_id}, performing chunked scan")
        
        # Find all HTML files
        html_files = list(self.html_export_path.glob('*.html'))
        
        chunk_size = 1024 * 128  # 128KB chunks
        overlap = 1024  # 1KB overlap
        
        for html_file in html_files:
            try:
                file_size = html_file.stat().st_size
                with open(html_file, 'r', encoding='utf-8', errors='ignore') as f:
                    offset = 0
                    while offset < file_size:
                        # Read chunk
                        f.seek(offset)
                        chunk_data = f.read(chunk_size + overlap)
                        
                        # Search for page ID patterns
                        # Look for data-page-id, page-id, or similar attributes
                        id_patterns = [
                            f'data-page-id="{page_id}"',
                            f'page-id="{page_id}"',
                            f'pageId: "{page_id}"',
                            f'"id": "{page_id}"',  # JSON-like metadata
                            f"'id': '{page_id}'",   # Alternative JSON format
                        ]
                        
                        if any(pattern in chunk_data for pattern in id_patterns):
                            logger.debug(f"Found page {page_id} in file: {html_file}")
                            return html_file
                        
                        # Also search for title if page ID not found
                        if page_title and page_title.lower() in chunk_data.lower():
                            # Found potential match, parse full file to confirm
                            chunk = chunk_data + f.read(min(chunk_size, file_size - offset - chunk_size))
                            if self._confirm_page_match(html_file, page_id, page_title):
                                logger.debug(f"Found page '{page_title}' in file: {html_file}")
                                return html_file
                        
                        offset += chunk_size
            except Exception as e:
                logger.debug(f"Error scanning file {html_file}: {str(e)}")
                continue
        
        # Not found
        raise FileNotFoundError(
            f"Page file not found for page_id={page_id}, title='{page_title}'. "
            f"Searched in: {self.html_export_path}"
        )
    
    def _confirm_page_match(self, file_path: Path, page_id: str, page_title: str) -> bool:
        """
        Confirm that a file matches the expected page.
        
        Args:
            file_path: File to check
            page_id: Expected page ID
            page_title: Expected page title
            
        Returns:
            True if confirmed match
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Check for exact page ID
                id_patterns = [
                    f'data-page-id="{page_id}"',
                    f'page-id="{page_id}"',
                    f'"id": "{page_id}"'
                ]
                
                for pattern in id_patterns:
                    if pattern in content:
                        return True
                
                # Check title more carefully
                if page_title and (f'<title>{page_title}</title>' in content or
                                 f'<h1>{page_title}</h1>' in content):
                    return True
        except:
            pass
        
        return False
    
    def _parse_page_file(self, page_file: Path, page_info: Dict[str, Any], space_key: str) -> ConfluencePage:
        """
        Parse page HTML file to extract content and metadata.
        
        Args:
            page_file: Path to page HTML file
            page_info: Page information dict
            space_key: Space key
            
        Returns:
            ConfluencePage model
        """
        logger.debug(f"Parsing page file: {page_file}")
        
        # Check if we should cache this parse based on file modification time
        page_cache_key = CacheManager.generate_cache_key('html_page_file', page_id=page_info['id'])
        cached_data = self.cache_manager.get(page_cache_key)
        current_mtime = page_file.stat().st_mtime
        
        if cached_data and self.cache_manager.enabled:
            # Validate file hasn't changed since last parse
            cached_mtime = cached_data.get('file_mtime', 0)
            if cached_mtime >= current_mtime:
                logger.debug(f"Using cached parsed page {page_info['id']}")
                self._cache_stats['hits'] += 1
                # Return cached page data
                return ConfluencePage(
                    id=page_info['id'],
                    title=page_info.get('title', 'Untitled'),
                    content=cached_data.get('content', ''),
                    space_key=space_key,
                    parent_id=page_info.get('parent_id'),
                    url=str(page_file.resolve()),
                    metadata=cached_data.get('metadata', {})
                )
        
        with open(page_file, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        soup = BeautifulSoup(content, 'lxml')
        
        # Extract title
        title = page_info.get('title')
        if not title:
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text().strip()
            elif soup.title:
                title = soup.title.string.strip()
            else:
                title = 'Untitled'
        
        # Extract main content
        # Try multiple selectors for content area
        content_selectors = [
            '#main-content',
            '.wiki-content',
            '.page-content',
            '.content'
        ]
        
        content_html = ''
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                content_html = str(content_elem)
                break
        
        if not content_html:
            # Fallback to entire body
            body = soup.body
            if body:
                content_html = str(body)
            else:
                content_html = str(soup)
        
        # Extract metadata
        metadata = self._extract_page_metadata(soup)
        
        # Initialize conversion metadata for quality tracking
        conversion_metadata = {
            'status': 'fetched',
            'macros_detected': [],  # HTML export macros may be pre-rendered
            'links_resolved': 0,
            'images_processed': 0,
            'warnings': [
                "HTML export mode: some dynamic content may be static snapshots",
                "Macro metadata may be limited in HTML export"
            ],
            'fetch_timestamp': datetime.utcnow().isoformat()
        }
        
        # Add warning for very minimal content
        if not content_html or len(content_html.strip()) < 50:
            conversion_metadata['warnings'].append("Page has very little or no content")
        
        # Create page model
        page = ConfluencePage(
            id=page_info['id'],
            title=title,
            content=content_html,
            space_key=space_key,
            parent_id=page_info.get('parent_id'),
            url=str(page_file.resolve()),
            metadata=metadata
        )
        
        # Set conversion metadata
        page.conversion_metadata = conversion_metadata
        logger.debug(f"Initialized conversion_metadata for page {page_info['id']}")
        
        # Identify attachments
        attachments = self._identify_attachments(page.id, content_html)
        for attachment in attachments:
            page.add_attachment(attachment)
        
        # Cache the parsed result with file modification time
        if self.cache_manager.enabled:
            self.cache_manager.set(
                page_cache_key,
                {
                    'page_id': page_info['id'],
                    'content': content_html,
                    'metadata': metadata,
                    'file_mtime': current_mtime,
                    'parsed_timestamp': time.time()
                }
            )
            self._cache_stats['misses'] += 1
        
        return page
    
    def _extract_page_metadata(self, soup: Any) -> Dict[str, Any]:
        """
        Extract page metadata from HTML.
        
        Args:
            soup: BeautifulSoup object
            
        Returns:
            Metadata dictionary
        """
        metadata = {
            'author': None,
            'last_modified': None,
            'version': 1,
            'labels': [],
            'content_type': 'page',
            'content_source': 'html_export'
        }
        
        # Try meta tags
        author_meta = soup.find('meta', {'name': 'author'})
        if author_meta and author_meta.get('content'):
            metadata['author'] = author_meta['content']
        
        modified_meta = soup.find('meta', {'name': 'last-modified'})
        if modified_meta and modified_meta.get('content'):
            metadata['last_modified'] = modified_meta['content']
        
        # Try footer or other elements
        if not metadata['last_modified']:
            # Look for date patterns
            date_patterns = [
                r'\d{4}-\d{2}-\d{2}',  # 2023-01-01
                r'\d{2}/\d{2}/\d{4}',  # 01/01/2023
            ]
            
            for pattern in date_patterns:
                match = re.search(pattern, str(soup))
                if match:
                    metadata['last_modified'] = match.group(0)
                    break
        
        return metadata
    
    def _identify_attachments(self, page_id: str, content_html: str) -> List[ConfluenceAttachment]:
        """
        Identify attachments from page content.
        
        Args:
            page_id: Page ID
            content_html: Page HTML content
            
        Returns:
            List of ConfluenceAttachment models
        """
        attachments = []
        
        # Patterns for attachment references
        patterns = [
            fr'/download/attachments/{page_id}/([^"<>\s]+)',
            fr'/download/attachments/\?pageId={page_id}&[^"<>\s]*filename=([^&"<>\s]+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content_html)
            for filename in matches:
                # Unquote filename if needed
                from urllib.parse import unquote
                filename = unquote(filename)
                
                # Build attachment path
                attachment_path = self.html_export_path / 'attachments' / page_id / filename
                
                # Check if file exists
                if attachment_path.exists():
                    file_size = attachment_path.stat().st_size
                    file_url = str(attachment_path.resolve())
                else:
                    # File not found, mark as missing
                    file_size = 0
                    file_url = f"attachment_missing: {filename}"
                    logger.warning(f"Attachment file not found: {attachment_path}")
                
                # Guess media type
                media_type = self._guess_media_type(filename)
                
                attachment = ConfluenceAttachment(
                    id=f"{page_id}_{filename}",
                    title=filename,
                    media_type=media_type,
                    file_size=file_size,
                    download_url=file_url,
                    page_id=page_id
                )
                
                attachments.append(attachment)
        
        # Remove duplicates
        unique_attachments = {}
        for att in attachments:
            unique_attachments[att.title] = att
        
        attachments = list(unique_attachments.values())
        
        logger.debug(f"Identified {len(attachments)} attachments for page {page_id}")
        return attachments
    
    def _guess_media_type(self, filename: str) -> str:
        """
        Guess MIME type from filename extension.
        
        Args:
            filename: Filename to guess type for
            
        Returns:
            MIME type string
        """
        ext_map = {
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.zip': 'application/zip',
            '.txt': 'text/plain',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.html': 'text/html',
            '.css': 'text/css',
            '.js': 'application/javascript',
        }
        
        ext = os.path.splitext(filename.lower())[1]
        return ext_map.get(ext, 'application/octet-stream')
    
    def _build_pages_from_tree(self, page_tree: List[Dict[str, Any]], space_key: str) -> List[ConfluencePage]:
        """
        Build ConfluencePage objects from parsed page tree structure.
        
        Args:
            page_tree: Parsed page tree structure
            space_key: Space key
            
        Returns:
            List of ConfluencePage objects
        """
        pages = []
        
        for page_info in page_tree:
            try:
                page = self._build_page_with_children(page_info, space_key)
                pages.append(page)
            except Exception as e:
                logger.warning(f"Failed to build page '{page_info.get('title')}': {str(e)}")
                continue
        
        return pages
    
    def _build_page_with_children(self, page_info: Dict[str, Any], space_key: str) -> ConfluencePage:
        """
        Recursively build page with children.
        
        Args:
            page_info: Page information dict
            space_key: Space key
            
        Returns:
            ConfluencePage with children populated
        """
        # Find page file
        try:
            page_file = self._find_page_file(page_info['id'], page_info.get('title', ''))
        except FileNotFoundError as e:
            logger.warning(f"Page file not found: {str(e)}, skipping")
            
            # Initialize conversion metadata for placeholder
            conversion_metadata = {
                'status': 'fetched',
                'macros_detected': [],
                'links_resolved': 0,
                'images_processed': 0,
                'warnings': [
                    "File not found: missing page content from export",
                    "HTML export mode: page file missing from filesystem"
                ],
                'fetch_timestamp': datetime.utcnow().isoformat()
            }
            
            # Create placeholder page
            page = ConfluencePage(
                id=page_info['id'],
                title=page_info.get('title', 'Untitled'),
                content=f"<p>Warning: Page file not found. {str(e)}</p>",
                space_key=space_key,
                parent_id=page_info.get('parent_id'),
                url=None
            )
            
            # Set conversion metadata
            page.conversion_metadata = conversion_metadata
            logger.debug(f"Initialized conversion_metadata for missing page {page_info['id']}")
            
            # Process children
            if 'children' in page_info:
                for child_info in page_info['children']:
                    child = self._build_page_with_children(child_info, space_key)
                    page.add_child(child)
            
            return page
        
        # Parse page file
        page = self._parse_page_file(page_file, page_info, space_key)
        
        # Process children
        if 'children' in page_info:
            for child_info in page_info['children']:
                child = self._build_page_with_children(child_info, space_key)
                page.add_child(child)
        
        return page
    
    def _find_page_in_tree(self, page_id: str, page_tree: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Find page info in tree structure by ID.
        
        Args:
            page_id: Page ID to find
            page_tree: Page tree structure
            
        Returns:
            Page info dict or None
        """
        for page_info in page_tree:
            if page_info['id'] == page_id:
                return page_info
            
            # Search children
            if 'children' in page_info:
                child_result = self._find_page_in_tree(page_id, page_info['children'])
                if child_result:
                    return child_result
        
        return None
