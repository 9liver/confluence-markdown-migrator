"""Attachment manager for downloading, deduplicating, and saving attachments."""

import hashlib
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse
import time

from models import ConfluenceAttachment, ConfluencePage
import requests

# Optional tqdm import
try:
    from tqdm import tqdm
except ImportError:
    tqdm = None  # Will show warning if progress bars requested but not available


class AttachmentManager:
    """
    Manages attachment downloads, deduplication, and saving for a single space.
    
    This manager:
    1. Checks exclusion criteria (file size, type)
    2. Downloads attachments via API or HTML mode
    3. Deduplicates by content hash
    4. Saves to space-level attachments directory
    5. Updates attachment local_path references
    """
    
    def __init__(
        self,
        config: Dict[str, Any],
        space_key: str,
        output_dir: Path,
        confluence_client=None,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the attachment manager.
        
        Args:
            config: Configuration dictionary
            space_key: Confluence space key
            output_dir: Space output directory
            confluence_client: ConfluenceClient instance (for API mode)
            logger: Logger instance
        """
        self.config = config
        self.space_key = space_key
        self.output_dir = output_dir
        self.confluence_client = confluence_client
        self.logger = logger or logging.getLogger('confluence_markdown_migrator.exporters.attachment_manager')
        
        # Extract attachment configuration
        attachment_config = config.get('export', {}).get('attachment_handling', {})
        self.download_attachments = attachment_config.get('download_attachments', True)
        self.max_file_size = attachment_config.get('max_file_size', 52428800)  # 50MB default
        self.skip_file_types = attachment_config.get('skip_file_types', [])
        self.attachment_directory = attachment_config.get('attachment_directory', 'attachments')
        self.mode = config.get('migration', {}).get('mode', 'api')
        self.html_export_path = config.get('confluence', {}).get('html_export_path')
        
        # Progress bar configuration
        self.show_progress = attachment_config.get('progress_bars', True)
        
        # Initialize cache for deduplication
        self.file_hash_cache = {}  # {hash: filepath}
        self.filename_cache = {}   # {filename: filepath}
        
        # Initialize statistics
        self.stats = {
            'total_attachments': 0,
            'downloaded': 0,
            'skipped': 0,
            'failed': 0,
            'deduplicated': 0,
            'total_size_bytes': 0
        }
        
        # Create attachments directory
        self.attachments_dir = output_dir / self.attachment_directory
        self.attachments_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"AttachmentManager initialized for space '{space_key}'")
    
    def process_attachments(self, page: ConfluencePage) -> Dict[str, int]:
        """
        Process all attachments for a page.
        
        Args:
            page: ConfluencePage instance
            
        Returns:
            Statistics dictionary
        """
        if not self.download_attachments:
            self.logger.debug("Attachment downloads disabled - skipping")
            return {'total_attachments': 0, 'downloaded': 0, 'skipped': 0, 'failed': 0}
        
        if not page.attachments:
            return {'total_attachments': 0, 'downloaded': 0, 'skipped': 0, 'failed': 0}
        
        self.logger.debug(f"Processing {len(page.attachments)} attachment(s) for page '{page.title}'")
        
        # Initialize per-page statistics
        page_stats = {'total_attachments': 0, 'downloaded': 0, 'skipped': 0, 'failed': 0}
        
        # Wrap with tqdm if enabled
        attachments_iter = page.attachments
        if self._should_show_progress():
            attachments_iter = tqdm(
                page.attachments,
                desc=f"Attachments: {page.title[:30]}",
                leave=False,
                disable=not self._should_show_progress()
            )
        
        for attachment in attachments_iter:
            # Skip if already processed
            if attachment.local_path:
                self.logger.debug(f"Attachment '{attachment.title}' already processed")
                continue
            
            self.stats['total_attachments'] += 1
            page_stats['total_attachments'] += 1
            
            try:
                # Check exclusion criteria
                should_skip, skip_reason = self._should_skip_attachment(attachment)
                if should_skip:
                    self.logger.info(f"Skipping attachment '{attachment.title}': {skip_reason}")
                    attachment.excluded = True
                    attachment.exclusion_reason = skip_reason
                    self.stats['skipped'] += 1
                    page_stats['skipped'] += 1
                    continue
                
                # Download attachment
                content = self._download_attachment(attachment)
                if not content:
                    error_msg = f"Failed to download '{attachment.title}'"
                    self.logger.warning(error_msg)
                    self.stats['failed'] += 1
                    page_stats['failed'] += 1
                    continue
                
                # Save attachment (with deduplication)
                saved_path = self._deduplicate_and_save(attachment, content)
                attachment.local_path = str(saved_path.relative_to(self.output_dir))
                
                self.stats['downloaded'] += 1
                page_stats['downloaded'] += 1
                self.stats['total_size_bytes'] += len(content)
                
                self.logger.debug(
                    f"Saved attachment '{attachment.title}' -> {saved_path}"
                )
                
            except Exception as e:
                self.logger.error(
                    f"Error processing attachment '{attachment.title}': {e}",
                    exc_info=True
                )
                self.stats['failed'] += 1
                page_stats['failed'] += 1
        
        return page_stats.copy()
    
    def _should_skip_attachment(self, attachment: ConfluenceAttachment) -> Tuple[bool, str]:
        """
        Check if attachment should be skipped based on exclusion criteria.
        
        Args:
            attachment: ConfluenceAttachment instance
            
        Returns:
            Tuple of (should_skip, reason)
        """
        # Check if already excluded
        if attachment.excluded and attachment.exclusion_reason:
            return True, attachment.exclusion_reason
        
        # Check file size (0 means unlimited)
        if self.max_file_size > 0 and attachment.file_size > self.max_file_size:
            return (
                True,
                f"File size ({attachment.file_size} bytes) exceeds limit ({self.max_file_size} bytes)"
            )
        
        # Check file type (handle multi-part extensions like .tar.gz)
        if attachment.title:
            # Get all suffixes
            suffixes = Path(attachment.title).suffixes
            
            # Build variants to check
            extensions_to_check = []
            if suffixes:
                # Last suffix (e.g., '.gz')
                extensions_to_check.append(suffixes[-1].lower())
                # Full multi-suffix (e.g., '.tar.gz')
                if len(suffixes) > 1:
                    extensions_to_check.append(''.join(suffixes).lower())
            
            # Check against skip list
            skip_types_lower = [ext.lower() for ext in self.skip_file_types]
            for ext in extensions_to_check:
                if ext in skip_types_lower:
                    return True, f"File type '{ext}' is in skip list"
        
        return False, ""
    
    def _download_attachment(self, attachment: ConfluenceAttachment) -> Optional[bytes]:
        """
        Download attachment content via API or HTML mode.
        
        Args:
            attachment: ConfluenceAttachment instance
            
        Returns:
            Binary content or None on failure
        """
        try:
            if self.mode == 'html':
                if not self.html_export_path:
                    raise ValueError("html_export_path required for HTML mode")
                return self._download_from_html(attachment)
            else:  # api mode
                if not self.confluence_client:
                    raise ValueError("confluence_client required for API mode")
                return self._download_from_api(attachment, max_retries=3)
                
        except Exception as e:
            self.logger.warning(f"Failed to download '{attachment.title}': {e}")
            return None
    
    def _download_from_html(self, attachment: ConfluenceAttachment) -> bytes:
        """
        Extract attachment from local HTML export.
        
        Args:
            attachment: ConfluenceAttachment instance
            
        Returns:
            Binary content
        """
        file_path = self._parse_local_path(attachment.download_url, attachment.page_id)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Attachment file not found: {file_path}")
        
        content = file_path.read_bytes()
        
        # Validate file size
        if len(content) == 0:
            self.logger.warning(f"Attachment file is empty: {file_path}")
        elif len(content) > 100 * 1024 * 1024:  # 100MB
            self.logger.warning(f"Large attachment file ({len(content)/1024/1024:.1f}MB): {file_path}")
        
        return content
    
    def _download_from_api(self, attachment: ConfluenceAttachment, max_retries: int = 3) -> bytes:
        """
        Download attachment via Confluence REST API with retries.
        
        Args:
            attachment: ConfluenceAttachment instance
            max_retries: Maximum retry attempts
            
        Returns:
            Binary content
        """
        if not self.confluence_client:
            raise ValueError("Missing confluence_client")
        
        last_exception = None
        for attempt in range(max_retries):
            try:
                return self.confluence_client.download_attachment(attachment.download_url)
            except Exception as e:
                last_exception = e
                self.logger.warning(
                    f"Download attempt {attempt + 1} failed for '{attachment.title}': {e}"
                )
                if attempt < max_retries - 1:
                    # Exponential backoff
                    time.sleep(2  ** attempt)
        
        raise last_exception or Exception("All download attempts failed")
    
    def _parse_local_path(self, download_url: str, page_id: str) -> Path:
        """
        Parse Confluence download URL and construct local file path.
        
        Args:
            download_url: Confluence attachment URL
            page_id: Confluence page ID
            
        Returns:
            Path to local file
        """
        if not self.html_export_path:
            raise ValueError("html_export_path not configured")
        
        # Check if it's already a local path
        if Path(download_url).exists():
            return Path(download_url)
        
        # Parse URL
        url_path = download_url.lstrip('/')
        url_path = unquote(url_path)
        
        # Handle directory path format
        if url_path.startswith('download/attachments/'):
            return Path(self.html_export_path) / url_path
        
        # Parse filename
        parts = url_path.split('/')
        if len(parts) >= 3 and parts[0] == 'download' and parts[1] == 'attachments':
            # Format: download/attachments/{pageId}/{filename}
            filename = '/'.join(parts[3:])  # Handle slashes in filename
            return Path(self.html_export_path) / 'download' / 'attachments' / parts[2] / filename
        
        # Fallback: construct from page_id
        filename = Path(url_path).name
        return Path(self.html_export_path) / 'download' / 'attachments' / page_id / filename
    
    def _deduplicate_and_save(self, attachment: ConfluenceAttachment, content: bytes) -> Path:
        """
        Save attachment with deduplication based on content hash.
        
        Args:
            attachment: ConfluenceAttachment instance
            content: Binary content
            
        Returns:
            Saved file path
        """
        # Calculate content hash
        content_hash = hashlib.sha256(content).hexdigest()
        
        # Check for duplicate
        if content_hash in self.file_hash_cache:
            # Reuse existing file
            dedup_path = Path(self.file_hash_cache[content_hash])
            self.stats['deduplicated'] += 1
            self.logger.debug(f"Duplicate attachment '{attachment.title}' -> {dedup_path}")
            return dedup_path
        
        # Generate target filename
        filename = attachment.title
        base_path = self.attachments_dir / filename
        
        # Handle filename collisions
        counter = 1
        while base_path.exists():
            # Check if existing file has same content
            existing_hash = hashlib.sha256(base_path.read_bytes()).hexdigest()
            if existing_hash == content_hash:
                # Same content, reuse path
                self.file_hash_cache[content_hash] = str(base_path.relative_to(self.output_dir))
                self.filename_cache[filename] = base_path
                return base_path
            
            # Different content, add counter suffix
            name = Path(filename).stem
            suffix = ''.join(Path(filename).suffixes)
            base_path = self.attachments_dir / f"{name}_{counter}{suffix}"
            counter += 1
        
        # Write file
        base_path.write_bytes(content)
        
        # Update caches
        self.file_hash_cache[content_hash] = str(base_path.relative_to(self.output_dir))
        self.filename_cache[filename] = base_path
        
        return base_path
    
    def get_attachment_path(self, attachment: ConfluenceAttachment) -> Optional[Path]:
        """
        Get saved attachment path.
        
        Args:
            attachment: ConfluenceAttachment instance
            
        Returns:
            Attachment path or None if not saved
        """
        if attachment.local_path:
            return self.output_dir / attachment.local_path
        
        # Try to find by title
        if attachment.title in self.filename_cache:
            return self.filename_cache[attachment.title]
        
        return None
    
    def _should_show_progress(self) -> bool:
        """Check if progress bars should be displayed."""
        if not self.show_progress:
            return False
        if not sys.stdout.isatty():
            return False
        if tqdm is None:
            return False
        return True
    
    def get_stats(self) -> Dict[str, int]:
        """Get attachment processing statistics."""
        return self.stats.copy()