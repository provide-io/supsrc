# src/supsrc/telemetry/logger/base.py
# -*- coding: utf-8 -*-
"""
Base logging setup for the supsrc application using structlog.
"""

import logging
import sys
import structlog
from structlog.typing import FilteringBoundLogger
from typing import Optional

from supsrc.telemetry.logger.processors import (
    add_emoji_processor,
    add_padded_logger_processor,
    remove_extra_keys_processor,
)

# --- Constants ---
BASE_LOGGER_NAME = "supsrc" # Used for filtering/formatting
# Emojis remain useful for the custom processor
LOG_EMOJIS = {
    logging.DEBUG: "🐛", logging.INFO: "ℹ️", logging.WARNING: "⚠️",
    logging.ERROR: "❌", logging.CRITICAL: "💥",
    "load": "📄", "validate": "✅", "fail": "🚫", "path": "📁", "time": "⏱️",
    "success": "🎉", "general": "➡️",
}

# --- Core structlog Setup Function ---

def setup_logging(level: int = logging.INFO, json_logs: bool = False, log_file: Optional[str] = None) -> None:
    """
    Configures structlog for the entire supsrc application.

    Args:
        level: The minimum logging level (e.g., logging.DEBUG).
        json_logs: If True, format console output as JSON. Otherwise, use colored console output.
        log_file: Optional path for JSON file logging.
    """
    log_level_name = logging.getLevelName(level)
    # Use stderr for setup messages to avoid interfering with potential JSON stdout
    print(f"--- Setting up structlog logging (Level: {log_level_name}, JSON: {json_logs}, File: {log_file}) ---", file=sys.stderr)

    # Shared processors used by both console/file and potentially JSON outputs
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars, # Merge contextvars if used
        structlog.stdlib.add_logger_name,      # Adds logger name (e.g., 'supsrc.cfg')
        structlog.stdlib.add_log_level,        # Adds log level name (e.g., 'info')
        # structlog.stdlib.remove_logger_module_info, # <<< REMOVED - Causes AttributeError
        structlog.processors.TimeStamper(fmt="iso", utc=True), # Add ISO timestamp in UTC
        # --- Add custom processors back if they exist ---
        add_emoji_processor,                   # Custom: Add emoji
        add_padded_logger_processor,           # Custom: Add padded logger name
        remove_extra_keys_processor,           # Custom: Clean up temporary keys
        # --- End custom processors ---
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter, # Prepare for stdlib formatting/handling
    ]

    # Configure structlog itself
    structlog.configure(
        processors=shared_processors,
        logger_factory=structlog.stdlib.LoggerFactory(), # Use stdlib loggers underneath
        wrapper_class=structlog.stdlib.BoundLogger,    # Standard wrapper
        cache_logger_on_first_use=True,
    )

    # Configure the underlying standard library logging system
    # This is where handlers and the final formatting/rendering happen

    # Define the final renderer based on json_logs flag
    if json_logs:
        # Use JSON renderer for console/file
        final_renderer = structlog.processors.JSONRenderer()
    else:
        # Use colored console renderer for development
        final_renderer = structlog.dev.ConsoleRenderer(
            # Customize ConsoleRenderer output format slightly if needed
            # Example: "{timestamp} {level:<8} [{padded_logger}] {event} {emoji}"
            # Refer to ConsoleRenderer docs for exact keys available after processors
             event_key = "event" # default key for the main message
        )

    # Create the formatter that integrates structlog processors with stdlib handlers
    formatter = structlog.stdlib.ProcessorFormatter(
        # The foreign_pre_chain is applied to logs NOT originating from structlog
        # but captured by our handlers (e.g., from libraries using standard logging)
        # foreign_pre_chain=[structlog.stdlib.add_log_level], # Example
        # The final processor in this chain is the renderer
        processor=final_renderer,
    )

    # Configure the standard library root logger handler (for console)
    handler = logging.StreamHandler(sys.stdout) # Explicitly use stdout
    handler.setFormatter(formatter)

    root_logger = logging.getLogger() # Get stdlib root logger
    root_logger.handlers.clear()      # Clear existing handlers
    root_logger.addHandler(handler)
    root_logger.setLevel(level)     # Set level on the root logger

    # Configure File Handler (Optional, always JSON for machine readability)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            # Use a separate formatter for the file, forcing JSON output
            file_formatter = structlog.stdlib.ProcessorFormatter(
                processor=structlog.processors.JSONRenderer(),
                # foreign_pre_chain=[structlog.stdlib.add_log_level], # Keep consistent if needed
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(level) # Set level for file handler too
            root_logger.addHandler(file_handler) # Add file handler to root
            # Use standard logging here as structlog might not be fully configured yet
            # for file output during this setup phase if root logger is used.
            logging.getLogger(BASE_LOGGER_NAME).info(f"File logging enabled to '{log_file}'")
        except Exception as e:
            logging.getLogger(BASE_LOGGER_NAME).error(f"Failed to setup file logging to '{log_file}': {e}", exc_info=True)

    # Log initial message using a structlog logger AFTER configuration
    slog = structlog.get_logger(BASE_LOGGER_NAME)
    slog.info(
        "structlog logging initialized",
        level=log_level_name,
        json_console=json_logs,
        log_file=log_file or "None"
    )


# --- Logger Type Hint ---
# Define a type hint for the logger returned by structlog
StructLogger = FilteringBoundLogger # Or more specific type if needed
