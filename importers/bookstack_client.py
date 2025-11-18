"""
BookStack REST API client for Confluence markdown migrator.

This module provides a client wrapper for the BookStack REST API,
handling authentication, retries, rate limiting, and common operations
for Shelves, Books, Chapters, Pages, and image uploads.
"""

import logging
import time
from typing import Dict, Any, Optional, List
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class BookStackClient:
    """BookStack REST API client with retry logic and rate limiting."""
    
    DEFAULT_TIMEOUT = 30
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_BACKOFF = 0.5
    DEFAULT_RATE_LIMIT = 0.0
    
    def __init__(
        self,
        base_url: str,
        token_id: str,
        token_secret: str,
        verify_ssl: bool = True,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_factor: float = DEFAULT_RETRY_BACKOFF,
        rate_limit: float = DEFAULT_RATE_LIMIT
    ):
        """
        Initialize BookStack client.
        
        Args:
            base_url: BookStack instance base URL
            token_id: API token ID
            token_secret: API token secret
            verify_ssl: Whether to verify SSL certificates
            timeout: Request timeout in seconds
            max_retries: Maximum number of retries for failed requests
            retry_backoff_factor: Backoff factor for retries
            rate_limit: Minimum seconds between requests (0 = no limit)
        """
        self.base_url = base_url.rstrip('/')
        self.token_id = token_id
        self.token_secret = token_secret
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.rate_limit = rate_limit
        self._last_request_time = 0.0
        
        # Setup session with retry strategy
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Token {token_id}:{token_secret}',
            'Accept': 'application/json'
        })
        
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=retry_backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        logger.debug(f"Initialized BookStack client for {base_url}")
    
    def _handle_rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        if self.rate_limit <= 0:
            return
            
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < self.rate_limit:
            sleep_time = self.rate_limit - time_since_last
            logger.debug(f"Rate limiting: sleeping {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self._last_request_time = time.time()
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Make HTTP request with error handling and retries.
        
        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint path
            data: JSON payload for POST/PUT requests
            params: Query parameters
            files: Files for multipart uploads
            
        Returns:
            JSON response as dictionary
            
        Raises:
            requests.RequestException: For HTTP errors
        """
        self._handle_rate_limit()
        
        url = f"{self.base_url}/api{endpoint}"
        
        logger.debug(f"{method} {url}")
        if data:
            logger.debug(f"Payload: {data}")
        
        try:
            # Build request headers conditionally
            request_headers = {}
            if files is None:
                # Add Content-Type: application/json for JSON requests
                request_headers['Content-Type'] = 'application/json'
            # else let requests library set multipart/form-data with boundary
            
            response = self.session.request(
                method=method,
                url=url,
                headers=request_headers if request_headers else None,
                params=params,
                json=json,
                data=data,
                files=files,
                verify=self.verify_ssl,
                timeout=self.timeout
            )
            
            logger.debug(f"Response status: {response.status_code}")
            
            # Handle rate limiting (429) with custom backoff
            if response.status_code == 429:
                retry_after = response.headers.get('Retry-After', '1')
                try:
                    wait_time = int(retry_after)
                except ValueError:
                    wait_time = 1
                
                logger.warning(f"Rate limited (429). Retrying after {wait_time}s")
                time.sleep(wait_time)
                return self._make_request(method, endpoint, params=params, json=json, data=data, files=files)
            
            response.raise_for_status()
            
            # Return JSON for successful requests
            if response.status_code in [200, 201]:
                return response.json()
            elif response.status_code == 204:
                return {}
            else:
                return response.json() if response.content else {}
                
        except requests.RequestException as e:
            logger.error(f"Request failed: {method} {url} - {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise
    
    def create_shelf(self, name: str, description: str = "") -> Dict[str, Any]:
        """Create a new shelf."""
        data = {'name': name, 'description': description}
        return self._make_request('POST', '/shelves', json=data)
    
    def get_shelf(self, shelf_id: int) -> Dict[str, Any]:
        """Get shelf by ID."""
        return self._make_request('GET', f'/shelves/{shelf_id}')
    
    def list_shelves(self) -> List[Dict[str, Any]]:
        """List all shelves."""
        response = self._make_request('GET', '/shelves')
        return response.get('data', [])
    
    def update_shelf(self, shelf_id: int, **kwargs) -> Dict[str, Any]:
        """Update shelf properties."""
        return self._make_request('PUT', f'/shelves/{shelf_id}', data=kwargs)
    
    def add_book_to_shelf(self, book_id: int, shelf_id: int) -> Dict[str, Any]:
        """Add a book to a shelf."""
        data = {'shelf_id': shelf_id}
        return self._make_request('PUT', f'/books/{book_id}', json=data)
    
    def create_book(self, name: str, description: str = "") -> Dict[str, Any]:
        """Create a new book."""
        data = {'name': name, 'description': description}
        return self._make_request('POST', '/books', json=data)
    
    def get_book(self, book_id: int) -> Dict[str, Any]:
        """Get book by ID."""
        return self._make_request('GET', f'/books/{book_id}')
    
    def update_book(self, book_id: int, **kwargs) -> Dict[str, Any]:
        """Update book properties."""
        return self._make_request('PUT', f'/books/{book_id}', data=kwargs)
    
    def create_chapter(self, book_id: int, name: str, description: str = "", priority: int = 0) -> Dict[str, Any]:
        """Create a new chapter in a book."""
        data = {
            'book_id': book_id,
            'name': name,
            'description': description,
            'priority': priority
        }
        return self._make_request('POST', '/chapters', json=data)
    
    def get_chapter(self, chapter_id: int) -> Dict[str, Any]:
        """Get chapter by ID."""
        return self._make_request('GET', f'/chapters/{chapter_id}')
    
    def update_chapter(self, chapter_id: int, **kwargs) -> Dict[str, Any]:
        """Update chapter properties."""
        return self._make_request('PUT', f'/chapters/{chapter_id}', data=kwargs)
    
    def create_page(
        self,
        book_id: int,
        name: str,
        html: str,
        chapter_id: Optional[int] = None,
        priority: int = 0
    ) -> Dict[str, Any]:
        """Create a new page in a book or chapter."""
        data = {
            'book_id': book_id,
            'name': name,
            'html': html,
            'priority': priority
        }
        if chapter_id is not None:
            data['chapter_id'] = chapter_id
        
        return self._make_request('POST', '/pages', json=data)
    
    def get_page(self, page_id: int) -> Dict[str, Any]:
        """Get page by ID."""
        return self._make_request('GET', f'/pages/{page_id}')
    
    def update_page(self, page_id: int, **kwargs) -> Dict[str, Any]:
        """Update page properties."""
        return self._make_request('PUT', f'/pages/{page_id}', data=kwargs)
    
    def upload_image(self, image_name: str, image_data: bytes, uploaded_to: int) -> Dict[str, Any]:
        """
        Upload an image as an attachment to a page.
        
        Args:
            image_name: Name of the image file
            image_data: Binary image data
            uploaded_to: ID of the page to attach image to
            
        Returns:
            Upload response with image details
        """
        files = {
            'file': (image_name, image_data, 'image/*')
        }
        data = {
            'name': image_name,
            'uploaded_to': uploaded_to
        }
        
        return self._make_request('POST', '/attachments', files=files, data=data)
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> 'BookStackClient':
        """
        Create client from configuration dictionary.
        
        Args:
            config: Configuration dict with 'bookstack' section
            
        Returns:
            Configured BookStackClient instance
        """
        bookstack_config = config.get('bookstack', {})
        
        # Extract advanced configuration with defaults
        advanced_config = config.get('advanced', {})
        
        return cls(
            base_url=bookstack_config.get('base_url'),
            token_id=bookstack_config.get('token_id'),
            token_secret=bookstack_config.get('token_secret'),
            verify_ssl=advanced_config.get('verify_ssl', True),
            timeout=advanced_config.get('request_timeout', cls.DEFAULT_TIMEOUT),
            max_retries=advanced_config.get('max_retries', cls.DEFAULT_MAX_RETRIES),
            retry_backoff_factor=advanced_config.get('retry_backoff_factor', cls.DEFAULT_RETRY_BACKOFF),
            rate_limit=advanced_config.get('rate_limit', cls.DEFAULT_RATE_LIMIT)
        )