# supsrc/config.py
# -*- coding: utf-8 -*-
"""
Configuration loading and validation for supsrc.

Uses the centralized logger from supsrc.telemetry.
"""

import logging
import sys
import tomllib
import argparse
import re
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Union, TypeAlias

# --- Third-party Libraries ---
try:
    # Still need rich for pretty printing the config object
    import rich.pretty
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

import cattrs
from attrs import define, field, validators, mutable

# --- Custom Exceptions Import ---
try:
    from .exceptions import (
        ConfigurationError, ConfigFileNotFoundError, ConfigParsingError,
        ConfigValidationError, DurationValidationError
        # PathValidationError is no longer raised fatally by load_config
    )
except ImportError:
    from exceptions import (
        ConfigurationError, ConfigFileNotFoundError, ConfigParsingError,
        ConfigValidationError, DurationValidationError
    )

# --- Centralized Logger ---
# Get a logger specific to this module, inheriting config from the base 'supsrc' logger
log = logging.getLogger("supsrc.cfg") # Or use: from supsrc.telemetry import logger as log

# --- Rich Markup Styles (Keep for log messages in this module) ---
PATH_STYLE = "bold cyan"
VALUE_STYLE = "bold magenta"
ERROR_DETAIL_STYLE = "italic red"
TIME_STYLE = "bold green"
WARN_STYLE = "yellow"

# --- Helper Functions & Validators (Log calls use 'log' instance) ---

def _parse_duration(duration_str: str, config_path_context: Path | None = None) -> timedelta:
    """Parses duration string. Raises DurationValidationError."""
    log.debug(f"Parsing duration string: [{VALUE_STYLE}]{duration_str}[/]", extra={"emoji_key": "time"})
    pattern = re.compile(r"^\s*(?:(?P<hours>\d+)\s*h)?\s*(?:(?P<minutes>\d+)\s*m)?\s*(?:(?P<seconds>\d+)\s*s)?\s*$")
    match = pattern.match(duration_str)
    if not match or not duration_str.strip():
        msg = f"Invalid duration format. Use '1h', '30m', '15s'. Got: [{ERROR_DETAIL_STYLE}]{duration_str}[/]"
        log.error(msg, extra={"emoji_key": "fail"})
        raise DurationValidationError("Invalid duration format", duration_str, str(config_path_context))
    parts = match.groupdict(); time_params = {k: int(v) for k, v in parts.items() if v}
    if not time_params:
        msg = f"Empty duration string: [{ERROR_DETAIL_STYLE}]{duration_str}[/]"
        log.error(msg, extra={"emoji_key": "fail"})
        raise DurationValidationError("Empty duration string", duration_str, str(config_path_context))
    try: duration = timedelta(**time_params)
    except ValueError as e:
         msg = f"Invalid time values ([{ERROR_DETAIL_STYLE}]{e}[/]) from '[{VALUE_STYLE}]{duration_str}[/]'"
         log.error(msg, exc_info=True, extra={"emoji_key": "fail"})
         raise DurationValidationError(f"Invalid time values: {e}", duration_str, str(config_path_context)) from e
    if duration <= timedelta(0):
        msg = f"Duration must be positive: [{TIME_STYLE}]{duration}[/] from '[{VALUE_STYLE}]{duration_str}[/]'"
        log.error(msg, extra={"emoji_key": "fail"})
        raise DurationValidationError(f"Duration must be positive: {duration}", duration_str, str(config_path_context))
    log.debug(f"Parsed '[{VALUE_STYLE}]{duration_str}[/]' to timedelta: [{TIME_STYLE}]{duration}[/]", extra={"emoji_key": "time"})
    return duration

def _validate_log_level(inst, attr, value: str):
    valid = logging._nameToLevel.keys()
    if value.upper() not in valid:
        msg = f"Invalid log_level '[{VALUE_STYLE}]{value}[/]'. Must be one of [{VALUE_STYLE}]{list(valid)}[/]."
        log.error(msg, extra={"emoji_key": "fail"})
        raise ConfigValidationError(f"Invalid log_level '{value}'")
    log.debug(f"Log level '[{VALUE_STYLE}]{value}[/]' is valid")

def _validate_positive_int(inst, attr, value: int):
    if not isinstance(value, int) or value <= 0:
        msg = f"Field '[{VALUE_STYLE}]{attr.name}[/]' must be positive integer, got: [{ERROR_DETAIL_STYLE}]{value}[/]"
        log.error(msg, extra={"emoji_key": "fail"})
        raise ConfigValidationError(f"Field '{attr.name}' must be positive integer, got {value}")
    log.debug(f"Field '[{VALUE_STYLE}]{attr.name}[/]' validated positive: [{VALUE_STYLE}]{value}[/]")


