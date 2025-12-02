#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Supsrc configuration using Foundation's config system."""

import logging
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any, TypeAlias

# Foundation includes attrs as a dependency
from attrs import define, field, mutable
from attrs.validators import instance_of
from provide.foundation.errors.config import ConfigurationError
from provide.foundation.file import read_toml

# Add Foundation parsing utilities
from provide.foundation.utils import parse_duration

from supsrc.config.defaults import (
    DEFAULT_EVENT_BUFFER_ENABLED,
    DEFAULT_EVENT_BUFFER_GROUPING_MODE,
    DEFAULT_EVENT_BUFFER_GROUPING_MODE_HEADLESS,
    DEFAULT_EVENT_BUFFER_GROUPING_MODE_TUI,
    DEFAULT_EVENT_BUFFER_WINDOW_MS,
)
from supsrc.utils.directories import SupsrcDirectories


def _validate_log_level(inst: Any, attr: Any, value: str) -> None:
    """Validator for standard logging level names."""
    valid = logging._nameToLevel.keys()
    if value.upper() not in valid:
        raise ValueError(f"Invalid log_level '{value}'. Must be one of {list(valid)}.")


def _validate_positive_int(inst: Any, attr: Any, value: int) -> None:
    """Validator ensures integer is positive."""
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"Field '{attr.name}' must be positive integer, got {value}")


def _validate_non_negative_int(inst: Any, attr: Any, value: int) -> None:
    """Validator ensures integer is non-negative (zero allowed for disabling)."""
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"Field '{attr.name}' must be non-negative integer, got {value}")


# --- Circuit Breaker Configuration ---
@define(frozen=True, slots=True)
class CircuitBreakerConfig:
    """Configuration for circuit breaker safety mechanisms."""

    # Bulk file change detection - pause when too many files change at once
    bulk_change_threshold: int = field(default=50, validator=_validate_non_negative_int)
    bulk_change_window_ms: int = field(default=5000, validator=_validate_positive_int)
    bulk_change_auto_pause: bool = field(default=True)

    # Branch change detection
    branch_change_detection_enabled: bool = field(default=True)
    branch_change_warning_enabled: bool = field(default=True)

    # Combined trigger: branch change + bulk files = error
    branch_with_bulk_change_error: bool = field(default=True)
    branch_with_bulk_change_threshold: int = field(default=20, validator=_validate_non_negative_int)

    # Auto-recovery settings
    auto_resume_after_bulk_pause_seconds: int = field(default=0)  # 0 = no auto-resume
    require_manual_acknowledgment: bool = field(default=False)


# --- attrs Data Classes for Rules ---
@define(slots=True)
class InactivityRuleConfig:
    """Configuration for the inactivity rule."""

    type: str = field(default="supsrc.rules.inactivity", kw_only=True)
    period: timedelta = field()


@define(slots=True)
class SaveCountRuleConfig:
    """Configuration for the save count rule."""

    type: str = field(default="supsrc.rules.save_count", kw_only=True)
    count: int = field(validator=_validate_positive_int)


@define(slots=True)
class ManualRuleConfig:
    """Configuration for the manual rule."""

    type: str = field(default="supsrc.rules.manual", kw_only=True)


RuleConfig: TypeAlias = InactivityRuleConfig | SaveCountRuleConfig | ManualRuleConfig


# --- LLM Configuration Model ---
@define(frozen=True, slots=True)
class LLMConfig:
    """Configuration for optional LLM features."""

    enabled: bool = field(default=False)
    provider: str = field(default="gemini")
    model: str = field(default="gemini-1.5-flash")
    api_key_env_var: str | None = field(default="GEMINI_API_KEY")

    # Feature Flags
    generate_commit_message: bool = field(default=True)
    use_conventional_commit: bool = field(default=True)
    review_changes: bool = field(default=True)
    run_tests: bool = field(default=True)
    analyze_test_failures: bool = field(default=True)
    generate_change_fragment: bool = field(default=False)

    # Configurable settings
    test_command: str | None = field(default=None)
    change_fragment_dir: str | None = field(default="changes")


# --- Repository and Global Config Models ---
@mutable(slots=True)
class RepositoryConfig:
    """Configuration for a repository. Mutable to allow disabling on load if path invalid."""

    path: Path = field()
    rule: RuleConfig = field()
    repository: Mapping[str, Any] = field(factory=dict)
    enabled: bool = field(default=True)
    llm: LLMConfig | None = field(default=None)
    _path_valid: bool = field(default=True, repr=False, init=False)


