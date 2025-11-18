"""Target-aware preview pane widget displaying destination structure."""

from typing import Any, Dict, Optional

from textual.reactive import reactive
from textual.widgets import Static

from ...models import DocumentationTree
from .preview_mappers import BookStackPreviewMapper, WikiJsPreviewMapper
from .selection_store import SelectionStore


class PreviewPane(Static):
    """Preview pane showing destination structure based on export target."""
    
    preview_content: reactive[str] = reactive("")
    
    def __init__(self, tree: DocumentationTree, store: SelectionStore, config: Dict[str, Any], **kwargs) -> None:
        """Initialize preview pane with tree, store, and configuration."""
        super().__init__(**kwargs)
        self.tree = tree
        self.store = store
        
        # Determine export target from config
        self.export_target = config.get('migration', {}).get('export_target', 'markdown_files')
    
    def render(self) -> str:
        """Render preview content or placeholder."""
        if self.preview_content:
            return self.preview_content
        
        return "[dim]Select pages from the tree to see preview[/dim]"
    
    def update_preview(self) -> None:
        """Update preview based on current selection and export target."""
        # Check if any pages selected
        if not self.store.selected_page_ids:
            self.preview_content = ""
            return
        
        # Handle both_wikis as special case
        if self.export_target == 'both_wikis':
            wikijs_text = ""
            bookstack_text = ""
            
            try:
                wikijs_preview = WikiJsPreviewMapper.build_preview(
                    self.store.selected_page_ids, self.tree
                )
                wikijs_text = WikiJsPreviewMapper.format_preview_tree(wikijs_preview)
            except Exception as e:
                wikijs_text = f"[red]Wiki.js preview error: {e}[/red]"
            
            try:
                bookstack_preview = BookStackPreviewMapper.build_preview(
                    self.store.selected_page_ids, self.tree
                )
                bookstack_text = BookStackPreviewMapper.format_preview_tree(bookstack_preview)
            except Exception as e:
                bookstack_text = f"[red]BookStack preview error: {e}[/red]"
            
            divider = "\n" + "─" * 50 + "\n"
            self.preview_content = (
                f"[bold cyan underline]Wiki.js Destination Preview[/bold cyan underline]\n"
                f"{wikijs_text}{divider}"
                f"[bold cyan underline]BookStack Destination Preview[/bold cyan underline]\n"
                f"{bookstack_text}"
            )
            return
        
        # Generate preview based on export target for single targets
        if self.export_target == 'markdown_files':
            self.preview_content = "[dim]Preview not available for markdown_files export[/dim]"
        elif self.export_target == 'wikijs':
            self._generate_wikijs_preview()
        elif self.export_target == 'bookstack':
            self._generate_bookstack_preview()
        else:
            self.preview_content = "[dim]Unknown export target[/dim]"
    
    def _generate_wikijs_preview(self) -> None:
        """Generate Wiki.js preview."""
        preview_dict = WikiJsPreviewMapper.build_preview(
            self.store.selected_page_ids,
            self.tree
        )
        
        preview_text = WikiJsPreviewMapper.format_preview_tree(preview_dict)
        
        title = "[bold cyan underline]Wiki.js Destination Preview[/bold cyan underline]"
        self.preview_content = f"{title}\n{preview_text}"
    
    def _generate_bookstack_preview(self) -> None:
        """Generate BookStack preview."""
        preview_dict = BookStackPreviewMapper.build_preview(
            self.store.selected_page_ids,
            self.tree
        )
        
        preview_text = BookStackPreviewMapper.format_preview_tree(preview_dict)
        
        title = "[bold cyan underline]BookStack Destination Preview[/bold cyan underline]"
        self.preview_content = f"{title}\n{preview_text}"
    
    def watch_preview_content(self, old: str, new: str) -> None:
        """React to preview content changes."""
        self.refresh()
    
    def on_selection_changed(self, event) -> None:
        """Listen for selection changes and update preview."""
        self.update_preview()
