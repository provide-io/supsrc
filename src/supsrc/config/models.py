#
# supsrc/config/models.py
# -*- coding: utf-8 -*-
"""
Attrs-based data models for supsrc configuration structure.
"""

import logging # Still needed for level names
from datetime import timedelta
from pathlib import Path
from typing import Dict, Literal, Optional, TypeAlias, Union, Any

from attrs import define, field, mutable, validators

# --- Validators (can stay here or move to a validators module) ---

def _validate_log_level(inst: Any, attr: Any, value: str) -> None:
    """Validator for standard logging level names."""
    valid = logging._nameToLevel.keys()
    if value.upper() not in valid:
        # Note: Raising validation error here is fine, structlog logger isn't needed
        raise ValueError(f"Invalid log_level '{value}'. Must be one of {list(valid)}.")

def _validate_positive_int(inst: Any, attr: Any, value: int) -> None:
    """Validator ensures integer is positive."""
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"Field '{attr.name}' must be positive integer, got {value}")

# --- attrs Data Classes ---

@define(slots=True)
class InactivityTrigger:
    """Commit trigger based on inactivity period."""
    type: Literal["inactivity"] = field(default="inactivity", init=False)
    period: timedelta = field()

@define(slots=True)
class SaveCountTrigger:
    """Commit trigger based on number of save events."""
    type: Literal["save_count"] = field(default="save_count", init=False)
    count: int = field(validator=_validate_positive_int)

@define(slots=True)
class ManualTrigger:
    """Commit trigger requiring manual intervention."""
    type: Literal["manual"] = field(default="manual", init=False)

# Type alias for the union of trigger types
TriggerConfig: TypeAlias = Union[InactivityTrigger, SaveCountTrigger, ManualTrigger]

@mutable(slots=True)
class RepositoryConfig:
    """
    Configuration for a repository. Mutable to allow disabling on load if path invalid.
    """
    # Mandatory fields first
    path: Path = field()
    trigger: TriggerConfig = field()
    # Optional fields after
    enabled: bool = field(default=True)
    commit_message: Optional[str] = field(default=None)
    auto_push: Optional[bool] = field(default=None)
    # Internal state flag
    _path_valid: bool = field(default=True, repr=False, init=False)

@define(frozen=True, slots=True)
class GlobalConfig:
    """Global default settings for supsrc."""
    log_level: str = field(default="INFO", validator=_validate_log_level)
    default_commit_message: str = field(
        default="supsrc auto-commit: {{timestamp}}"
    )
    default_auto_push: bool = field(default=True)

    @property
    def numeric_log_level(self) -> int:
        """Return the numeric logging level."""
        return logging.getLevelName(self.log_level.upper())

@define(frozen=True, slots=True)
class SupsrcConfig:
    """Root configuration object for the supsrc application."""
    repositories: Dict[str, RepositoryConfig] = field(factory=dict)
    global_config: GlobalConfig = field(
        factory=GlobalConfig, metadata={"toml_name": "global"}
    )

# 🔼⚙️
