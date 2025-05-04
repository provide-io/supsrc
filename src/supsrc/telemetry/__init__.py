#
# supsrc/telemetry/__init__.py
# -*- coding: utf-8 -*-
"""
Telemetry package for supsrc.
"""

from supsrc.telemetry.logger import setup_logging, StructLogger

__all__ = ["setup_logging", "StructLogger"] # Export setup function and type hint
