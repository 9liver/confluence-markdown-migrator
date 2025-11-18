"""Data models for Confluence to Markdown migration pipeline."""

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from datetime import datetime

logger = logging.getLogger('confluence_markdown_migrator')


class ExportTarget(Enum):
    """Export target destinations for migration."""
    MARKDOWN_FILES = "markdown_files"
    WIKIJS = "wikijs"
    BOOKSTACK = "bookstack"
    BOTH_WIKIS = "both_wikis"


@dataclass
class ConfluenceAttachment:
    """Represents a Confluence attachment with enhanced metadata."""
    
    id: str
    title: str
    media_type: str
    file_size: int
    download_url: str
    page_id: str
    local_path: Optional[str] = None
    excluded: bool = False
    exclusion_reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize attachment to dictionary."""
        return {
            'id': self.id,
            'title': self.title,
            'media_type': self.media_type,
            'file_size': self.file_size,
            'download_url': self.download_url,
            'page_id': self.page_id,
            'local_path': self.local_path,
            'excluded': self.excluded,
            'exclusion_reason': self.exclusion_reason
        }


@dataclass
class ConfluencePage:
    """Represents a Confluence page with metadata and markdown conversion tracking."""
    
    id: str
    title: str
    content: str  # HTML content
    space_key: str
    parent_id: Optional[str] = None
    children: List['ConfluencePage'] = field(default_factory=list)
    attachments: List[ConfluenceAttachment] = field(default_factory=list)
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    markdown_content: Optional[str] = None
    conversion_metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Initialize default metadata if empty."""
        if not self.metadata:
            self.metadata = {
                'author': None,
                'last_modified': None,
                'version': 1,
                'labels': [],
                'content_type': 'page',
                'content_source': 'api'
            }
            
        if not self.conversion_metadata:
            self.conversion_metadata = {
                'conversion_status': 'pending',
                'macros_found': [],
                'macros_converted': [],
                'macros_failed': [],
                'links_internal': 0,
                'links_external': 0,
                'images_count': 0,
                'conversion_warnings': []
            }
    
    def add_child(self, child: 'ConfluencePage') -> None:
        """Add a child page."""
        self.children.append(child)
    
    def add_attachment(self, attachment: ConfluenceAttachment) -> None:
        """Add an attachment."""
        self.attachments.append(attachment)
    
    def is_root_page(self) -> bool:
        """Check if this page is a root page (no parent)."""
        return self.parent_id is None
    
    def get_all_descendants(self, include_self: bool = False) -> List['ConfluencePage']:
        """Get all descendant pages recursively."""
        descendants = []
        if include_self:
            descendants.append(self)
        
        for child in self.children:
            descendants.append(child)
            descendants.extend(child.get_all_descendants())
        
        return descendants
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize page to dictionary."""
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'space_key': self.space_key,
            'parent_id': self.parent_id,
            'children': [child.to_dict() for child in self.children],
            'attachments': [att.to_dict() for att in self.attachments],
            'url': self.url,
            'metadata': self.metadata,
            'markdown_content': self.markdown_content,
            'conversion_metadata': self.conversion_metadata
        }
    
    def __eq__(self, other: Any) -> bool:
        """Compare pages by ID."""
        if not isinstance(other, ConfluencePage):
            return False
        return self.id == other.id
    
    def __hash__(self) -> int:
        """Hash page by ID."""
        return hash(self.id)


@dataclass
class ConfluenceSpace:
    """Represents a Confluence space with metadata."""
    
    key: str
    name: str
    id: str
    description: str
    pages: List[ConfluencePage] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Initialize default metadata if empty."""
        if not self.metadata:
            self.metadata = {
                'homepage_id': None,
                'type': 'global',
                'permissions': {}
            }
    
    def add_page(self, page: ConfluencePage) -> None:
        """Add a page to the space."""
        self.pages.append(page)
    
    def get_page_by_id(self, page_id: str) -> Optional[ConfluencePage]:
        """Find a page by ID recursively."""
        for page in self.pages:
            if page.id == page_id:
                return page
            # Check children
            child = page.get_all_descendants()
            for p in child:
                if p.id == page_id:
                    return p
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize space to dictionary."""
        return {
            'key': self.key,
            'name': self.name,
            'id': self.id,
            'description': self.description,
            'pages': [page.to_dict() for page in self.pages],
            'metadata': self.metadata
        }


@dataclass
class DocumentationTree:
    """Represents the complete Confluence documentation tree."""
    
    spaces: Dict[str, ConfluenceSpace] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self) -> None:
        """Initialize default metadata if empty."""
        if not self.metadata:
            self.metadata = {
                'fetch_mode': 'api',
                'fetch_timestamp': datetime.utcnow().isoformat(),
                'confluence_base_url': None,
                'filters_applied': {},
                'total_pages_fetched': 0,
                'total_attachments_fetched': 0
            }
    
    def add_space(self, space: ConfluenceSpace) -> None:
        """Add a space to the documentation tree."""
        self.spaces[space.key] = space
    
    def get_space(self, space_key: str) -> Optional[ConfluenceSpace]:
        """Get a space by key."""
        return self.spaces.get(space_key)
    
    def get_all_pages(self) -> List[ConfluencePage]:
        """Get all pages across all spaces."""
        all_pages = []
        for space in self.spaces.values():
            for page in space.pages:
                all_pages.append(page)
                all_pages.extend(page.get_all_descendants())
        return all_pages
    
    def get_page_by_id(self, page_id: str) -> Optional[ConfluencePage]:
        """Find a page by ID across all spaces."""
        for space in self.spaces.values():
            page = space.get_page_by_id(page_id)
            if page:
                return page
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get migration statistics."""
        total_pages = 0
        total_attachments = 0
        total_failed = 0
        total_success = 0
        total_partial = 0
        
        for page in self.get_all_pages():
            total_pages += 1
            total_attachments += len(page.attachments)
            
            status = page.conversion_metadata.get('conversion_status', 'pending')
            if status == 'failed':
                total_failed += 1
            elif status == 'success':
                total_success += 1
            elif status == 'partial':
                total_partial += 1
        
        return {
            'spaces': len(self.spaces),
            'pages': total_pages,
            'attachments': total_attachments,
            'conversion_status': {
                'failed': total_failed,
                'success': total_success,
                'partial': total_partial,
                'pending': total_pages - (total_failed + total_success + total_partial)
            }
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize tree to dictionary."""
        return {
            'spaces': {key: space.to_dict() for key, space in self.spaces.items()},
            'metadata': self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DocumentationTree':
        """Deserialize from dictionary."""
        tree = cls()
        
        if 'metadata' in data:
            tree.metadata = data['metadata']
        
        for space_key, space_data in data.get('spaces', {}).items():
            space = ConfluenceSpace(
                key=space_data['key'],
                name=space_data['name'],
                id=space_data['id'],
                description=space_data['description'],
                metadata=space_data.get('metadata', {})
            )
            
            for page_data in space_data.get('pages', []):
                page = cls._page_from_dict(page_data)
                space.add_page(page)
            
            tree.add_space(space)
        
        return tree
    
    @staticmethod
    def _page_from_dict(data: Dict[str, Any]) -> ConfluencePage:
        """Recursively reconstruct page from dictionary."""
        page = ConfluencePage(
            id=data['id'],
            title=data['title'],
            content=data['content'],
            space_key=data['space_key'],
            parent_id=data.get('parent_id'),
            url=data.get('url'),
            metadata=data.get('metadata', {}),
            markdown_content=data.get('markdown_content'),
            conversion_metadata=data.get('conversion_metadata', {})
        )
        
        for child_data in data.get('children', []):
            child = DocumentationTree._page_from_dict(child_data)
            page.add_child(child)
        
        for attachment_data in data.get('attachments', []):
            attachment = ConfluenceAttachment(
                id=attachment_data['id'],
                title=attachment_data['title'],
                media_type=attachment_data['media_type'],
                file_size=attachment_data['file_size'],
                download_url=attachment_data['download_url'],
                page_id=attachment_data['page_id'],
                local_path=attachment_data.get('local_path'),
                excluded=attachment_data.get('excluded', False),
                exclusion_reason=attachment_data.get('exclusion_reason')
            )
            page.add_attachment(attachment)
        
        return page


@dataclass
class MigrationStatus:
    """Tracks migration progress and status for reporting."""
    
    page_id: str
    page_title: str
    status: str  # "pending", "fetched", "converted", "exported", "failed"
    error_message: Optional[str] = None
    timestamp: Optional[str] = None
    
    def __post_init__(self) -> None:
        """Set timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.utcnow().isoformat()


__all__ = [
    'ConfluenceAttachment',
    'ConfluencePage',
    'ConfluenceSpace',
    'DocumentationTree',
    'ExportTarget',
    'MigrationStatus'
]
