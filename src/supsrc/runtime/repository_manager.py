#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Repository management functionality for the WatchOrchestrator.
Handles repository initialization, state management, and lifecycle operations."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from provide.foundation.logger import get_logger

from supsrc.config import SupsrcConfig
from supsrc.engines.git import GitEngine, GitRepoSummary
from supsrc.state import RepositoryState, RepositoryStatus
from supsrc.utils.directories import SupsrcDirectories

if TYPE_CHECKING:
    from supsrc.protocols import RepositoryEngine
    from supsrc.runtime.tui_interface import TUIInterface

log = get_logger("runtime.repository_manager")

RULE_EMOJI_MAP: dict[str, str] = {
    "supsrc.rules.inactivity": "⏳",
    "supsrc.rules.save_count": "💾",
    "supsrc.rules.manual": "✋",
    "default": "⚙️",
}


class RepositoryManager:
    """Manages repository initialization, state, and lifecycle operations."""

    def __init__(
        self,
        repo_states: dict[str, RepositoryState],
        repo_engines: dict[str, RepositoryEngine],
        tui_update_callback: Callable[[], None] | None = None,
        event_collector: Any | None = None,
    ) -> None:
        self.repo_states = repo_states
        self.repo_engines = repo_engines
        self.tui_update_callback = tui_update_callback
        self.event_collector = event_collector
        self._log = log.bind(manager_id=id(self))
        self._log.debug("RepositoryManager initialized")

    async def initialize_repositories(self, config: SupsrcConfig, tui: TUIInterface) -> list[str]:
        """Initialize all enabled repositories from config."""
        self._log.info("Initializing repositories...")
        tui.post_log_update(None, "INFO", "Initializing repositories...")
        enabled_repo_ids = []

        # Import events for repository discovery
        from supsrc.events.monitor import MonitoringStartEvent
        from supsrc.events.system import ErrorEvent

        for repo_id, repo_config in config.repositories.items():
            init_log = self._log.bind(repo_id=repo_id)
            if not repo_config.enabled or not repo_config._path_valid:
                init_log.info("Skipping disabled/invalid repo")
                continue

            # Ensure .supsrc directory structure exists
            try:
                SupsrcDirectories.ensure_structure(repo_config.path)
                init_log.debug("Directory structure ensured")
            except Exception as e:
                init_log.error("Failed to create directory structure", error=str(e))
                continue

            repo_state = RepositoryState(repo_id=repo_id)
            self.repo_states[repo_id] = repo_state

            try:
                engine_type = repo_config.repository.get("type", "supsrc.engines.git")
                init_log.debug("Attempting to load engine", engine_type=engine_type)
                if engine_type == "supsrc.engines.git":
                    self.repo_engines[repo_id] = GitEngine()
                else:
                    raise NotImplementedError(f"Engine '{engine_type}' not supported.")
                init_log.debug("Engine loaded successfully")

                rule_type_str = getattr(repo_config.rule, "type", "default")
                repo_state.rule_emoji = RULE_EMOJI_MAP.get(rule_type_str, RULE_EMOJI_MAP["default"])
                repo_state.rule_dynamic_indicator = rule_type_str.split(".")[-1].replace("_", " ").capitalize()
                init_log.debug(
                    "Rule configuration set",
                    repo_id=repo_id,
                    rule_type=rule_type_str,
                    rule_emoji=repo_state.rule_emoji,
                    rule_indicator=repo_state.rule_dynamic_indicator,
                )

                engine = self.repo_engines[repo_id]
                if hasattr(engine, "get_summary"):
                    init_log.debug("Getting initial repository summary")
                    summary = cast(GitRepoSummary, await engine.get_summary(repo_config.path))
                    if summary.head_commit_hash:
                        repo_state.last_commit_short_hash = summary.head_commit_hash[:7]
                        repo_state.last_commit_message_summary = summary.head_commit_message_summary
                        if hasattr(summary, "head_commit_timestamp") and summary.head_commit_timestamp:
                            repo_state.last_commit_timestamp = summary.head_commit_timestamp
                        msg = f"HEAD at {summary.head_ref_name} ({repo_state.last_commit_short_hash})"
                        init_log.info(msg)
                        tui.post_log_update(repo_id, "INFO", msg)
                    elif summary.is_empty or summary.head_ref_name == "UNBORN":
                        init_log.info("Repo is empty or unborn.")
                        tui.post_log_update(repo_id, "INFO", "Repo is empty or unborn.")
                    elif summary.head_ref_name == "ERROR":
                        init_log.warning(
                            "Failed to get repo summary.",
                            details=summary.head_commit_message_summary,
                        )
                        repo_state.update_status(
                            RepositoryStatus.ERROR,
                            f"Init failed: {summary.head_commit_message_summary}",
                        )
                    else:
                        init_log.warning("Could not determine initial HEAD commit.", summary_details=summary)

                # Load initial repository statistics
                init_log.debug("Loading initial repository statistics")
                try:
                    status_result = await engine.get_status(
                        repo_state, repo_config.repository, config.global_config, repo_config.path
                    )
                    if status_result.success:
                        repo_state.total_files = status_result.total_files or 0
                        repo_state.changed_files = status_result.changed_files or 0
                        repo_state.added_files = status_result.added_files or 0
                        repo_state.deleted_files = status_result.deleted_files or 0
                        repo_state.modified_files = status_result.modified_files or 0
                        repo_state.has_uncommitted_changes = not status_result.is_clean
                        repo_state.current_branch = status_result.current_branch
                        init_log.debug(
                            "Repository statistics loaded",
                            total_files=repo_state.total_files,
                            changed_files=repo_state.changed_files,
                        )

                        # Load cached commit stats for TUI display
                        try:
                            commit_stats = await engine.get_last_commit_stats(
                                repo_state,
                                repo_config.repository,
                                config.global_config,
                                repo_config.path,
                            )
                            if commit_stats.get("success", False):
                                init_log.debug(
                                    "Last commit stats loaded",
                                    commit_hash=commit_stats.get("commit_hash"),
                                    added=commit_stats.get("added", 0),
                                    deleted=commit_stats.get("deleted", 0),
                                    modified=commit_stats.get("modified", 0),
                                )
                        except Exception as e:
                            init_log.warning("Failed to load commit stats", error=str(e))

                    else:
                        init_log.warning("Failed to load initial statistics", error=status_result.message)
                except Exception as stats_error:
                    init_log.warning("Error loading initial statistics", error=str(stats_error))

                enabled_repo_ids.append(repo_id)

                # Emit monitoring start event
                if self.event_collector:
                    init_log.debug(
                        "Emitting monitoring start event via repository manager event collector",
                        repo_id=repo_id,
                    )
                    start_event = MonitoringStartEvent(
                        description=f"Started monitoring repository {repo_id}",
                        repo_id=repo_id,
                        path=repo_config.path,
                    )
                    self.event_collector.emit(start_event)  # type: ignore[arg-type]
                elif hasattr(tui.app, "event_collector"):
                    init_log.debug("Emitting monitoring start event via TUI app", repo_id=repo_id)
                    start_event = MonitoringStartEvent(
                        description=f"Started monitoring repository {repo_id}",
                        repo_id=repo_id,
                        path=repo_config.path,
                    )
                    tui.app.event_collector.emit(start_event)  # type: ignore[arg-type]
                else:
                    init_log.warning(
                        "No event collector available for monitoring start event", repo_id=repo_id
                    )
            except Exception as e:
                init_log.error("Failed to initialize repository", error=str(e), exc_info=True)
                repo_state.update_status(RepositoryStatus.ERROR, f"Initialization failed: {e}")

                # Emit error event for failed initialization
                if self.event_collector:
                    error_event = ErrorEvent(
                        description=f"Failed to initialize repository {repo_id}: {e}",
                        source="repository_manager",
                        error_type="InitializationError",
                        repo_id=repo_id,
                    )
                    self.event_collector.emit(error_event)  # type: ignore[arg-type]
                elif hasattr(tui.app, "event_collector"):
                    error_event = ErrorEvent(
                        description=f"Failed to initialize repository {repo_id}: {e}",
                        source="repository_manager",
                        error_type="InitializationError",
                        repo_id=repo_id,
                    )
                    tui.app.event_collector.emit(error_event)  # type: ignore[arg-type]
                continue

        # Log detailed state before posting to TUI
        for repo_id, state in self.repo_states.items():
            self._log.info(
                "Repository initialized",
                repo_id=repo_id,
                status=state.status.name,
                total_files=state.total_files,
                changed_files=state.changed_files,
                rule_emoji=state.rule_emoji,
                current_branch=state.current_branch,
            )

        tui.post_state_update(self.repo_states)
        self._log.info(f"Initialized {len(enabled_repo_ids)} repositories.")
        return enabled_repo_ids

    def toggle_repository_pause(self, repo_id: str) -> bool:
        """Toggle pause state for a specific repository."""
        repo_state = self.repo_states.get(repo_id)
        if not repo_state:
            self._log.warning("Attempted to toggle pause on non-existent repo state", repo_id=repo_id)
            return False

        repo_state.is_paused = not repo_state.is_paused

        # Cancel timers when pausing
        if repo_state.is_paused:
            repo_state.cancel_inactivity_timer()
            repo_state.cancel_debounce_timer()
            self._log.debug(
                "Cancelled timers for paused repository",
                repo_id=repo_id,
            )

        repo_state._update_display_emoji()
        self._log.info("Toggled repository pause state", repo_id=repo_id, paused=repo_state.is_paused)

        # Trigger TUI update to reflect the change
        if self.tui_update_callback:
            self.tui_update_callback()

        return True

    async def toggle_repository_stop(self, repo_id: str, config: SupsrcConfig, monitor_service: Any) -> bool:
        """Toggle stop state for a specific repository."""
        repo_config = config.repositories.get(repo_id) if config else None
        repo_state = self.repo_states.get(repo_id)

        if not repo_config:
            self._log.warning("Attempted to toggle stop on non-existent repo config", repo_id=repo_id)
            return False

        if not repo_state:
            self._log.warning("Attempted to toggle stop on non-existent repo state", repo_id=repo_id)
            return False

        repo_state.is_stopped = not repo_state.is_stopped

        if repo_state.is_stopped:
            self._log.info("Stopping monitoring for repository", repo_id=repo_id)
            if monitor_service:
                monitor_service.unschedule_repository(repo_id)
        else:
            self._log.info("Resuming monitoring for stopped repository", repo_id=repo_id)
            if monitor_service:
                try:
                    loop = asyncio.get_running_loop()
                    monitor_service.add_repository(repo_id, repo_config, loop)
                    if repo_state.status == RepositoryStatus.ERROR:
                        repo_state.reset_after_action()
                except Exception as e:
                    self._log.error(
                        "Failed to re-add repository to monitor",
                        repo_id=repo_id,
                        error=str(e),
                        exc_info=True,
                    )
                    repo_state.update_status(RepositoryStatus.ERROR, f"Failed to resume monitoring: {e}")
                    repo_state.is_stopped = True

                    # Emit error event for resume monitoring failure
                    if self.event_collector:
                        from supsrc.events.system import ErrorEvent

                        resume_error_event = ErrorEvent(
                            description=f"Failed to resume monitoring: {e!s}",
                            source="monitor",
                            error_type="ResumeMonitoringFailed",
                            repo_id=repo_id,
                        )
                        self.event_collector.emit(resume_error_event)

                    return False

        repo_state._update_display_emoji()
        if self.tui_update_callback:
            self.tui_update_callback()
        return True

    async def resume_repository_monitoring(self, repo_id: str) -> bool:
        """Resume monitoring for a specific repository."""
        repo_state = self.repo_states.get(repo_id)
        if not repo_state:
            return False

        if repo_state.is_paused:
            repo_state.is_paused = False
            repo_state.pause_until = None
            self._log.info(f"Repository {repo_id} unpaused.")

        if repo_state.is_stopped:
            # Note: This would need access to monitor_service and config
            # For now, just log the attempt
            self._log.info(f"Repository {repo_id} stop state needs to be handled by orchestrator.")
            return False

        if self.tui_update_callback:
            self.tui_update_callback()
        return True

    async def get_repository_details(self, repo_id: str, config: SupsrcConfig) -> dict[str, Any]:
        """Get detailed information about a repository."""
        self._log.debug("Fetching repository details for TUI", repo_id=repo_id)
        repo_engine = self.repo_engines.get(repo_id)
        repo_config = config.repositories.get(repo_id) if config else None

        if not repo_engine or not repo_config:
            return {"error": "Repository data not found."}

        if isinstance(repo_engine, GitEngine) and hasattr(repo_engine, "get_commit_history"):
            try:
                history = await repo_engine.get_commit_history(repo_config.path, limit=20)
                return {"commit_history": history}
            except Exception as e:
                self._log.error("Failed to get commit history from engine", repo_id=repo_id, error=str(e))
                return {"commit_history": [f"[bold red]Error fetching history: {e}[/]"]}

        return {"commit_history": ["Details not available for this engine type."]}

    async def cleanup_repository_timers(self) -> None:
        """Clean up all repository timers to prevent resource leaks."""
        self._log.info("Cleaning up repository timers", repo_count=len(self.repo_states))
        cleanup_count = 0

        for repo_id, repo_state in self.repo_states.items():
            try:
                # Cancel any inactivity timers
                if repo_state.inactivity_timer_handle and not repo_state.inactivity_timer_handle.cancelled():
                    repo_state.inactivity_timer_handle.cancel()
                    cleanup_count += 1

                # Cancel any debounce timers
                if repo_state.debounce_timer_handle and not repo_state.debounce_timer_handle.cancelled():
                    repo_state.debounce_timer_handle.cancel()
                    cleanup_count += 1

                # Reset timer-related state
                repo_state.inactivity_timer_handle = None
                repo_state.debounce_timer_handle = None
                repo_state._timer_total_seconds = None
                repo_state._timer_start_time = None
                repo_state.timer_seconds_left = None

            except Exception as e:
                self._log.warning("Error cleaning up timers for repository", repo_id=repo_id, error=str(e))

        self._log.info("Repository timer cleanup complete", timers_cancelled=cleanup_count)

    async def refresh_repository_status(self, repo_id: str, status_manager: Any) -> bool:
        """Refresh the status and statistics for a specific repository."""
        if status_manager:
            # Delegate to status manager
            return await status_manager.refresh_repository_status(repo_id)
        return False

    def set_repo_refreshing_status(self, repo_id: str, is_refreshing: bool, status_manager: Any) -> None:
        """Set the refreshing status for a repository."""
        if status_manager:
            status_manager.set_repo_refreshing_status(repo_id, is_refreshing)


# 🔼⚙️🔚
