# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Draggable splitter widget for resizing TUI panes."""

from __future__ import annotations

from textual.events import MouseDown, MouseMove, MouseUp
from textual.reactive import reactive
from textual.widgets import Static


class DraggableSplitter(Static):
    """A draggable splitter that can resize panes."""

    # Reactive for tracking drag state
    is_dragging: bool = reactive(False, init=False)

    def __init__(self, **kwargs) -> None:
        super().__init__("═══", **kwargs)
        self._drag_start_y = 0
        self._initial_repo_height = 60
        self._initial_log_height = 35

    def on_mouse_down(self, event: MouseDown) -> None:
        """Start dragging the splitter."""
        self.capture_mouse()
        self.is_dragging = True
        self._drag_start_y = event.screen_y

        # Get current heights
        try:
            repo_section = self.app.query_one("#repository_section")
            log_section = self.app.query_one("#log_section")

            # Extract height percentages
            repo_height_str = str(repo_section.styles.height)
            log_height_str = str(log_section.styles.height)

            if repo_height_str.endswith("%"):
                self._initial_repo_height = float(repo_height_str[:-1])
            if log_height_str.endswith("%"):
                self._initial_log_height = float(log_height_str[:-1])

        except Exception:
            # Fallback to default values
            self._initial_repo_height = 60
            self._initial_log_height = 35

    def on_mouse_move(self, event: MouseMove) -> None:
        """Handle splitter dragging."""
        if not self.is_dragging:
            return

        try:
            # Calculate movement delta
            delta_y = event.screen_y - self._drag_start_y

            # Get screen height to calculate percentage change
            screen_height = self.app.size.height - 6  # Account for header/footer
            if screen_height <= 0:
                return

            # Convert pixel movement to percentage
            percentage_change = (delta_y / screen_height) * 100

            # Calculate new heights
            new_repo_height = self._initial_repo_height + percentage_change
            new_log_height = self._initial_log_height - percentage_change

            # Constrain heights (min 15%, max 80%)
            new_repo_height = max(15, min(80, new_repo_height))
            new_log_height = max(15, min(80, new_log_height))

            # Ensure they add up reasonably (allowing for splitter space)
            total = new_repo_height + new_log_height
            if total > 95:  # Leave 5% for splitter and margins
                ratio = 95 / total
                new_repo_height *= ratio
                new_log_height *= ratio

            # Update pane heights
            repo_section = self.app.query_one("#repository_section")
            log_section = self.app.query_one("#log_section")

            repo_section.styles.height = f"{new_repo_height:.1f}%"
            log_section.styles.height = f"{new_log_height:.1f}%"

        except Exception:
            # Silently ignore errors during dragging
            pass

    def on_mouse_up(self, event: MouseUp) -> None:
        """Stop dragging the splitter."""
        self.release_mouse()
        self.is_dragging = False

        # Update stored heights to current values
        try:
            repo_section = self.app.query_one("#repository_section")
            log_section = self.app.query_one("#log_section")

            repo_height_str = str(repo_section.styles.height)
            log_height_str = str(log_section.styles.height)

            if repo_height_str.endswith("%"):
                self._initial_repo_height = float(repo_height_str[:-1])
            if log_height_str.endswith("%"):
                self._initial_log_height = float(log_height_str[:-1])
        except Exception:
            # Keep existing values if we can't read them
            pass

    def watch_is_dragging(self, is_dragging: bool) -> None:
        """Update appearance when dragging state changes."""
        if is_dragging:
            self.styles.background = "#666666"
        else:
            self.styles.background = "#444444"


# 🔼⚙️🔚
