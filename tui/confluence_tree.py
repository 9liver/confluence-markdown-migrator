"""Custom Tree widget for Confluence hierarchy with checkbox rendering."""

from typing import Any, Dict, List, Optional

from textual.widgets import Tree

from ..models import DocumentationTree, ConfluenceSpace, ConfluencePage
from .selection_store import SelectionStore, FilterChanged


class ConfluenceTreeView(Tree[Dict[str, Any]]):
    """Tree view for Confluence hierarchy with tri-state checkbox rendering."""
    
    def __init__(self, tree: DocumentationTree, store: SelectionStore, **kwargs) -> None:
        """Initialize tree view with DocumentationTree and SelectionStore."""
        super().__init__("Confluence Content", **kwargs)
        self.doc_tree = tree
        self.store = store
        self.data = {}  # Store node data for reference
    
    def on_mount(self) -> None:
        """Build full tree when mounted."""
        self.build_full_tree()
    
    def build_full_tree(self) -> None:
        """Build complete Confluence tree from DocumentationTree."""
        self.clear()
        root = self.root
        
        for space_key, space in self.doc_tree.spaces.items():
            space_node = root.add(
                self._render_space_label(space),
                data={'type': 'space', 'space_key': space_key, 'space': space}
            )
            space_node.expand()
            
            # Add pages recursively
            for page in space.pages:
                self._add_page_node(space_node, page)
    
    def build_filtered_tree(self, query: str) -> None:
        """Rebuild tree with only nodes matching search query."""
        if not query:
            self.build_full_tree()
            return
        
        self.clear()
        root = self.root
        
        for space_key, space in self.doc_tree.spaces.items():
            # Check if space matches filter or has matching pages
            if self._space_matches_filter(space, query):
                space_node = root.add(
                    self._render_space_label(space),
                    data={'type': 'space', 'space_key': space_key, 'space': space}
                )
                space_node.expand()
                
                # Add all pages (they'll be filtered recursively)
                for page in space.pages:
                    self._add_page_node(space_node, page)
            else:
                # Check if any pages match
                matching_pages = []
                for page in space.pages:
                    matching = self._get_matching_pages(page, query)
                    matching_pages.extend(matching)
                
                if matching_pages:
                    space_node = root.add(
                        self._render_space_label(space),
                        data={'type': 'space', 'space_key': space_key, 'space': space}
                    )
                    space_node.expand()
                    
                    # Add matching pages with their ancestors to preserve hierarchy
                    added_pages = set()
                    for page in matching_pages:
                        self._add_page_with_ancestors(space_node, page, added_pages)
    
    def _add_page_node(self, parent_node, page: ConfluencePage) -> None:
        """Recursively add page node with children."""
        page_node = parent_node.add(
            self._render_page_label(page),
            data={'type': 'page', 'page': page, 'page_id': page.id}
        )
        
        for child in page.children:
            self._add_page_node(page_node, child)
    
    def _render_space_label(self, space: ConfluenceSpace) -> str:
        """Render space label with tri-state checkbox reflecting page selection."""
        state = self.store.get_space_selection_state(space.key)
        if state == 'all':
            check = "[bold green]✓[/bold green]"
        elif state == 'some':
            check = "[bold yellow]~[/bold yellow]"
        else:
            check = "[dim] [/dim]"
        return f"[{check}] Space: {space.name} ([dim]{space.key}[/dim])"
    
    def _render_page_label(self, page: ConfluencePage) -> str:
        """Render page label with tri-state checkbox."""
        state = self.store.get_selection_state(page)
        
        if state == 'all':
            check = "[bold green]✓[/bold green]"
        elif state == 'some':
            check = "[bold yellow]~[/bold yellow]"
        else:
            check = "[dim] [/dim]"
        
        label = page.title
        if not label:
            label = "Untitled"
        
        return f"[{check}] {label}"
    
    def _space_matches_filter(self, space: ConfluenceSpace, query: str) -> bool:
        """Check if space matches search query."""
        if not query:
            return True
        
        query = query.lower()
        return (
            query in space.name.lower() or
            query in space.key.lower() or
            query in space.description.lower()
        )
    
    def _page_matches_filter(self, page: ConfluencePage, query: str) -> bool:
        """Check if page matches search query or has matching descendants."""
        if not query:
            return True
        
        query = query.lower()
        
        # Check page itself
        if query in page.title.lower():
            return True
        
        # Check children
        for child in page.children:
            if self._page_matches_filter(child, query):
                return True
        
        return False
    
    def _get_matching_pages(self, page: ConfluencePage, query: str) -> List[ConfluencePage]:
        """Find all pages matching query in subtree."""
        matching = []
        
        if self._page_matches_filter(page, query):
            matching.append(page)
        
        for child in page.children:
            matching.extend(self._get_matching_pages(child, query))
        
        return matching
    
    def _add_page_with_ancestors(self, parent_node, page: ConfluencePage, added_pages: set) -> None:
        """Add page with all its ancestors to preserve hierarchy."""
        if page.id in added_pages:
            return
        
        # Find parent node by ID
        insertion_parent = parent_node
        if page.parent_id:
            for sibling in parent_node.children:
                if sibling.data and 'page' in sibling.data:
                    sibling_page = sibling.data['page']
                    if isinstance(sibling_page, ConfluencePage) and sibling_page.id == page.parent_id:
                        insertion_parent = sibling
                        break
        
        # Add parent first if not found
        if page.parent_id and insertion_parent == parent_node:
            parent_page = self._find_page_by_id(page.parent_id)
            if parent_page:
                self._add_page_with_ancestors(parent_node, parent_page, added_pages)
                # After adding parent, find it for correct insertion
                for sibling in parent_node.children:
                    if sibling.data and 'page' in sibling.data:
                        sibling_page = sibling.data['page']
                        if isinstance(sibling_page, ConfluencePage) and sibling_page.id == page.parent_id:
                            insertion_parent = sibling
                            break
        
        # Add the page
        page_node = insertion_parent.add(
            self._render_page_label(page),
            data={'type': 'page', 'page': page, 'page_id': page.id}
        )
        added_pages.add(page.id)
    
    def _find_page_by_id(self, page_id: str) -> Optional[ConfluencePage]:
        """Find page by ID across all spaces."""
        for space in self.doc_tree.spaces.values():
            for page in space.get_all_pages():
                if page.id == page_id:
                    return page
        return None
    
    def select_all_visible(self) -> None:
        """Select all visible page nodes in current tree (respects filter)."""
        visible_ids = set()
        
        def collect_ids(node):
            if node.data and node.data.get('type') == 'page':
                page = node.data['page']
                # Add the page itself
                visible_ids.add(page.id)
                # Add all descendants (even if not visible) to maintain hierarchy
                descendant_ids = self.store._get_all_descendant_ids(page)
                visible_ids.update(descendant_ids)
            
            for child in node.children:
                collect_ids(child)
        
        collect_ids(self.root)
        
        # If there's a filter, only select pages that match the filter
        if self.store.filter_query:
            filtered_ids = set()
            for page_id in visible_ids:
                page = self._find_page_by_id(page_id)
                if page and self._page_matches_filter(page, self.store.filter_query):
                    filtered_ids.add(page_id)
            visible_ids = filtered_ids
        
        self.store.select_all_pages(visible_ids)
        self.refresh()
    
    def deselect_all(self) -> None:
        """Deselect all pages."""
        self.store.deselect_all_pages()
        self.refresh()


# Reactive message handlers

    def watch_data(self) -> None:
        """React to data changes."""
        self.refresh()

    def on_filter_changed(self, message: FilterChanged) -> None:
        """Handle filter changes and rebuild the tree."""
        self.apply_filter(message.query)
        # Expand first node and focus for better UX
        if message.query:
            if self.root.children:
                first_node = self.root.children[0]
                first_node.expand()
                self.set_focus(first_node)


    def on_tree_node_selected(self, event) -> None:
        """Handle tree node selection with click-to-toggle."""
        node = event.node
        
        if node.data:
            if node.data.get('type') == 'space':
                space = node.data['space']
                self.store.toggle_space(space.key, space.pages)
            elif node.data.get('type') == 'page':
                page = node.data['page']
                self.store.toggle_page(page.id, page)
        
        # Refresh to update checkboxes
        self.refresh()
    
    def apply_filter(self, query: str) -> None:
        """Apply search filter to tree."""
        if query:
            self.build_filtered_tree(query)
        else:
            self.build_full_tree()
