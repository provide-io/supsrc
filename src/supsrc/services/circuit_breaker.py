#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Circuit breaker service for detecting dangerous operations and pausing automation."""

from datetime import UTC, datetime, timedelta

from provide.foundation.logger import get_logger

from supsrc.config.models import CircuitBreakerConfig
from supsrc.state.runtime import RepositoryState, RepositoryStatus

log = get_logger("services.circuit_breaker")


class CircuitBreakerService:
    """Service for monitoring and triggering circuit breakers on repository operations."""

    def __init__(self, config: CircuitBreakerConfig):
        """Initialize circuit breaker service with configuration.

        Args:
            config: Circuit breaker configuration settings
        """
        self.config = config
        log.info(
            "CircuitBreakerService initialized",
            bulk_change_threshold=config.bulk_change_threshold,
            bulk_change_window_ms=config.bulk_change_window_ms,
            branch_change_detection=config.branch_change_detection_enabled,
            branch_with_bulk_threshold=config.branch_with_bulk_change_threshold,
        )

    def check_and_update_bulk_change(self, repo_state: RepositoryState, file_path: str) -> bool:
        """Check if bulk change threshold has been exceeded.

        Args:
            repo_state: Repository state to check and update
            file_path: Path of the file that changed

        Returns:
            True if circuit breaker was triggered, False otherwise
        """
        if self.config.bulk_change_threshold == 0:
            # Feature disabled
            return False

        if repo_state.circuit_breaker_triggered:
            # Already triggered, don't process further
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
                log.warning(
                    "Bulk change circuit breaker triggered",
                    repo_id=repo_state.repo_id,
                    unique_files=unique_files,
                    threshold=self.config.bulk_change_threshold,
                    files=repo_state.bulk_change_files[:10],  # Log first 10
                )
                return True
            else:
                log.warning(
                    "Bulk change threshold exceeded but auto-pause disabled",
                    repo_id=repo_state.repo_id,
                    unique_files=unique_files,
                    threshold=self.config.bulk_change_threshold,
                )

        return False

    def check_branch_change(self, repo_state: RepositoryState, current_branch: str) -> tuple[bool, bool]:
        """Check if branch has changed and handle accordingly.

        Args:
            repo_state: Repository state to check
            current_branch: Current branch name from git

        Returns:
            Tuple of (branch_changed, circuit_breaker_triggered)
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
                f"Branch change with bulk file modifications detected: "
                f"Branch changed from '{old_branch}' to '{current_branch}' "
                f"with {unique_files} files changed "
                f"(threshold: {self.config.branch_with_bulk_change_threshold})"
            )
            repo_state.trigger_circuit_breaker(reason, RepositoryStatus.BRANCH_CHANGE_ERROR)
            log.error(
                "Branch change with bulk files circuit breaker triggered",
                repo_id=repo_state.repo_id,
                old_branch=old_branch,
                current_branch=current_branch,
                unique_files=unique_files,
                threshold=self.config.branch_with_bulk_change_threshold,
            )
            return True, True

        # Just branch change - warning only
        if self.config.branch_change_warning_enabled:
            reason = f"Branch changed from '{old_branch}' to '{current_branch}'"
            repo_state.trigger_circuit_breaker(reason, RepositoryStatus.BRANCH_CHANGE_WARNING)
            log.warning(
                "Branch change warning triggered",
                repo_id=repo_state.repo_id,
                old_branch=old_branch,
                current_branch=current_branch,
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

    def should_process_event(self, repo_state: RepositoryState) -> bool:
        """Check if events should be processed for this repository.

        Args:
            repo_state: Repository state to check

        Returns:
            True if events should be processed, False if circuit breaker is active
        """
        if not repo_state.circuit_breaker_triggered:
            return True

        # Check if in a blocking circuit breaker state
        blocking_states = {
            RepositoryStatus.BULK_CHANGE_PAUSED,
            RepositoryStatus.BRANCH_CHANGE_ERROR,
        }

        if repo_state.status in blocking_states:
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

        return True

    def acknowledge_circuit_breaker(self, repo_state: RepositoryState) -> None:
        """Acknowledge and reset a triggered circuit breaker.

        Args:
            repo_state: Repository state to reset
        """
        if not repo_state.circuit_breaker_triggered:
            log.debug("No circuit breaker to acknowledge", repo_id=repo_state.repo_id)
            return

        log.info(
            "Acknowledging circuit breaker",
            repo_id=repo_state.repo_id,
            reason=repo_state.circuit_breaker_reason,
            status=repo_state.status.name,
        )

        repo_state.reset_circuit_breaker()
        repo_state.update_status(RepositoryStatus.IDLE)

    def get_circuit_breaker_summary(self, repo_state: RepositoryState) -> dict[str, str | int | bool | None]:
        """Get a summary of the current circuit breaker state.

        Args:
            repo_state: Repository state to summarize

        Returns:
            Dictionary with circuit breaker status information
        """
        return {
            "triggered": repo_state.circuit_breaker_triggered,
            "reason": repo_state.circuit_breaker_reason,
            "status": repo_state.status.name,
            "bulk_change_count": repo_state.bulk_change_count,
            "unique_files_in_window": len(repo_state.bulk_change_files),
            "current_branch": repo_state.current_branch,
            "previous_branch": repo_state.previous_branch,
        }


# 🔼⚙️🔚
