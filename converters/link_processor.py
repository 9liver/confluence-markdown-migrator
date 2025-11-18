"""Link processor for handling Confluence links, images, and attachment references."""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger('confluence_markdown_migrator.converters.linkprocessor')


MAX_CHARS_BETWEEN_BRACKETS = 1000  # Prevent catastrophic backtracking


class LinkProcessor:
    """Processes Confluence links, images, and attachment references in markdown content."""
    
    def __init__(self, confluence_base_url: Optional[str] = None, logger: logging.Logger = None):
        """Initialize link processor with Confluence base URL for link detection."""
        self.logger = logger or logging.getLogger('confluence_markdown_migrator.converters.linkprocessor')
        self.confluence_base_url = confluence_base_url
        
        # Compile regex patterns
        self.link_pattern = re.compile(r'\[([^\]]{1,' + str(MAX_CHARS_BETWEEN_BRACKETS) + r'})\]\(([^\)\s]*)\)')
        self.image_pattern = re.compile(r'!\[([^\]]*)\]\(([^\)\s]*)\)')
        self.attachment_pattern = re.compile(r'/download/attachments/(\d+)/([^"\)\s]+)')
        
        # Confluence URL patterns for internal link detection
        self.confluence_patterns = [
            r'/pages/viewpage.action\?pageId=(\d+)',
            r'/display/[^/]+/(\d+)',
            r'/spaces/[^/]+/(\d+)',
        ]
    
    def process_links(self, markdown_content: str, page: Any) -> Tuple[str, Dict[str, Any]]:
        """
        Process all links and images in markdown content.
        
        Args:
            markdown_content: The markdown content to process
            page: ConfluencePage object containing attachments and metadata
            
        Returns:
            Tuple of (processed_markdown, link_stats)
        """
        self.logger.debug(f"Processing links for page {page.id}")
        
        stats = {
            'links_internal': 0,
            'links_external': 0,
            'links_attachment': 0,
            'images_count': 0,
            'images_with_alt': 0,
            'images_with_attachment': 0,
            'broken_links': [],
            'links_rewritten': 0
        }
        
        # Extract links before processing
        links = self._extract_links(markdown_content)
        images = self._extract_images(markdown_content)
        
        # Process links
        processed_content = markdown_content
        
        # Process attachment references
        if page.attachments:
            processed_content = self._rewrite_attachment_references(
                processed_content, page.attachments, get_attachment_base_path(page)
            )
        
        # Process internal Confluence links
        processed_content = self._process_internal_links(processed_content, page, stats)
        
        # Process external links
        processed_content = self._process_external_links(processed_content, stats)
        
        # Process images
        processed_content = self._process_images(processed_content, page, stats)
        
        self.logger.debug(f"Link processing complete: {stats}")
        return processed_content, stats
    
    def extract_links(self, soup: Any) -> List[Dict[str, str]]:
        """Extract all links from HTML for metadata tracking before markdown conversion."""
        links = []
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text(strip=True)
            
            # Check if it's an internal Confluence link
            is_internal = self._is_confluence_link(href)
            
            links.append({
                'href': href,
                'text': text,
                'is_internal': is_internal
            })
        
        return links
    
    def extract_images(self, soup: Any) -> List[Dict[str, str]]:
        """Extract all images from HTML for metadata tracking."""
        images = []
        
        for img in soup.find_all('img', src=True):
            src = img['src']
            alt = img.get('alt', '')
            title = img.get('title', '')
            
            # Use title as alt if alt is missing
            if not alt and title:
                alt = title
            
            images.append({
                'src': src,
                'alt': alt,
                'title': title
            })
        
        return images
    
    def _extract_links(self, markdown: str) -> List[Tuple[str, str]]:
        """Extract markdown links for processing."""
        links = []
        for match in self.link_pattern.finditer(markdown):
            text = match.group(1)
            url = match.group(2)
            links.append((text, url))
        return links
    
    def _extract_images(self, markdown: str) -> List[Tuple[str, str]]:
        """Extract markdown images for processing."""
        images = []
        for match in self.image_pattern.finditer(markdown):
            alt = match.group(1)
            url = match.group(2)
            images.append((alt, url))
        return images
    
    def _rewrite_attachment_references(self, markdown: str, attachments: List[Any], base_path: str) -> str:
        """Rewrite attachment URLs to relative paths."""
        def replacer(match):
            full_url = match.group(0)
            
            # Find matching attachment
            for att in attachments:
                if att.download_url in full_url or att.title in full_url:
                    # Generate relative path
                    rel_path = f"attachments/{att.page_id}/{att.title}"
                    return f"({rel_path})"
            
            return match.group(0)
        
        # Pattern for attachment URLs
        att_pattern = re.compile(r'\(([^\)]+/download/attachments/\d+/[^\)]+)\)')
        return att_pattern.sub(replacer, markdown)
    
    def _process_internal_links(self, markdown: str, page: Any, stats: Dict[str, Any]) -> str:
        """Process internal Confluence links."""
        def replacer(match):
            text = match.group(1)
            url = match.group(2)
            
            if self._is_confluence_link(url):
                stats['links_internal'] += 1
                
                # For now, preserve as-is (exporters will handle rewriting)
                # Add metadata for tracking
                return match.group(0)
            
            return match.group(0)
        
        return self.link_pattern.sub(replacer, markdown)
    
    def _process_external_links(self, markdown: str, stats: Dict[str, Any]) -> str:
        """Process and validate external links."""
        def replacer(match):
            text = match.group(1)
            url = match.group(2)
            
            # Skip if already processed as internal
            if self._is_confluence_link(url):
                return match.group(0)
            
            # Check if it's a valid URL
            try:
                result = urlparse(url)
                if result.scheme and result.netloc:
                    stats['links_external'] += 1
                    # TODO: Validate URL (check for 404s, timeouts)
                else:
                    # Relative link or fragment
                    if url.startswith('#'):
                        stats['links_anchor'] = stats.get('links_anchor', 0) + 1
                    else:
                        stats['links_relative'] = stats.get('links_relative', 0) + 1
            except Exception:
                stats['broken_links'].append(url)
            
            return match.group(0)
        
        return self.link_pattern.sub(replacer, markdown)
    
    def _process_images(self, markdown: str, page: Any, stats: Dict[str, Any]) -> str:
        """Process image references in markdown."""
        def replacer(match):
            alt = match.group(1)
            url = match.group(2)
            
            # Check for alt text
            if alt and len(alt.strip()) > 0:
                stats['images_with_alt'] += 1
            
            # Check if image matches an attachment
            is_attachment = False
            if page.attachments:
                for att in page.attachments:
                    if att.download_url in url or att.title in url:
                        stats['images_with_attachment'] += 1
                        is_attachment = True
                        break
            
            stats['images_count'] += 1
            return match.group(0)
        
        return self.image_pattern.sub(replacer, markdown)
    
    def _is_confluence_link(self, url: str) -> bool:
        """Check if URL is an internal Confluence link."""
        # Check if URL starts with base URL
        if self.confluence_base_url and url.startswith(self.confluence_base_url):
            return True
        
        # Check for Confluence URL patterns
        patterns = self.confluence_patterns
        for pattern in patterns:
            if re.search(pattern, url):
                return True
        
        return False
    
    def _extract_confluence_page_id(self, url: str) -> Optional[str]:
        """Extract Confluence page ID from URL."""
        for pattern in self.confluence_patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None
    
    def extract_alt_text(self, img_element: Any) -> str:
        """Extract alt text from img element."""
        # Check alt attribute first
        alt = img_element.get('alt', '')
        if alt:
            return alt
        
        # Fall back to title
        title = img_element.get('title', '')
        if title:
            return title
        
        # Fall back to filename from src
        src = img_element.get('src', '')
        if src:
            filename = src.split('/')[-1]
            # Remove query parameters
            filename = filename.split('?')[0]
            # Remove file extension
            name_without_ext = filename.rsplit('.', 1)[0]
            return name_without_ext
        
        return ''
    
    def _is_attachment_url(self, url: str) -> bool:
        """Check if URL points to Confluence attachment."""
        return bool(self.attachment_pattern.search(url))
    
    def _match_attachment_by_url(self, url: str, attachments: List[Any]) -> Optional[Any]:
        """Match URL to ConfluenceAttachment object."""
        for att in attachments:
            if att.download_url in url or att.title in url:
                return att
        return None


def get_attachment_base_path(page: Any) -> str:
    """Get base path for attachment references."""
    # For local markdown files, use relative path
    return f"attachments/{page.id}"


def rewrite_image_url(url: str, attachments: List[Any], base_path: str) -> str:
    """Rewrite image URL to relative path if it's an attachment."""
    for att in attachments:
        if att.download_url in url or att.title in url:
            # Generate relative path
            return f"{base_path}/{att.title}"
    return url