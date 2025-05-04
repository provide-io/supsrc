# supsrc/telemetry/logger/__init__.py
# -*- coding: utf-8 -*-
"""
Exposes the configured logger instance for the supsrc application.

Usage: from supsrc.telemetry import logger
       logger.info("...")

Requires setup_logging() from .base to be called first.
"""

import logging
from .base import BASE_LOGGER_NAME

# Retrieve the logger instance configured by setup_logging in base.py
logger = logging.getLogger(BASE_LOGGER_NAME)
