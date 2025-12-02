#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Configuration module for supsrc.

Re-exports all configuration models and loading functions for backwards compatibility."""

from __future__ import annotations

# Re-export all config models and functions
from supsrc.config.models import (
    BranchProtectionConfig,
    ConfigurationError,
    GlobalConfig,
    InactivityRuleConfig,
    LLMConfig,
    ManualRuleConfig,
    RepositoryConfig,
    RuleConfig,
    SaveCountRuleConfig,
    SupsrcConfig,
    load_config,
    load_repository_config,
)

__all__ = [
    "BranchProtectionConfig",
    "ConfigurationError",
    "GlobalConfig",
    "InactivityRuleConfig",
    "LLMConfig",
    "ManualRuleConfig",
    "RepositoryConfig",
    "RuleConfig",
    "SaveCountRuleConfig",
    "SupsrcConfig",
    "load_config",
    "load_repository_config",
]

# 🔼⚙️🔚
