
# supsrc/telemetry/logger/base.py
# -*- coding: utf-8 -*-

"""
Base logging setup for the supsrc application using Rich.

Provides the core configuration function, formatter, and helpers.
"""

import cattrs
import logging
import sys
from typing import Optional

# --- Third-party Libraries ---
try:
    import rich.logging
    from rich.traceback import install as install_rich_tracebacks
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    # Define dummy handler if rich is not available
    class DummyRichHandler(logging.Handler):
        def emit(self, record): print(self.format(record), file=sys.stderr)

# --- Constants ---
BASE_LOGGER_NAME = "supsrc" # Parent logger for the application
DEFAULT_LOG_FORMAT = "[%Y-%m-%dT%H:%M:%S.%f]" # Timestamp format

# --- Logging Emojis ---
LOG_EMOJIS = {
    logging.DEBUG: "🐛",
    logging.INFO: "ℹ️",
    logging.WARNING: "⚠️",
    logging.ERROR: "❌",
    logging.CRITICAL: "💥",
    "load": "📄",
    "validate": "✅",
    "fail": "🚫",
    "path": "📁",
    "time": "⏱️",
    "success": "🎉", # Generic success
    "general": "➡️", # Generic fallback
}

# --- Helper Functions ---
def get_emoji(record: logging.LogRecord) -> str:
    """Gets appropriate emoji based on level or extra key."""
    if hasattr(record, "emoji_key") and record.emoji_key in LOG_EMOJIS:
        return LOG_EMOJIS[record.emoji_key]
    return LOG_EMOJIS.get(record.levelno, LOG_EMOJIS["general"])

# --- Custom Log Formatter for Rich ---
class RichLogFormatter(logging.Formatter):
    """Custom formatter for RichHandler: <emoji> | <padded_name> | <message>"""
    def format(self, record: logging.LogRecord) -> str:
        emoji = get_emoji(record)
        logger_name = record.name
        # Ensure name starts relative to base logger if possible for padding
        if logger_name.startswith(BASE_LOGGER_NAME + "."):
            logger_name = logger_name[len(BASE_LOGGER_NAME) + 1:]

        if len(logger_name) > 32:
            logger_name = "..." + logger_name[-29:] # Truncate with ellipsis
        padded_name = f"{logger_name:<32}" # Pad to 32

        message = record.getMessage()
        # Note: Assumes message doesn't contain unintended Rich markup.
        return f"{emoji} | {padded_name} | {message}"

# --- Core Setup Function ---
def setup_logging(level: int = logging.INFO, log_file: Optional[str] = None) -> None:
    """
    Configures logging for the entire supsrc application.

    Sets up handlers (console, optional file) and formatters, using Rich
    if available. Configures the base 'supsrc' logger.

    Args:
        level: The minimum logging level to output (e.g., logging.DEBUG, logging.INFO).
        log_file: Optional path to a file for logging output.
    """
    log_level_name = logging.getLevelName(level)
    base_logger = logging.getLogger(BASE_LOGGER_NAME)
    base_logger.handlers.clear() # Remove existing handlers to prevent duplication
    base_logger.setLevel(level)  # Set level on the base logger

    handlers: list[logging.Handler] = []

    # Configure Console Handler (Rich or Basic)
    if RICH_AVAILABLE:
        print(f"--- Setting up Rich logging (Level: {log_level_name}) ---", file=sys.stderr)
        # Install rich tracebacks
        install_rich_tracebacks(
            theme="compact",
            show_locals=False,
            # Suppress internal frames from common libraries if desired
            suppress=[cattrs] if 'cattrs' in sys.modules else []
        )

        console_handler = rich.logging.RichHandler(
            level=level,
            show_level=False, # Hide level name per request
            show_path=False,
            markup=True,
            rich_tracebacks=True,
            tracebacks_theme="compact",
            tracebacks_show_locals=False,
            tracebacks_suppress=[cattrs] if 'cattrs' in sys.modules else [],
            log_time_format=DEFAULT_LOG_FORMAT,
        )
        console_handler.setFormatter(RichLogFormatter())
        handlers.append(console_handler)
    else:
        print(f"--- Rich library not found. Basic console logging (Level: {log_level_name}) ---", file=sys.stderr)
        console_handler = DummyRichHandler(level=level) # Use basic fallback handler
        # Basic formatter for fallback console
        formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    # Configure File Handler (Optional)
    if log_file:
        try:
            print(f"--- Setting up file logging to '{log_file}' (Level: {log_level_name}) ---", file=sys.stderr)
            # Use a basic formatter for the file to keep it clean
            file_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(name)-32s | %(message)s',
                datefmt='%Y-%m-%dT%H:%M:%S.%f%z' # ISO format with timezone
            )
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(level)
            file_handler.setFormatter(file_formatter)
            handlers.append(file_handler)
        except Exception as e:
            print(f"--- Failed to setup file logging to '{log_file}': {e} ---", file=sys.stderr)

    # Add configured handlers to the base logger
    for handler in handlers:
        base_logger.addHandler(handler)

    # Log initial message using the configured base logger
    base_logger.info(f"Logging initialized (Level: {log_level_name}, Rich: {RICH_AVAILABLE}, File: '{log_file or 'None'}')")

# --- Initial Logger Instance ---
# This gets the base logger instance, which will be configured by setup_logging.
# Other modules will typically get their own loggers via logging.getLogger(__name__)
# or logging.getLogger('supsrc.module'), inheriting config from 'supsrc'.
_initial_logger = logging.getLogger(BASE_LOGGER_NAME)

# Optional: Add a basic handler during import time for critical errors before setup?
# Generally avoided unless absolutely necessary, setup should happen early.
# _initial_logger.addHandler(logging.NullHandler()) # Prevents "No handler found" warnings if used before setup
