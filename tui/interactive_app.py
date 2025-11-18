"""Main Textual application for interactive Confluence migration."""

from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Static

from models import DocumentationTree
from .confluence_tree import ConfluenceTreeView
from .preview_pane import PreviewPane
from .search_input import SearchInput
from .selection_store import SelectionStore
from .statistics_panel import StatisticsPanel


class InteractiveMigrationApp(App):
    """Main application for interactive Confluence content selection and migration."""
    
    TITLE = "Confluence to Markdown Migration - Interactive Mode"
    CSS_PATH = Path(__file__).with_name('interactive_app.css')
    
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("m", "migrate", "Migrate Selection", key_display="M"),
        Binding("a", "select_all", "Select All", key_display="A"),
        Binding("d", "deselect_all", "Deselect All", key_display="D"),
        Binding("/", "focus_search", "Search", key_display="/"),
        Binding("escape", "clear_search", "Clear Search"),
        Binding("?", "help", "Help", key_display="?"),
    ]
    
    def __init__(self, tree: DocumentationTree, config: Dict[str, Any]) -> None:
        """Initialize interactive app with DocumentationTree and configuration."""
        super().__init__()
        self.tree = tree
        self.config = config
        self.selection_result: Optional[Dict[str, Any]] = None
    
    def compose(self) -> ComposeResult:
        """Compose the UI layout."""
        yield Header()
        
        # Create and yield Store first
        store = SelectionStore(self.tree)
        yield store
        
        # Use store directly in other widgets
        yield Horizontal(
            Vertical(
                SearchInput(store),
                ConfluenceTreeView(self.tree, store),
                id="left-pane"
            ),
            Vertical(
                PreviewPane(self.tree, store, self.config),
                StatisticsPanel(self.tree, store),
                id="right-pane"
            )
        )
        
        yield Footer()
    
    def on_mount(self) -> None:
        """Set up the application after mounting."""
        self.notify("Select pages to migrate, then press 'm' to continue", severity="information")
        self.query_one(ConfluenceTreeView).focus()
    
    def action_quit(self) -> None:
        """Quit the application without selection."""
        self.selection_result = None
        self.notify("Migration cancelled", severity="warning")
        self.exit()
    
    def action_migrate(self) -> None:
        """Validate selection and exit with migration result."""
        is_valid, message = self._validate_selection()
        
        if not is_valid:
            self.notify(message, severity="error")
            return
        
        # Collect selection result
        store = self.query_one(SelectionStore)
        tree_view = self.query_one(ConfluenceTreeView)
        
        # Get full statistics
        statistics = store.get_statistics(self.tree)
        
        # Build result
        self.selection_result = {
            'selected_page_ids': list(store.selected_page_ids),
            'selected_space_keys': list(store.selected_space_keys),
            'statistics': statistics
        }
        
        # Show confirmation
        pages = statistics.get('total_pages', 0)
        spaces = statistics.get('selected_spaces', 0)
        attachments = statistics.get('total_attachments', 0)
        
        self.notify(
            f"Migration configured: {pages} pages, {spaces} spaces, {attachments} attachments",
            severity="information"
        )
        
        # Exit with result
        self.exit(self.selection_result)
    
    def action_select_all(self) -> None:
        """Select all visible pages."""
        tree_view = self.query_one(ConfluenceTreeView)
        tree_view.select_all_visible()
        self.notify("Selected all pages", severity="information")
    
    def action_deselect_all(self) -> None:
        """Deselect all pages."""
        tree_view = self.query_one(ConfluenceTreeView)
        tree_view.deselect_all()
        self.notify("Deselected all pages", severity="information")
    
    def action_focus_search(self) -> None:
        """Focus the search input."""
        search_input = self.query_one(SearchInput)
        search_input.focus()
    
    def action_clear_search(self) -> None:
        """Clear search filter and focus tree."""
        search_input = self.query_one(SearchInput)
        search_input.value = ""
        self.query_one(SelectionStore).set_filter("")
        self.query_one(ConfluenceTreeView).focus()
        self.notify("Search cleared", severity="information")
    
    def action_help(self) -> None:
        """Show help notification."""
        help_text = """[bold]Keyboard Shortcuts:[/bold]
[m] Migrate selected content
[q] Quit without migrating
[a] Select all visible pages
[d] Deselect all pages
[/] Focus search
[ESC] Clear search and focus tree
[?] Show this help
[SPACE/ENTER] Toggle selection on focused node
[ARROWS] Navigate tree

Checkbox states:
[✓] All descendants selected (green)
[~] Some descendants selected (yellow)
[ ] None selected (dim)
"""
        self.notify(help_text, severity="information", timeout=10)
    
    def _validate_selection(self) -> Tuple[bool, str]:
        """Validate that selection is non-empty."""
        store = self.query_one(SelectionStore)
        
        if not store.selected_page_ids:
            return False, "No pages selected. Please select at least one page to migrate."
        
        return True, "Selection valid"
    
    def on_interactive_migration_app_exit(self, result: Optional[Dict[str, Any]]) -> None:
        """Handle application exit with result."""
        if result:
            self.selection_result = result
