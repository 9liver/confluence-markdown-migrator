"""
Image uploader for BookStack import.

This module handles uploading images as attachments to BookStack pages
and rewriting image references in HTML content.
"""

import logging
import re
from typing import Dict, Any, Optional
from pathlib import Path
import mimetypes

logger = logging.getLogger(__name__)


class ImageUploader:
    """Handles image uploads and reference rewriting for BookStack."""
    
    # Supported image MIME types
    SUPPORTED_IMAGE_TYPES = {
        'image/png',
        'image/jpeg',
        'image/jpg',
        'image/gif',
        'image/svg+xml',
        'image/webp'
    }
    
    def __init__(
        self,
        config: Dict[str, Any],
        bookstack_client: Any,  # BookStackClient - avoid circular import
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize image uploader.
        
        Args:
            config: Configuration dictionary
            bookstack_client: BookStackClient instance
            logger: Optional logger instance
        """
        self.config = config
        self.client = bookstack_client
        self.logger = logger or logging.getLogger(__name__)
        
        self.logger.debug("Initialized ImageUploader")
    
    def upload_images_for_page(
        self,
        page: Any,  # ConfluencePage - avoid circular import
        bookstack_page_id: int
    ) -> Dict[str, str]:
        """
        Upload all images for a page to BookStack.
        
        Args:
            page: ConfluencePage with attachments
            bookstack_page_id: BookStack page ID to associate images with
            
        Returns:
            Dict mapping original filenames to BookStack image URLs
        """
        if not bookstack_page_id:
            self.logger.error("Cannot upload images: bookstack_page_id is required")
            return {}
        
        if not hasattr(page, 'attachments') or not page.attachments:
            self.logger.debug(f"No attachments to upload for page: {page.title}")
            return {}
        
        image_map = {}
        uploaded_count = 0
        
        for attachment in page.attachments:
            # Check if this is an image
            if not self._is_image_attachment(attachment):
                continue
            
            # Skip if no local path available
            if not hasattr(attachment, 'local_path') or not attachment.local_path:
                self.logger.warning(
                    f"Attachment '{attachment.title}' has no local_path. Skipping upload."
                )
                continue
            
            # Check if file exists
            file_path = Path(attachment.local_path)
            if not file_path.exists():
                self.logger.warning(
                    f"Attachment file not found: {attachment.local_path}. Skipping upload."
                )
                continue
            
            try:
                # Read image data
                image_data = file_path.read_bytes()
                
                # Upload to BookStack
                upload_response = self.client.upload_image(
                    image_name=attachment.title,
                    image_data=image_data,
                    uploaded_to=bookstack_page_id
                )
                
                # Extract the URL/path from the response
                if upload_response:
                    # Try different possible field names for the image URL/path
                    image_url = (
                        upload_response.get('path') or 
                        upload_response.get('url') or 
                        upload_response.get('links', {}).get('download', '')
                    )
                    if image_url:
                        image_map[attachment.title] = image_url
                        uploaded_count += 1
                        self.logger.debug(
                            f"Uploaded image '{attachment.title}' to {image_url}"
                        )
                    else:
                        self.logger.warning(
                            f"Uploaded image '{attachment.title}' but no URL/path found in response: {upload_response}"
                        )
                else:
                    self.logger.error(
                        f"Failed to upload image '{attachment.title}': "
                        f"No valid response from server"
                    )
                    
            except Exception as e:
                self.logger.error(
                    f"Failed to upload image '{attachment.title}': {str(e)}"
                )
                continue
        
        self.logger.info(
            f"Uploaded {uploaded_count} images for page '{page.title}'"
        )
        
        return image_map
    
    def rewrite_image_references(
        self,
        html_content: str,
        image_map: Dict[str, str]
    ) -> str:
        """
        Rewrite local image references to use BookStack attachment URLs.
        
        Args:
            html_content: HTML content with local image references
            image_map: Dict mapping original filenames to BookStack URLs
            
        Returns:
            HTML with rewritten image URLs
        """
        if not image_map:
            self.logger.debug("No image map provided, skipping reference rewriting")
            return html_content
        
        if not html_content:
            return html_content
        
        rewritten_content = html_content
        replacements = 0
        
        # Pattern to match img tags with src attribute
        # Captures the entire img tag and the src URL
        img_pattern = re.compile(
            r'<img([^>]*)src=["\']([^"\']+)["\']([^>]*)>',
            re.IGNORECASE
        )
        
        def replace_src(match):
            nonlocal replacements
            
            prefix = match.group(1)  # Attributes before src
            original_src = match.group(2)  # Current src value
            suffix = match.group(3)  # Attributes after src
            
            # Extract filename from the src path
            src_filename = self._extract_filename(original_src)
            
            # Check if we have a mapping for this filename
            for attachment_name, bookstack_url in image_map.items():
                if src_filename == attachment_name or src_filename in attachment_name:
                    # Replace the src with BookStack URL
                    replacements += 1
                    new_tag = f'<img{prefix}src="{bookstack_url}"{suffix}>'
                    self.logger.debug(
                        f"Replaced image src: '{original_src}' -> '{bookstack_url}'"
                    )
                    return new_tag
            
            # No replacement found, return original
            return match.group(0)
        
        # Apply replacements
        rewritten_content = img_pattern.sub(replace_src, rewritten_content)
        
        if replacements > 0:
            self.logger.info(
                f"Rewrote {replacements} image references in HTML content"
            )
        else:
            self.logger.debug("No image references required rewriting")
        
        return rewritten_content
    
    def _is_image_attachment(self, attachment: Any) -> bool:
        """
        Check if attachment is an image based on media type.
        
        Args:
            attachment: Attachment object
            
        Returns:
            True if attachment is an image
        """
        # Check for media_type attribute
        if hasattr(attachment, 'media_type') and attachment.media_type:
            return attachment.media_type in self.SUPPORTED_IMAGE_TYPES
        
        # Fallback: check file extension
        if hasattr(attachment, 'title') and attachment.title:
            mime_type, _ = mimetypes.guess_type(attachment.title)
            if mime_type and mime_type in self.SUPPORTED_IMAGE_TYPES:
                return True
        
        return False
    
    def _extract_filename(self, src_path: str) -> str:
        """
        Extract filename from a src path or URL.
        
        Args:
            src_path: Image src path/URL
            
        Returns:
            Filename without path or query parameters
        """
        # Remove URL parameters
        clean_path = src_path.split('?')[0]
        
        # Extract filename from path
        filename = clean_path.split('/')[-1]
        
        # URL decode if needed
        try:
            from urllib.parse import unquote
            filename = unquote(filename)
        except ImportError:
            pass
        
        return filename