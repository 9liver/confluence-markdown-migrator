"""Wiki.js preview mapper for flat path-based structure generation."""

import re
from typing import Any, Dict, List, Optional, Set

from ...models import DocumentationTree, ConfluencePage, ConfluenceSpace


class WikiJsPreviewMapper:
    """Generates Wiki.js flat path-based preview from selected pages."""
    
    @staticmethod
    def build_preview(selected_page_ids: Set[str], tree: DocumentationTree) -> Dict[str, Any]:
        """
        Build Wiki.js flat path preview structure.
        
        Args:
            selected_page_ids: Set of selected Confluence page IDs
            tree: DocumentationTree with all spaces and pages
            
        Returns:
            Dict with 'spaces' list containing flat path structure
        """
        pages = WikiJsPreviewMapper._get_selected_pages(selected_page_ids, tree)
        
        # Group by space
        pages_by_space = WikiJsPreviewMapper._group_by_space(pages)
        
        spaces = []
        for space_key, space_pages in pages_by_space.items():
            space = tree.get_space(space_key)
            if not space:
                continue
            
            # Build space structure (flat paths)
            space_structure = WikiJsPreviewMapper._build_space_structure(space, space_pages, tree)
            spaces.append(space_structure)
        
        return {'spaces': spaces}
    
    @staticmethod
    def _get_selected_pages(page_ids: Set[str], tree: DocumentationTree) -> List[ConfluencePage]:
        """Get selected ConfluencePage objects from IDs."""
        pages = []
        for space in tree.spaces.values():
            for page in space.get_all_pages():
                if page.id in page_ids:
                    pages.append(page)
        return pages
    
    @staticmethod
    def _group_by_space(pages: List[ConfluencePage]) -> Dict[str, List[ConfluencePage]]:
        """Group pages by space key."""
        groups = {}
        for page in pages:
            groups.setdefault(page.space_key, []).append(page)
        return groups
    
    @staticmethod
    def _build_space_structure(space: ConfluenceSpace, pages: List[ConfluencePage], tree: DocumentationTree) -> Dict[str, Any]:
        """Build flat path structure for a space."""
        path_pages = []
        
        for page in pages:
            path = WikiJsPreviewMapper._build_page_path(page, space, tree, True)
            path_pages.append({
                'title': page.title,
                'path': path,
                'source_page_id': page.id,
                'level': path.count('/')
            })
        
        # Sort by path to show hierarchy
        path_pages.sort(key=lambda x: x['path'])
        
        return {
            'name': space.name,
            'key': space.key,
            'pages': path_pages
        }
    
    @staticmethod
    def _build_page_path(page: ConfluencePage, space: ConfluenceSpace, tree: DocumentationTree,
                        include_space: bool = True) -> str:
        """Build hierarchical path for page (e.g., /space/parent/child)."""
        components = []
        
        # Start with space if requested
        if include_space:
            components.append(WikiJsPreviewMapper._sanitize_path_component(space.key))
        
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
            components.append(WikiJsPreviewMapper._sanitize_path_component(ancestor.title))
        
        # Add current page
        components.append(WikiJsPreviewMapper._sanitize_path_component(page.title))
        
        # Join with slashes
        return "/" + "/".join(components)
    
    @staticmethod
    def _sanitize_path_component(title: str) -> str:
        """Convert title to URL-safe slug."""
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
        
        return slug
    
    @staticmethod
    def _find_page_by_id(page_id: str, tree: DocumentationTree) -> Optional[ConfluencePage]:
        """Find page by ID in tree."""
        return tree.get_page_by_id(page_id)
    
    @staticmethod
    def format_preview_tree(preview: Dict[str, Any]) -> str:
        """Format preview tree as Rich markup string."""
        if not preview or not preview.get('spaces'):
            return "[dim]No content selected for preview[/dim]"
        
        lines = []
        
        for space in preview['spaces']:
            lines.append(f"\n[bold cyan]Space: {space['name']}[/bold cyan]")
            
            if not space['pages']:
                lines.append("  [dim]No pages selected[/dim]")
                continue
            
            # Group by common prefixes to show hierarchy
            paths = [p['path'] for p in space['pages']]
            paths.sort()
            
            for page_idx, page in enumerate(space['pages']):
                is_last = page_idx == len(space['pages']) - 1
                prefix = "└─" if is_last else "├─"
                
                # Show path relative to space
                display_path = page['path']
                if display_path.startswith(f"/{space['key']}/"):
                    display_path = display_path[len(f"/{space['key']}"):]
                
                lines.append(f"{prefix} {page['title']}")
                lines.append(f"        [dim]{display_path}.md[/dim]")
        
        return "\n".join(lines)