@define(frozen=True, slots=True)
class GlobalConfig:
    """Global default settings for supsrc."""

    log_level: str = field(default="INFO", validator=_validate_log_level)

    # Event buffering configuration
    event_buffering_enabled: bool = field(default=DEFAULT_EVENT_BUFFER_ENABLED)
    event_buffer_window_ms: int = field(
        default=DEFAULT_EVENT_BUFFER_WINDOW_MS, validator=_validate_positive_int
    )

    # Mode-specific grouping modes (Foundation bugs fixed!)
    event_grouping_mode_tui: str = field(
        default=DEFAULT_EVENT_BUFFER_GROUPING_MODE_TUI, validator=instance_of(str)
    )
    event_grouping_mode_headless: str = field(
        default=DEFAULT_EVENT_BUFFER_GROUPING_MODE_HEADLESS, validator=instance_of(str)
    )

    # Legacy fallback for backwards compatibility
    event_grouping_mode: str = field(default=DEFAULT_EVENT_BUFFER_GROUPING_MODE, validator=instance_of(str))

    # File warning thresholds
    large_file_threshold_bytes: int = field(default=1_000_000, validator=_validate_positive_int)
    binary_file_warning_enabled: bool = field(default=True)

    # Circuit breaker configuration for safety mechanisms
    circuit_breaker: CircuitBreakerConfig = field(factory=CircuitBreakerConfig)

    @property
    def numeric_log_level(self) -> int:
        return logging.getLevelName(self.log_level.upper())


@define(frozen=True, slots=True)
class SupsrcConfig:
    """Root configuration object for the supsrc application."""

    repositories: dict[str, RepositoryConfig] = field(factory=dict)
    global_config: GlobalConfig = field(factory=GlobalConfig)


def load_config(config_path: Path) -> SupsrcConfig:
    """Load supsrc configuration using Foundation's error handling."""
    import tomllib

    from cattrs import Converter

    from supsrc.exceptions import ConfigFileNotFoundError, ConfigParsingError

    try:
        # Use Foundation error handling but keep our TOML loading logic
        if not config_path.is_file():
            raise ConfigFileNotFoundError(f"Config file not found: {config_path}")

        try:
            with open(config_path, "rb") as f:
                toml_data = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            raise ConfigParsingError(f"Invalid TOML syntax in {config_path}: {e}") from e

        if "global" in toml_data:
            toml_data["global_config"] = toml_data.pop("global")

        # Use the original converter logic
        converter = Converter()

        # Use Foundation's duration parser instead of custom implementation

        def _structure_path_simple(path_str: str, type_hint: type[Path]) -> Path:
            """Structure hook for Path."""
            if not isinstance(path_str, str):
                raise ValueError(f"Path must be string, got: {type(path_str).__name__}")
            return Path(path_str).expanduser().resolve()

        def structure_rule_hook(data: Mapping[str, Any], cl: type[RuleConfig]) -> RuleConfig:
            """Structure the correct RuleConfig based on the 'type' field."""
            if not isinstance(data, Mapping):
                raise ValueError(f"Rule configuration must be a mapping, got {type(data).__name__}")

            rule_type = data.get("type")
            if not rule_type or not isinstance(rule_type, str):
                raise ValueError("Rule configuration missing or invalid 'type' field.")

            type_map: dict[str, type[RuleConfig]] = {
                "supsrc.rules.inactivity": InactivityRuleConfig,
                "supsrc.rules.save_count": SaveCountRuleConfig,
                "supsrc.rules.manual": ManualRuleConfig,
            }

            target_class = type_map.get(rule_type)
            if target_class is None:
                raise ValueError(f"Unknown rule type specified: '{rule_type}'")

            data_copy = dict(data)
            if hasattr(target_class.__attrs_attrs__, "type") and target_class.__attrs_attrs__.type.kw_only:
                data_copy.pop("type", None)

            return converter.structure(data_copy, target_class)

        converter.register_structure_hook(Path, _structure_path_simple)
        converter.register_structure_hook(timedelta, lambda d, t: timedelta(seconds=parse_duration(d)))
        converter.register_structure_hook(RuleConfig, structure_rule_hook)

        config_object = converter.structure(toml_data, SupsrcConfig)

        # Validate paths and disable repos with invalid paths
        for _repo_id, repo_config in config_object.repositories.items():
            p = repo_config.path
            path_valid = True
            try:
                if not p.exists() or not p.is_dir():
                    path_valid = False
            except OSError:
                path_valid = False

            if not path_valid:
                repo_config.enabled = False
                repo_config._path_valid = False

        return config_object

    except (ConfigFileNotFoundError, ConfigParsingError):
        # Re-raise specific config exceptions as-is
        raise
    except Exception as e:
        raise ConfigurationError(f"Failed to load config from {config_path}: {e}") from e


def load_repository_config(repo_path: Path) -> dict[str, Any] | None:
    """Load repository-specific config from .supsrc/config.toml if it exists.

    Args:
        repo_path: Path to the repository

    Returns:
        Dictionary of config values if file exists, None otherwise
    """
    config_file = SupsrcDirectories.get_config_file(repo_path)

    if not config_file.exists():
        return None

    return read_toml(config_file, default=None)


# Export all the models and functions that were in the original config package
__all__ = [
    "CircuitBreakerConfig",
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
