"""Reactive state store for managing selection state across TUI widgets."""

from typing import Any, Dict, List, Optional, Set
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import Static

from models import DocumentationTree, ConfluencePage


class SelectionChanged(Message):
    """Message posted when selection state changes."""
    
    def __init__(self, selected_page_ids: Set[str], selected_space_keys: Set[str]) -> None:
        """Initialize selection changed message."""
        self.selected_page_ids = selected_page_ids
        self.selected_space_keys = selected_space_keys
        super().__init__()


class FilterChanged(Message):
    """Message posted when filter query changes."""
    
    def __init__(self, query: str) -> None:
        """Initialize filter changed message."""
        self.query = query
        super().__init__()


class SelectionStore(Static):
    """Reactive store for managing selection state."""
    
    selected_page_ids: reactive[Set[str]] = reactive(set)
    selected_space_keys: reactive[Set[str]] = reactive(set)
    filter_query: reactive[str] = reactive("")
    
    def __init__(self, tree: DocumentationTree, **kwargs) -> None:
        """Initialize selection store with DocumentationTree."""
        super().__init__(**kwargs)
        self.tree = tree
    
    def toggle_page(self, page_id: str, page: ConfluencePage) -> None:
        """Toggle page selection (recursive for descendants)."""
        if page_id in self.selected_page_ids:
            self._deselect_page_recursive(page_id, page)
        else:
            self._select_page_recursive(page_id, page)
        
        self.post_message(SelectionChanged(self.selected_page_ids, self.selected_space_keys))
    
    def toggle_space(self, space_key: str, pages: List[ConfluencePage]) -> None:
        """Toggle entire space selection."""
        if space_key in self.selected_space_keys:
            # Deselect all pages in space
            for page in pages:
                self._deselect_page_recursive(page.id, page)
            self.selected_space_keys.discard(space_key)
        else:
            # Select all pages in space
            for page in pages:
                self._select_page_recursive(page.id, page)
            self.selected_space_keys.add(space_key)
        
        self.post_message(SelectionChanged(self.selected_page_ids, self.selected_space_keys))
    
    def is_page_selected(self, page_id: str) -> bool:
        """Check if page is selected."""
        return page_id in self.selected_page_ids
    
    def is_space_selected(self, space_key: str) -> bool:
        """Check if space is selected (explicit or all pages selected)."""
        if space_key in self.selected_space_keys:
            return True
        space = self.tree.get_space(space_key)
        if not space:
            return False
        all_page_ids = {p.id for p in space.get_all_pages()}
        if not all_page_ids:
            return False
        selected_in_space = self.selected_page_ids & all_page_ids
        return len(selected_in_space) == len(all_page_ids)
    
    def get_space_selection_state(self, space_key: str) -> str:
        """Get tri-state for space: 'all', 'some', 'none'."""
        space = self.tree.get_space(space_key)
        if not space:
            return 'none'
        all_ids = {p.id for p in space.get_all_pages()}
        if not all_ids:
            return 'none'
        selected_count = len(self.selected_page_ids & all_ids)
        if selected_count == 0:
            return 'none'
        elif selected_count == len(all_ids):
            return 'all'
        else:
            return 'some'
    
    def get_selection_state(self, page: ConfluencePage) -> str:
        """Get tri-state selection state: 'all', 'some', or 'none'."""
        descendant_ids = self._get_all_descendant_ids(page)
        if not descendant_ids:
            return 'all' if page.id in self.selected_page_ids else 'none'
        
        selected_count = sum(1 for pid in descendant_ids if pid in self.selected_page_ids)
        
        if selected_count == 0:
            return 'none'
        elif selected_count == len(descendant_ids):
            return 'all'
        else:
            return 'some'
    
    def set_filter(self, query: str) -> None:
        """Set search filter query."""
        self.filter_query = query.lower().strip()
        self.post_message(FilterChanged(self.filter_query))
    
    def select_all_pages(self, page_ids: Set[str]) -> None:
        """Bulk select pages and trigger reactive update."""
        if page_ids:
            self.selected_page_ids.update(page_ids)
            # Reassign to trigger reactive watcher
            self.selected_page_ids = self.selected_page_ids.copy()
            # Update space selections if fully selected
            for space_key in self.tree.spaces:
                space = self.tree.spaces[space_key]
                space_page_ids = {p.id for p in space.get_all_pages()}
                if space_page_ids and space_page_ids.issubset(self.selected_page_ids):
                    self.selected_space_keys.add(space_key)
            # Reassign to trigger watcher
            self.selected_space_keys = self.selected_space_keys.copy()
    
    def deselect_all_pages(self) -> None:
        """Bulk deselect all and trigger reactive update."""
        if self.selected_page_ids:
            self.selected_page_ids.clear()
            self.selected_space_keys.clear()
            # Force reactive update by reassignment
            self.selected_page_ids = set()
            self.selected_space_keys = set()
            # Watcher will post SelectionChanged
    
    def get_statistics(self, tree: DocumentationTree) -> Dict[str, Any]:
        """Calculate selection statistics."""
        total_pages = len(self.selected_page_ids)
        selected_spaces = len(self.selected_space_keys)
        
        # Count attachments for selected pages
        total_attachments = 0
        for space in tree.spaces.values():
            for page in space.get_all_pages():
                if page.id in self.selected_page_ids:
                    total_attachments += len(page.attachments)
        
        # Estimate size (very rough: assume 1KB per page + 100KB per attachment)
        estimated_size_kb = (total_pages * 1) + (total_attachments * 100)
        
        return {
            'total_pages': total_pages,
            'selected_spaces': selected_spaces,
            'total_attachments': total_attachments,
            'estimated_size_mb': estimated_size_kb / 1024
        }
    
    def _select_page_recursive(self, page_id: str, page: ConfluencePage) -> None:
        """Recursively select page and all descendants."""
        self.selected_page_ids.add(page_id)
        
        # Also select all children
        for child in page.children:
            self._select_page_recursive(child.id, child)
        # Trigger reactive watcher
        self.selected_page_ids = self.selected_page_ids.copy()
    
    def _deselect_page_recursive(self, page_id: str, page: ConfluencePage) -> None:
        """Recursively deselect page and all descendants."""
        self.selected_page_ids.discard(page_id)
        
        # Also deselect all children
        for child in page.children:
            self._deselect_page_recursive(child.id, child)
        # Trigger reactive watcher
        self.selected_page_ids = self.selected_page_ids.copy()
    
    def _get_all_descendant_ids(self, page: ConfluencePage) -> Set[str]:
        """Get all descendant page IDs recursively."""
        descendant_ids = {page.id}
        for child in page.children:
            descendant_ids.update(self._get_all_descendant_ids(child))
        return descendant_ids


# Reactive watchers

    def watch_selected_page_ids(self, old: Set[str], new: Set[str]) -> None:
        """React to page selection changes."""
        self.post_message(SelectionChanged(self.selected_page_ids, self.selected_space_keys))
    
    def watch_selected_space_keys(self, old: Set[str], new: Set[str]) -> None:
        """React to space selection changes."""
        self.post_message(SelectionChanged(self.selected_page_ids, self.selected_space_keys))
    
    def watch_filter_query(self, old: str, new: str) -> None:
        """React to filter query changes."""
        self.post_message(FilterChanged(self.filter_query))
