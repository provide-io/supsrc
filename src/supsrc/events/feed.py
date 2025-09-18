# src/supsrc/events/feed.py

"""
EventFeed widget for displaying events in the TUI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import RichLog

if TYPE_CHECKING:
    from supsrc.events.protocol import Event


class EventFeed(RichLog):
    """Widget for displaying events in the TUI.

    This widget can display any event that implements the Event protocol.
    It applies simple color coding based on the event source.
    """

    def add_event(self, event: Event) -> None:
        """Add an event to the feed for display.

        Args:
            event: Event to display
        """
        text = event.format()

        # Simple color mapping based on event source
        colors = {
            "git": "green",
            "monitor": "blue",
            "rules": "yellow",
            "tui": "cyan",
        }
        color = colors.get(event.source, "white")

        self.write(f"[{color}]{text}[/{color}]")
