#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Event handler methods for the TUI application."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any, cast

from provide.foundation.logger import get_logger
from textual.coordinate import Coordinate
from textual.widgets import DataTable
from textual.widgets import Log as TextualLog
from textual.worker import Worker, WorkerState

from supsrc.state import RepositoryStatus
from supsrc.tui.messages import LogMessageUpdate, RepoDetailUpdate, StateUpdate
from supsrc.tui.utils import format_last_commit_time, get_countdown_display

log = get_logger(__name__)


class EventHandlerMixin:
    """Mixin containing event handler methods for the TUI."""

    if TYPE_CHECKING:
        _cli_shutdown_event: asyncio.Event | None
        _orchestrator: Any
        app: Any

        def query_one(self, selector: str, widget_type: type[Any] | None = ...) -> Any: ...

    def _format_change_display(self, current: int, previous: int, color: str, has_changes: bool) -> str:
        """Format change display: bright current values when changes exist, dim previous values otherwise."""
        if has_changes and current > 0:
            return f"[bold {color}]{current}[/bold {color}]"
        elif not has_changes and previous > 0:
            return f"[dim]{previous}[/dim]"
        else:
            return "[dim]0[/dim]"

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

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection in the repository table (triggered by click or Enter)."""
        try:
            # Only handle clicks on the repository table
            if event.data_table.id != "repository_table":
                return

            # Get the row key (which is the repo_id)
            repo_id = str(event.row_key.value)
            log.debug("Repository row selected via click", repo_id=repo_id)

            # Update selected repo and switch to details tab
            self.selected_repo_id = repo_id  # type: ignore[attr-defined]
            self._update_repo_details_tab(repo_id)  # type: ignore[attr-defined]

            # Focus the details tab content
            try:
                # The tab is already switched by _update_repo_details_tab
                # Now focus the content area
                details_content = self.query_one("#repo-details-content")  # type: ignore[attr-defined]
                details_content.focus()
            except Exception as focus_err:
                log.debug("Could not focus details content", error=str(focus_err))

        except Exception as e:
            log.error("Error handling row selection", error=str(e))

    def on_state_update(self, message: StateUpdate) -> None:
        """Handle repository state updates."""
        log.info(
            "TUI on_state_update received",
            num_states=len(message.repo_states),
            repo_ids=list(message.repo_states.keys()),
        )

        # Log individual repository states for debugging
        for repo_id, state in message.repo_states.items():
            log.info(
                "Repository state",
                repo_id=repo_id,
                status=state.status.name,
                save_count=state.save_count,
                changed_files=state.changed_files,
                total_files=state.total_files,
                has_uncommitted_changes=state.has_uncommitted_changes,
            )
        try:
            # The original debug log has been replaced by the more structured one above.
            # If the repr(message.repo_states) is still desired for deep debugging,
            # it could be added here or a separate log line. For now, it's removed
            # to avoid redundancy with the new structured log.
            # debug_message_content = repr(message.repo_states)
            # log.debug(f"DEBUG_TUI_APP: on_state_update received: {debug_message_content}")

            table = cast(DataTable, self.query_one("#repository_table", DataTable))
            table_any = cast(Any, table)

            # Save cursor position using row key (more stable than index)
            cursor_row_key = None
            try:
                if table.cursor_row < table.row_count:
                    cursor_coordinate = table.coordinate_to_cell_key(
                        Coordinate(row=table.cursor_row, column=0)
                    )
                    cursor_row_key = cursor_coordinate.row_key.value
                    log.debug("Saved cursor position", row_key=cursor_row_key)
            except Exception:
                pass

            current_keys = {row_key.value for row_key in table_any.rows}
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
                log.debug(
                    "TUI timer display",
                    repo_id=repo_id_str,
                    timer_seconds_left=state.timer_seconds_left,
                    timer_display=repr(timer_display),
                    has_timer_handle=state.inactivity_timer_handle is not None,
                )
                repository_display = repo_id_str

                # Use relative time for recent changes, full date for older ones
                # Get threshold from config if available
                threshold = 3.0  # default
                if hasattr(self, "_orchestrator") and self._orchestrator and self._orchestrator.config:
                    threshold = getattr(
                        self._orchestrator.config.global_config, "last_change_threshold_hours", 3.0
                    )
                # Use actual Git commit timestamp only (not file change time)
                last_change_display = format_last_commit_time(state.last_commit_timestamp, threshold)

                rule_emoji = state.rule_emoji or ""
                rule_indicator = state.rule_dynamic_indicator or "N/A"
                rule_display = f"{rule_emoji} {rule_indicator}".strip()
                log.debug(
                    "TUI rule display formatting",
                    repo_id=repo_id_str,
                    rule_emoji=repr(rule_emoji),
                    rule_indicator=repr(rule_indicator),
                    rule_display=repr(rule_display),
                )

                # Format total file count for display in the table
                if (
                    state.total_files == 0
                    and not state.has_uncommitted_changes
                    and state.status == RepositoryStatus.IDLE
                ):
                    total_files_display = "[dim]...[/dim]"
                elif state.total_files == 0:
                    total_files_display = "[bold red]?[/bold red]"
                else:
                    total_files_display = str(state.total_files)

                # Format file statistics: current (bright) when changes exist, previous (dim) otherwise
                changed_files_display = self._format_change_display(
                    state.changed_files,
                    state.last_committed_changed,
                    "yellow",
                    state.has_uncommitted_changes,
                )
                added_display = self._format_change_display(
                    state.added_files,
                    state.last_committed_added,
                    "green",
                    state.has_uncommitted_changes,
                )
                deleted_display = self._format_change_display(
                    state.deleted_files,
                    state.last_committed_deleted,
                    "red",
                    state.has_uncommitted_changes,
                )
                modified_display = self._format_change_display(
                    state.modified_files,
                    state.last_committed_modified,
                    "blue",
                    state.has_uncommitted_changes,
                )

                # Get branch display - let auto-sizing handle width, minimal truncation for very long names
                branch_name = state.current_branch or "main"
                branch_display = "..." + branch_name[-37:] if len(branch_name) > 40 else branch_name

                row_data = (
                    status_display,
                    timer_display,
                    repository_display,
                    branch_display,
                    total_files_display,
                    changed_files_display,
                    added_display,
                    deleted_display,
                    modified_display,
                    last_change_display,
                    rule_display,
                )

                if repo_id_str in current_keys:
                    # Update existing row in-place to prevent counter resets and cursor jumps
                    try:
                        # Try to update cells first, with improved error handling
                        cell_update_failed = False
                        ordered_columns = table.ordered_columns
                        for col_index, cell_value in enumerate(row_data):
                            if col_index < len(ordered_columns):
                                try:
                                    column_key = ordered_columns[col_index].key
                                    table.update_cell(repo_id_str, column_key, cell_value)
                                except Exception as cell_err:
                                    log.debug(
                                        "Cell update failed, will need to remove/re-add row",
                                        repo_id=repo_id_str,
                                        column_key=str(column_key),
                                        col_index=col_index,
                                        error=str(cell_err),
                                    )
                                    cell_update_failed = True
                                    break

                        # Only remove/re-add if cell updates failed
                        if cell_update_failed:
                            log.debug(
                                "Removing and re-adding row due to cell update failure",
                                repo_id=repo_id_str,
                            )
                            table.remove_row(repo_id_str)
                            table.add_row(*row_data, key=repo_id_str)

                    except Exception as e:
                        log.debug(
                            "Failed to update row in-place, re-adding",
                            repo_id=repo_id_str,
                            error=str(e),
                        )
                        # Fallback: remove and re-add
                        with contextlib.suppress(Exception):
                            table.remove_row(repo_id_str)
                        table.add_row(*row_data, key=repo_id_str)
                else:
                    table.add_row(*row_data, key=repo_id_str)

            # Restore cursor position using row key
            row_keys_after = {row_key.value for row_key in table.rows}
            if cursor_row_key is not None:
                try:
                    # Find the row index for the saved row key
                    if cursor_row_key in row_keys_after:
                        new_cursor_row = table.get_row_index(cursor_row_key)
                        if new_cursor_row != table.cursor_row:
                            table_any.cursor_row = new_cursor_row
                            log.debug(
                                "Restored cursor position",
                                new_row=new_cursor_row,
                                row_key=cursor_row_key,
                            )
                except Exception as e:
                    log.debug("Failed to restore cursor position", error=str(e))

            # Update repo details pane if currently viewing a repo
            if (
                hasattr(self, "selected_repo_id")
                and self.selected_repo_id
                and self.selected_repo_id in message.repo_states
            ):
                # Refresh the repo details with updated state
                self._update_repo_details_tab(self.selected_repo_id)  # type: ignore[attr-defined]

        except Exception as e:
            log.error("Failed to update TUI table", error=str(e))

    def on_log_message_update(self, message: LogMessageUpdate) -> None:
        """Handle log message updates."""
        try:
            # Try to find the log widget - it should be findable even inside a TabPane
            log_widget = cast(TextualLog, self.query_one("#event-log", TextualLog))
            # Format message with repo name if available
            formatted_message = (
                f"[{message.repo_id}] {message.message}" if message.repo_id else message.message
            )
            log_widget.write_line(formatted_message)
        except Exception as e:
            # Check if this is a "widget not found" error (expected during initialization)
            error_msg = str(e)
            if "No nodes match" in error_msg:
                # Widget not ready yet - expected during initialization
                log.debug(
                    "TUI log widget not yet available",
                    error=error_msg,
                    message_level=message.level,
                )
            else:
                # Unexpected error - log as error
                log.error(
                    "Failed to write to TUI log widget",
                    error=error_msg,
                    message_level=message.level,
                    message_content=message.message,
                )

    def on_repo_detail_update(self, message: RepoDetailUpdate) -> None:
        """Handle repository detail updates (simplified - log to main log)."""
        try:
            log_widget = cast(TextualLog, self.query_one("#event-log", TextualLog))
            commit_history = message.details.get("commit_history", [])
            if commit_history:
                log_widget.write_line(f"[b]Recent commits for {message.repo_id}:[/b]")
                # Show only the first few commits to avoid flooding the log
                for entry in commit_history[:3]:
                    log_widget.write_line(f"  {entry}")
                if len(commit_history) > 3:
                    log_widget.write_line(f"  ... and {len(commit_history) - 3} more commits")
        except Exception as e:
            # Check if this is a "widget not found" error (expected during initialization)
            error_msg = str(e)
            if "No nodes match" in error_msg:
                # Widget not ready yet - expected during initialization
                log.debug(
                    "TUI log widget not yet available for repo details",
                    repo_id=message.repo_id,
                    error=error_msg,
                )
            else:
                # Unexpected error - log as error
                log.error(
                    "Error updating repo details",
                    repo_id=message.repo_id,
                    error=error_msg,
                )


# 🔼⚙️🔚
