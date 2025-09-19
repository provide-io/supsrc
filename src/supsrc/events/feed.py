# src/supsrc/events/feed.py

"""
EventFeed widget for displaying events in the TUI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.widgets import RichLog
from provide.foundation.logger import get_logger

if TYPE_CHECKING:
    from supsrc.events.protocol import Event

log = get_logger("events.feed")


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
        try:
            text = event.format()
            log.warning(f"📝 EventFeed.add_event called with: {event.source} - {text[:50]}...")

            # Simple color mapping based on event source
            colors = {
                "git": "green",
                "monitor": "blue",
                "rules": "yellow",
                "tui": "cyan",
            }
            color = colors.get(event.source, "white")

            formatted_text = f"[{color}]{text}[/{color}]"
            self.write(formatted_text)
            log.warning(f"✍️ Written to EventFeed: {formatted_text[:50]}...")

            # Force a screen refresh to ensure the event is visible
            if hasattr(self, 'refresh'):
                self.refresh()
                log.warning("🔄 EventFeed refreshed after write")

            # Check widget state
            log.warning(f"📊 EventFeed state - visible: {getattr(self, 'visible', 'unknown')}, "
                       f"display: {getattr(self, 'display', 'unknown')}, "
                       f"line_count: {getattr(self, 'line_count', 'unknown')}")

            log.warning("✅ Event successfully processed by EventFeed")
        except Exception as e:
            log.error("Failed to add event to feed",
                     error=str(e),
                     event_source=getattr(event, 'source', 'unknown'),
                     exc_info=True)
