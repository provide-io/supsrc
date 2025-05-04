#
# src/supsrc/rules.py
#
"""
Implements the rule engine logic for supsrc triggers.

Determines if configured conditions (e.g., inactivity, save count) are met
based on the current state of a repository.
"""

from datetime import datetime, timedelta, timezone
from typing import TypeAlias  # Import TypeAlias explicitly

import structlog

# Use ABSOLUTE imports based on the 'src' layout
from supsrc.config.models import (
    RepositoryConfig,
    InactivityTrigger,
    SaveCountTrigger,
    ManualTrigger,
    TriggerConfig, # Keep TypeAlias import if using directly, or rely on the union below
)
from supsrc.state import RepositoryState, RepositoryStatus

# Logger specific to the rule engine
log: structlog.stdlib.BoundLogger = structlog.get_logger("rules")

# Re-define TypeAlias if needed, though importing it from models is fine
# TriggerConfig: TypeAlias = Union[InactivityTrigger, SaveCountTrigger, ManualTrigger]


def check_trigger_condition(
    repo_state: RepositoryState, repo_config: RepositoryConfig
) -> bool:
    """
    Checks if the configured trigger condition for the repository is met.

    Delegates to specific checking functions based on the trigger type.

    Args:
        repo_state: The current dynamic state of the repository.
        repo_config: The static configuration for the repository.

    Returns:
        True if the trigger condition is met, False otherwise.
    """
    trigger_config = repo_config.trigger
    repo_id = repo_state.repo_id # Use repo_id from state for logging context

    log.debug("Checking trigger condition", repo_id=repo_id, trigger_type=type(trigger_config).__name__)

    match trigger_config:
        case InactivityTrigger():
            result = check_inactivity(repo_state, trigger_config)
            log.debug("Inactivity check result", repo_id=repo_id, result=result)
            return result
        case SaveCountTrigger():
            result = check_save_count(repo_state, trigger_config)
            log.debug("Save count check result", repo_id=repo_id, result=result)
            return result
        case ManualTrigger():
            log.debug("Manual trigger configured, condition always false for automation.", repo_id=repo_id)
            return False
        case _:
            # This should ideally be caught during config validation by cattrs/attrs
            log.error(
                "Unsupported trigger type encountered in rule engine",
                repo_id=repo_id,
                trigger_config=trigger_config,
                type=type(trigger_config).__name__,
            )
            # Raise an error or return False? Returning False is safer for loop continuation.
            # Consider raising a specific exception if this indicates a programming error.
            # raise TypeError(f"Unsupported trigger type: {type(trigger_config).__name__}")
            return False


def check_inactivity(
    repo_state: RepositoryState, trigger: InactivityTrigger
) -> bool:
    """
    Checks if the inactivity period has elapsed since the last change.

    Args:
        repo_state: The current dynamic state of the repository.
        trigger: The specific InactivityTrigger configuration.

    Returns:
        True if the inactivity period has been met or exceeded, False otherwise.
    """
    repo_id = repo_state.repo_id
    last_change_time_utc = repo_state.last_change_time

    if last_change_time_utc is None:
        # This state might occur if the timer fires before any change was recorded,
        # or potentially after a reset. Assume condition not met.
        log.debug("Inactivity check: No last change time recorded, condition false.", repo_id=repo_id)
        return False

    # Ensure comparison uses consistent timezone (UTC)
    now_utc = datetime.now(timezone.utc)
    elapsed_time = now_utc - last_change_time_utc
    required_period = trigger.period

    log.debug(
        "Checking inactivity period",
        repo_id=repo_id,
        last_change_utc=last_change_time_utc.isoformat(),
        current_time_utc=now_utc.isoformat(),
        elapsed_seconds=elapsed_time.total_seconds(),
        required_period_seconds=required_period.total_seconds(),
    )

    return elapsed_time >= required_period


def check_save_count(
    repo_state: RepositoryState, trigger: SaveCountTrigger
) -> bool:
    """
    Checks if the number of saves meets or exceeds the configured count.

    Args:
        repo_state: The current dynamic state of the repository.
        trigger: The specific SaveCountTrigger configuration.

    Returns:
        True if the save count has been met or exceeded, False otherwise.
    """
    repo_id = repo_state.repo_id
    current_saves = repo_state.save_count
    required_saves = trigger.count

    log.debug(
        "Checking save count",
        repo_id=repo_id,
        current_saves=current_saves,
        required_saves=required_saves,
    )

    return current_saves >= required_saves

# 🔼⚙️
