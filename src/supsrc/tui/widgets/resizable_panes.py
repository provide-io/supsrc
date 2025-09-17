# src/supsrc/tui/widgets/resizable_panes.py

"""
Resizable panes widget for the TUI application.
"""

from __future__ import annotations

from textual.containers import Vertical
from textual.events import MouseEvent
from textual.reactive import reactive
from textual.widgets import Static


class ResizablePanes(Vertical):
    """A vertical container with resizable panes separated by a draggable splitter."""

    top_pane_height = reactive(70)  # Percentage of total height

    def __init__(self, *children, **kwargs) -> None:
        self._children_to_add = list(children)
        super().__init__(**kwargs)
        self._dragging = False
        self._drag_start_y = 0
        self._initial_height = 70

    def compose(self):
        """Compose the resizable panes."""
        # Top pane - direct widget without container wrapper
        if len(self._children_to_add) > 0:
            child = self._children_to_add[0]
            child.id = "top_pane"
            child.add_class("resizable-pane")
            yield child

        # Splitter
        yield ResizableSplitter(id="splitter")

        # Bottom pane - direct widget without container wrapper
        if len(self._children_to_add) > 1:
            child = self._children_to_add[1]
            child.id = "bottom_pane"
            child.add_class("resizable-pane")
            yield child

    def watch_top_pane_height(self, height: int) -> None:
        """Update pane heights when top pane height changes."""
        try:
            top_pane = self.query_one("#top_pane")
            bottom_pane = self.query_one("#bottom_pane")

            # Constrain height between 20% and 80%
            height = max(20, min(80, height))

            top_pane.styles.height = f"{height}%"
            bottom_pane.styles.height = f"{100 - height}%"
        except Exception:
            pass  # Widget might not be mounted yet


class ResizableSplitter(Static):
    """A draggable splitter between panes."""

    def __init__(self, **kwargs) -> None:
        super().__init__("═══", **kwargs)
        self.styles.height = 1
        self.styles.background = "#444444"
        self.styles.text_align = "center"

    def on_mouse_down(self, event: MouseEvent) -> None:
        """Start dragging the splitter."""
        self.capture_mouse()
        parent = self.parent
        if isinstance(parent, ResizablePanes):
            parent._dragging = True
            parent._drag_start_y = event.screen_y
            parent._initial_height = parent.top_pane_height

    def on_mouse_move(self, event: MouseEvent) -> None:
        """Handle splitter dragging."""
        parent = self.parent
        if isinstance(parent, ResizablePanes) and parent._dragging:
            # Calculate the new height based on mouse movement
            container_height = parent.content_size.height
            if container_height > 0:
                delta_y = event.screen_y - parent._drag_start_y
                delta_percent = (delta_y / container_height) * 100
                new_height = parent._initial_height + delta_percent
                parent.top_pane_height = new_height

    def on_mouse_up(self, event: MouseEvent) -> None:
        """Stop dragging the splitter."""
        self.release_mouse()
        parent = self.parent
        if isinstance(parent, ResizablePanes):
            parent._dragging = False
