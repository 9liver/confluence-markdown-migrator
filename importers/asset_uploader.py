"""
Asset Uploader for Confluence Attachments to Wiki.js

Handles uploading Confluence attachments to Wiki.js as assets and rewriting markdown links.
"""

import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

from models import ConfluenceAttachment, ConfluencePage
from .wikijs_client import WikiJsClient, WikiJsApiError


logger = logging.getLogger('confluence_markdown_migrator.importers.asset_uploader')


class AssetUploader:
    """
    Handles uploading Confluence attachments to Wiki.js assets API.
    
    This uploader:
    1. Reads attachments from local paths
    2. Uploads to Wiki.js via GraphQL mutations
    3. Rewrites markdown links to point to asset URLs
    """

    def __init__(
        self,
        config: Dict[str, Any],
        wikijs_client: WikiJsClient,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize the asset uploader.
        
        Args:
            config: Configuration dictionary
            wikijs_client: WikiJsClient instance
            logger: Logger instance
        """
        self.config = config
        self.wikijs_client = wikijs_client
        self.logger = logger or logging.getLogger('confluence_markdown_migrator.importers.asset_uploader')
        
        # Extract configuration
        self.enabled = self.wikijs_config.get('asset_upload', {}).get('enabled', True)
        self.folder = self.wikijs_config.get('asset_upload', {}).get('folder', '/confluence-assets')
        self.max_workers = self.wikijs_config.get('asset_upload', {}).get('max_workers', 3)
        self.rewrite_links = self.wikijs_config.get('asset_upload', {}).get('rewrite_links', True)
        self.show_progress = self.config.get('export', {}).get('progress_bars', True)
        
        self.logger.info("AssetUploader initialized")
    
    @property
    def wikijs_config(self) -> Dict[str, Any]:
        """Get Wiki.js configuration."""
        return self.config.get('wikijs', {})

    def upload_attachments_batch(
        self,
        attachments: List[ConfluenceAttachment],
        progress_callback: Optional[callable] = None,
        dry_run: bool = False
    ) -> Dict[str, str]:
        """
        Upload multiple attachments in batch.
        
        Args:
            attachments: List of ConfluenceAttachment objects
            progress_callback: Optional callback for progress updates
            dry_run: If True, simulate uploads without API calls
            
        Returns:
            Dict mapping attachment title to asset URL
        """
        if not self.enabled:
            self.logger.debug("Asset upload disabled")
            return {}
        
        if not attachments:
            return {}
        
        uploaded_map = {}
        
        if dry_run:
            # Dry run: simulate success for all attachments
            for attachment in attachments:
                if progress_callback:
                    progress_callback(attachment, True)
            return uploaded_map
        
        # Submit tasks to ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_attachment = {
                executor.submit(self._upload_single_with_callback, attachment, progress_callback): 
                attachment 
                for attachment in attachments
            }
            
            # Process completed tasks with optional progress bar
            futures = list(future_to_attachment.keys())
            if self._should_show_progress():
                futures = tqdm(futures, desc="Uploading attachments", total=len(attachments))
            
            for future in futures:
                attachment = future_to_attachment[future]
                try:
                    asset_url = future.result()
                    if asset_url:
                        uploaded_map[attachment.title] = asset_url
                except Exception as e:
                    self.logger.error(f"Failed to upload attachment '{attachment.title}': {e}", exc_info=True)
        
        return uploaded_map
    
    def _upload_single_with_callback(self, attachment: ConfluenceAttachment, callback: Optional[callable]) -> Optional[str]:
        """
        Upload a single attachment and invoke callback.
        
        Args:
            attachment: ConfluenceAttachment to upload
            callback: Optional callback for progress updates
            
        Returns:
            Asset URL if successful, None otherwise
        """
        try:
            asset_url = self.upload_attachment(attachment)
            if callback:
                callback(attachment, asset_url is not None)
            return asset_url
        except Exception as e:
            if callback:
                callback(attachment, False)
            raise

    def upload_attachment(self, attachment: ConfluenceAttachment) -> Optional[str]:
        """
        Upload a single attachment to Wiki.js.
        
        Args:
            attachment: ConfluenceAttachment to upload
            
        Returns:
            Asset URL if successful, None otherwise
        """
        if not attachment.local_path:
            self.logger.warning(f"Attachment has no local_path: {attachment.title}")
            return None
        
        file_path = Path(attachment.local_path)
        if not file_path.exists():
            self.logger.warning(f"Attachment file not found: {file_path}")
            return None
        
        try:
            # Read file content
            file_content = file_path.read_bytes()
            
            # Encode as base64 for GraphQL
            encoded_content = base64.b64encode(file_content).decode('utf-8')
            
            # Guess MIME type
            mime_type, _ = mimetypes.guess_type(file_path.name)
            if not mime_type:
                mime_type = 'application/octet-stream'
            
            # Upload via GraphQL mutation
            asset_url = self._create_asset(
                filename=attachment.title,
                content=encoded_content,
                mime_type=mime_type,
                folder=self.folder
            )
            
            if asset_url:
                self.logger.debug(f"Uploaded asset: {attachment.title} -> {asset_url}")
            else:
                self.logger.warning(f"Failed to create asset: {attachment.title}")
            
            return asset_url
            
        except Exception as e:
            self.logger.error(f"Error uploading attachment '{attachment.title}': {e}", exc_info=True)
            return None

    def _create_asset(
        self,
        filename: str,
        content: str,
        mime_type: str,
        folder: str
    ) -> Optional[str]:
        """
        Create asset via Wiki.js GraphQL API.
        
        Args:
            filename: Asset filename
            content: Base64 encoded content
            mime_type: MIME type
            folder: Target folder in Wiki.js
            
        Returns:
            Asset URL if successful
        """
        # Note: Wiki.js v2.x GraphQL API structure for assets
        # This is a placeholder - actual mutation may vary based on Wiki.js version
        mutation = """
            mutation CreateAsset($filename: String!, $content: String!, $mimeType: String!, $folder: String!) {
                assets {
                    create(filename: $filename, content: $content, mimeType: $mimeType, folder: $folder) {
                        responseResult {
                            succeeded
                            errorCode
                            slug
                            message
                        }
                        asset {
                            id
                            filename
                            url
                            mimeType
                            size
                        }
                    }
                }
            }
        """
        
        try:
            # Import here to avoid circular dependency
            from gql import gql
            
            mutation_gql = gql(mutation)
            variables = {
                "filename": filename,
                "content": content,
                "mimeType": mime_type,
                "folder": folder
            }
            
            result = self.wikijs_client.client.execute(mutation_gql, variable_values=variables)
            create_result = result['assets']['create']
            
            response_result = create_result['responseResult']
            if not response_result['succeeded']:
                self.logger.error(
                    f"Asset creation failed: {response_result.get('message', 'Unknown error')}"
                )
                return None
            
            asset = create_result['asset']
            return asset.get('url') if asset else None
            
        except Exception as e:
            self.logger.error(f"Error creating asset '{filename}': {e}", exc_info=True)
            return None

    def rewrite_attachment_links(
        self,
        markdown_content: str,
        attachment_map: Dict[str, str]
    ) -> str:
        """
        Rewrite markdown attachment links to point to Wiki.js assets.
        
        Args:
            markdown_content: Original markdown content
            attachment_map: Dict mapping attachment title to asset URL
            
        Returns:
            Updated markdown content
        """
        if not self.rewrite_links:
            return markdown_content
        
        if not attachment_map:
            return markdown_content
        
        # Pattern to match markdown image and link references
        # Matches both ![alt](url) and [text](url)
        pattern = r'!\[[^\]]*\]\([^\)\s]*\)|\[[^\]]*\]\([^\)\s]*\)'
        
        def replace_url(match):
            match_str = match.group(0)
            
            # Extract the URL part
            url_start = match_str.rfind('(') + 1
            url_end = match_str.rfind(')')
            if url_start >= url_end:
                return match_str
            
            url = match_str[url_start:url_end]
            
            # Check if this URL matches an attachment we uploaded
            for original_title, asset_url in attachment_map.items():
                # Match by filename (handle URL encoding)
                if original_title in url or url.endswith(original_title):
                    # Replace the URL but keep the rest
                    new_match = match_str[:url_start] + asset_url + match_str[url_end:]
                    return new_match
            
            return match_str
        
        import re
        rewritten = re.sub(pattern, replace_url, markdown_content)
        
        if rewritten != markdown_content:
            self.logger.debug(f"Rewrote {len(attachment_map)} attachment links")
        
        return rewritten
    
    def _should_show_progress(self) -> bool:
        """Check if progress bars should be displayed."""
        return (
            self.show_progress and
            tqdm is not None
        )


# Export for easy access
__all__ = ['AssetUploader']