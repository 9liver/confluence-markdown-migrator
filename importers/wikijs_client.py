"""
Wiki.js GraphQL API Client for Confluence to Wiki.js Migration.

Adapted from bookstack_wikijs_sync/wikijs_client.py for the new config structure.
Provides GraphQL operations for creating, updating, and managing Wiki.js pages.
"""

import logging
import time
from typing import Dict, List, Optional, Any

from gql import gql, Client
from gql.transport.requests import RequestsHTTPTransport
from gql.transport.exceptions import (
    TransportServerError,
    TransportQueryError,
    TransportProtocolError
)


logger = logging.getLogger('confluence_markdown_migrator.importers.wikijs_client')


# Constants
DEFAULT_LOCALE = "en"
DEFAULT_EDITOR = "markdown"
DEFAULT_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF = 2.0


class WikiJsApiError(Exception):
    """Custom exception for Wiki.js API errors."""

    def __init__(self, error_code: str, slug: str, message: str):
        """
        Initialize API error.

        Args:
            error_code: Wiki.js error code
            slug: Error slug identifier
            message: Human-readable error message
        """
        self.error_code = error_code
        self.slug = slug
        self.message = message
        super().__init__(f"[{error_code}] {slug}: {message}")

    def __str__(self) -> str:
        """String representation of error."""
        return f"WikiJsApiError(code={self.error_code}, slug={self.slug}, message={self.message})"


class WikiJsConnectionError(Exception):
    """Exception for connection/transport failures."""
    pass


