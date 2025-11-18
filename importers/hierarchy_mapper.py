"""
Hierarchy Mapper for Confluence to Wiki.js Path Generation.

Maps Confluence's hierarchical page structure (spaces with parent/child pages) 
to Wiki.js flat path format (e.g., /space-key/parent-page/child-page).
"""

import logging
import re
from typing import Dict, List, Optional, Any

from ..models import ConfluencePage, ConfluenceSpace, DocumentationTree


# Constants
DEFAULT_PATH_SEPARATOR = "/"
DEFAULT_MAX_PATH_LENGTH = 255
INVALID_PATH_CHARS = {' ', '\t', '\n', '\r', '#', '?', '&', '%', '+', '\\', '"', "'", '<', '>', '|', '*'}


class ConfluenceHierarchyMapper:
    """
    Utility class for converting Confluence hierarchies to Wiki.js paths.
    
    Adapts path generation logic from TUI's WikiJsPreviewMapper for actual imports.
    """

    def __init__(
        self,
        path_separator: str = DEFAULT_PATH_SEPARATOR,
        max_path_length: int = DEFAULT_MAX_PATH_LENGTH,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the hierarchy mapper.

        Args:
            path_separator: Separator for path components (default: "/")
            max_path_length: Maximum path length (default: 255)
            logger: Optional logger instance
        """
        self.path_separator = path_separator
        self.max_path_length = max_path_length
        self.logger = logger or logging.getLogger('confluence_markdown_migrator.importers.hierarchy_mapper')

    def generate_path(
        self,
        page: ConfluencePage,
        space: ConfluenceSpace,
        tree: DocumentationTree,
        include_space: bool = True
    ) -> str:
        """
        Build hierarchical path for page (e.g., /space-key/parent-page/child-page).

        Args:
            page: Confluence page to generate path for
            space: Confluence space containing the page
            tree: DocumentationTree for parent lookups
            include_space: Whether to include space key in path

        Returns:
            Wiki.js compatible path string
        """
        components = []

        # Start with space if requested
        if include_space:
            components.append(self._sanitize_path_component(space.key))

        # Build ancestor chain by walking up parent hierarchy
        ancestors = []
        current = page

        while current.parent_id:
            parent = tree.get_page_by_id(current.parent_id)
            if not parent:
                break
            ancestors.insert(0, parent)  # Insert at beginning to maintain order
            current = parent

        # Add ancestor titles
        for ancestor in ancestors:
            components.append(self._sanitize_path_component(ancestor.title))

        # Add current page
        components.append(self._sanitize_path_component(page.title))

        # Join with slashes
        path = self.path_separator + self.path_separator.join(components)

        # Validate path length
        if len(path) > self.max_path_length:
            self.logger.warning(
                f"Generated path exceeds max length ({len(path)} > {self.max_path_length}): {path}. "
                f"Consider using shorter page titles."
            )

        return path

    def validate_path(self, path: str) -> bool:
        """
        Validate path format for Wiki.js compatibility.

        Args:
            path: Path to validate

        Returns:
            True if valid, False otherwise
        """
        if not path:
            return False

        if not path.startswith(self.path_separator):
            return False

        if len(path) > self.max_path_length:
            return False

        # Check for invalid characters
        for char in INVALID_PATH_CHARS:
            if char in path:
                return False

        # Check for consecutive separators
        if self.path_separator * 2 in path:
            return False

        return True

    def generate_unique_path(
        self,
        base_path: str,
        wikijs_client,
        max_attempts: int = 10
    ) -> str:
        """
        Generate unique path by appending numeric suffix if conflict exists.

        Args:
            base_path: Original path to base uniqueness on
            wikijs_client: WikiJsClient instance for existence checks
            max_attempts: Maximum attempts to find unique path

        Returns:
            Unique path string
        """
        if not self.validate_path(base_path):
            raise ValueError(f"Invalid base path: {base_path}")

        # Check if base path already exists
        if not wikijs_client.get_page_by_path(base_path):
            return base_path

        # Split path into components
        components = [comp for comp in base_path.strip(self.path_separator).split(self.path_separator) if comp]
        if not components:
            raise ValueError("Invalid base path for unique path generation")

        last_component = components[-1]

        # Try numeric suffixes on the last component only
        for suffix_num in range(2, max_attempts + 1):
            suffixed_last = f"{last_component}-{suffix_num}"
            new_components = components[:-1] + [suffixed_last]
            candidate = self.path_separator + self.path_separator.join(new_components)

            if self.validate_path(candidate) and not wikijs_client.get_page_by_path(candidate):
                self.logger.info(f"Generated unique path: {candidate} (conflict with {base_path})")
                return candidate

        raise ValueError(f"Could not generate unique path after {max_attempts} attempts for: {base_path}")

    def parse_path(self, path: str) -> Optional[Dict[str, Any]]:
        """
        Decompose path into components (space, ancestors, page) for debugging.

        Args:
            path: Path to parse

        Returns:
            Dict with components or None if invalid
        """
        if not self.validate_path(path):
            return None

        # Remove leading separator and split
        parts = path[len(self.path_separator):].split(self.path_separator)

        if not parts:
            return None

        return {
            'space': parts[0] if len(parts) > 0 else None,
            'ancestors': parts[1:-1] if len(parts) > 2 else [],
            'page': parts[-1] if len(parts) > 0 else None,
            'full_path': path
        }

    def _sanitize_path_component(self, title: str) -> str:
        """
        Convert title to URL-safe slug.

        Args:
            title: Title to sanitize

        Returns:
            URL-safe slug string
        """
        if not title:
            return "untitled"

        # Convert to lowercase
        slug = title.lower()

        # Replace spaces with hyphens
        slug = slug.replace(' ', '-')

        # Remove special characters (keep alphanumeric, hyphens, underscores)
        slug = re.sub(r'[^a-z0-9\-_]', '', slug)

        # Remove multiple consecutive hyphens
        slug = re.sub(r'-+', '-', slug)

        # Trim leading/trailing hyphens
        slug = slug.strip('-')

        # Ensure not empty
        if not slug:
            slug = "page"

        # Truncate if too long (reserve space for path)
        max_component_length = 50  # Reasonable limit per component
        if len(slug) > max_component_length:
            slug = slug[:max_component_length]
            # Remove trailing hyphen if created by truncation
            slug = slug.rstrip('-')

        return slug


# Export mapper for easy access
__all__ = ['ConfluenceHierarchyMapper']