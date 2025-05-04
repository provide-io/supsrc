#
# supsrc/config/__init__.py
# -*- coding: utf-8 -*-
"""
Configuration handling sub-package for supsrc.

Exports the loading function and core configuration model.
"""

from supsrc.config.loader import load_config
from supsrc.config.models import SupsrcConfig

__all__ = ["load_config", "SupsrcConfig"]

# 🔼⚙️
