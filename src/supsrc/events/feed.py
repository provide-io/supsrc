#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""EventFeed widget for displaying events in the TUI."""

from __future__ import annotations

from typing import TYPE_CHECKING

from provide.foundation.logger import get_logger
from rich.text import Text
from textual.widgets import RichLog

if TYPE_CHECKING:
    from supsrc.events.protocol import Event

log = get_logger("events.feed")


class EventFeed(RichLog):
    """Widget for displaying events in the TUI.

    This widget can display any event that implements the Event protocol.
    It applies simple color coding based on the event source.
    """

    # Enable focus for keyboard navigation
    can_focus = True

    def on_mount(self) -> None:
        """Initialize the EventFeed widget when mounted."""
        # Add an initial message to show the widget is ready
        self.write(Text.from_markup("[bold yellow]📋 EventFeed Ready - Events will appear here[/bold yellow]"))
        self.write(Text.from_markup("[dim]📅 Widget mounted at startup[/dim]"))

        # Ensure the widget scrolls to show new content
        self.scroll_end()

    def add_event(self, event: Event) -> None:
        """Add an event to the feed for display.

        Args:
            event: Event to display
        """
        try:
            text = event.format()

            # Simple color mapping based on event source
            colors = {
                "git": "green",
                "monitor": "blue",
                "rules": "yellow",
                "tui": "cyan",
            }
            color = colors.get(event.source, "white")

            formatted_text = f"[{color}]{text}[/{color}]"
            self.write(Text.from_markup(formatted_text))

            # Scroll to the end to show new events
            self.scroll_end()
        except Exception as e:
            log.error(
                "Failed to add event to feed",
                error=str(e),
                event_source=getattr(event, "source", "unknown"),
                exc_info=True,
            )

    def key_up(self) -> None:
        """Handle up arrow key for scrolling."""
        self.scroll_up()

    def key_down(self) -> None:
        """Handle down arrow key for scrolling."""
        self.scroll_down()

    def key_page_up(self) -> None:
        """Handle page up key for scrolling."""
        self.scroll_relative(y=-10)

    def key_page_down(self) -> None:
        """Handle page down key for scrolling."""
        self.scroll_relative(y=10)

    def key_home(self) -> None:
        """Handle home key for scrolling."""
        self.scroll_home()

    def key_end(self) -> None:
        """Handle end key for scrolling."""
        self.scroll_end()


# 🔼⚙️🔚
