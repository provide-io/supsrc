#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Log panel widget for capturing and displaying log messages in the TUI."""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from textual.widgets import RichLog

if TYPE_CHECKING:
    from textual.app import App


class TuiLogHandler(logging.Handler):
    """Custom logging handler that routes log messages to a TUI widget.

    This handler captures log messages and sends them to a LogPanel widget
    for display, preventing logs from corrupting the TUI display.
    """

    def __init__(self, app: App | None = None, max_buffer: int = 1000) -> None:
        """Initialize the TUI log handler.

        Args:
            app: The Textual app instance (can be set later)
            max_buffer: Maximum number of buffered messages before app is ready
        """
        super().__init__()
        self._app = app
        self._buffer: deque[tuple[str, str, str]] = deque(maxlen=max_buffer)
        self._widget: LogPanel | None = None

        # Set a simple format
        self.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
        )

    def set_app(self, app: App) -> None:
        """Set the app instance and flush buffered messages."""
        self._app = app

    def set_widget(self, widget: LogPanel) -> None:
        """Set the log panel widget and flush buffered messages."""
        self._widget = widget
        self._flush_buffer()

    def _flush_buffer(self) -> None:
        """Flush buffered messages to the widget."""
        if self._widget:
            for level, formatted, timestamp in self._buffer:
                self._widget.add_log_entry(level, formatted, timestamp)
            self._buffer.clear()

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the TUI widget."""
        try:
            formatted = self.format(record)
            level = record.levelname
            timestamp = datetime.now().strftime("%H:%M:%S")

            if self._widget:
                self._widget.add_log_entry(level, formatted, timestamp)
            else:
                # Buffer until widget is ready
                self._buffer.append((level, formatted, timestamp))

        except Exception:
            # Don't let logging errors crash the app
            self.handleError(record)


class LogPanel(RichLog):
    """A panel widget for displaying log messages in the TUI.

    This widget receives log messages from TuiLogHandler and displays
    them with color-coding based on log level.
    """

    LEVEL_STYLES: ClassVar[dict[str, str]] = {
        "DEBUG": "[dim]",
        "INFO": "[white]",
        "WARNING": "[yellow]",
        "ERROR": "[red]",
        "CRITICAL": "[bold red]",
    }

    LEVEL_ENDS: ClassVar[dict[str, str]] = {
        "DEBUG": "[/dim]",
        "INFO": "[/white]",
        "WARNING": "[/yellow]",
        "ERROR": "[/red]",
        "CRITICAL": "[/bold red]",
    }

    def __init__(self, *args, **kwargs) -> None:
        """Initialize the log panel."""
        super().__init__(*args, highlight=True, markup=True, **kwargs)
        self._entry_count = 0
        self._max_entries = 5000

    def add_log_entry(self, level: str, message: str, timestamp: str) -> None:
        """Add a log entry to the panel.

        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            message: The formatted log message
            timestamp: Timestamp string
        """
        # Escape any Rich markup in the message
        escaped_message = message.replace("[", "\\[")

        # Get style for this level
        style_open = self.LEVEL_STYLES.get(level, "")
        style_close = self.LEVEL_ENDS.get(level, "")

        # Format with color
        formatted = f"{style_open}{escaped_message}{style_close}"

        # Write to the log
        self.write(formatted)
        self._entry_count += 1

        # Auto-scroll to bottom
        self.scroll_end(animate=False)

    def clear_logs(self) -> None:
        """Clear all log entries."""
        self.clear()
        self._entry_count = 0


# Global handler instance for easy access
_tui_log_handler: TuiLogHandler | None = None


def get_tui_log_handler() -> TuiLogHandler:
    """Get or create the global TUI log handler."""
    global _tui_log_handler
    if _tui_log_handler is None:
        _tui_log_handler = TuiLogHandler()
    return _tui_log_handler


def install_tui_log_handler(level: int = logging.DEBUG) -> TuiLogHandler:
    """Install the TUI log handler on the root logger.

    This should be called early in TUI startup to capture all log messages.

    Args:
        level: Minimum log level to capture

    Returns:
        The installed handler
    """
    handler = get_tui_log_handler()
    handler.setLevel(level)

    # Add to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)

    return handler


# 🔼⚙️🔚
