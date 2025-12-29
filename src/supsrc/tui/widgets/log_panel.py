#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Log panel widget for capturing and displaying log messages in the TUI."""

from __future__ import annotations

from collections import deque
from datetime import datetime
import io
import logging
import re
import sys
from typing import TYPE_CHECKING, ClassVar

from textual.widgets import RichLog

if TYPE_CHECKING:
    from textual.app import App


class TuiOutputStream(io.TextIOBase):
    """A custom output stream that captures writes and forwards to TUI log panel.

    This stream captures output from structlog/Foundation and routes it to the
    LogPanel widget instead of writing to the terminal.
    """

    def __init__(self, panel: LogPanel | None = None, max_buffer: int = 1000) -> None:
        """Initialize the TUI output stream.

        Args:
            panel: The LogPanel widget to send output to
            max_buffer: Maximum buffered lines before panel is ready
        """
        super().__init__()
        self._panel: LogPanel | None = panel
        self._buffer: deque[str] = deque(maxlen=max_buffer)
        self._line_buffer = ""

        # Pattern to detect log level from Foundation's format
        # Matches things like "[info     ]" or "[warning  ]" or "[error    ]"
        self._level_pattern = re.compile(r"\[(\w+)\s*\]")

    def set_panel(self, panel: LogPanel) -> None:
        """Set the panel and flush buffered output."""
        self._panel = panel
        self._flush_buffer()

    def _flush_buffer(self) -> None:
        """Flush buffered lines to the panel."""
        if self._panel:
            for line in self._buffer:
                self._write_to_panel(line)
            self._buffer.clear()

    def _detect_level(self, line: str) -> str:
        """Detect log level from a log line."""
        match = self._level_pattern.search(line)
        if match:
            level_name = match.group(1).upper().strip()
            if level_name in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "TRACE"):
                return level_name
        return "INFO"

    def _write_to_panel(self, line: str) -> None:
        """Write a line to the panel with appropriate styling."""
        if not line.strip():
            return

        level = self._detect_level(line)
        timestamp = datetime.now().strftime("%H:%M:%S")
        if self._panel:
            self._panel.add_log_entry(level, line.rstrip(), timestamp)

    def write(self, text: str) -> int:
        """Write text to the stream.

        Args:
            text: Text to write

        Returns:
            Number of characters written
        """
        if not text:
            return 0

        # Accumulate text in line buffer
        self._line_buffer += text

        # Process complete lines
        while "\n" in self._line_buffer:
            line, self._line_buffer = self._line_buffer.split("\n", 1)
            if line:  # Skip empty lines
                if self._panel:
                    self._write_to_panel(line)
                else:
                    self._buffer.append(line)

        return len(text)

    def flush(self) -> None:
        """Flush any remaining buffered content."""
        if self._line_buffer and self._line_buffer.strip():
            if self._panel:
                self._write_to_panel(self._line_buffer)
            else:
                self._buffer.append(self._line_buffer)
            self._line_buffer = ""

    def isatty(self) -> bool:
        """Return False - this is not a TTY."""
        return False

    @property
    def closed(self) -> bool:
        """Return False - stream is never closed."""
        return False

    def readable(self) -> bool:
        """Return False - not readable."""
        return False

    def writable(self) -> bool:
        """Return True - always writable."""
        return True

    def seekable(self) -> bool:
        """Return False - not seekable."""
        return False


# Global TUI output stream for Foundation
_tui_output_stream: TuiOutputStream | None = None


def get_tui_output_stream() -> TuiOutputStream:
    """Get or create the global TUI output stream."""
    global _tui_output_stream
    if _tui_output_stream is None:
        _tui_output_stream = TuiOutputStream()
    return _tui_output_stream


def redirect_foundation_to_tui() -> None:
    """Redirect Foundation's log stream to the TUI output stream.

    This should be called early in TUI startup before Foundation logs anything.
    """
    stream = get_tui_output_stream()

    try:
        # Redirect Foundation's log stream
        from provide.foundation.streams import set_log_stream_for_testing

        set_log_stream_for_testing(stream)
    except Exception:
        # If Foundation redirect fails, at least capture streams directly
        pass

    # Redirect both sys.stdout and sys.stderr to capture any direct writes
    # Save the originals for restoration later
    if not hasattr(sys, "_original_stdout"):
        sys._original_stdout = sys.stdout  # type: ignore[attr-defined]
    if not hasattr(sys, "_original_stderr"):
        sys._original_stderr = sys.stderr  # type: ignore[attr-defined]
    sys.stdout = stream
    sys.stderr = stream


def restore_streams() -> None:
    """Restore original stdout and stderr (call on TUI shutdown)."""
    if hasattr(sys, "_original_stdout"):
        sys.stdout = sys._original_stdout
        delattr(sys, "_original_stdout")
    if hasattr(sys, "_original_stderr"):
        sys.stderr = sys._original_stderr
        delattr(sys, "_original_stderr")


# Backward compatibility alias
restore_stderr = restore_streams


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
