#
# supsrc/telemetry/__init__.py
# -*- coding: utf-8 -*-
"""
Telemetry package for supsrc.
"""

from supsrc.telemetry.logger import StructLogger, setup_logging

__all__ = ["StructLogger", "setup_logging"] # Export setup function and type hint
