# src/supsrc/logging.py

"""
Simple logging setup using Foundation directly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from provide.foundation.logger.config import LoggingConfig, TelemetryConfig
from provide.foundation.setup import internal_setup

if TYPE_CHECKING:
    from supsrc.tui.app import SupsrcTuiApp


def setup_logging(
    level: int = logging.INFO,
    json_logs: bool = False,
    log_file: str | None = None,
    file_only: bool = False,
    tui_app_instance: SupsrcTuiApp | None = None,
    headless_mode: bool = False,
) -> None:
    """Configure logging using Foundation directly."""
    # Determine formatter based on mode
    if json_logs:
        formatter = "json"
    else:
        formatter = "key_value"  # Foundation's console formatter

    # Set up Foundation logging
    config = TelemetryConfig(
        logging=LoggingConfig(
            console_formatter=formatter,
            default_level=logging.getLevelName(level),
            das_emoji_prefix_enabled=True,
            logger_name_emoji_prefix_enabled=True,
        )
    )

    internal_setup(config)

    # Add file handler if requested
    if log_file:
        try:
            import structlog

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_formatter = structlog.stdlib.ProcessorFormatter(
                processor=structlog.processors.JSONRenderer(sort_keys=True)
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(level)
            logging.getLogger().addHandler(file_handler)
        except Exception:
            # Fallback to basic file handler
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(level)
            logging.getLogger().addHandler(file_handler)


# For backward compatibility
StructLogger = logging.Logger