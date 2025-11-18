"""Link rewriter for updating markdown links and images to relative paths."""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

from models import ConfluenceAttachment, ConfluencePage

logger = logging.getLogger('confluence_markdown_migrator.exporters.link_rewriter')

MAX_CHARS_BETWEEN_BRACKETS = 1000  # Prevent catastrophic backtracking


class LinkRewriter:
    """
    Rewrites markdown links and images to use relative paths for local export.
    
    This rewriter:
    1. Finds markdown links [text](url) and images ![alt](url)
    2. Matches URLs against attachment metadata
    3. Calculates relative paths based on page depth
    4. Updates markdown content with relative paths
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize the link rewriter.
        
        Args:
            logger: Logger instance
        """
        self.logger = logger or logging.getLogger('confluence_markdown_migrator.exporters.link_rewriter')
        
        # Compile regex patterns for markdown links and images
        self.link_pattern = re.compile(
            r'\[([^\]]{1,' + str(MAX_CHARS_BETWEEN_BRACKETS) + r'})\]\(([^\)\s]*)\)'
        )
        self.image_pattern = re.compile(
            r'!\[([^\]]*)\]\(([^\)\s]*)\)'
        )
    
    def rewrite_links(
        self,
        page: ConfluencePage,
        attachment_manager,
        page_depth: int = 0
    ) -> str:
        """
        Rewrite all links and images in page markdown content.
        
        Args:
            page: ConfluencePage instance
            attachment_manager: AttachmentManager instance for this space
            page_depth: Hierarchy depth of the page (0 = root)
            
        Returns:
            Updated markdown content with relative paths
        """
        if not page.markdown_content:
            return ""
        
        markdown = page.markdown_content
        total_rewritten = 0
        broken_references = []
        
        self.logger.debug(f"Rewriting links for page '{page.title}' (depth={page_depth})")
        
        # Rewrite attachment links
        attachment_mapping = {}
        for attachment in page.attachments:
            if attachment.local_path:
                attachment_mapping[attachment.title] = attachment.local_path
        
        # Process markdown content
        rewritten_markdown, att_rewritten, att_broken = self._rewrite_attachment_links(
            markdown=markdown,
            attachment_mapping=attachment_mapping,
            page_depth=page_depth
        )
        total_rewritten += att_rewritten
        broken_references.extend(att_broken)
        
        # Rewrite internal page links (placeholder - future enhancement)
        rewritten_markdown, internal_rewritten, internal_broken = self._rewrite_internal_links(
            markdown=rewritten_markdown,
            page=page,
            page_depth=page_depth
        )
        total_rewritten += internal_rewritten
        broken_references.extend(internal_broken)
        
        # Update metadata
        if 'links_rewritten' not in page.conversion_metadata:
            page.conversion_metadata['links_rewritten'] = 0
        page.conversion_metadata['links_rewritten'] += total_rewritten
        
        if broken_references:
            if 'broken_links' not in page.conversion_metadata:
                page.conversion_metadata['broken_links'] = []
            page.conversion_metadata['broken_links'].extend(broken_references)
        
        self.logger.debug(
            f"Rewrote {total_rewritten} links for page '{page.title}', "
            f"found {len(broken_references)} broken references"
        )
        
        return rewritten_markdown
    
    def _rewrite_attachment_links(
        self,
        markdown: str,
        attachment_mapping: Dict[str, str],
        page_depth: int = 0
    ) -> Tuple[str, int, List[str]]:
        """
        Rewrite attachment links to relative paths.
        
        Args:
            markdown: Markdown content
            attachment_mapping: Dict of {filename: relative_path}
            page_depth: Page hierarchy depth
            
        Returns:
            Tuple of (updated_markdown, rewritten_count, broken_references)
        """
        rewritten_count = 0
        broken_references = []
        
        def replace_url(match):
            nonlocal rewritten_count
            
            text = match.group(1)
            url = match.group(2)
            
            # Check if this is an attachment URL
            if not self._is_attachment_url(url):
                return match.group(0)  # Return original
            
            # Extract filename from URL
            filename = self._extract_filename(url)
            if not filename:
                return match.group(0)
            
            # Look up attachment path
            attachment_path = self._find_attachment_path(url, attachment_mapping)
            if not attachment_path:
                broken_references.append(f"Attachment '{filename}' not found")
                return match.group(0)
            
            # Calculate relative path from page to attachment
            relative_path = self._calculate_relative_path(page_depth, attachment_path)
            
            # Replace URL
            rewritten_count += 1
            if match.group(0).startswith('!'):
                # Image: ![alt](url)
                return f'![{text}]({relative_path})'
            else:
                # Link: [text](url)
                return f'[{text}]({relative_path})'
        
        # Process both links and images
        result = self.link_pattern.sub(replace_url, markdown)
        result = self.image_pattern.sub(replace_url, result)
        
        return result, rewritten_count, broken_references
    
    def _rewrite_internal_links(
        self,
        markdown: str,
        page: ConfluencePage,
        page_depth: int = 0
    ) -> Tuple[str, int, List[str]]:
        """
        Rewrite internal Confluence page links (placeholder for future enhancement).
        
        Args:
            markdown: Markdown content
            page: ConfluencePage instance
            page_depth: Page hierarchy depth
            
        Returns:
            Tuple of (updated_markdown, rewritten_count, broken_references)
        """
        # TODO: Implement internal page link rewriting
        # For now, log a warning and preserve original URLs
        
        rewritten_count = 0
        broken_references = []
        
        # Find potential internal link patterns
        internal_patterns = [
            r'/pages/viewpage\.action\?pageId=(\d+)',
            r'/display/[^/]+/(\d+)',
            r'/spaces/[^/]+/(\d+)',
        ]
        
        for pattern in internal_patterns:
            matches = re.finditer(pattern, markdown)
            for match in matches:
                page_id = match.group(1)
                self.logger.debug(
                    f"TODO: Internal link to page ID {page_id} found in page '{page.title}'"
                )
                # Current behavior: preserve original URL
        
        # Log once per page if internal links are found
        if any(re.search(pattern, markdown) for pattern in internal_patterns):
            self.logger.debug(
                f"Internal page links found in '{page.title}' - not yet implemented"
            )
        
        return markdown, rewritten_count, broken_references
    
    def _is_attachment_url(self, url: str) -> bool:
        """
        Check if URL is a Confluence attachment URL.
        
        Args:
            url: URL to check
            
        Returns:
            True if URL is an attachment URL
        """
        if not url:
            return False
        
        # Check for Confluence attachment patterns
        patterns = [
            r'/download/attachments/',
            r'download/attachments/',
        ]
        
        return any(re.search(pattern, url) for pattern in patterns)
    
    def _extract_filename(self, url: str) -> Optional[str]:
        """
        Extract filename from Confluence attachment URL.
        
        Args:
            url: Confluence attachment URL
            
        Returns:
            Filename or None if extraction fails
        """
        if not url:
            return None
        
        # Parse URL
        parsed = urlparse(url)
        path = parsed.path
        
        # Decode URL encoding
        path = unquote(path)
        
        # Extract filename from path
        parts = path.split('/')
        
        # Find 'attachments' in path
        try:
            attachments_idx = parts.index('attachments')
            if len(parts) > attachments_idx + 2:
                # Join remaining parts (handle filenames with slashes)
                filename = '/'.join(parts[attachments_idx + 2:])
                return filename
        except (ValueError, IndexError):
            pass
        
        # Fallback: get last part
        if parts:
            return parts[-1]
        
        return None
    
    def _find_attachment_path(
        self,
        url: str,
        attachment_mapping: Dict[str, str]
    ) -> Optional[str]:
        """
        Find attachment path in mapping.
        
        Args:
            url: Attachment URL
            attachment_mapping: Dict of {filename: relative_path}
            
        Returns:
            Attachment path or None if not found
        """
        # Extract filename
        filename = self._extract_filename(url)
        if not filename:
            return None
        
        # Try exact match
        if filename in attachment_mapping:
            return attachment_mapping[filename]
        
        # Try case-insensitive match
        filename_lower = filename.lower()
        for key, value in attachment_mapping.items():
            if key.lower() == filename_lower:
                return value
        
        # Try URL-decoded variants
        decoded_filename = unquote(filename)
        if decoded_filename != filename:
            if decoded_filename in attachment_mapping:
                return attachment_mapping[decoded_filename]
            
            # Try case-insensitive on decoded
            decoded_lower = decoded_filename.lower()
            for key, value in attachment_mapping.items():
                if key.lower() == decoded_lower:
                    return value
        
        # Try basename match (for filenames with subdirectories)
        basename = filename.split('/')[-1]
        if basename != filename:
            # Try exact basename match
            if basename in attachment_mapping:
                return attachment_mapping[basename]
            
            # Try case-insensitive basename match
            basename_lower = basename.lower()
            for key, value in attachment_mapping.items():
                if key.lower() == basename_lower:
                    return value
        
        return None
    
    def _calculate_relative_path(self, page_depth: int, attachment_path: str) -> str:
        """
        Calculate relative path from page to attachment.
        
        Args:
            page_depth: Page hierarchy depth (0 = root)
            attachment_path: Attachment path relative to space root
            
        Returns:
            Relative path string
        """
        # Build prefix of .. based on depth
        if page_depth == 0:
            prefix = "./"
        else:
            prefix = "../" * page_depth
        
        return f"{prefix}{attachment_path}"