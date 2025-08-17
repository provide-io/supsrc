# src/supsrc/runtime/action_handler.py

"""
Handles the execution of the triggered action sequence for a repository.
"""

import structlog

from supsrc.config import SupsrcConfig
from supsrc.protocols import (
    CommitResult,
    PushResult,
    RepositoryEngine,
    RepoStatusResult,
    StageResult,
)
from supsrc.runtime.tui_interface import TUIInterface
from supsrc.state import RepositoryState, RepositoryStatus
from supsrc.telemetry import StructLogger

log: StructLogger = structlog.get_logger("runtime.action_handler")


class ActionHandler:
    """Executes the full status -> stage -> commit -> push sequence."""

    def __init__(
        self,
        config: SupsrcConfig,
        repo_states: dict[str, RepositoryState],
        repo_engines: dict[str, RepositoryEngine],
        tui: TUIInterface,
    ):
        self.config = config
        self.repo_states = repo_states
        self.repo_engines = repo_engines
        self.tui = tui
        log.debug("ActionHandler initialized.")
    
    async def update_repository_stats(self, repo_id: str) -> bool:
        """
        Update file statistics for a repository by checking git status.
        
        Returns True if the repository is clean (no changes), False otherwise.
        """
        repo_state = self.repo_states.get(repo_id)
        repo_config = self.config.repositories.get(repo_id)
        repo_engine = self.repo_engines.get(repo_id)
        
        if not repo_state or not repo_config or not repo_engine:
            return False
        
        try:
            status_result: RepoStatusResult = await repo_engine.get_status(
                repo_state, repo_config.repository, self.config.global_config, repo_config.path
            )
            
            if status_result.success:
                # Update file statistics in repository state
                repo_state.total_files = status_result.total_files
                repo_state.changed_files = status_result.changed_files
                repo_state.added_files = status_result.added_files
                repo_state.deleted_files = status_result.deleted_files
                repo_state.modified_files = status_result.modified_files
                repo_state.has_uncommitted_changes = not status_result.is_clean
                repo_state.current_branch = status_result.current_branch
                
                # Update status if clean
                if status_result.is_clean:
                    repo_state.update_status(RepositoryStatus.IDLE)
                    
                return status_result.is_clean
        except Exception as e:
            log.warning("Failed to update repository stats", repo_id=repo_id, error=str(e))
            
        return False

    async def execute_action_sequence(self, repo_id: str) -> None:
        """
        Runs the full Git action workflow for a repository, handling all
        operational errors gracefully by updating state instead of raising.
        """
        repo_state = self.repo_states.get(repo_id)
        repo_config = self.config.repositories.get(repo_id)
        repo_engine = self.repo_engines.get(repo_id)

        action_log = log.bind(repo_id=repo_id)

        if not all((repo_state, repo_config, repo_engine)):
            action_log.error("Action failed: Missing state, config, or engine.")
            self.tui.post_log_update(repo_id, "ERROR", "Action failed: Missing state/config/engine.")
            return

        action_log.info("Executing action sequence...")
        self.tui.post_log_update(repo_id, "INFO", "Action triggered. Starting workflow...")

        try:
            # 1. Get Status
            repo_state.update_status(RepositoryStatus.PROCESSING)
            repo_state.action_description = "Checking status..."
            self.tui.post_state_update(self.repo_states)

            status_result: RepoStatusResult = await repo_engine.get_status(
                repo_state, repo_config.repository, self.config.global_config, repo_config.path
            )

            if not status_result.success:
                msg = f"Failed to get repo status: {status_result.message}"
                repo_state.update_status(RepositoryStatus.ERROR, msg)
                self.tui.post_log_update(repo_id, "ERROR", msg)
                self.tui.post_state_update(self.repo_states)
                return
            
            # Update file statistics in repository state
            repo_state.total_files = status_result.total_files
            repo_state.changed_files = status_result.changed_files
            repo_state.added_files = status_result.added_files
            repo_state.deleted_files = status_result.deleted_files
            repo_state.modified_files = status_result.modified_files
            repo_state.has_uncommitted_changes = not status_result.is_clean
            repo_state.current_branch = status_result.current_branch

            if status_result.is_conflicted:
                msg = "Repository has conflicts, action aborted."
                repo_state.is_frozen = True
                repo_state.freeze_reason = "Merge conflicts detected"
                repo_state.update_status(RepositoryStatus.ERROR, msg)
                self.tui.post_log_update(repo_id, "ERROR", msg)
                self.tui.post_state_update(self.repo_states)
                return

            if status_result.is_clean:
                action_log.info("Action skipped: Repository is already clean.")
                self.tui.post_log_update(repo_id, "INFO", "Action skipped: Repository clean.")
                repo_state.reset_after_action()
                self.tui.post_state_update(self.repo_states)
                return

            # 2. Stage Changes
            repo_state.update_status(RepositoryStatus.STAGING)
            repo_state.action_description = "Staging changes..."
            self.tui.post_state_update(self.repo_states)

            stage_result: StageResult = await repo_engine.stage_changes(
                None, repo_state, repo_config.repository, self.config.global_config, repo_config.path
            )
            if not stage_result.success:
                msg = f"Failed to stage changes: {stage_result.message}"
                repo_state.update_status(RepositoryStatus.ERROR, msg)
                self.tui.post_log_update(repo_id, "ERROR", msg)
                self.tui.post_state_update(self.repo_states)
                return

            staged_count = len(stage_result.files_staged or [])
            self.tui.post_log_update(repo_id, "DEBUG", f"Staged {staged_count} file(s).")
            repo_state.action_description = f"Staged {staged_count} file(s)"
            self.tui.post_state_update(self.repo_states)

            # 3. Perform Commit
            repo_state.update_status(RepositoryStatus.COMMITTING)
            repo_state.action_description = "Committing..."
            self.tui.post_state_update(self.repo_states)

            commit_result: CommitResult = await repo_engine.perform_commit(
                "", repo_state, repo_config.repository, self.config.global_config, repo_config.path
            )
            if not commit_result.success:
                msg = f"Commit failed: {commit_result.message}"
                repo_state.update_status(RepositoryStatus.ERROR, msg)
                self.tui.post_log_update(repo_id, "ERROR", msg)
                self.tui.post_state_update(self.repo_states)
                return

            if commit_result.commit_hash is None:
                action_log.info("Commit skipped by engine (no changes).")
                self.tui.post_log_update(repo_id, "INFO", "Commit skipped (no changes).")
                repo_state.reset_after_action()
            else:
                short_hash = commit_result.commit_hash[:7]
                repo_state.last_commit_short_hash = short_hash
                # Update last commit timestamp to now since we just made the commit
                from datetime import datetime, UTC
                repo_state.last_commit_timestamp = datetime.now(UTC)
                # Note: We don't have the commit message here, but we could fetch it if needed
                repo_state.action_description = f"Committed: {short_hash}"
                self.tui.post_log_update(repo_id, "INFO", f"Commit successful: {short_hash}")

                # 4. Perform Push (only after successful commit)
                repo_state.update_status(RepositoryStatus.PUSHING)
                repo_state.action_description = "Pushing..."
                self.tui.post_state_update(self.repo_states)
                push_result: PushResult = await repo_engine.perform_push(
                    repo_state, repo_config.repository, self.config.global_config, repo_config.path
                )
                if not push_result.success:
                    action_log.warning("Push operation failed", reason=push_result.message)
                    self.tui.post_log_update(repo_id, "WARNING", f"Push failed: {push_result.message}")
                elif push_result.skipped:
                    self.tui.post_log_update(repo_id, "INFO", "Push skipped by configuration.")
                else:
                    self.tui.post_log_update(repo_id, "INFO", "Push successful.")
                repo_state.reset_after_action()

            self.tui.post_state_update(self.repo_states)

        except Exception as e:
            action_log.critical("Unexpected error in action sequence", error=str(e), exc_info=True)
            if repo_state:
                error_msg = f"Unexpected action failure: {e}"
                repo_state.update_status(RepositoryStatus.ERROR, error_msg)
                self.tui.post_log_update(repo_id, "CRITICAL", error_msg)
                self.tui.post_state_update(self.repo_states)
