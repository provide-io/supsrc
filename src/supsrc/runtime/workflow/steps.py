# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#


from __future__ import annotations

from typing import TYPE_CHECKING

from provide.foundation.logger import get_logger

from supsrc.events.system import (
    ConflictDetectedEvent,
    ExternalCommitEvent,
    GitSpecialStateDetectedEvent,
    LLMVetoEvent,
    RepositoryFrozenEvent,
    TestFailureEvent,
)
from supsrc.runtime.workflow.test_runner import TestRunner
from supsrc.state import RepositoryStatus

if TYPE_CHECKING:
    from supsrc.config import LLMConfig, SupsrcConfig
    from supsrc.llm.providers.base import LLMProvider
    from supsrc.protocols import RepositoryEngine
    from supsrc.runtime.tui_interface import TUIInterface
    from supsrc.state import RepositoryState

log = get_logger("runtime.workflow.steps")


class WorkflowSteps:
    """Individual workflow step implementations."""

    def __init__(
        self,
        config: SupsrcConfig,
        repo_states: dict[str, RepositoryState],
        repo_engines: dict[str, RepositoryEngine],
        tui: TUIInterface,
        emit_event_callback,
    ) -> None:
        """Initialize workflow steps with dependencies.

        Args:
            config: Global supsrc configuration
            repo_states: Repository state dictionary
            repo_engines: Repository engine dictionary
            tui: TUI interface for updates
            emit_event_callback: Callback function to emit events
        """
        self.config = config
        self.repo_states = repo_states
        self.repo_engines = repo_engines
        self.tui = tui
        self._emit_event = emit_event_callback

    async def execute_status_check(self, repo_id: str) -> bool:
        """Execute the status check workflow step.

        Args:
            repo_id: Repository identifier

        Returns:
            True if should continue workflow, False if should abort
        """
        repo_state = self.repo_states[repo_id]
        repo_config = self.config.repositories[repo_id]
        repo_engine = self.repo_engines[repo_id]
        action_log = log.bind(repo_id=repo_id)

        # Update status and UI
        repo_state.update_status(RepositoryStatus.PROCESSING)
        repo_state.action_description = "Checking status..."
        self.tui.post_state_update(self.repo_states)

        # Get repository status
        status_result = await repo_engine.get_status(
            repo_state, repo_config.repository, self.config.global_config, repo_config.path
        )

        # Update repository statistics if status was retrieved successfully
        if status_result.success:
            repo_state.total_files = status_result.total_files or 0
            repo_state.changed_files = status_result.changed_files or 0
            repo_state.added_files = status_result.added_files or 0
            repo_state.deleted_files = status_result.deleted_files or 0
            repo_state.modified_files = status_result.modified_files or 0
            repo_state.has_uncommitted_changes = not status_result.is_clean
            repo_state.current_branch = status_result.current_branch
            # Update remote sync status
            repo_state.commits_ahead = status_result.commits_ahead
            repo_state.commits_behind = status_result.commits_behind
            repo_state.has_upstream = status_result.has_upstream
            repo_state.upstream_branch = status_result.upstream_branch

        # Check for special Git states (merge, rebase, cherry-pick, revert in progress)
        if (
            status_result.is_merge_in_progress
            or status_result.is_rebase_in_progress
            or status_result.is_cherry_pick_in_progress
            or status_result.is_revert_in_progress
        ):
            await self._handle_special_git_state_detected(repo_id, repo_state, status_result)
            self.tui.post_state_update(self.repo_states)
            return False

        # Handle various failure/edge cases
        if not status_result.success or status_result.is_conflicted or status_result.is_clean:
            if not status_result.success:
                await self._handle_status_check_failure(repo_id, repo_state, status_result, action_log)
            elif status_result.is_conflicted:
                await self._handle_conflict_detected(repo_id, repo_state)
            else:  # is_clean - likely external commit
                await self._handle_external_commit_detected(repo_id, repo_state, action_log)

            self.tui.post_state_update(self.repo_states)
            return False

        # Check branch protection AFTER we know the current branch
        return await self._check_branch_protection(repo_id, repo_state, repo_config)

    async def execute_staging(self, repo_id: str) -> tuple[bool, list[str] | None]:
        """Execute the staging workflow step.

        Args:
            repo_id: Repository identifier

        Returns:
            Tuple of (should_continue, staged_files_list)
        """
        repo_state = self.repo_states[repo_id]
        repo_config = self.config.repositories[repo_id]
        repo_engine = self.repo_engines[repo_id]

        # Check for large/binary file warnings BEFORE staging
        if hasattr(repo_engine, "operations"):
            global_config = self.config.global_config
            warnings = repo_engine.operations.analyze_files_for_warnings(
                repo_config.path,
                large_threshold=global_config.large_file_threshold_bytes,
                binary_warn=global_config.binary_file_warning_enabled,
            )
            if warnings:
                # Trigger circuit breaker for file warnings
                large_files = [w for w in warnings if w["type"] == "large_file"]
                binary_files = [w for w in warnings if w["type"] == "binary_file"]

                warning_messages = []
                if large_files:
                    warning_messages.append(f"{len(large_files)} large file(s) detected")
                if binary_files:
                    warning_messages.append(f"{len(binary_files)} binary file(s) detected")

                reason = f"File warnings: {', '.join(warning_messages)}"
                repo_state.trigger_circuit_breaker(reason, RepositoryStatus.BULK_CHANGE_PAUSED)
                repo_state.action_description = reason

                # Store warnings in state for TUI display
                repo_state.file_warnings = warnings

                # Emit warning event
                from supsrc.events.system import ErrorEvent

                warning_event = ErrorEvent(
                    description=reason,
                    source="file_analysis",
                    error_type="FileWarning",
                    repo_id=repo_id,
                )
                self._emit_event(warning_event)

                self.tui.post_state_update(self.repo_states)
                self.tui.post_log_update(
                    repo_id, "WARNING", f"Circuit breaker triggered: {reason}. Press [A] to acknowledge."
                )
                return False, None

        # Update status
        repo_state.update_status(RepositoryStatus.STAGING)
        repo_state.action_description = "Staging changes..."

        # Stage changes
        stage_result = await repo_engine.stage_changes(
            None, repo_state, repo_config.repository, self.config.global_config, repo_config.path
        )

        if not stage_result.success:
            repo_state.update_status(RepositoryStatus.ERROR, f"Staging failed: {stage_result.message}")
            repo_state.action_description = "Staging failed."

            # Emit error event for staging failure
            from supsrc.events.system import ErrorEvent

            staging_error_event = ErrorEvent(
                description=f"Git staging failed: {stage_result.message}",
                source="git",
                error_type="StagingFailed",
                repo_id=repo_id,
            )
            self._emit_event(staging_error_event)

            self.tui.post_state_update(self.repo_states)
            return False, None

        return True, stage_result.files_staged

    async def execute_llm_pipeline(
        self, repo_id: str, llm_config: LLMConfig, llm_provider: LLMProvider, staged_diff: str
    ) -> tuple[bool, str]:
        """Execute the LLM pipeline workflow step.

        Args:
            repo_id: Repository identifier
            llm_config: LLM configuration
            llm_provider: LLM provider instance
            staged_diff: Staged diff content

        Returns:
            Tuple of (should_continue, commit_message)
        """
        repo_state = self.repo_states[repo_id]
        repo_config = self.config.repositories[repo_id]
        commit_message = ""

        # LLM Review Step
        if llm_config.review_changes:
            repo_state.update_status(RepositoryStatus.REVIEWING)
            repo_state.action_description = "Reviewing changes with LLM..."
            veto, reason = await llm_provider.review_changes(staged_diff)
            if veto:
                repo_state.update_status(RepositoryStatus.ERROR, f"LLM Review Veto: {reason}")
                repo_state.action_description = f"LLM Review Veto: {reason}"

                # Emit LLM veto event
                veto_event = LLMVetoEvent(
                    description=f"LLM review blocked commit: {reason}",
                    repo_id=repo_id,
                    reason=reason,
                )
                self._emit_event(veto_event)

                self.tui.post_state_update(self.repo_states)
                return False, ""

        # LLM Test Step
        if llm_config.run_tests:
            repo_state.update_status(RepositoryStatus.TESTING)
            repo_state.action_description = "Running automated tests..."
            exit_code, stdout, stderr = await TestRunner.run_tests(llm_config.test_command, repo_config.path)
            if exit_code != 0:
                failure_output = f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
                analysis = "Test run failed."
                if llm_config.analyze_test_failures:
                    repo_state.update_status(RepositoryStatus.ANALYZING)
                    repo_state.action_description = "Analyzing test failure with LLM..."
                    analysis = await llm_provider.analyze_test_failure(failure_output)
                repo_state.update_status(RepositoryStatus.ERROR, f"Tests Failed: {analysis}")
                repo_state.action_description = "Automated tests failed."

                # Emit test failure event
                test_failure_event = TestFailureEvent(
                    description=f"Automated tests failed: {analysis}",
                    repo_id=repo_id,
                    test_output=failure_output,
                )
                self._emit_event(test_failure_event)

                self.tui.post_state_update(self.repo_states)
                return False, ""

        # LLM Commit Message Generation Step
        if llm_config.generate_commit_message:
            repo_state.update_status(RepositoryStatus.GENERATING_COMMIT)
            repo_state.action_description = "Generating commit message with LLM..."
            # The LLM now generates only the subject line of the commit.
            llm_subject = await llm_provider.generate_commit_message(
                staged_diff, llm_config.use_conventional_commit
            )
            # We construct the final message template, preserving the placeholder for the body.
            commit_message = f"{llm_subject}\n\n{{{{change_summary}}}}"

        return True, commit_message

    async def _handle_status_check_failure(self, repo_id: str, repo_state, status_result, action_log):
        """Handle status check failure."""
        action_log.warning(
            "Git status check failed during action",
            message=status_result.message,
            success=status_result.success,
        )
        repo_state.update_status(RepositoryStatus.ERROR, f"Status check failed: {status_result.message}")
        repo_state.action_description = "Status check failed."

        # Emit error event for status check failure
        from supsrc.events.system import ErrorEvent

        status_error_event = ErrorEvent(
            description=f"Git status check failed: {status_result.message}",
            source="git",
            error_type="StatusCheckFailed",
            repo_id=repo_id,
        )
        self._emit_event(status_error_event)

    async def _handle_conflict_detected(self, repo_id: str, repo_state):
        """Handle merge conflict detection."""
        repo_state.update_status(RepositoryStatus.CONFLICT_DETECTED, "Repo has conflicts.")
        repo_state.action_description = "Merge conflict detected."
        repo_state.is_frozen = True
        repo_state.freeze_reason = "Merge conflicts detected"

        # Emit conflict detected event
        conflict_event = ConflictDetectedEvent(
            description="Merge conflicts detected in repository",
            repo_id=repo_id,
            conflict_files=[],  # Could be enhanced to show specific files
        )
        self._emit_event(conflict_event)

        # Emit repository frozen event
        frozen_event = RepositoryFrozenEvent(
            description="Repository frozen due to merge conflicts",
            repo_id=repo_id,
            reason="Merge conflicts detected",
        )
        self._emit_event(frozen_event)

    async def _handle_external_commit_detected(self, repo_id: str, repo_state, action_log):
        """Handle external commit detection."""
        # Log the detection for debugging
        action_log.info("Repository is clean during action - external commit detected")

        # Update status to indicate external commit was detected
        repo_state.update_status(RepositoryStatus.EXTERNAL_COMMIT_DETECTED, "Changes committed externally")
        repo_state.action_description = "External commit detected"

        # Emit external commit event
        external_commit_event = ExternalCommitEvent(
            description="Changes were committed externally",
            repo_id=repo_id,
            commit_hash=None,  # Could be enhanced to get actual commit hash
        )
        self._emit_event(external_commit_event)

    async def _handle_special_git_state_detected(self, repo_id: str, repo_state, status_result):
        """Handle special Git state detection (merge, rebase, cherry-pick, revert)."""
        # Determine which state is active
        state_type = None
        status_enum = None

        if status_result.is_merge_in_progress:
            state_type = "merge"
            status_enum = RepositoryStatus.MERGE_IN_PROGRESS
        elif status_result.is_rebase_in_progress:
            state_type = "rebase"
            status_enum = RepositoryStatus.REBASE_IN_PROGRESS
        elif status_result.is_cherry_pick_in_progress:
            state_type = "cherry-pick"
            status_enum = RepositoryStatus.CHERRY_PICK_IN_PROGRESS
        elif status_result.is_revert_in_progress:
            state_type = "revert"
            status_enum = RepositoryStatus.REVERT_IN_PROGRESS

        if state_type and status_enum:
            # Update repository state
            repo_state.update_status(status_enum, f"{state_type.capitalize()} operation in progress")
            repo_state.action_description = f"{state_type.capitalize()} in progress - auto-commit paused"
            repo_state.is_frozen = True
            repo_state.freeze_reason = f"{state_type.capitalize()} operation in progress"

            # Emit special state detected event
            special_state_event = GitSpecialStateDetectedEvent(
                description=f"{state_type.capitalize()} operation detected in repository",
                repo_id=repo_id,
                state_type=state_type,
            )
            self._emit_event(special_state_event)

            # Emit repository frozen event
            frozen_event = RepositoryFrozenEvent(
                description=f"Repository frozen due to {state_type} operation in progress",
                repo_id=repo_id,
                reason=f"{state_type.capitalize()} operation in progress",
            )
            self._emit_event(frozen_event)

    async def _check_branch_protection(self, repo_id: str, repo_state, repo_config) -> bool:
        """Check if current branch is protected and handle accordingly.

        Args:
            repo_id: Repository identifier
            repo_state: Repository state object
            repo_config: Repository configuration

        Returns:
            True if commit should proceed, False if blocked/warned
        """
        branch_protection = repo_config.branch_protection
        if not branch_protection.enabled:
            return True

        current_branch = repo_state.current_branch
        if not current_branch:
            return True  # Can't check if we don't know the branch

        # Check if current branch matches any protected pattern
        if not _is_branch_protected(current_branch, branch_protection.protected_branches):
            return True

        # Branch is protected
        reason = f"Branch '{current_branch}' is protected"

        if branch_protection.warn_only:
            # Just log a warning but allow commit
            self.tui.post_log_update(repo_id, "WARNING", f"{reason} - proceeding with caution")
            return True

        if branch_protection.block_commits:
            # Block the commit with circuit breaker
            repo_state.trigger_circuit_breaker(reason, RepositoryStatus.BULK_CHANGE_PAUSED)
            repo_state.action_description = reason

            # Emit branch protection event
            from supsrc.events.system import ErrorEvent

            protection_event = ErrorEvent(
                description=reason,
                source="branch_protection",
                error_type="ProtectedBranch",
                repo_id=repo_id,
            )
            self._emit_event(protection_event)

            self.tui.post_state_update(self.repo_states)
            self.tui.post_log_update(
                repo_id, "WARNING", f"Circuit breaker triggered: {reason}. Press [A] to acknowledge."
            )
            return False

        return True


def _is_branch_protected(branch: str, patterns: tuple[str, ...]) -> bool:
    """Check if a branch matches any protected pattern.

    Supports simple wildcard patterns:
    - "main" matches exactly "main"
    - "release/*" matches "release/1.0", "release/2.0", etc.
    - "*" at the end matches any suffix

    Args:
        branch: Current branch name
        patterns: Tuple of protected branch patterns

    Returns:
        True if branch matches any pattern
    """
    import fnmatch

    return any(fnmatch.fnmatch(branch, pattern) for pattern in patterns)


# 🔼⚙️🔚
