#
# supsrc/telemetry/logger/__init__.py
# -*- coding: utf-8 -*-
"""
Logging setup for supsrc using structlog.
"""

from supsrc.telemetry.logger.base import setup_logging, StructLogger # Expose setup and type hint

__all__ = ["setup_logging", "StructLogger"]

#
