# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Circuit breaker service for detecting dangerous operations and pausing automation.

This module provides safety mechanisms to prevent accidental commits of large-scale changes
or operations during branch switches. The circuit breaker pattern helps protect against:

- Bulk file changes (e.g., IDE refactoring, package updates)
- Unexpected branch switches while monitoring
- Combined scenarios that indicate non-standard operations

Usage:
    config = CircuitBreakerConfig(
        bulk_change_threshold=50,
        bulk_change_window_ms=5000,
        branch_change_detection_enabled=True,
    )
    service = CircuitBreakerService(config)

    # In your event processing loop:
    if service.should_process_event(repo_state):
        if not service.check_and_update_bulk_change(repo_state, file_path):
            # Process the event normally
            pass
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from attrs import define, field
from provide.foundation.logger import get_logger

from supsrc.config.models import CircuitBreakerConfig
from supsrc.state.runtime import RepositoryState, RepositoryStatus

log = get_logger("services.circuit_breaker")


@define
class CircuitBreakerMetrics:
    """Metrics for circuit breaker operations."""

    # Trigger counts by type
    bulk_change_triggers: int = field(default=0)
    branch_change_triggers: int = field(default=0)
    combined_triggers: int = field(default=0)

    # Recovery metrics
    auto_recoveries: int = field(default=0)
    manual_acknowledgments: int = field(default=0)

    # Performance metrics
    total_events_blocked: int = field(default=0)
    total_events_processed: int = field(default=0)

    # Last trigger info
    last_trigger_time: datetime | None = field(default=None)
    last_trigger_reason: str | None = field(default=None)
    last_trigger_type: str | None = field(default=None)

    # Cooldown tracking
    triggers_in_last_hour: int = field(default=0)
    last_hour_reset: datetime = field(factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary for reporting."""
        return {
            "bulk_change_triggers": self.bulk_change_triggers,
            "branch_change_triggers": self.branch_change_triggers,
            "combined_triggers": self.combined_triggers,
            "auto_recoveries": self.auto_recoveries,
            "manual_acknowledgments": self.manual_acknowledgments,
            "total_events_blocked": self.total_events_blocked,
            "total_events_processed": self.total_events_processed,
            "last_trigger_time": self.last_trigger_time.isoformat() if self.last_trigger_time else None,
            "last_trigger_reason": self.last_trigger_reason,
            "last_trigger_type": self.last_trigger_type,
            "triggers_in_last_hour": self.triggers_in_last_hour,
        }


class CircuitBreakerError(Exception):
    """Base exception for circuit breaker errors."""

    def __init__(self, message: str, repo_id: str, trigger_type: str):
        self.repo_id = repo_id
        self.trigger_type = trigger_type
        super().__init__(message)


class BulkChangeError(CircuitBreakerError):
    """Raised when bulk change threshold is exceeded."""

    def __init__(self, repo_id: str, file_count: int, threshold: int, window_ms: int):
        self.file_count = file_count
        self.threshold = threshold
        self.window_ms = window_ms
        message = (
            f"Repository '{repo_id}': Bulk change detected - {file_count} files changed "
            f"within {window_ms}ms (threshold: {threshold}). "
            f"This may indicate a large refactoring operation or package update. "
            f"Review the changes before acknowledging the circuit breaker."
        )
        super().__init__(message, repo_id, "bulk_change")


class BranchChangeError(CircuitBreakerError):
    """Raised when branch change with bulk modifications is detected."""

    def __init__(self, repo_id: str, old_branch: str, new_branch: str, file_count: int):
        self.old_branch = old_branch
        self.new_branch = new_branch
        self.file_count = file_count
        message = (
            f"Repository '{repo_id}': Branch switched from '{old_branch}' to '{new_branch}' "
            f"with {file_count} file modifications detected. "
            f"This may indicate a checkout operation or large merge. "
            f"Verify you are on the correct branch before acknowledging."
        )
        super().__init__(message, repo_id, "branch_change_with_bulk")


class CircuitBreakerService:
    """Service for monitoring and triggering circuit breakers on repository operations.

    The circuit breaker provides safety mechanisms to prevent accidental commits:

    1. **Bulk Change Detection**: Monitors file change rate and triggers when too many
       files change within a time window. This catches IDE refactoring operations,
       package updates, or mass file generation.

    2. **Branch Change Detection**: Monitors for unexpected branch switches. A warning
       is triggered on branch change, and an error is triggered if branch change is
       combined with bulk file modifications.

    3. **Auto-Recovery**: Optional automatic recovery after a cooldown period.

    4. **Metrics Collection**: Tracks trigger counts, recovery rates, and patterns.
    """

    def __init__(self, config: CircuitBreakerConfig):
        """Initialize circuit breaker service with configuration.

        Args:
            config: Circuit breaker configuration settings
        """
        self.config = config
        self.metrics = CircuitBreakerMetrics()
        self._auto_recovery_tasks: dict[str, datetime] = {}

        log.info(
            "CircuitBreakerService initialized",
            bulk_change_threshold=config.bulk_change_threshold,
            bulk_change_window_ms=config.bulk_change_window_ms,
            branch_change_detection=config.branch_change_detection_enabled,
            branch_with_bulk_threshold=config.branch_with_bulk_change_threshold,
            auto_resume_seconds=config.auto_resume_after_bulk_pause_seconds,
        )

    def _update_hourly_metrics(self) -> None:
        """Update hourly trigger tracking, resetting if hour has passed."""
        now = datetime.now(UTC)
        if now - self.metrics.last_hour_reset > timedelta(hours=1):
            self.metrics.triggers_in_last_hour = 0
            self.metrics.last_hour_reset = now

    def _record_trigger(self, trigger_type: str, reason: str) -> None:
        """Record a circuit breaker trigger in metrics."""
        self._update_hourly_metrics()

        self.metrics.last_trigger_time = datetime.now(UTC)
        self.metrics.last_trigger_reason = reason
        self.metrics.last_trigger_type = trigger_type
        self.metrics.triggers_in_last_hour += 1

        if trigger_type == "bulk_change":
            self.metrics.bulk_change_triggers += 1
        elif trigger_type == "branch_change":
            self.metrics.branch_change_triggers += 1
        elif trigger_type == "combined":
            self.metrics.combined_triggers += 1

        log.info(
            "Circuit breaker trigger recorded",
            trigger_type=trigger_type,
            triggers_in_hour=self.metrics.triggers_in_last_hour,
            total_triggers=sum(
                [
                    self.metrics.bulk_change_triggers,
                    self.metrics.branch_change_triggers,
                    self.metrics.combined_triggers,
                ]
            ),
        )

    def check_and_update_bulk_change(self, repo_state: RepositoryState, file_path: str) -> bool:
        """Check if bulk change threshold has been exceeded.

        Args:
            repo_state: Repository state to check and update
            file_path: Path of the file that changed

        Returns:
            True if circuit breaker was triggered, False otherwise

        Raises:
            BulkChangeError: If threshold exceeded and require_manual_acknowledgment is True
        """
        if self.config.bulk_change_threshold == 0:
            # Feature disabled
            return False

        if repo_state.circuit_breaker_triggered:
            # Already triggered, don't process further
            self.metrics.total_events_blocked += 1
            log.debug(
                "Circuit breaker already triggered, ignoring event",
                repo_id=repo_state.repo_id,
            )
            return True

        # Check if window has expired
        now_utc = datetime.now(UTC)
        window_delta = timedelta(milliseconds=self.config.bulk_change_window_ms)

        if repo_state.bulk_change_window_start is not None:
            elapsed = now_utc - repo_state.bulk_change_window_start
            if elapsed > window_delta:
                # Window expired, reset
                log.debug(
                    "Bulk change window expired, resetting",
                    repo_id=repo_state.repo_id,
                    elapsed_ms=elapsed.total_seconds() * 1000,
                    window_ms=self.config.bulk_change_window_ms,
                )
                repo_state.reset_bulk_change_window()

        # Record the change
        repo_state.record_bulk_change_event(file_path)

        # Check threshold
        unique_files = len(repo_state.bulk_change_files)
        if unique_files >= self.config.bulk_change_threshold:
            if self.config.bulk_change_auto_pause:
                reason = (
                    f"Bulk change detected: {unique_files} files changed within "
                    f"{self.config.bulk_change_window_ms}ms window "
                    f"(threshold: {self.config.bulk_change_threshold})"
                )
                repo_state.trigger_circuit_breaker(reason, RepositoryStatus.BULK_CHANGE_PAUSED)
                self._record_trigger("bulk_change", reason)

                # Schedule auto-recovery if configured
                if self.config.auto_resume_after_bulk_pause_seconds > 0:
                    recovery_time = now_utc + timedelta(
                        seconds=self.config.auto_resume_after_bulk_pause_seconds
                    )
                    self._auto_recovery_tasks[repo_state.repo_id] = recovery_time
                    log.info(
                        "Auto-recovery scheduled",
                        repo_id=repo_state.repo_id,
                        recovery_time=recovery_time.isoformat(),
                        seconds=self.config.auto_resume_after_bulk_pause_seconds,
                    )

                log.warning(
                    "CIRCUIT BREAKER TRIGGERED: Bulk file changes detected",
                    repo_id=repo_state.repo_id,
                    unique_files=unique_files,
                    threshold=self.config.bulk_change_threshold,
                    sample_files=repo_state.bulk_change_files[:10],  # Log first 10
                    action="Event processing paused. Acknowledge to resume.",
                )

                if self.config.require_manual_acknowledgment:
                    raise BulkChangeError(
                        repo_state.repo_id,
                        unique_files,
                        self.config.bulk_change_threshold,
                        self.config.bulk_change_window_ms,
                    )

                return True
            else:
                log.warning(
                    "Bulk change threshold exceeded but auto-pause disabled",
                    repo_id=repo_state.repo_id,
                    unique_files=unique_files,
                    threshold=self.config.bulk_change_threshold,
                )

        self.metrics.total_events_processed += 1
        return False

    def check_branch_change(self, repo_state: RepositoryState, current_branch: str) -> tuple[bool, bool]:
        """Check if branch has changed and handle accordingly.

        Args:
            repo_state: Repository state to check
            current_branch: Current branch name from git

        Returns:
            Tuple of (branch_changed, circuit_breaker_triggered)

        Raises:
            BranchChangeError: If branch changed with bulk modifications and
                              require_manual_acknowledgment is True
        """
        if not self.config.branch_change_detection_enabled:
            # Just track the branch without warnings
            repo_state.update_branch(current_branch)
            return False, False

        if repo_state.circuit_breaker_triggered:
            # Already triggered, don't process further
            return False, True

        branch_changed = repo_state.check_branch_changed(current_branch)

        if not branch_changed:
            return False, False

        # Branch has changed
        old_branch = repo_state.previous_branch
        repo_state.update_branch(current_branch)

        # Check if combined with bulk changes should trigger error
        unique_files = len(repo_state.bulk_change_files)

        if (
            self.config.branch_with_bulk_change_error
            and unique_files >= self.config.branch_with_bulk_change_threshold
        ):
            reason = (
                f"Branch change with bulk file modifications: "
                f"'{old_branch}' → '{current_branch}' "
                f"with {unique_files} files changed "
                f"(threshold: {self.config.branch_with_bulk_change_threshold})"
            )
            repo_state.trigger_circuit_breaker(reason, RepositoryStatus.BRANCH_CHANGE_ERROR)
            self._record_trigger("combined", reason)

            log.error(
                "CIRCUIT BREAKER TRIGGERED: Branch change with bulk modifications",
                repo_id=repo_state.repo_id,
                old_branch=old_branch,
                current_branch=current_branch,
                unique_files=unique_files,
                threshold=self.config.branch_with_bulk_change_threshold,
                action="Verify branch and acknowledge to resume.",
            )

            if self.config.require_manual_acknowledgment:
                raise BranchChangeError(repo_state.repo_id, old_branch or "", current_branch, unique_files)

            return True, True

        # Just branch change - warning only
        if self.config.branch_change_warning_enabled:
            reason = f"Branch changed: '{old_branch}' → '{current_branch}'"
            repo_state.trigger_circuit_breaker(reason, RepositoryStatus.BRANCH_CHANGE_WARNING)
            self._record_trigger("branch_change", reason)

            log.warning(
                "CIRCUIT BREAKER WARNING: Branch switch detected",
                repo_id=repo_state.repo_id,
                old_branch=old_branch,
                current_branch=current_branch,
                action="Verify you are on the intended branch.",
            )
            return True, True

        # Branch changed but warnings disabled
        log.info(
            "Branch change detected (warnings disabled)",
            repo_id=repo_state.repo_id,
            old_branch=old_branch,
            current_branch=current_branch,
        )
        return True, False

    def check_auto_recovery(self, repo_state: RepositoryState) -> bool:
        """Check if auto-recovery should be triggered.

        Args:
            repo_state: Repository state to check

        Returns:
            True if auto-recovery was performed, False otherwise
        """
        if repo_state.repo_id not in self._auto_recovery_tasks:
            return False

        recovery_time = self._auto_recovery_tasks[repo_state.repo_id]
        now = datetime.now(UTC)

        if now >= recovery_time:
            log.info(
                "Auto-recovery triggered",
                repo_id=repo_state.repo_id,
                scheduled_time=recovery_time.isoformat(),
            )
            # acknowledge_circuit_breaker will clean up the auto-recovery task
            self.acknowledge_circuit_breaker(repo_state, auto_recovery=True)
            return True

        return False

    def should_process_event(self, repo_state: RepositoryState) -> bool:
        """Check if events should be processed for this repository.

        Args:
            repo_state: Repository state to check

        Returns:
            True if events should be processed, False if circuit breaker is active
        """
        # Check for auto-recovery first
        self.check_auto_recovery(repo_state)

        if not repo_state.circuit_breaker_triggered:
            return True

        # Check if in a blocking circuit breaker state
        blocking_states = {
            RepositoryStatus.BULK_CHANGE_PAUSED,
            RepositoryStatus.BRANCH_CHANGE_ERROR,
        }

        if repo_state.status in blocking_states:
            self.metrics.total_events_blocked += 1
            log.debug(
                "Event processing blocked by circuit breaker",
                repo_id=repo_state.repo_id,
                status=repo_state.status.name,
                reason=repo_state.circuit_breaker_reason,
            )
            return False

        # Warning states allow event processing but flag the warning
        if repo_state.status == RepositoryStatus.BRANCH_CHANGE_WARNING:
            log.debug(
                "Event processing allowed with warning",
                repo_id=repo_state.repo_id,
                warning=repo_state.circuit_breaker_reason,
            )
            # Allow processing but keep the warning active

        self.metrics.total_events_processed += 1
        return True

    def acknowledge_circuit_breaker(self, repo_state: RepositoryState, auto_recovery: bool = False) -> None:
        """Acknowledge and reset a triggered circuit breaker.

        Args:
            repo_state: Repository state to reset
            auto_recovery: Whether this is an auto-recovery (vs manual acknowledgment)
        """
        if not repo_state.circuit_breaker_triggered:
            log.debug("No circuit breaker to acknowledge", repo_id=repo_state.repo_id)
            return

        if auto_recovery:
            self.metrics.auto_recoveries += 1
            log.info(
                "Circuit breaker auto-recovered",
                repo_id=repo_state.repo_id,
                reason=repo_state.circuit_breaker_reason,
                status=repo_state.status.name,
            )
        else:
            self.metrics.manual_acknowledgments += 1
            log.info(
                "Circuit breaker manually acknowledged",
                repo_id=repo_state.repo_id,
                reason=repo_state.circuit_breaker_reason,
                status=repo_state.status.name,
            )

        repo_state.reset_circuit_breaker()
        repo_state.update_status(RepositoryStatus.IDLE)

        # Clean up any scheduled auto-recovery
        if repo_state.repo_id in self._auto_recovery_tasks:
            del self._auto_recovery_tasks[repo_state.repo_id]

    def get_circuit_breaker_summary(self, repo_state: RepositoryState) -> dict[str, Any]:
        """Get a summary of the current circuit breaker state.

        Args:
            repo_state: Repository state to summarize

        Returns:
            Dictionary with circuit breaker status information
        """
        summary: dict[str, Any] = {
            "triggered": repo_state.circuit_breaker_triggered,
            "reason": repo_state.circuit_breaker_reason,
            "status": repo_state.status.name,
            "bulk_change_count": repo_state.bulk_change_count,
            "unique_files_in_window": len(repo_state.bulk_change_files),
            "current_branch": repo_state.current_branch,
            "previous_branch": repo_state.previous_branch,
        }

        # Add auto-recovery info if scheduled
        if repo_state.repo_id in self._auto_recovery_tasks:
            recovery_time = self._auto_recovery_tasks[repo_state.repo_id]
            remaining = (recovery_time - datetime.now(UTC)).total_seconds()
            summary["auto_recovery_scheduled"] = True
            summary["auto_recovery_in_seconds"] = max(0, int(remaining))
        else:
            summary["auto_recovery_scheduled"] = False

        return summary

    def get_metrics(self) -> CircuitBreakerMetrics:
        """Get the current metrics for this circuit breaker service.

        Returns:
            CircuitBreakerMetrics instance with current statistics
        """
        return self.metrics

    def reset_metrics(self) -> None:
        """Reset all metrics counters."""
        self.metrics = CircuitBreakerMetrics()
        log.info("Circuit breaker metrics reset")


# 🔼⚙️🔚
