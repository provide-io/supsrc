#
# supsrc/config/loader.py
# -*- coding: utf-8 -*-
"""
Handles loading, validation, and structuring of supsrc configuration files.
"""

import logging
import re
import sys
import tomllib
from datetime import timedelta
from pathlib import Path
from typing import Optional

import cattrs
import structlog

# --- Custom Exceptions Import ---
# Use relative imports within the same package
from ..exceptions import (
    ConfigurationError,
    ConfigFileNotFoundError,
    ConfigParsingError,
    ConfigValidationError,
    DurationValidationError,
)
# Import models from sibling module
from .models import SupsrcConfig, RepositoryConfig

log: structlog.stdlib.BoundLogger = structlog.get_logger("config.loader")

# --- Rich Markup Styles ---
# These are used by the logger configured elsewhere, but defining them here
# helps if we construct messages with markup within this module.
PATH_STYLE = "bold cyan"
VALUE_STYLE = "bold magenta"
ERROR_DETAIL_STYLE = "italic red"
TIME_STYLE = "bold green"
WARN_STYLE = "yellow"

# --- Helper Functions & Validators ---

# Context variable for hooks - consider alternatives for complex apps
_CURRENT_CONFIG_PATH_CONTEXT: Path | None = None

def _parse_duration(
    duration_str: str, config_path_context: Path | None = None
) -> timedelta:
    """Parses duration string. Raises DurationValidationError."""
    log.debug("Parsing duration", duration_str=duration_str, emoji_key="time")
    pattern = re.compile(
        r"^\s*(?:(?P<hours>\d+)\s*h)?\s*(?:(?P<minutes>\d+)\s*m)?\s*(?:(?P<seconds>\d+)\s*s)?\s*$"
    )
    match = pattern.match(duration_str)
    if not match or not duration_str.strip():
        msg = "Invalid duration format. Use '1h', '30m', '15s'."
        log.error(msg, received=duration_str, emoji_key="fail")
        raise DurationValidationError(msg, duration_str, str(config_path_context))

    parts = match.groupdict(); time_params = {k: int(v) for k, v in parts.items() if v}
    if not time_params:
        msg = "Empty duration string provided"; log.error(msg, received=duration_str, emoji_key="fail")
        raise DurationValidationError(msg, duration_str, str(config_path_context))
    try: duration = timedelta(**time_params)
    except ValueError as e:
        msg = "Invalid time values for timedelta"; log.error(msg, error=str(e), duration_str=duration_str, exc_info=True, emoji_key="fail")
        raise DurationValidationError(f"{msg}: {e}", duration_str, str(config_path_context)) from e
    if duration <= timedelta(0):
        msg = "Duration must be positive"; log.error(msg, result=str(duration), duration_str=duration_str, emoji_key="fail")
        raise DurationValidationError(f"{msg}: {duration}", duration_str, str(config_path_context))
    log.debug("Parsed duration", duration_str=duration_str, result=str(duration), emoji_key="time")
    return duration

# --- Cattrs Converter and Hooks ---

converter = cattrs.Converter()

def _structure_path_simple(path_str: str, type_hint: type[Path]) -> Path:
    """Cattrs structure hook for Path: Expands/resolves ONLY."""
    if not isinstance(path_str, str):
        raise ConfigValidationError(f"Path must be string, got: {type(path_str).__name__}")
    log.debug("Structuring path string", path_str=path_str, emoji_key="path")
    try:
        p = Path(path_str).expanduser().resolve()
        log.debug("Expanded/resolved path", path=str(p), emoji_key="path")
        return p
    except Exception as e:
        msg = "Error processing path string"; log.error(msg, path_str=path_str, error=str(e), exc_info=True, emoji_key="fail")
        raise ConfigValidationError(f"{msg} '{path_str}': {e}") from e

converter.register_structure_hook(Path, _structure_path_simple)
converter.register_structure_hook(
    timedelta, lambda d, t: _parse_duration(d, _CURRENT_CONFIG_PATH_CONTEXT)
)

# --- Core Loading Function ---

def load_config(config_path: Path) -> SupsrcConfig:
    """Loads, validates, structures config. Handles invalid paths gracefully."""
    global _CURRENT_CONFIG_PATH_CONTEXT
    _CURRENT_CONFIG_PATH_CONTEXT = config_path

    log.info("Attempting config load", path=str(config_path), emoji_key="load")
    if not config_path.is_file():
        msg = "Config file not found"; log.error(msg, path=str(config_path), emoji_key="fail")
        raise ConfigFileNotFoundError(path=str(config_path))

    try:
        log.debug("Reading TOML...")
        with open(config_path, "rb") as f: toml_data = tomllib.load(f)
        log.debug("TOML read OK.")
    except tomllib.TOMLDecodeError as e:
        msg = "Invalid TOML syntax"; log.error(msg, path=str(config_path), error=str(e), exc_info=True, emoji_key="fail")
        raise ConfigParsingError(str(e), path=str(config_path), details=e) from e

    try:
        log.debug("Structuring TOML data...")
        config_object = converter.structure(toml_data, SupsrcConfig)
        log.debug("Initial structuring complete.")

        log.debug("Performing post-structuring path validation...")
        repos_to_process = list(config_object.repositories.items())
        for repo_id, repo_config in repos_to_process:
            p = repo_config.path; path_valid = True
            try:
                if not p.exists():
                    path_valid = False; log.warning("Path does not exist, disabling repo", repo_id=repo_id, path=str(p), emoji_key="fail")
                elif not p.is_dir():
                    path_valid = False; log.warning("Path is not a directory, disabling repo", repo_id=repo_id, path=str(p), emoji_key="fail")
            except OSError as e: # Catch permission errors etc. during checks
                 path_valid = False; log.warning("Cannot access path, disabling repo", repo_id=repo_id, path=str(p), error=str(e), emoji_key="fail")

            if not path_valid:
                repo_config.enabled = False; repo_config._path_valid = False

        log.info("Config loaded (potential warnings for invalid paths).", emoji_key="validate")
        return config_object

    except (cattrs.BaseValidationError, ConfigValidationError) as e:
        log.error("Config validation failed", path=str(config_path), error=str(e), exc_info=True, emoji_key="fail")
        details_str = ""; notes = getattr(e, "__notes__", None)
        if notes: details_str = "\nDetails:\n" + "\n".join(notes)
        raise ConfigValidationError(f"{e}{details_str}", path=str(config_path), details=e) from e
    except Exception as e:
        log.critical("Unexpected error during config structuring", error=str(e), exc_info=True, emoji_key="fail")
        raise ConfigurationError(f"Unexpected error processing config: {e}", path=str(config_path)) from e
    finally: _CURRENT_CONFIG_PATH_CONTEXT = None

# 🔼⚙️
