"""Enhanced Confluence REST API client with robust error handling and retry logic."""

import json
import logging
import time
import warnings
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin, urlparse

import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger('confluence_markdown_migrator.client')


class ConfluenceClient:
    """Enhanced Confluence REST API client with authentication, retry logic, and error handling."""
    
    def __init__(
        self,
        base_url: str,
        auth_type: str = 'basic',
        username: Optional[str] = None,
        password: Optional[str] = None,
        api_token: Optional[str] = None,
        verify_ssl: bool = True,
        timeout: int = 30,
        max_retries: int = 3,
        retry_backoff_factor: float = 2.0,
        rate_limit: float = 0.0
    ):
        """
        Initialize Confluence client with proper authentication and retry configuration.
        
        Args:
            base_url: Confluence base URL (e.g., "https://confluence.example.com")
            auth_type: "basic" or "bearer" authentication
            username: Username for basic auth
            password: Password for basic auth
            api_token: API token for bearer auth (Confluence Cloud)
            verify_ssl: Whether to verify SSL certificates
            timeout: HTTP request timeout in seconds
            max_retries: Maximum retry attempts for transient errors
            retry_backoff_factor: Exponential backoff factor
            rate_limit: Minimum seconds between requests (0.0 = no rate limiting)
        """
        self.base_url = base_url.rstrip('/')
        self.auth_type = auth_type
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_factor = retry_backoff_factor
        self.rate_limit = rate_limit
        self.last_request_time = 0.0
        
        # Initialize session with authentication
        self.session = requests.Session()
        
        if auth_type == 'basic':
            if not username or not password:
                raise ValueError("Basic auth requires username and password")
            self.session.auth = (username, password)
            logger.info(f"Initialized Confluence client with Basic auth for {base_url}")
        elif auth_type == 'bearer':
            if not api_token:
                raise ValueError("Bearer auth requires api_token")
            self.session.headers['Authorization'] = f'Bearer {api_token}'
            logger.info(f"Initialized Confluence client with Bearer auth for {base_url}")
        else:
            raise ValueError(f"Unsupported auth_type: {auth_type}")
        
        # Configure SSL verification
        self.session.verify = verify_ssl
        if not verify_ssl:
            logger.warning("SSL verification disabled - this is insecure!")
            # Suppress urllib3 warnings about unverified HTTPS requests
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Configure retry strategy for GET requests
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=retry_backoff_factor,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        # Mount adapter with retry strategy
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        logger.debug(f"Client configured with timeout={timeout}s, max_retries={max_retries}, "
                    f"backoff_factor={retry_backoff_factor}, rate_limit={rate_limit}s")
    
    def _enforce_rate_limit(self) -> None:
        """Enforce rate limiting if configured."""
        if self.rate_limit <= 0:
            return
        
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.rate_limit:
            sleep_time = self.rate_limit - time_since_last
            logger.warning(f"Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        full_url: Optional[str] = None,
        expected_status: Optional[int] = 200,
        **kwargs
    ) -> requests.Response:
        """
        Make HTTP request to Confluence API with rate limiting and error handling.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path (e.g., "/rest/api/space")
            full_url: Optional full URL (overrides base_url + endpoint)
            expected_status: Expected success status code
            **kwargs: Additional arguments for requests
            
        Returns:
            Response object
            
        Raises:
            requests.exceptions.HTTPError: For HTTP errors
            requests.exceptions.Timeout: For timeout errors
            requests.exceptions.RequestException: For other request errors
        """
        self._enforce_rate_limit()
        
        url = full_url if full_url else urljoin(self.base_url, endpoint.lstrip('/'))
        
        start_time = time.time()
        logger.debug(f"API Request: {method} {url}")
        
        try:
            response = self.session.request(method, url, timeout=self.timeout, **kwargs)
            elapsed = time.time() - start_time
            
            # Log response details
            logger.debug(f"API Response: {response.status_code} {url} ({elapsed:.3f}s)")
            
            # Handle rate limiting (429) with retry loop
            retry_count = 0
            max_retries = self.max_retries
            while response.status_code == 429 and retry_count < max_retries:
                retry_after = response.headers.get('Retry-After', '1')
                try:
                    wait_time = int(retry_after)
                except ValueError:
                    wait_time = 1
                
                logger.warning(f"Rate limited (429): attempt {retry_count + 1}/{max_retries}, "
                             f"waiting {wait_time}s before retry")
                
                # Close response before retry to avoid connection issues
                response.close()
                
                # Retry after delay
                time.sleep(wait_time)
                
                # Make the request again
                retry_count += 1
                response = self.session.request(method, url, timeout=self.timeout, **kwargs)
                logger.debug(f"Retry Response ({retry_count}/{max_retries}): {response.status_code} {url}")
            
            # If still 429 after all retries, let it proceed to raise_for_status()
            if response.status_code == 429 and retry_count >= max_retries:
                logger.error(f"Rate limit exceeded after {max_retries} attempts: {url}")
            
            # Raise for other HTTP errors
            if expected_status and response.status_code != expected_status:
                # Try to extract error details from JSON response
                error_details = ""
                try:
                    error_json = response.json()
                    if 'message' in error_json:
                        error_details = f" - {error_json['message']}"
                    elif 'error' in error_json:
                        error_details = f" - {error_json['error']}"
                except (ValueError, KeyError):
                    # Not JSON or no error message
                    pass
                
                response.raise_for_status()
            
            return response
            
        except requests.exceptions.Timeout as e:
            logger.error(f"Request timeout after {self.timeout}s: {method} {url}")
            raise
            
        except requests.exceptions.HTTPError as e:
            # Log HTTP error details
            status_code = e.response.status_code if e.response else "unknown"
            logger.error(f"HTTP Error {status_code}: {method} {url}")
            
            # Extract error message if available
            if e.response is not None:
                try:
                    error_data = e.response.json()
                    logger.error(f"Error details: {json.dumps(error_data, indent=2)}")
                except ValueError:
                    logger.error(f"Error response: {e.response.text[:500]}")
            
            raise
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {method} {url} - {str(e)}")
            raise
        
        finally:
            # Ensure request time is updated even on errors
            self.last_request_time = time.time()
    
    def get_spaces(self, limit: int = 500) -> List[Dict[str, Any]]:
        """
        Fetch all Confluence spaces with pagination.
        
        Args:
            limit: Number of spaces per page
            
        Returns:
            List of space dictionaries
            
        Raises:
            requests.exceptions.RequestException: For API errors
        """
        spaces = []
        start = 0
        
        while True:
            params = {
                'limit': limit,
                'start': start,
                'type': ['global', 'personal']  # Include both global and personal spaces
            }
            
            response = self._make_request('GET', '/rest/api/space', params=params)
            data = response.json()
            
            spaces.extend(data['results'])
            
            if 'next' not in data.get('_links', {}):
                break
            
            start += limit
            logger.debug(f"Fetched {len(spaces)} spaces so far...")
        
        logger.info(f"Fetched {len(spaces)} total spaces")
        return spaces
    
    def get_space_content(self, space_key: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get top-level pages in a space with full content.
        
        This method first fetches a list of page IDs, then fetches each page individually
        to ensure full body content is retrieved.
        
        Args:
            space_key: Confluence space key
            limit: Number of pages per page
            
        Returns:
            List of page dictionaries with full content
        """
        logger.info(f"Fetching pages with full content for space '{space_key}'")
        
        # Step 1: Get page list (IDs only)
        page_list = []
        start = 0
        last_log_time = time.time()
        
        while True:
            params = {
                'spaceKey': space_key,
                'limit': limit,
                'start': start
            }
            
            response = self._make_request('GET', '/rest/api/content', params=params)
            data = response.json()
            
            page_list.extend(data['results'])
            
            # Log progress
            current_time = time.time()
            if len(page_list) % 500 == 0 or (current_time - last_log_time) > 10:
                logger.info(f"Discovered {len(page_list)} pages so far in space '{space_key}'...")
                last_log_time = current_time
            
            if 'next' not in data.get('_links', {}):
                break
            
            start += limit
        
        logger.info(f"Found {len(page_list)} pages in space '{space_key}' - fetching full content")
        
        # Step 2: Fetch each page individually with full expansions
        pages_with_content = []
        for idx, page_info in enumerate(page_list):
            page_id = page_info['id']
            try:
                # Fetch full page content with expansions
                expand_fields = ['body.export_view', 'body.view', 'ancestors', 'space', 'version', 'metadata.labels', 'history']
                full_page = self.get_page(page_id, expand=expand_fields)
                pages_with_content.append(full_page)
                
                # Log progress every 50 pages
                if (idx + 1) % 50 == 0:
                    logger.info(f"Retrieved full content for {idx + 1}/{len(page_list)} pages")
                    
            except Exception as e:
                logger.warning(f"Failed to fetch page {page_id}: {str(e)} - skipping")
        
        logger.info(f"Successfully fetched {len(pages_with_content)} pages with full content")
        return pages_with_content
    
    def get_page(
        self,
        page_id: str,
        expand: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Fetch single page with specified expansions.
        
        Args:
            page_id: Confluence page ID
            expand: List of expansions (e.g., ['body.export_view', 'ancestors', 'version'])
            
        Returns:
            Page dictionary with expanded fields
            
        Raises:
            requests.exceptions.HTTPError: For 404 or other HTTP errors
        """
        params = {}
        if expand:
            params['expand'] = ','.join(expand)
        
        response = self._make_request(
            'GET',
            f'/rest/api/content/{page_id}',
            params=params
        )
        
        return response.json()
    
    def get_page_children(self, page_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get child pages of a specific page.
        
        Args:
            page_id: Parent page ID
            limit: Number of children per page
            
        Returns:
            List of child page dictionaries
        """
        children = []
        start = 0
        
        while True:
            params = {
                'limit': limit,
                'start': start
            }
            
            response = self._make_request(
                'GET',
                f'/rest/api/content/{page_id}/child/page',
                params=params
            )
            data = response.json()
            
            children.extend(data['results'])
            
            if 'next' not in data.get('_links', {}):
                break
            
            start += limit
        
        logger.debug(f"Fetched {len(children)} children for page {page_id}")
        return children
    
    def get_attachments(self, page_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get attachments of a specific page.
        
        Args:
            page_id: Page ID
            limit: Number of attachments per page
            
        Returns:
            List of attachment dictionaries
        """
        attachments = []
        start = 0
        
        while True:
            params = {
                'limit': limit,
                'start': start
            }
            
            response = self._make_request(
                'GET',
                f'/rest/api/content/{page_id}/child/attachment',
                params=params
            )
            
            data = response.json()
            attachments.extend(data['results'])
            
            if 'next' not in data.get('_links', {}):
                break
            
            start += limit
        
        logger.debug(f"Fetched {len(attachments)} attachments for page {page_id}")
        return attachments
    
    def download_attachment(self, download_url: str) -> bytes:
        """
        Download attachment from Confluence.
        
        Args:
            download_url: Full URL to download attachment
            
        Returns:
            Attachment binary data
            
        Raises:
            requests.exceptions.HTTPError: For API errors
            requests.exceptions.Timeout: For timeout errors
        """
        return self._download_with_retry(download_url)
    
    def _download_with_retry(
        self,
        url: str,
        expected_status: int = 200
    ) -> bytes:
        """
        Download file with exponential backoff retry logic.
        
        Args:
            url: URL to download from
            expected_status: Expected HTTP status code
            
        Returns:
            Downloaded bytes
            
        Raises:
            requests.exceptions.HTTPError: For HTTP errors after retries
            requests.exceptions.RequestException: For other errors after retries
        """
        max_attempts = self.max_retries + 1  # +1 for initial attempt
        
        for attempt in range(max_attempts):
            try:
                response = self._make_request('GET', '', full_url=url, expected_status=expected_status)
                return response.content
                
            except requests.exceptions.RequestException as e:
                # Check if this is a transient error worth retrying
                is_transient = self._is_transient_error(e)
                
                if not is_transient or attempt >= self.max_retries:
                    # Permanent error or max retries reached
                    if attempt > 0:
                        logger.error(f"Download failed after {attempt + 1} attempts: {url}")
                    raise
                
                # Calculate backoff time
                wait_time = self.retry_backoff_factor * (2 ** attempt)
                logger.warning(
                    f"Download attempt {attempt + 1} failed ({str(e)}), "
                    f"retrying in {wait_time:.1f}s: {url}"
                )
                
                time.sleep(wait_time)
        
        # This should not be reached due to raise on max retries, but just in case
        raise requests.exceptions.RequestException(f"Download failed after {max_attempts} attempts: {url}")
    
    def _is_transient_error(self, exception: Exception) -> bool:
        """
        Determine if an error is transient (should retry) or permanent (fail fast).
        
        Args:
            exception: The exception to check
            
        Returns:
            True if error is transient, False if permanent
        """
        # Check for HTTP errors with specific status codes
        if hasattr(exception, 'response') and exception.response is not None:
            status_code = exception.response.status_code
            
            # Transient errors (retry)
            if status_code in [429, 500, 502, 503, 504]:
                return True
            
            # Permanent errors (don't retry)
            if status_code in [401, 403, 404, 400]:
                return False
        
        # Check for timeout errors (transient)
        if isinstance(exception, requests.exceptions.Timeout):
            return True
        
        # Check for connection errors (transient)
        if isinstance(exception, requests.exceptions.ConnectionError):
            return True
        
        # Unknown errors: be conservative and don't retry
        logger.warning(f"Treating error as permanent (no retry): {type(exception).__name__}")
        return False
    
    def search_content(self, cql: str, limit: int = 100, expand: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Search content using Confluence Query Language (CQL).
        
        Args:
            cql: CQL search query
            limit: Number of results per page
            expand: Optional expansions for result items
            
        Returns:
            List of content dictionaries matching search
        """
        results = []
        start = 0
        
        while True:
            params = {
                'cql': cql,
                'limit': limit,
                'start': start
            }
            
            if expand:
                params['expand'] = ','.join(expand)
            
            response = self._make_request(
                'GET',
                '/rest/api/search',
                params=params
            )
            
            data = response.json()
            results.extend(data['results'])
            
            if 'next' not in data.get('_links', {}):
                break
            
            start += limit
        
        logger.info(f"CQL search returned {len(results)} results for query: {cql}")
        return results
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> 'ConfluenceClient':
        """
        Initialize Confluence client from configuration dictionary.
        
        Args:
            config: Configuration dictionary with confluence and advanced settings
            
        Returns:
            ConfluenceClient instance
        """
        confluence_config = config.get('confluence', {})
        advanced_config = config.get('advanced', {})
        
        return cls(
            base_url=confluence_config.get('base_url'),
            auth_type=confluence_config.get('auth_type', 'basic'),
            username=confluence_config.get('username'),
            password=confluence_config.get('password'),
            api_token=confluence_config.get('api_token'),
            verify_ssl=confluence_config.get('verify_ssl', True),
            timeout=advanced_config.get('request_timeout', 30),
            max_retries=advanced_config.get('max_retries', 3),
            retry_backoff_factor=advanced_config.get('retry_backoff_factor', 2.0),
            rate_limit=advanced_config.get('rate_limit', 0.0)
        )
