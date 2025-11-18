"""Statistics panel widget displaying selection metrics."""

from typing import Any, Dict

from textual.reactive import reactive
from textual.widgets import Static

from models import DocumentationTree
from .selection_store import SelectionStore


class StatisticsPanel(Static):
    """Panel displaying selection statistics."""
    
    stats: reactive[Dict[str, Any]] = reactive({})
    
    def __init__(self, tree: DocumentationTree, store: SelectionStore, **kwargs) -> None:
        """Initialize statistics panel with tree and selection store."""
        super().__init__(**kwargs)
        self.tree = tree
        self.store = store
    
    def on_mount(self) -> None:
        """Initialize statistics on mount."""
        self.update_statistics()
    
    def render(self) -> str:
        """Render statistics as Rich markup."""
        if not self.stats:
            self.update_statistics()
        
        result = []
        result.append("[bold yellow underline]Selection Statistics[/bold yellow underline]")
        result.append("")
        
        if self.stats.get('total_pages', 0) == 0:
            result.append("[dim]No content selected[/dim]")
        else:
            # Pages
            pages = self.stats.get('total_pages', 0)
            pages_str = f"[bold green]{pages}[/bold green]" if pages > 0 else f"[dim]{pages}[/dim]"
            result.append(f"Pages: {pages_str}")
            
            # Spaces
            spaces = self.stats.get('selected_spaces', 0)
            spaces_str = f"[bold green]{spaces}[/bold green]" if spaces > 0 else f"[dim]{spaces}[/dim]"
            result.append(f"Spaces: {spaces_str}")
            
            # Attachments
            attachments = self.stats.get('total_attachments', 0)
            att_str = f"[bold green]{attachments}[/bold green]" if attachments > 0 else f"[dim]{attachments}[/dim]"
            result.append(f"Attachments: {att_str}")
            
            # Estimated size
            size_mb = self.stats.get('estimated_size_mb', 0)
            if size_mb > 0:
                size_str = f"[bold]{size_mb:.1f} MB[/bold]"
                result.append(f"Estimated Size: {size_str}")
        
        result.append("")
        return "\n".join(result)
    
    def update_statistics(self) -> None:
        """Update statistics from selection store."""
        self.stats = self.store.get_statistics(self.tree)
    
    def watch_stats(self, old: Dict[str, Any], new: Dict[str, Any]) -> None:
        """React to statistics changes."""
        self.refresh()
    
    def on_selection_changed(self, event) -> None:
        """Listen for selection changes and update statistics."""
        self.update_statistics()
