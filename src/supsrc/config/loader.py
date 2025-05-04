#
# supsrc/config/loader.py
#
"""
Handles loading, validation, and structuring of supsrc configuration files.
Applies environment variable overrides for global defaults.
"""

import logging
import re
import sys
import os # <<< Added for os.getenv
import tomllib
from datetime import timedelta
from pathlib import Path
from typing import Optional, Any

import cattrs
import structlog
import attrs # <<< Added for attrs.evolve

# --- Custom Exceptions Import ---
from ..exceptions import (
    ConfigurationError,
    ConfigFileNotFoundError,
    ConfigParsingError,
    ConfigValidationError,
    DurationValidationError,
)
# Import models from sibling module
from .models import SupsrcConfig, RepositoryConfig, GlobalConfig # Import GlobalConfig
from ..telemetry import StructLogger # Import type hint

log: StructLogger = structlog.get_logger("config.loader")

# --- Rich Markup Styles ---
PATH_STYLE = "bold cyan"
VALUE_STYLE = "bold magenta"
ERROR_DETAIL_STYLE = "italic red"
TIME_STYLE = "bold green"
WARN_STYLE = "yellow"

# --- Helper Functions & Validators ---

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
    """
    Loads, validates, structures config. Handles invalid paths gracefully.
    Applies environment variable overrides for global settings.
    """
    global _CURRENT_CONFIG_PATH_CONTEXT
    _CURRENT_CONFIG_PATH_CONTEXT = config_path
    final_config_object: SupsrcConfig | None = None # Define outside try

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
        # Initial structure from TOML + attrs defaults
        config_object = converter.structure(toml_data, SupsrcConfig)
        log.debug("Initial structuring complete.")

        # --- Apply Environment Variable Overrides for Global Config ---
        global_config = config_object.global_config
        global_overrides: dict[str, Any] = {}

        # Check SUPSRC_DEFAULT_AUTO_PUSH
        env_auto_push = os.getenv('SUPSRC_DEFAULT_AUTO_PUSH')
        if env_auto_push is not None:
            parsed_auto_push = env_auto_push.lower() in ('true', '1', 'yes', 'on')
            if parsed_auto_push != global_config.default_auto_push:
                log.debug("Overriding global.default_auto_push from env var", value=parsed_auto_push)
                global_overrides['default_auto_push'] = parsed_auto_push

        # Check SUPSRC_DEFAULT_COMMIT_MESSAGE
        env_commit_msg = os.getenv('SUPSRC_DEFAULT_COMMIT_MESSAGE')
        if env_commit_msg is not None:
             # Allow empty string from env var if needed, otherwise check difference
             if env_commit_msg != global_config.default_commit_message:
                log.debug("Overriding global.default_commit_message from env var", value=env_commit_msg)
                global_overrides['default_commit_message'] = env_commit_msg

        # Apply overrides if any were found
        if global_overrides:
            log.info("Applying global config overrides from environment variables", overrides=list(global_overrides.keys()))
            try:
                # Create a new GlobalConfig with the overrides applied
                new_global_config = attrs.evolve(global_config, **global_overrides)
                # Create a new SupsrcConfig replacing the global_config part
                final_config_object = attrs.evolve(config_object, global_config=new_global_config)
            except Exception as evolve_exc:
                 # Should be unlikely if types match, but catch just in case
                 log.error("Failed to apply environment variable overrides", error=str(evolve_exc), exc_info=True)
                 final_config_object = config_object # Fallback to original
        else:
            final_config_object = config_object # No overrides needed

        # --- Post-Structuring Path Validation ---
        log.debug("Performing post-structuring path validation...")
        # Operate on the potentially modified final_config_object
        repos_to_process = list(final_config_object.repositories.items())
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
                # Modify the mutable RepositoryConfig object (this is okay even if SupsrcConfig is frozen)
                repo_config.enabled = False; repo_config._path_valid = False

        log.info("Config loaded (env overrides applied, potential warnings for invalid paths).", emoji_key="validate")
        return final_config_object # Return the final version

    except (cattrs.BaseValidationError, ConfigValidationError) as e:
        log.error("Config validation failed", path=str(config_path), error=str(e), exc_info=True, emoji_key="fail")
        details_str = ""; notes = getattr(e, "__notes__", None)
        if notes: details_str = "\nDetails:\n" + "\n".join(notes)
        raise ConfigValidationError(f"{e}{details_str}", path=str(config_path), details=e) from e
    except Exception as e:
        log.critical("Unexpected error during config structuring", error=str(e), exc_info=True, emoji_key="fail")
        raise ConfigurationError(f"Unexpected error processing config: {e}", path=str(config_path)) from e
    finally:
        _CURRENT_CONFIG_PATH_CONTEXT = None

# 🔼⚙️