# --- attrs Data Classes (No changes needed here) ---

@define(slots=True)
class InactivityTrigger:
    type: Literal["inactivity"] = field(default="inactivity", init=False)
    period: timedelta = field()

@define(slots=True)
class SaveCountTrigger:
    type: Literal["save_count"] = field(default="save_count", init=False)
    count: int = field(validator=_validate_positive_int)

@define(slots=True)
class ManualTrigger:
    type: Literal["manual"] = field(default="manual", init=False)

TriggerConfig: TypeAlias = Union[InactivityTrigger, SaveCountTrigger, ManualTrigger]

@mutable(slots=True)
class RepositoryConfig:
    path: Path = field()
    trigger: TriggerConfig = field()
    enabled: bool = field(default=True)
    commit_message: Optional[str] = field(default=None)
    auto_push: Optional[bool] = field(default=None)
    _path_valid: bool = field(default=True, repr=False, init=False)

@define(frozen=True, slots=True)
class GlobalConfig:
    log_level: str = field(default="INFO", validator=_validate_log_level)
    default_commit_message: str = field(default="supsrc auto-commit: {{timestamp}}")
    default_auto_push: bool = field(default=True)
    @property
    def numeric_log_level(self) -> int: return logging.getLevelName(self.log_level.upper())

@define(frozen=True, slots=True)
class SupsrcConfig:
    repositories: Dict[str, RepositoryConfig] = field(factory=dict)
    global_config: GlobalConfig = field(factory=GlobalConfig, metadata={'toml_name': 'global'})


# --- Cattrs Converter and Hooks ---

converter = cattrs.Converter()
_CURRENT_CONFIG_PATH_CONTEXT: Path | None = None

def _structure_path_simple(path_str: str, type_hint: type[Path]) -> Path:
    """Cattrs structure hook for Path: Expands/resolves ONLY."""
    if not isinstance(path_str, str):
        raise ConfigValidationError(f"Path must be a string, got: {type(path_str).__name__}")
    log.debug(f"Structuring path string: [{PATH_STYLE}]{path_str}[/]", extra={"emoji_key": "path"})
    try:
        p = Path(path_str).expanduser().resolve()
        log.debug(f"Expanded/resolved path: [{PATH_STYLE}]{p}[/]", extra={"emoji_key": "path"})
        return p
    except Exception as e:
        msg = f"Error processing path string [{PATH_STYLE}]{path_str}[/]: [{ERROR_DETAIL_STYLE}]{e}[/]"
        log.error(msg, exc_info=True, extra={"emoji_key": "fail"})
        raise ConfigValidationError(f"Error processing path string '{path_str}': {e}") from e

converter.register_structure_hook(Path, _structure_path_simple)
converter.register_structure_hook(
    timedelta,
    lambda d, t: _parse_duration(d, config_path_context=_CURRENT_CONFIG_PATH_CONTEXT)
)


# --- Core Loading Function (No changes needed here) ---

