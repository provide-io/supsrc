#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""TODO: Add module docstring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from provide.foundation.logger import get_logger
from textual.widgets import DataTable

from supsrc.events.feed_table.formatters import EventFormatter

if TYPE_CHECKING:
    from supsrc.events.protocol import Event

log = get_logger("events.feed_table")


class EventFeedTable(DataTable):
    """Widget for displaying events in a structured table format.

    This widget displays events in columns: Time, Repo, Emoji, Count, Files
    It provides a cleaner, more organized view than the simple text log.
    """

    # Enable focus for keyboard navigation
    can_focus = True

    def __init__(self, **kwargs) -> None:
        """Initialize the EventFeedTable with columns."""
        super().__init__(
            cursor_type="row",
            zebra_stripes=True,
            header_height=1,
            show_row_labels=False,
            **kwargs,
        )

    def on_mount(self) -> None:
        """Initialize the EventFeedTable when mounted."""
        # Set up columns with proper proportions
        self.add_column("⏰", width=8)  # Time - HH:MM:SS format
        self.add_column("📦", width=8)  # Source/Repo - Repository identifier
        self.add_column("🎯", width=3)  # Operation - Operation type emoji
        self.add_column("#️⃣", width=5)  # Impact - Numerical impact
        self.add_column("📄", width=20)  # Files - Affected files
        self.add_column("💬")  # Message - Auto-size remaining space

        # Add initial message to show the widget is ready
        self.add_row(
            "--:--:--",
            "system",
            "📋",
            "1",
            "Ready",
            "EventFeed initialized",
            key="ready_message",
        )

        self.add_row(
            "--:--:--",
            "system",
            "🚀",
            "1",
            "startup",
            "Widget mounted",
            key="mounted_message",
        )

    def add_event(self, event: Event) -> None:
        """Add an event to the feed table.

        Args:
            event: Event to display
        """
        try:
            # Extract basic information
            time_str = event.timestamp.strftime("%H:%M:%S")
            repo_id = EventFormatter.extract_repo_id(event)
            operation_emoji = EventFormatter.get_event_emoji(event)
            impact_str, file_str, message_str = EventFormatter.format_event_details(event)

            # Add row to table
            self.add_row(
                time_str,
                repo_id,
                operation_emoji,
                impact_str,
                file_str,
                message_str,
                key=f"event_{event.timestamp.isoformat()}",
            )

            # Scroll to show the latest event
            self.scroll_end()

        except Exception as e:
            log.error(
                "Failed to add event to feed table",
                error=str(e),
                event_source=getattr(event, "source", "unknown"),
                exc_info=True,
            )

    def clear(self) -> None:
        """Clear all events from the table."""
        # Clear all rows but keep columns
        for row_key in list(self.rows.keys()):
            self.remove_row(row_key)

        # Add back the ready message
        self.add_row(
            "--:--:--",
            "system",
            "🧹",
            "1",
            "cleared",
            "Event feed cleared",
            key="cleared_message",
        )

    # Keyboard navigation methods (inherited from DataTable should work)
    def key_up(self) -> None:
        """Handle up arrow key for scrolling."""
        self.cursor_coordinate = (max(0, self.cursor_coordinate.row - 1), 0)

    def key_down(self) -> None:
        """Handle down arrow key for scrolling."""
        max_row = self.row_count - 1
        self.cursor_coordinate = (min(max_row, self.cursor_coordinate.row + 1), 0)

    def key_page_up(self) -> None:
        """Handle page up key for scrolling."""
        new_row = max(0, self.cursor_coordinate.row - 10)
        self.cursor_coordinate = (new_row, 0)

    def key_page_down(self) -> None:
        """Handle page down key for scrolling."""
        max_row = self.row_count - 1
        new_row = min(max_row, self.cursor_coordinate.row + 10)
        self.cursor_coordinate = (new_row, 0)

    def key_home(self) -> None:
        """Handle home key for scrolling."""
        self.cursor_coordinate = (0, 0)

    def key_end(self) -> None:
        """Handle end key for scrolling."""
        max_row = max(0, self.row_count - 1)
        self.cursor_coordinate = (max_row, 0)


# 🔼⚙️🔚
