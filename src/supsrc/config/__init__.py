#
# config/__init__.py
#
"""
Configuration handling sub-package for supsrc.

Exports the loading function and core configuration model.
"""

# Export the main loading function from the loader module
from .loader import load_config

# Export the core configuration models from the models module
from .models import (
    SupsrcConfig,
    GlobalConfig,
    RepositoryConfig,
    RuleConfig, # Export the union type
    InactivityRuleConfig, # Export specific rule types if needed externally
    SaveCountRuleConfig,
    ManualRuleConfig,
)

__all__ = [
    "load_config",
    "SupsrcConfig",
    "GlobalConfig",
    "RepositoryConfig",
    "RuleConfig",
    "InactivityRuleConfig",
    "SaveCountRuleConfig",
    "ManualRuleConfig",
]

# 🔼⚙️
