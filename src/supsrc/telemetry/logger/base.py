# src/supsrc/telemetry/logger/base.py

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from provide.foundation import LoggingConfig, TelemetryConfig, logger
from provide.foundation.setup import internal_setup
from provide.foundation.eventsets.types import EventMapping, EventSet
from provide.foundation.hub import get_component_registry
from provide.foundation.hub.components import ComponentCategory
from structlog.typing import FilteringBoundLogger

try:
    from supsrc.tui.logging_handler import TextualLogHandler

    HAS_TUI = True
except ImportError:
    TextualLogHandler = None
    HAS_TUI = False

if TYPE_CHECKING:
    from supsrc.tui.app import SupsrcTuiApp


BASE_LOGGER_NAME = "supsrc"

# Register supsrc-specific event set with Foundation's registry
_supsrc_event_mapping = EventMapping(
    name="supsrc_operations",
    visual_markers={
        "load": "📄",
        "validate": "✅",
        "fail": "🚫",
        "path": "📁",
        "time": "⏱️",
        "success": "🎉",
        "general": "➡️",
    },
    default_key="general",
)

_supsrc_event_set = EventSet(
    name="supsrc",
    description="Event set for supsrc operations",
    mappings=[_supsrc_event_mapping],
    priority=100,
)


def _register_supsrc_event_set():
    """Register supsrc-specific event set with Foundation registry."""
    registry = get_component_registry()
    registry.register(
        name="supsrc",
        value=_supsrc_event_set,
        dimension=ComponentCategory.EVENT_SET.value,
        metadata={"domain": "supsrc", "priority": 100},
        replace=True,
    )


def setup_logging(
    level: int = logging.INFO,
    json_logs: bool = False,
    log_file: str | None = None,
    file_only: bool = False,
    tui_app_instance: SupsrcTuiApp | None = None,
    headless_mode: bool = False,
) -> None:
    """Configures logging using Foundation with supsrc customizations."""
    # Register supsrc-specific event set first
    _register_supsrc_event_set()

    # Use Foundation's TelemetryConfig
    log_level_name = logging.getLevelName(level)

    # Determine formatter based on mode
    if json_logs:
        formatter = "json"
    else:
        formatter = "key_value"  # Foundation's console formatter is "key_value"

    # Set up Foundation logging
    config = TelemetryConfig(
        logging=LoggingConfig(
            console_formatter=formatter,
            default_level=log_level_name,
            das_emoji_prefix_enabled=True,
            logger_name_emoji_prefix_enabled=True,
        )
    )

    internal_setup(config)

    # Get Foundation's logger for supsrc-specific setup
    slog = logger.bind(logger_name=BASE_LOGGER_NAME)

    # Add custom handlers for file and TUI modes
    root_logger = logging.getLogger()

    if log_file:
        try:
            import structlog

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_formatter = structlog.stdlib.ProcessorFormatter(
                processor=structlog.processors.JSONRenderer(sort_keys=True)
            )
            file_handler.setFormatter(file_formatter)
            file_handler.setLevel(level)
            root_logger.addHandler(file_handler)
            slog.info("File logging enabled", file=log_file)
        except Exception as e:
            slog.error("Failed to setup file logging", file=log_file, error=str(e))

    # Add TUI handler if needed
    is_tui_mode = tui_app_instance is not None
    if is_tui_mode and tui_app_instance:
        if HAS_TUI and TextualLogHandler:
            import structlog

            textual_handler = TextualLogHandler(app=tui_app_instance)
            textual_handler.setLevel(level)
            # Use Foundation-compatible formatter
            formatter = structlog.stdlib.ProcessorFormatter(
                processor=structlog.dev.ConsoleRenderer(colors=True)
            )
            textual_handler.setFormatter(formatter)
            root_logger.addHandler(textual_handler)
            slog.info("TextualLogHandler added for TUI")
        else:
            slog.error("TUI mode active but textual is not installed")

    slog.info(
        "Foundation-based logging initialization complete",
        log_level=log_level_name,
        json_logs=json_logs,
        file_logging=log_file or "disabled",
        tui_mode=is_tui_mode,
    )


StructLogger = FilteringBoundLogger

# 🔼⚙️
