"""Abstract base fetcher interface and common functionality."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional

from dateutil.parser import isoparse

from ..models import ConfluenceSpace, DocumentationTree


class FetcherError(Exception):
    """Base exception for fetcher-related errors."""
    pass


class FilterValidationError(FetcherError):
    """Exception for invalid filter parameters."""
    pass


class BaseFetcher(ABC):
    """Abstract base class for Confluence content fetchers."""
    
    def __init__(self, config: Dict[str, Any], logger=None):
        """
        Initialize base fetcher with configuration and logger.
        
        Args:
            config: Configuration dictionary
            logger: Logger instance (optional, uses module logger if not provided)
        """
        self.config = config
        self.logger = logger
        
        # Import logger if not provided
        if not self.logger:
            import logging
            self.logger = logging.getLogger('confluence_markdown_migrator.fetcher')
    
    @abstractmethod
    def fetch_spaces(self, space_keys: Optional[List[str]] = None) -> List[ConfluenceSpace]:
        """
        Fetch Confluence spaces, optionally filtered by keys.
        
        Args:
            space_keys: Optional list of space keys to filter
            
        Returns:
            List of ConfluenceSpace objects (pages not loaded)
        """
        pass
    
    @abstractmethod
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
        pass
    
    @abstractmethod
    def fetch_page_tree(self, page_id: str) -> object:  # Returns ConfluencePage
        """
        Fetch specific page and all descendants recursively.
        
        Args:
            page_id: Confluence page ID
            
        Returns:
            Root ConfluencePage with children populated
        """
        pass
    
    @abstractmethod
    def fetch_page_content(self, page_id: str) -> object:  # Returns ConfluencePage
        """
        Fetch single page content without children.
        
        Args:
            page_id: Confluence page ID
            
        Returns:
            ConfluencePage without children loaded
        """
        pass
    
    @abstractmethod
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
        pass
    
    def _apply_filters(
        self,
        pages: List[object],  # List of ConfluencePage
        filters: Optional[Dict[str, Any]] = None
    ) -> List[object]:
        """
        Apply filters to page list while preserving hierarchy.
        
        Args:
            pages: List of pages to filter
            filters: Dictionary with filter criteria
            
        Returns:
            Filtered list of pages
        """
        if not filters:
            return pages
        
        filtered_pages = []
        
        for page in pages:
            include_page = self._should_include_page(page, filters)
            
            # Apply filters to children recursively
            if page.children:
                page.children = self._apply_filters(page.children, filters)
            
            # Include page if it matches filters or has matching children
            if include_page or page.children:
                filtered_pages.append(page)
        
        return filtered_pages
    
    def _should_include_page(self, page: object, filters: Dict[str, Any]) -> bool:
        """
        Check if page matches filter criteria.
        
        Args:
            page: ConfluencePage to check
            filters: Filter dictionary
            
        Returns:
            True if page should be included
        """
        # Page ID filter
        if 'page_id' in filters and filters['page_id']:
            if page.id == filters['page_id']:
                return True
            # Check if any descendant matches
            for child in page.get_all_descendants():
                if child.id == filters['page_id']:
                    return True
            return False
        
        # Date filter
        if 'since_date' in filters and filters['since_date']:
            since_date = self._parse_date(filters['since_date'])
            if since_date is None:
                return True  # Invalid date filter, include all
            
            # Use last_modified from metadata if available
            last_modified_str = page.metadata.get('last_modified')
            if not last_modified_str:
                return True  # No modification date, include page
            
            try:
                last_modified = self._parse_date(last_modified_str)
                if last_modified and last_modified >= since_date:
                    return True
            except ValueError:
                # Invalid date string, include page
                return True
        
        # No filters or page passes all filters
        return True
    
    def _validate_filters(self, filters: Optional[Dict[str, Any]] = None) -> None:
        """
        Validate filter dictionary structure.
        
        Args:
            filters: Filter dictionary to validate
            
        Raises:
            FilterValidationError: If filters are invalid
        """
        if not filters:
            return
        
        allowed_keys = {'page_id', 'since_date'}
        invalid_keys = set(filters.keys()) - allowed_keys
        
        if invalid_keys:
            raise FilterValidationError(
                f"Invalid filter keys: {invalid_keys}. Allowed: {allowed_keys}"
            )
        
        # Validate since_date format
        if 'since_date' in filters and filters['since_date']:
            since_date = self._parse_date(filters['since_date'])
            if since_date is None:
                raise FilterValidationError(
                    f"Invalid date format for since_date: {filters['since_date']}. "
                    "Must be ISO 8601 format (e.g., 2023-01-01T00:00:00Z)"
                )
    
    def _parse_date(self, date_string: str) -> Optional[datetime]:
        """
        Parse ISO 8601 date string.
        
        Args:
            date_string: ISO 8601 formatted date string
            
        Returns:
            Parsed datetime object, or None if parsing fails
        """
        try:
            # Handle milliseconds if present
            if '.' in date_string:
                # Remove milliseconds beyond 6 digits (Python limitation)
                parts = date_string.split('.')
                if len(parts) > 1 and len(parts[1]) > 6:
                    parts[1] = parts[1][:6]
                    date_string = '.'.join(parts)
            
            return isoparse(date_string)
        except (ValueError, TypeError) as e:
            self.logger.warning(f"Failed to parse date string '{date_string}': {str(e)}")
            return None
    
    def _log_progress(self, message: str, level: str = 'info') -> None:
        """
        Log progress message at specified level.
        
        Args:
            message: Message to log
            level: Log level (debug, info, warning, error)
        """
        log_method = getattr(self.logger, level, self.logger.info)
        log_method(message)