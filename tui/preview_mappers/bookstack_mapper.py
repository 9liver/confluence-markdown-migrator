"""BookStack preview mapper for hierarchical structure generation."""

from typing import Any, Dict, List, Optional, Set

from ...models import DocumentationTree, ConfluencePage, ConfluenceSpace


class BookStackPreviewMapper:
    """Generates BookStack hierarchical preview from selected pages."""
    
    @staticmethod
    def build_preview(selected_page_ids: Set[str], tree: DocumentationTree) -> Dict[str, Any]:
        """
        Build BookStack hierarchical preview structure.
        
        Args:
            selected_page_ids: Set of selected Confluence page IDs
            tree: DocumentationTree with all spaces and pages
            
        Returns:
            Dict with 'shelves' list containing hierarchical structure
        """
        pages = BookStackPreviewMapper._get_selected_pages(selected_page_ids, tree)
        
        # Group by space (becomes Shelf)
        pages_by_space = BookStackPreviewMapper._group_by_space(pages)
        
        shelves = []
        for space_key, space_pages in pages_by_space.items():
            space = tree.get_space(space_key)
            if not space:
                continue
            
            # Build space structure (space → shelf, pages organized into books/chapters)
            shelf_structure = BookStackPreviewMapper._build_space_structure(space, space_pages, selected_page_ids)
            shelves.append(shelf_structure)
        
        return {'shelves': shelves}
    
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
    def _build_space_structure(space: ConfluenceSpace, pages: List[ConfluencePage],
                                selected_ids: Set[str]) -> Dict[str, Any]:
        """Build hierarchical structure for a space."""
        # Find top-level pages (pages with no parent or parent not selected)
        top_level_pages = BookStackPreviewMapper._identify_top_level_pages(pages, selected_ids)
        
        books = []
        for page in top_level_pages:
            book = BookStackPreviewMapper._build_book_structure(page, selected_ids)
            if book:
                books.append(book)
        
        return {
            'name': space.name,
            'source_space_key': space.key,
            'books': books
        }
    
    @staticmethod
    def _identify_top_level_pages(pages: List[ConfluencePage],
                                  selected_ids: Set[str]) -> List[ConfluencePage]:
        """Identify pages that should become Books (top level in hierarchy)."""
        top_level = []
        
        for page in pages:
            # Page is top-level if:
            # 1. It has no parent, or
            # 2. Its parent is not selected (becomes root-level book)
            if not page.parent_id or page.parent_id not in selected_ids:
                top_level.append(page)
        
        return top_level
    
    @staticmethod
    def _build_book_structure(page: ConfluencePage, selected_ids: Set[str]) -> Optional[Dict[str, Any]]:
        """Build Book structure with Chapters and Pages."""
        if not page:
            return None
        
        # Get selected children
        selected_children = BookStackPreviewMapper._get_selected_children(page, selected_ids)
        
        chapters = []
        direct_pages = []
        
        for child in selected_children:
            # If child has its own selected children, it becomes a Chapter
            child_selected_children = BookStackPreviewMapper._get_selected_children(child, selected_ids)
            if child_selected_children:
                chapter = BookStackPreviewMapper._build_chapter_structure(child, selected_ids)
                if chapter:
                    chapters.append(chapter)
            else:
                # Child becomes a direct Page
                direct_pages.append({
                    'name': child.title,
                    'source_page_id': child.id
                })
        
        return {
            'name': page.title,
            'source_page_id': page.id,
            'chapters': chapters,
            'pages': direct_pages
        }
    
    @staticmethod
    def _build_chapter_structure(page: ConfluencePage, selected_ids: Set[str]) -> Optional[Dict[str, Any]]:
        """Build Chapter structure with Pages."""
        if not page:
            return None
        
        selected_children = BookStackPreviewMapper._get_selected_children(page, selected_ids)
        
        pages = []
        for child in selected_children:
            # Create page entry
            pages.append({
                'name': child.title,
                'source_page_id': child.id
            })
        
        return {
            'name': page.title,
            'source_page_id': page.id,
            'pages': pages
        }
    
    @staticmethod
    def _get_selected_children(page: ConfluencePage, selected_ids: Set[str]) -> List[ConfluencePage]:
        """Get children of page that are in selected_ids."""
        return [child for child in page.children if child.id in selected_ids]
    
    @staticmethod
    def format_preview_tree(preview: Dict[str, Any]) -> str:
        """Format preview tree as Rich markup string."""
        if not preview or not preview.get('shelves'):
            return "[dim]No content selected for preview[/dim]"
        
        lines = []
        
        for shelf in preview['shelves']:
            lines.append(f"\n[bold cyan]Shelf: {shelf['name']}[/bold cyan]")
            
            if not shelf['books']:
                lines.append("  [dim]No books selected[/dim]")
                continue
            
            for book_idx, book in enumerate(shelf['books']):
                is_last_book = book_idx == len(shelf['books']) - 1
                book_prefix = "└─" if is_last_book else "├─"
                lines.append(f"{book_prefix} [bold]Book: {book['name']}[/bold]")
                
                # Add direct pages
                if book['pages']:
                    for page_idx, page in enumerate(book['pages']):
                        is_last_page = page_idx == len(book['pages']) - 1 and not book['chapters']
                        page_prefix = "   └─" if is_last_page else "   ├─"
                        lines.append(f"{page_prefix} Page: {page['name']}")
                
                # Add chapters
                if book['chapters']:
                    for chapter_idx, chapter in enumerate(book['chapters']):
                        is_last_chap = chapter_idx == len(book['chapters']) - 1
                        chap_prefix = "   └─" if is_last_chap else "   ├─"
                        lines.append(f"{chap_prefix} [bold]Chapter: {chapter['name']}[/bold]")
                        
                        # Add chapter pages
                        if chapter['pages']:
                            for page_idx, page in enumerate(chapter['pages']):
                                is_last = page_idx == len(chapter['pages']) - 1
                                page_prefix = "      └─" if is_last else "      ├─"
                                lines.append(f"{page_prefix} Page: {page['name']}")
        
        return "\n".join(lines)
