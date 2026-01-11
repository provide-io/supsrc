# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#


from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from provide.foundation.errors import resilient
from provide.foundation.logger import get_logger

from supsrc.runtime.workflow.git_operations import GitOperationsHelper
from supsrc.runtime.workflow.llm_utils import LLM_AVAILABLE, LLMProviderManager
from supsrc.runtime.workflow.steps import WorkflowSteps
from supsrc.state import RepositoryStatus

if TYPE_CHECKING:
    from supsrc.config import SupsrcConfig
    from supsrc.events.collector import EventCollector
    from supsrc.protocols import RepositoryEngine
    from supsrc.runtime.tui_interface import TUIInterface
    from supsrc.state import RepositoryState

log = get_logger("runtime.workflow.executor")


class RuntimeWorkflow:
    """Executes the full status -> stage -> commit -> push sequence."""

    def __init__(
        self,
        config: SupsrcConfig,
        repo_states: dict[str, RepositoryState],
        repo_engines: dict[str, RepositoryEngine],
        tui: TUIInterface,
        event_collector: EventCollector | None = None,
    ):
        """Initialize the RuntimeWorkflow.

        Args:
            config: Global supsrc configuration
            repo_states: Repository state dictionary
            repo_engines: Repository engine dictionary
            tui: TUI interface for updates
            event_collector: Optional event collector for headless mode
        """
        self.config = config
        self.repo_states = repo_states
        self.repo_engines = repo_engines
        self.tui = tui
        self.event_collector = event_collector
        self._llm_manager = LLMProviderManager()
        self._workflow_steps = WorkflowSteps(config, repo_states, repo_engines, tui, self._emit_event)
        self._background_tasks: set[asyncio.Task[None]] = set()
        log.debug("RuntimeWorkflow initialized.")

    def _emit_event(self, event) -> None:
        """Emit event to available event collector (TUI or standalone)."""
        # Try standalone event collector first (headless mode)
        if self.event_collector:
            log.debug("Emitting event via workflow event collector", event_type=type(event).__name__)
            self.event_collector.emit(event)
            return

        # Fall back to TUI event collector if available
        tui_app = getattr(self.tui, "app", None)
        event_collector = getattr(tui_app, "event_collector", None) if tui_app else None
        if event_collector:
            log.debug("Emitting event via TUI app event collector", event_type=type(event).__name__)
            event_collector.emit(event)
            return

        log.warning("No event collector available to emit event", event_type=type(event).__name__)

    async def _delayed_reset_after_external_commit(self, repo_state: RepositoryState) -> None:
        """Reset repository state after a brief delay to show external commit status."""
        await asyncio.sleep(2.0)  # Show the status for 2 seconds
        repo_state.reset_after_action()
        self.tui.post_state_update(self.repo_states)

    @resilient(
        log_errors=True,
        suppress=(Exception,),  # Suppress all errors to avoid crashing the orchestrator
        context_provider=lambda: {
            "component": "runtime_workflow",
            "method": "execute_action_sequence",
        },
    )
    async def execute_action_sequence(self, repo_id: str) -> None:
        """Runs the full action workflow, including optional LLM steps.

        Args:
            repo_id: Repository identifier to execute workflow for
        """
        repo_state = self.repo_states.get(repo_id)
        repo_config = self.config.repositories.get(repo_id)
        repo_engine = self.repo_engines.get(repo_id)
        action_log = log.bind(repo_id=repo_id)

        if repo_state is None or repo_config is None or repo_engine is None:
            action_log.error("Action failed: Missing state, config, or engine.")
            self.tui.post_log_update(repo_id, "ERROR", "Action failed: Missing state/config/engine.")
            return

        action_log.info("Executing action sequence...")
        self.tui.post_log_update(repo_id, "INFO", "Action triggered. Starting workflow...")

        try:
            # 1. Status Check
            if not await self._workflow_steps.execute_status_check(repo_id):
                # Handle special case of external commit detection
                if repo_state.status == RepositoryStatus.EXTERNAL_COMMIT_DETECTED:
                    # Reset after brief pause to show the status
                    reset_task = asyncio.create_task(self._delayed_reset_after_external_commit(repo_state))
                    self._background_tasks.add(reset_task)
                    reset_task.add_done_callback(self._background_tasks.discard)
                return

            # 2. Staging
            should_continue, staged_files = await self._workflow_steps.execute_staging(repo_id)
            if not should_continue:
                return

            # Get staged diff for LLM processing
            staged_diff = await GitOperationsHelper.get_staged_diff(repo_config.path)
            commit_message = ""

            # 3. LLM Pipeline (if enabled)
            llm_config = repo_config.llm
            if llm_config and llm_config.enabled:
                if not LLM_AVAILABLE:
                    await self._handle_llm_provider_failure(repo_id, repo_state)
                    return

                llm_provider = self._llm_manager.get_llm_provider(llm_config)
                if not llm_provider:
                    await self._handle_llm_provider_failure(repo_id, repo_state)
                    return

                should_continue, commit_message = await self._workflow_steps.execute_llm_pipeline(
                    repo_id, llm_config, llm_provider, staged_diff
                )
                if not should_continue:
                    return

            # 4. Commit
            await self._execute_commit_step(
                repo_id, repo_state, repo_config, repo_engine, commit_message, staged_files
            )

        except Exception as e:
            await self._handle_unexpected_error(repo_id, repo_state, action_log, e)

    async def _handle_llm_provider_failure(self, repo_id: str, repo_state: RepositoryState) -> None:
        """Handle LLM provider initialization failure."""
        repo_state.update_status(RepositoryStatus.ERROR, "LLM provider failed to init.")
        repo_state.action_description = "LLM provider failed."

        # Emit error event for LLM provider failure
        from supsrc.events.system import ErrorEvent

        llm_error_event = ErrorEvent(
            description="LLM provider failed to initialize",
            source="llm",
            error_type="ProviderInitFailed",
            repo_id=repo_id,
        )
        self._emit_event(llm_error_event)

        self.tui.post_state_update(self.repo_states)

    async def _execute_commit_step(
        self,
        repo_id: str,
        repo_state,
        repo_config,
        repo_engine,
        commit_message: str,
        staged_files: list[str] | None,
    ) -> None:
        """Execute the commit and push workflow steps."""
        action_log = log.bind(repo_id=repo_id)

        # Perform Commit
        repo_state.update_status(RepositoryStatus.COMMITTING)
        repo_state.action_description = "Performing commit..."
        commit_result = await repo_engine.perform_commit(
            commit_message,
            repo_state,
            repo_config.repository,
            self.config.global_config,
            repo_config.path,
        )

        if not commit_result.success:
            await self._handle_commit_failure(repo_id, repo_state, commit_result)
        elif commit_result.commit_hash is None:
            repo_state.reset_after_action()
        else:
            await self._handle_commit_success(
                repo_id,
                repo_state,
                repo_config,
                repo_engine,
                commit_result,
                action_log,
                staged_files,
            )

        self.tui.post_state_update(self.repo_states)

    async def _handle_commit_failure(self, repo_id: str, repo_state, commit_result) -> None:
        """Handle commit failure."""
        repo_state.update_status(RepositoryStatus.ERROR, f"Commit failed: {commit_result.message}")
        repo_state.action_description = "Commit operation failed."

        # Emit error event for commit failure
        from supsrc.events.system import ErrorEvent

        commit_error_event = ErrorEvent(
            description=f"Git commit failed: {commit_result.message}",
            source="git",
            error_type="CommitFailed",
            repo_id=repo_id,
        )
        self._emit_event(commit_error_event)

    async def _handle_commit_success(
        self,
        repo_id: str,
        repo_state,
        repo_config,
        repo_engine,
        commit_result,
        action_log,
        staged_files: list[str] | None,
    ) -> None:
        """Handle successful commit and execute push."""
        from datetime import UTC, datetime

        repo_state.last_commit_short_hash = commit_result.commit_hash[:7]
        # Update last commit timestamp to current time
        repo_state.last_commit_timestamp = datetime.now(UTC)

        # Generate change fragment if configured
        llm_config = repo_config.llm
        if llm_config and llm_config.enabled and llm_config.generate_change_fragment and LLM_AVAILABLE:
            await self._generate_change_fragment(
                repo_id, repo_config, repo_engine, llm_config, commit_result.commit_hash
            )

        # Emit git commit event
        from supsrc.engines.git.events import GitCommitEvent

        # Use the staged files count from before the commit
        files_count = len(staged_files) if staged_files else 0

        commit_event = GitCommitEvent(
            description=f"Committed {files_count} files",
            repo_id=repo_id,
            commit_hash=commit_result.commit_hash,
            branch=repo_state.current_branch or "main",
            files_changed=files_count,
        )
        self._emit_event(commit_event)

        # Record session statistics
        repo_state.record_session_commit(files_count)

        # Execute Push
        await self._execute_push_step(repo_id, repo_state, repo_config, repo_engine, action_log)

        # Reset state after action
        repo_state.reset_after_action()

        # Refresh repository statistics
        await self._refresh_repository_statistics(repo_id, repo_state, repo_config, repo_engine, action_log)

    async def _execute_push_step(self, repo_id: str, repo_state, repo_config, repo_engine, action_log) -> None:
        """Execute the push workflow step."""
        action_log.info("Commit successful", commit_hash=repo_state.last_commit_short_hash)

        # Check for upstream conflicts BEFORE pushing
        if hasattr(repo_engine, "operations"):
            conflict_info = await repo_engine.operations.check_upstream_conflicts(repo_config.path)

            # Block push if merge conflicts detected
            if conflict_info.get("has_conflicts"):
                conflict_files = conflict_info.get("conflict_files", [])
                reason = f"Merge conflicts detected in {len(conflict_files)} file(s)"
                repo_state.trigger_circuit_breaker(reason, RepositoryStatus.CONFLICT_DETECTED)
                repo_state.action_description = reason

                # Emit conflict detected event
                from supsrc.events.system import ConflictDetectedEvent

                conflict_event = ConflictDetectedEvent(
                    description=reason,
                    repo_id=repo_id,
                    conflict_files=conflict_files,
                )
                self._emit_event(conflict_event)

                self.tui.post_state_update(self.repo_states)
                self.tui.post_log_update(
                    repo_id, "WARNING", f"Circuit breaker triggered: {reason}. Press [A] to acknowledge."
                )
                return

            # Block push if branch has diverged (both ahead and behind)
            if conflict_info.get("diverged"):
                ahead = conflict_info.get("ahead", 0)
                behind = conflict_info.get("behind", 0)
                reason = f"Branch diverged: {ahead} ahead, {behind} behind upstream"
                repo_state.trigger_circuit_breaker(reason, RepositoryStatus.BULK_CHANGE_PAUSED)
                repo_state.action_description = reason

                # Emit warning event
                from supsrc.events.system import ErrorEvent

                divergence_event = ErrorEvent(
                    description=reason,
                    source="git",
                    error_type="BranchDiverged",
                    repo_id=repo_id,
                )
                self._emit_event(divergence_event)

                self.tui.post_state_update(self.repo_states)
                self.tui.post_log_update(
                    repo_id, "WARNING", f"Circuit breaker triggered: {reason}. Press [A] to acknowledge."
                )
                return

        repo_state.update_status(RepositoryStatus.PUSHING)
        repo_state.action_description = "Pushing to remote..."
        push_result = await repo_engine.perform_push(
            repo_state, repo_config.repository, self.config.global_config, repo_config.path
        )

        if not push_result.success:
            action_log.warning("Push failed", reason=push_result.message)
            self.tui.post_log_update(repo_id, "WARNING", f"Push failed: {push_result.message}")
        elif push_result.skipped:
            self.tui.post_log_update(repo_id, "INFO", "Push skipped by configuration.")
        else:
            # Push succeeded - emit push event
            from supsrc.engines.git.events import GitPushEvent

            push_event = GitPushEvent(
                description="Pushed to remote repository",
                repo_id=repo_id,
                remote=repo_config.repository.get("remote", "origin"),
                branch=repo_state.current_branch or "main",
                commits_pushed=1,
            )
            self._emit_event(push_event)

            # Record session push statistics
            repo_state.record_session_push()

    async def _generate_change_fragment(
        self, repo_id: str, repo_config, repo_engine, llm_config, commit_hash: str
    ) -> None:
        """Generate and save change fragment using LLM."""
        llm_provider = self._llm_manager.get_llm_provider(llm_config)
        if not llm_provider:
            return

        summary_result = await repo_engine.get_summary(repo_config.path)
        final_commit_message = summary_result.head_commit_message_summary or ""

        # Get staged diff for fragment generation
        staged_diff = await GitOperationsHelper.get_staged_diff(repo_config.path)

        fragment = await llm_provider.generate_change_fragment(staged_diff, final_commit_message)
        await GitOperationsHelper.save_change_fragment(
            fragment, repo_config.path, llm_config.change_fragment_dir, commit_hash
        )

    async def _refresh_repository_statistics(
        self, repo_id: str, repo_state, repo_config, repo_engine, action_log
    ) -> None:
        """Refresh repository statistics after successful commit."""
        try:
            status_result = await repo_engine.get_status(
                repo_state, repo_config.repository, self.config.global_config, repo_config.path
            )
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
        except Exception as e:
            action_log.warning("Failed to refresh repository statistics after commit", error=str(e))

    async def _handle_unexpected_error(self, repo_id: str, repo_state, action_log, error: Exception) -> None:
        """Handle unexpected errors during workflow execution."""
        action_log.critical("Unexpected error in action sequence", error=str(error), exc_info=True)
        if repo_state:
            repo_state.update_status(RepositoryStatus.ERROR, f"Action failure: {error}")
            repo_state.action_description = "Unexpected action failure."

            # Emit error event for unexpected action failure
            from supsrc.events.system import ErrorEvent

            action_error_event = ErrorEvent(
                description=f"Unexpected action failure: {error!s}",
                source="runtime_workflow",
                error_type="UnexpectedFailure",
                repo_id=repo_id,
            )
            self._emit_event(action_error_event)

            self.tui.post_state_update(self.repo_states)


# 🔼⚙️🔚