def load_config(config_path: Path) -> SupsrcConfig:
    """Loads, validates, and structures config. Handles invalid paths gracefully."""
    global _CURRENT_CONFIG_PATH_CONTEXT
    _CURRENT_CONFIG_PATH_CONTEXT = config_path

    log.info(f"Attempting load from: [{PATH_STYLE}]{config_path}[/]", extra={"emoji_key": "load"})
    if not config_path.is_file():
        msg = "Config file not found"
        log.error(f"{msg}: [{PATH_STYLE}]{config_path}[/]", extra={"emoji_key": "fail"})
        raise ConfigFileNotFoundError(path=str(config_path))

    try:
        log.debug("Reading TOML...")
        with open(config_path, "rb") as f: toml_data = tomllib.load(f)
        log.debug("TOML read OK.")
    except tomllib.TOMLDecodeError as e:
        msg = f"Invalid TOML syntax: [{ERROR_DETAIL_STYLE}]{e}[/]"
        log.error(f"Failed TOML parse: [{PATH_STYLE}]{config_path}[/]\n{msg}", exc_info=True, extra={"emoji_key": "fail"})
        raise ConfigParsingError(str(e), path=str(config_path), details=e) from e

    try:
        log.debug("Structuring TOML data...")
        config_object = converter.structure(toml_data, SupsrcConfig)
        log.debug("Initial structuring complete.")

        log.debug("Performing post-structuring path validation...")
        repos_to_process = list(config_object.repositories.items())
        for repo_id, repo_config in repos_to_process:
            p = repo_config.path; path_valid = True
            if not p.exists():
                path_valid = False
                log.warning(f"Path does not exist for repo '[{VALUE_STYLE}]{repo_id}[/]', disabling: [{PATH_STYLE}]{p}[/]", extra={"emoji_key": "fail"})
            elif not p.is_dir():
                path_valid = False
                log.warning(f"Path is not a directory for repo '[{VALUE_STYLE}]{repo_id}[/]', disabling: [{PATH_STYLE}]{p}[/]", extra={"emoji_key": "fail"})
            if not path_valid:
                repo_config.enabled = False; repo_config._path_valid = False

        log.info("Config loaded (potential warnings for invalid paths).", extra={"emoji_key": "validate"})
        return config_object

    except (cattrs.BaseValidationError, ConfigValidationError) as e:
        log.error(f"Config validation failed: [{PATH_STYLE}]{config_path}[/]\n[{ERROR_DETAIL_STYLE}]{e}[/]", exc_info=True, extra={"emoji_key": "fail"})
        details_str = ""; notes = getattr(e, "__notes__", None)
        if notes: details_str = "\nDetails:\n" + "\n".join(notes)
        raise ConfigValidationError(f"{e}{details_str}", path=str(config_path), details=e) from e
    except Exception as e:
        log.critical(f"Unexpected error during config structuring: [{ERROR_DETAIL_STYLE}]{e}[/]", exc_info=True, extra={"emoji_key": "fail"})
        raise ConfigurationError(f"Unexpected error processing config: {e}", path=str(config_path)) from e
    finally:
        _CURRENT_CONFIG_PATH_CONTEXT = None


# --- Main Function for Demo/Testing ---

# IMPORTANT: Import the setup function from its new location
try:
    from .telemetry.logger.base import setup_logging
except ImportError:
    # Fallback if running config.py directly
    try:
        from telemetry.logger.base import setup_logging
    except ImportError as e:
        print(f"ERROR: Could not import setup_logging. Ensure supsrc is installed or paths correct.\n{e}", file=sys.stderr)
        sys.exit(99)

def main() -> None:
    """Parses arguments, sets up logging, loads config, prints result."""
    parser = argparse.ArgumentParser(description="Load/validate supsrc config.")
    parser.add_argument("-c", "--config", type=Path, default=Path("supsrc.conf"), help="Config file path")
    parser.add_argument("--log-level", choices=logging._nameToLevel.keys(), default="DEBUG", help="Logging level")
    # Add optional log file argument
    parser.add_argument("--log-file", type=str, default=None, help="Optional path to write logs to a file.")
    args = parser.parse_args()

    log_level_numeric = logging.getLevelName(args.log_level.upper())
    # Call the centralized setup function
    setup_logging(level=log_level_numeric, log_file=args.log_file)

    # Now use the 'log' instance obtained via getLogger("supsrc.cfg")
    log.info(f"Starting config load process via main (Log Level: {args.log_level})...")

    exit_code = 0
    try:
        config = load_config(args.config)

        if RICH_AVAILABLE:
            log.debug("Final configuration object (invalid paths auto-disabled):")
            rich.pretty.pprint(config, expand_all=True)
        else:
            import pprint
            log.debug("Final configuration object (invalid paths auto-disabled):")
            pprint.pprint(config, indent=2)

        disabled_count = sum(1 for repo in config.repositories.values() if not repo._path_valid)
        if disabled_count > 0:
            log.warning(f"✅ Config processed, [{WARN_STYLE}]{disabled_count}[/] repo(s) disabled due to invalid paths.", extra={"emoji_key": "validate"})
        else:
            log.info("✅ Config loading finished successfully!", extra={"emoji_key": "validate"})

    except ConfigFileNotFoundError as e: exit_code = 1
    except ConfigParsingError as e: exit_code = 2
    except ConfigValidationError as e: exit_code = 3
    except ConfigurationError as e:
        log.error(f"🚫 Config error: [{ERROR_DETAIL_STYLE}]{e}[/]", extra={"emoji_key": "fail"})
        exit_code = 4
    except Exception as e:
        log.critical(f"💥 Unexpected critical error: [{ERROR_DETAIL_STYLE}]{e}[/]", exc_info=True)
        exit_code = 5
    finally:
        if exit_code == 0: log.debug(f"Exiting code {exit_code} (Success)")
        else: log.warning(f"Exiting code {exit_code} (Error)")
        sys.exit(exit_code)

if __name__ == "__main__":
    main()
