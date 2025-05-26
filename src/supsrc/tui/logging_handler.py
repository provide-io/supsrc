#
# supsrc/tui/logging_handler.py
#
"""
Custom logging handler for integrating structlog output with the Textual TUI.
"""

import logging
import sys # Ensured import
from typing import TYPE_CHECKING, Any, Optional # Optional and Any might not be needed if not used elsewhere

import structlog # For ConsoleRenderer # Keep if structlog types are used, though not directly in this snippet
from rich.text import Text

# Assuming LogMessageUpdate is in supsrc.tui.messages
from supsrc.tui.messages import LogMessageUpdate

if TYPE_CHECKING:
    from supsrc.tui.app import SupsrcTuiApp


class TextualLogHandler(logging.Handler):
    """
    A logging handler that forwards formatted log records to a SupsrcTuiApp
    via a LogMessageUpdate message.
    """

    def __init__(self, app: "SupsrcTuiApp", level: int = logging.NOTSET) -> None:
        """
        Initialize the handler.

        Args:
            app: The SupsrcTuiApp instance to post messages to.
            level: The logging level for this handler.
        """
        super().__init__(level=level)
        self.app = app
        # self.renderer = structlog.dev.ConsoleRenderer(colors=True) # Removed as per instructions

    def emit(self, record: logging.LogRecord) -> None:
        try:
            repo_id = getattr(record, 'repo_id', 'SYSTEM')
            message_str: str = self.format(record).rstrip()

            # Check if string is empty after rstrip to avoid sending empty Text objects.
            if not message_str:
                return # Don't process or send empty messages

            rich_text = Text.from_ansi(message_str)
            
            log_update_msg = LogMessageUpdate(
                repo_id=repo_id,
                level=record.levelname,
                message=rich_text
            )
            
            # Check if self.app and post_message are available before calling
            if self.app and hasattr(self.app, 'post_message'):
                 self.app.post_message(log_update_msg)
            # else:
                 # Optionally, log to stderr if app is not available,
                 # but this might be too noisy for normal operation if it happens often.
                 # print(f"TextualLogHandler: TUI app not available for message: {message_str}", file=sys.stderr)

        except Exception:
            # Keep basic error handling for the handler itself.
            # This uses the standard library's handler error reporting.
            self.handleError(record)

# 🪵🎨
