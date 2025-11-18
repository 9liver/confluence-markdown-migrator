"""Search input widget with real-time filtering."""

from textual.widgets import Input
from textual.events import Key

from .selection_store import SelectionStore


class SearchInput(Input):
    """Search input widget for real-time filtering."""
    
    def __init__(self, store: SelectionStore, **kwargs) -> None:
        """Initialize search input with SelectionStore."""
        super().__init__(
            placeholder="Search pages and spaces...",
            **kwargs
        )
        self.store = store
    
    def on_input_changed(self, event) -> None:
        """Handle input change to update filter in real-time."""
        self.store.set_filter(event.value)
    
    def on_key(self, event: Key) -> None:
        """Handle keyboard shortcuts for search clearing."""
        # Ctrl+Backspace or Ctrl+H to clear search
        if event.key == "ctrl+backspace" or event.key == "ctrl+h":
            self.value = ""
            self.store.set_filter("")
            event.prevent_default()
            event.stop()