class WikiJsClient:
    """Client for Wiki.js GraphQL API operations."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        verify_ssl: bool = True,
        timeout: int = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff_factor: float = DEFAULT_RETRY_BACKOFF,
        rate_limit: float = 0.0,
        default_locale: str = DEFAULT_LOCALE,
        default_editor: str = DEFAULT_EDITOR
    ):
        """
        Initialize Wiki.js API client.

        Args:
            base_url: Wiki.js instance URL (e.g., https://wiki.example.com)
            api_key: JWT API key from Wiki.js admin panel (API Access section)
            verify_ssl: Enable SSL certificate verification (default: True)
            timeout: HTTP request timeout in seconds (default: 30)
            max_retries: Maximum number of retries for failed requests (default: 3)
            retry_backoff_factor: Backoff factor for retries (default: 2.0)
            rate_limit: Minimum seconds between requests (default: 0.0, disabled)
            default_locale: Default locale for pages (default: "en")
        """
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff_factor = retry_backoff_factor
        self.rate_limit = rate_limit
        self.default_locale = default_locale
        self.default_editor = default_editor
        self._last_request_time = 0.0

        # Create GraphQL transport with Bearer token authentication
        # Note: retries parameter expects an integer, not a Retry object
        self.transport = RequestsHTTPTransport(
            url=f"{self.base_url}/graphql",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            verify=verify_ssl,
            timeout=timeout,
            retries=max_retries
        )

        # Initialize GraphQL client
        self.client = Client(
            transport=self.transport,
            fetch_schema_from_transport=False  # Avoid startup latency
        )

        logger.info(f"Initialized Wiki.js client for {self.base_url} "
                   f"(retries={max_retries}, backoff={retry_backoff_factor}, rate_limit={rate_limit}s, "
                   f"default_editor={default_editor})")

    # ========================================================================
    # Page Query Methods
    # ========================================================================

    def list_pages(
        self,
        limit: int = 100,
        order_by: str = "PATH",
        order_direction: str = "ASC",
        tags: Optional[List[str]] = None,
        locale: Optional[str] = None,
        creator_id: Optional[int] = None,
        author_id: Optional[int] = None,
        fetch_all: bool = False,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List all pages with pagination support.

        IMPORTANT: Wiki.js v2.x GraphQL API Limitation
        -----------------------------------------------
        The Wiki.js GraphQL API does NOT support time-based filtering parameters such as:
        - modifiedAfter / updatedAfter (filter by modification date)
        - createdAfter (filter by creation date)
        - Date range queries

        This is a known limitation of the Wiki.js v2.x API. As a result, all pages must be
        fetched and then filtered client-side based on updatedAt timestamps.

        Args:
            limit: Maximum number of pages to retrieve per query (default: 100)
            order_by: Sort field (PATH, TITLE, CREATED, UPDATED) (default: PATH)
            order_direction: Sort direction (ASC, DESC) (default: ASC)
            tags: Filter by tags (optional)
            locale: Filter by locale (optional)
            creator_id: Filter by creator user ID (optional)
            author_id: Filter by author user ID (optional)
            fetch_all: If True, automatically fetch all pages across multiple requests (default: False)
            offset: Starting offset for pagination (default: 0)

        Returns:
            List of page dictionaries with id, path, title, description, etc.
        """
        query = gql("""
            query ListPages($limit: Int!, $offset: Int!, $orderBy: PageOrderBy, $orderDirection: OrderDirection,
                           $tags: [String], $locale: String, $creatorId: Int, $authorId: Int) {
                pages {
                    list(limit: $limit, offset: $offset, orderBy: $orderBy, orderDirection: $orderDirection,
                         tags: $tags, locale: $locale, creatorId: $creatorId, authorId: $authorId) {
                        id
                        path
                        title
                        description
                        content
                        contentType
                        isPublished
                        isPrivate
                        privateNS
                        publishStartDate
                        publishEndDate
                        tags {
                            tag
                        }
                        editor
                        createdAt
                        updatedAt
                        authorId
                        creatorId
                        locale
                    }
                }
            }
        """)

        variables = {
            "limit": limit,
            "offset": offset,
            "orderBy": order_by,
            "orderDirection": order_direction
        }

        # Add optional filters
        if tags:
            variables["tags"] = tags
        if locale:
            variables["locale"] = locale
        if creator_id:
            variables["creatorId"] = creator_id
        if author_id:
            variables["authorId"] = author_id

        self._apply_rate_limit()

        try:
            result = self.client.execute(query, variable_values=variables)
            pages = result['pages']['list']

            # Recursively fetch remaining pages if fetch_all is enabled
            if fetch_all and len(pages) == limit:
                next_offset = offset + limit
                next_pages = self.list_pages(
                    limit=limit,
                    order_by=order_by,
                    order_direction=order_direction,
                    tags=tags,
                    locale=locale,
                    creator_id=creator_id,
                    author_id=author_id,
                    fetch_all=True,
                    offset=next_offset
                )
                pages.extend(next_pages)

            return pages

        except TransportQueryError as e:
            self._handle_graphql_error(e)
        except (TransportServerError, TransportProtocolError) as e:
            raise WikiJsConnectionError(f"Connection error during list_pages: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in list_pages: {e}", exc_info=True)
            raise

        return []

    def get_page(self, page_id: int, render: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get a single page by ID.

        Args:
            page_id: Wiki.js page ID
            render: Whether to render content to HTML (default: False), not used in query

        Returns:
            Page dictionary with content, metadata, and author info
        """
        query = gql("""
            query GetPage($pageId: Int!) {
                pages {
                    single(id: $pageId) {
                        id
                        path
                        title
                        description
                        content
                        contentType
                        isPublished
                        isPrivate
                        privateNS
                        publishStartDate
                        publishEndDate
                        tags {
                            tag
                        }
                        editor
                        createdAt
                        updatedAt
                        authorId
                        creatorId
                        locale
                    }
                }
            }
        """)

        variables = {"pageId": page_id}

        self._apply_rate_limit()

        try:
            result = self.client.execute(query, variable_values=variables)
            page = result['pages']['single']
            return page if page else None
        except TransportQueryError as e:
            self._handle_graphql_error(e)
        except (TransportServerError, TransportProtocolError) as e:
            raise WikiJsConnectionError(f"Connection error during get_page: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in get_page: {e}", exc_info=True)
            raise

        return None

    def get_page_by_path(self, path: str, locale: Optional[str] = None, render: bool = False) -> Optional[Dict[str, Any]]:
        """
        Get a page by its path.

        Args:
            path: Page path (e.g., "/docs/example")
            locale: Locale filter (optional)
            render: Whether to render content to HTML (default: False), not used in query

        Returns:
            Page dictionary or None if not found
        """
        query = gql("""
            query GetPageByPath($path: String!, $locale: String!) {
                pages {
                    singleByPath(path: $path, locale: $locale) {
                        id
                        path
                        title
                        description
                        content
                        contentType
                        isPublished
                        isPrivate
                        privateNS
                        publishStartDate
                        publishEndDate
                        tags {
                            tag
                        }
                        editor
                        createdAt
                        updatedAt
                        authorId
                        creatorId
                        locale
                    }
                }
            }
        """)

        variables = {
            "path": path,
            "locale": locale or self.default_locale
        }

        self._apply_rate_limit()

        try:
            result = self.client.execute(query, variable_values=variables)
            page = result['pages']['singleByPath']
            return page if page else None
        except TransportQueryError as e:
            # singleByPath returns an error for not found pages
            error_str = str(e).lower()
            if "not found" in error_str or "does not exist" in error_str:
                return None
            self._handle_graphql_error(e)
        except (TransportServerError, TransportProtocolError) as e:
            raise WikiJsConnectionError(f"Connection error during get_page_by_path: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in get_page_by_path: {e}", exc_info=True)
            raise

        return None

    # ========================================================================
    # Page Mutation Methods
    # ========================================================================

    def create_page(
        self,
        path: str,
        title: str,
        content: str,
        description: str = "",
        editor: str = DEFAULT_EDITOR,
        is_published: bool = True,
        is_private: bool = False,
        private_ns: Optional[str] = None,
        locale: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a new page.

        Args:
            path: Page path (e.g., "/confluence/space/page")
            title: Page title
            content: Page content in markdown
            description: Optional description
            editor: Editor type (default: markdown)
            is_published: Whether page is published (default: True)
            is_private: Whether page is private (default: False)
            private_ns: Private namespace (optional)
            locale: Locale (optional, defaults to instance default)
            tags: List of tags (optional)

        Returns:
            Created page dictionary with id, path, title
        """
        mutation = gql("""
            mutation CreatePage($content: String!, $description: String!, $editor: String!, $isPublished: Boolean!,
                               $isPrivate: Boolean!, $locale: String!, $path: String!,
                               $publishEndDate: Date, $publishStartDate: Date, $tags: [String]!, $title: String!) {
                pages {
                    create(content: $content, description: $description, editor: $editor, isPublished: $isPublished,
                          isPrivate: $isPrivate, locale: $locale, path: $path,
                          publishEndDate: $publishEndDate, publishStartDate: $publishStartDate, tags: $tags, title: $title) {
                        responseResult {
                            succeeded
                            errorCode
                            slug
                            message
                        }
                        page {
                            id
                            path
                            title
                        }
                    }
                }
            }
        """)

        variables = {
            "path": path,
            "title": title,
            "content": content,
            "description": description,
            "editor": editor,
            "isPublished": is_published,
            "isPrivate": is_private,
            "locale": locale or self.default_locale,
            "tags": tags or []
        }

        self._apply_rate_limit()

        try:
            result = self.client.execute(mutation, variable_values=variables)
            create_result = result['pages']['create']

            response_result = create_result['responseResult']
            if not response_result['succeeded']:
                raise WikiJsApiError(
                    error_code=response_result.get('errorCode', 'UNKNOWN'),
                    slug=response_result.get('slug', 'unknown_error'),
                    message=response_result.get('message', 'Unknown error creating page')
                )

            return create_result['page']

        except TransportQueryError as e:
            self._handle_graphql_error(e)
        except (TransportServerError, TransportProtocolError) as e:
            raise WikiJsConnectionError(f"Connection error during create_page: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in create_page: {e}", exc_info=True)
            raise

        return None

    def update_page(
        self,
        page_id: int,
        content: Optional[str] = None,
        title: Optional[str] = None,
        description: Optional[str] = None,
        editor: Optional[str] = None,
        is_published: Optional[bool] = None,
        is_private: Optional[bool] = None,
        private_ns: Optional[str] = None,
        locale: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Update an existing page.

        Args:
            page_id: Wiki.js page ID
            content: Updated content (optional)
            title: Updated title (optional)
            description: Updated description (optional)
            editor: Editor type (optional)
            is_published: Published status (optional)
            is_private: Private status (optional)
            private_ns: Private namespace (optional)
            locale: Locale (optional)
            tags: Updated tags (optional)

        Returns:
            Updated page dictionary
        """
        mutation = gql("""
            mutation UpdatePage($id: Int!, $content: String, $description: String, $editor: String,
                               $isPublished: Boolean, $isPrivate: Boolean, $locale: String,
                               $publishEndDate: Date, $publishStartDate: Date,
                               $tags: [String], $title: String) {
                pages {
                    update(id: $id, content: $content, description: $description, editor: $editor,
                          isPublished: $isPublished, isPrivate: $isPrivate, locale: $locale,
                          publishEndDate: $publishEndDate,
                          publishStartDate: $publishStartDate, tags: $tags, title: $title) {
                        responseResult {
                            succeeded
                            errorCode
                            slug
                            message
                        }
                        page {
                            id
                            path
                            title
                            description
                            content
                            contentType
                            isPublished
                            isPrivate
                            publishStartDate
                            publishEndDate
                            tags {
                                tag
                            }
                            editor
                            createdAt
                            updatedAt
                            authorId
                            creatorId
                            locale
                        }
                    }
                }
            }
        """)

        variables = {"id": page_id}
        if content is not None:
            variables["content"] = content
        if title is not None:
            variables["title"] = title
        if description is not None:
            variables["description"] = description
        if editor is not None:
            variables["editor"] = editor
        if is_published is not None:
            variables["isPublished"] = is_published
        if is_private is not None:
            variables["isPrivate"] = is_private
        if locale is not None:
            variables["locale"] = locale
        if tags is not None:
            variables["tags"] = tags

        self._apply_rate_limit()

        try:
            result = self.client.execute(mutation, variable_values=variables)
            update_result = result['pages']['update']

            response_result = update_result['responseResult']
            if not response_result['succeeded']:
                raise WikiJsApiError(
                    error_code=response_result.get('errorCode', 'UNKNOWN'),
                    slug=response_result.get('slug', 'unknown_error'),
                    message=response_result.get('message', 'Unknown error updating page')
                )

            return update_result['page']

        except TransportQueryError as e:
            self._handle_graphql_error(e)
        except (TransportServerError, TransportProtocolError) as e:
            raise WikiJsConnectionError(f"Connection error during update_page: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in update_page: {e}", exc_info=True)
            raise

        return None

    def delete_page(self, page_id: int) -> bool:
        """
        Delete a page.

        Args:
            page_id: Wiki.js page ID

        Returns:
            True if successful, False otherwise
        """
        mutation = gql("""
            mutation DeletePage($id: Int!) {
                pages {
                    delete(id: $id) {
                        responseResult {
                            succeeded
                            errorCode
                            slug
                            message
                        }
                    }
                }
            }
        """)

        variables = {"id": page_id}

        self._apply_rate_limit()

        try:
            result = self.client.execute(mutation, variable_values=variables)
            delete_result = result['pages']['delete']

            response_result = delete_result['responseResult']
            if not response_result['succeeded']:
                raise WikiJsApiError(
                    error_code=response_result.get('errorCode', 'UNKNOWN'),
                    slug=response_result.get('slug', 'unknown_error'),
                    message=response_result.get('message', 'Unknown error deleting page')
                )

            return True

        except TransportQueryError as e:
            self._handle_graphql_error(e)
        except (TransportServerError, TransportProtocolError) as e:
            raise WikiJsConnectionError(f"Connection error during delete_page: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in delete_page: {e}", exc_info=True)
            raise

        return False

    # ========================================================================
    # Internal Helper Methods
    # ========================================================================

    def _apply_rate_limit(self):
        """Apply rate limiting between requests."""
        if self.rate_limit <= 0:
            return

        current_time = time.time()
        time_since_last = current_time - self._last_request_time

        if time_since_last < self.rate_limit:
            sleep_duration = self.rate_limit - time_since_last
            logger.debug(f"Rate limiting: sleeping {sleep_duration:.2f}s")
            time.sleep(sleep_duration)

        self._last_request_time = time.time()

    def _handle_graphql_error(self, error: TransportQueryError):
        """Handle GraphQL errors and convert to meaningful exceptions."""
        errors = getattr(error, 'errors', None)
        if errors and isinstance(errors, list):
            for err in errors:
                message = err.get('message', str(error))
                extensions = err.get('extensions', {})
                code = extensions.get('code', 'GRAPHQL_ERROR')

                # Extract Wiki.js specific error info
                error_code = extensions.get('error', {}).get('code', code)
                slug = extensions.get('error', {}).get('slug', 'unknown_error')
                error_message = extensions.get('error', {}).get('message', message)

                logger.error(f"Wiki.js GraphQL Error: {error_code} - {slug}: {error_message}")

                raise WikiJsApiError(error_code, slug, error_message)

        # Fallback for non-standard errors
        raise WikiJsApiError("GRAPHQL_ERROR", "unknown_error", str(error))

    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> 'WikiJsClient':
        """
        Initialize Wiki.js client from configuration dictionary.

        Args:
            config: Configuration dictionary with wikijs and advanced settings

        Returns:
            WikiJsClient instance
        """
        wikijs_config = config.get('wikijs', {})
        advanced_config = config.get('advanced', {})

        return cls(
            base_url=wikijs_config.get('base_url'),
            api_key=wikijs_config.get('api_key'),
            verify_ssl=wikijs_config.get('verify_ssl', True),
            timeout=advanced_config.get('request_timeout', DEFAULT_TIMEOUT),
            max_retries=advanced_config.get('max_retries', DEFAULT_MAX_RETRIES),
            retry_backoff_factor=advanced_config.get('retry_backoff_factor', DEFAULT_RETRY_BACKOFF),
            rate_limit=advanced_config.get('rate_limit', 0),
            default_locale=wikijs_config.get('default_locale', DEFAULT_LOCALE),
            default_editor=wikijs_config.get('default_editor', DEFAULT_EDITOR)
        )