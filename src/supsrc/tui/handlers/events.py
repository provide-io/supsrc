# src/supsrc/tui/handlers/events.py

"""
Event handler methods for the TUI application.
"""

from __future__ import annotations

import structlog
from textual.widgets import DataTable
from textual.widgets import Log as TextualLog
from textual.worker import Worker, WorkerState

from supsrc.state import RepositoryStatus
from supsrc.tui.messages import LogMessageUpdate, RepoDetailUpdate, StateUpdate
from supsrc.tui.utils import format_last_commit_time, get_countdown_display

log = structlog.get_logger("tui.events")


class EventHandlerMixin:
    """Mixin containing event handler methods for the TUI."""

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        try:
            if event.state == WorkerState.SUCCESS and event.worker.group == "orchestrator_runner":
                log.info("Orchestrator completed successfully")
                if self._cli_shutdown_event:
                    self._cli_shutdown_event.set()
            elif event.state == WorkerState.ERROR and event.worker.group == "orchestrator_runner":
                log.error("Orchestrator failed", error=str(event.worker.result))
                if self._cli_shutdown_event:
                    self._cli_shutdown_event.set()
        except Exception as e:
            log.error("Error handling worker state change", error=str(e))

    def on_state_update(self, message: StateUpdate) -> None:
        """Handle repository state updates."""
        log.debug(
            "TUI on_state_update received",
            num_states=len(message.repo_states),
            repo_ids=list(message.repo_states.keys()),
        )
        try:
            # The original debug log has been replaced by the more structured one above.
            # If the repr(message.repo_states) is still desired for deep debugging,
            # it could be added here or a separate log line. For now, it's removed
            # to avoid redundancy with the new structured log.
            # debug_message_content = repr(message.repo_states)
            # log.debug(f"DEBUG_TUI_APP: on_state_update received: {debug_message_content}")

            table = self.query_one(DataTable)
            current_keys = set(table.rows.keys())
            incoming_keys = set(message.repo_states.keys())

            # Remove obsolete rows
            for key_to_remove in current_keys - incoming_keys:
                try:  # noqa: SIM105
                    table.remove_row(key_to_remove)
                except Exception:
                    # Row may have already been removed
                    pass

            # Update/add rows
            for repo_id_obj, state in message.repo_states.items():
                repo_id_str = str(repo_id_obj)

                # Format display data
                status_display = state.display_status_emoji
                # Debug log to see the state
                log.debug(
                    f"Repository {repo_id_str} - emoji: '{status_display}', "
                    f"paused: {state.is_paused}, stopped: {state.is_stopped}, "
                    f"status: {state.status.name}"
                )
                timer_display = get_countdown_display(state.timer_seconds_left)
                repository_display = repo_id_str

                # Use relative time for recent changes, full date for older ones
                # Get threshold from config if available
                threshold = 3.0  # default
                if (
                    hasattr(self, "_orchestrator")
                    and self._orchestrator
                    and self._orchestrator.config
                ):
                    threshold = getattr(
                        self._orchestrator.config.global_config, "last_change_threshold_hours", 3.0
                    )
                # Use actual Git commit timestamp if available, fallback to last_change_time
                timestamp = state.last_commit_timestamp or state.last_change_time
                last_change_display = format_last_commit_time(timestamp, threshold)

                rule_emoji = state.rule_emoji or ""
                rule_indicator = state.rule_dynamic_indicator or "N/A"
                rule_display = f"{rule_emoji} {rule_indicator}".strip()

                # Format file statistics with color based on commit status
                # Show loading indicator for repos that haven't been initialized yet
                if (
                    state.total_files == 0
                    and not state.has_uncommitted_changes
                    and state.status == RepositoryStatus.IDLE
                ):
                    # Likely still loading
                    total_files_display = "[dim]...[/dim]"
                elif state.total_files == 0:
                    # Show a question mark for 0 files after loading is complete
                    total_files_display = "[bold red]?[/bold red]"
                else:
                    total_files_display = str(state.total_files)

                if state.has_uncommitted_changes:
                    # Active colors for uncommitted changes
                    changed_files_display = (
                        f"[bold yellow]{state.changed_files}[/bold yellow]"
                        if state.changed_files > 0
                        else "0"
                    )
                    added_display = (
                        f"[bold green]{state.added_files}[/bold green]"
                        if state.added_files > 0
                        else "0"
                    )
                    deleted_display = (
                        f"[bold red]{state.deleted_files}[/bold red]"
                        if state.deleted_files > 0
                        else "0"
                    )
                    modified_display = (
                        f"[bold blue]{state.modified_files}[/bold blue]"
                        if state.modified_files > 0
                        else "0"
                    )
                else:
                    # Grey/dim for committed state
                    changed_files_display = (
                        f"[dim]{state.changed_files}[/dim]" if state.changed_files > 0 else "0"
                    )
                    added_display = (
                        f"[dim]{state.added_files}[/dim]" if state.added_files > 0 else "0"
                    )
                    deleted_display = (
                        f"[dim]{state.deleted_files}[/dim]" if state.deleted_files > 0 else "0"
                    )
                    modified_display = (
                        f"[dim]{state.modified_files}[/dim]" if state.modified_files > 0 else "0"
                    )

                # Get branch display - truncate from beginning if too long
                branch_name = state.current_branch or "main"
                branch_display = "..." + branch_name[-17:] if len(branch_name) > 20 else branch_name

                row_data = (
                    status_display,
                    timer_display,
                    repository_display,
                    branch_display,  # New branch column
                    total_files_display,
                    changed_files_display,
                    added_display,
                    deleted_display,
                    modified_display,
                    last_change_display,  # Moved after modified
                    rule_display,
                )

                if repo_id_str in table.rows:
                    # Save cursor position before update
                    cursor_row = table.cursor_row
                    cursor_column = table.cursor_column

                    # Update existing row by removing and re-adding
                    table.remove_row(repo_id_str)
                    table.add_row(*row_data, key=repo_id_str)

                    # Restore cursor position if it's still valid
                    if cursor_row < table.row_count:
                        table.cursor_coordinate = (cursor_row, cursor_column)
                else:
                    table.add_row(*row_data, key=repo_id_str)

        except Exception as e:
            log.error("Failed to update TUI table", error=str(e))

    def on_log_message_update(self, message: LogMessageUpdate) -> None:
        """Handle log message updates."""
        try:
            log_widget = self.query_one("#event-log", TextualLog)
            # Format message with repo name if available
            formatted_message = (
                f"[{message.repo_id}] {message.message}" if message.repo_id else message.message
            )
            log_widget.write_line(formatted_message)
        except Exception as e:
            # Using the app's own logger here is fine for TUI-specific errors.
            log.error(
                "Failed to write to TUI log widget",
                error=str(e),
                raw_message_level=message.level,
                raw_message_content=message.message,
            )

    def on_repo_detail_update(self, message: RepoDetailUpdate) -> None:
        """Handle repository detail updates (simplified - log to main log)."""
        try:
            log_widget = self.query_one("#event-log", TextualLog)
            commit_history = message.details.get("commit_history", [])
            if commit_history:
                log_widget.write_line(f"[b]Recent commits for {message.repo_id}:[/b]")
                # Show only the first few commits to avoid flooding the log
                for entry in commit_history[:3]:
                    log_widget.write_line(f"  {entry}")
                if len(commit_history) > 3:
                    log_widget.write_line(f"  ... and {len(commit_history) - 3} more commits")
        except Exception as e:
            log.error("Error updating repo details", error=str(e))
