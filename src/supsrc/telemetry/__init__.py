#
# supsrc/telemetry/__init__.py
#
"""
Telemetry package for supsrc - now using Foundation's telemetry system.
"""

# Re-export Foundation's logger and setup functions
from provide.foundation.logger import get_logger, setup_logger
from structlog.typing import FilteringBoundLogger as StructLogger

# Re-export our custom setup function from the logger base module
from supsrc.telemetry.logger.base import setup_logging

__all__ = ["StructLogger", "setup_logging", "get_logger", "setup_logger"]

# 🔼⚙️