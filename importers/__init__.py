"""Import package for Confluence to Wiki.js/BookStack migration.

This package provides functionality to import converted Confluence content to
wiki platforms like Wiki.js and BookStack using their respective APIs.

Package Structure:
- wikijs_client: GraphQL client for Wiki.js API operations
- hierarchy_mapper: Maps Confluence hierarchies to flat wiki paths
- asset_uploader: Uploads attachments as wiki assets
- wikijs_importer: Orchestrates the Wiki.js import process
- bookstack_client: REST API client for BookStack operations
- bookstack_hierarchy_mapper: Maps Confluence hierarchies to BookStack's 3-level structure
- content_transformer: Converts markdown to HTML for BookStack
- image_uploader: Uploads images as BookStack attachments
- id_mapping_tracker: Tracks Confluence to BookStack ID mappings
- ordering_manager: Manages content ordering in BookStack
- bookstack_importer: Orchestrates the BookStack import process

Key Features:
- Wiki.js GraphQL API integration for page creation/updates
- BookStack REST API integration for hierarchical content import
- Hierarchical path generation from Confluence parent-child relationships
- Space→Shelf, Book, Chapter, Page hierarchy mapping for BookStack
- Asset upload with parallel processing and retry logic
- Conflict resolution strategies (skip, overwrite, version)
- Tag preservation from Confluence labels
- Markdown to HTML conversion for BookStack storage
- Image upload with automatic reference rewriting
- Dry-run mode for safe preview of import operations

Models Referenced:
- ConfluencePage: Uses markdown_content, attachments, metadata
- ConfluenceSpace: Space key and name for path generation
- DocumentationTree: Input structure for import operations

Configuration Referenced:
- wikijs.*: Wiki.js API settings and authentication
- bookstack.*: BookStack API settings and authentication
- export.*: General export settings
- migration.*: Migration mode and behavior settings
"""

from .wikijs_importer import WikiJsImporter
from .wikijs_client import WikiJsClient
from .hierarchy_mapper import ConfluenceHierarchyMapper
from .asset_uploader import AssetUploader
from .bookstack_importer import BookStackImporter
from .bookstack_client import BookStackClient
from .bookstack_hierarchy_mapper import BookStackHierarchyMapper
from .content_transformer import ContentTransformer
from .image_uploader import ImageUploader
from .id_mapping_tracker import IdMappingTracker
from .ordering_manager import OrderingManager

__all__ = [
    # Wiki.js imports (existing)
    'WikiJsImporter',
    'WikiJsClient',
    'ConfluenceHierarchyMapper',
    'AssetUploader',
    # BookStack imports (new)
    'BookStackImporter',
    'BookStackClient',
    'BookStackHierarchyMapper',
    'ContentTransformer',
    'ImageUploader',
    'IdMappingTracker',
    'OrderingManager'
]