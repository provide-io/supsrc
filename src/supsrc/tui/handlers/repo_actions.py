# src/supsrc/tui/handlers/repo_actions.py

"""
Repository action handler methods for the TUI application.
"""

from __future__ import annotations

import structlog
from textual.widgets import DataTable
from textual.widgets import Log as TextualLog

from supsrc.tui.messages import LogMessageUpdate

log = structlog.get_logger("tui.repo_actions")


class RepoActionHandlerMixin:
    """Mixin containing repository-specific action handler methods for the TUI."""

    def action_select_repo_for_detail(self) -> None:
        """Show detail pane for the selected repository."""
        try:
            table = self.query_one(DataTable)
            # Get the row key using coordinate_to_cell_key
            try:
                cell_key = table.coordinate_to_cell_key((table.cursor_row, 0))
                row_key = cell_key.row_key
                self.selected_repo_id = str(row_key.value) if row_key else None
            except Exception:
                self.selected_repo_id = None

            if self.selected_repo_id:
                self.show_detail_pane = True

                if self._orchestrator and self.selected_repo_id:
                    detail_log = self.query_one("#repo_detail_log", TextualLog)
                    detail_log.clear()
                    detail_log.write_line(f"Fetching details for [b]{self.selected_repo_id}[/b]...")

                    self.run_worker(
                        self._fetch_repo_details_worker(self.selected_repo_id),
                        thread=True,
                        group="repo_detail_fetcher",
                        name=f"fetch_details_{self.selected_repo_id}",
                    )
        except Exception as e:
            log.error("Error selecting repo for detail", error=str(e))

    def action_hide_detail_pane(self) -> None:
        """Hide the detail pane."""
        if self.show_detail_pane:
            self.show_detail_pane = False
            self.selected_repo_id = None
            try:
                self.query_one("#repo_detail_log", TextualLog).clear()
                self.query_one(DataTable).focus()
            except Exception as e:
                log.error("Error hiding detail pane", error=str(e))

    def action_refresh_details(self) -> None:
        """Refresh the current detail view."""
        if self.show_detail_pane and self.selected_repo_id:
            self.action_select_repo_for_detail()

    def _get_selected_repo_id(self) -> str | None:
        """Helper to get the ID of the currently selected repository."""
        try:
            table = self.query_one(DataTable)
            cell_key = table.coordinate_to_cell_key((table.cursor_row, 0))
            row_key = cell_key.row_key
            return str(row_key.value) if row_key else None
        except Exception:
            return None

    async def action_toggle_repo_pause(self) -> None:
        """Toggle pause state for the selected repository."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(
                LogMessageUpdate(
                    None, "WARNING", "No repository selected or orchestrator not ready."
                )
            )
            return

        success = self._orchestrator.toggle_repository_pause(repo_id)
        if success:
            # Force an immediate state update to ensure UI reflects the change
            self._orchestrator._post_tui_state_update()

            repo_state = self._orchestrator.repo_states.get(repo_id)
            if repo_state and repo_state.is_paused:
                self.post_message(
                    LogMessageUpdate(None, "INFO", f"⏸️ Repository '{repo_id}' paused.")
                )
            else:
                self.post_message(
                    LogMessageUpdate(None, "INFO", f"▶️ Repository '{repo_id}' resumed.")
                )
        else:
            self.post_message(
                LogMessageUpdate(None, "ERROR", f"Failed to toggle pause for '{repo_id}'.")
            )

    async def action_toggle_repo_stop(self) -> None:
        """Toggle stop state for the selected repository."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(
                LogMessageUpdate(
                    None, "WARNING", "No repository selected or orchestrator not ready."
                )
            )
            return

        success = await self._orchestrator.toggle_repository_stop(repo_id)
        if success:
            repo_state = self._orchestrator.repo_states.get(repo_id)
            if repo_state and repo_state.is_stopped:
                self.post_message(
                    LogMessageUpdate(
                        None, "INFO", f"⏹️ Repository '{repo_id}' stopped from monitoring."
                    )
                )
            else:
                self.post_message(
                    LogMessageUpdate(None, "INFO", f"▶️ Repository '{repo_id}' resumed monitoring.")
                )
        else:
            self.post_message(
                LogMessageUpdate(None, "ERROR", f"Failed to toggle stop for '{repo_id}'.")
            )

    async def action_refresh_repo_status(self) -> None:
        """Force refresh status for the selected repository."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(
                LogMessageUpdate(
                    None, "WARNING", "No repository selected or orchestrator not ready."
                )
            )
            return

        self._orchestrator.set_repo_refreshing_status(repo_id, True)
        self.post_message(
            LogMessageUpdate(None, "INFO", f"🔄 Refreshing status for '{repo_id}'...")
        )
        success = await self._orchestrator.refresh_repository_status(repo_id)
        self._orchestrator.set_repo_refreshing_status(repo_id, False)
        if success:
            self.post_message(
                LogMessageUpdate(None, "INFO", f"✅ Status for '{repo_id}' refreshed.")
            )
        else:
            self.post_message(
                LogMessageUpdate(None, "ERROR", f"❌ Failed to refresh status for '{repo_id}'.")
            )

    async def action_resume_repo_monitoring(self) -> None:
        """Resume monitoring for the selected repository (unpause/unstop)."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(
                LogMessageUpdate(
                    None, "WARNING", "No repository selected or orchestrator not ready."
                )
            )
            return

        # First try to unpause
        paused_success = self._orchestrator.toggle_repository_pause(repo_id)
        # Then try to unstop
        stopped_success = await self._orchestrator.toggle_repository_stop(repo_id)

        if paused_success or stopped_success:
            self.post_message(
                LogMessageUpdate(None, "INFO", f"▶️ Repository '{repo_id}' monitoring resumed.")
            )
        else:
            self.post_message(
                LogMessageUpdate(None, "ERROR", f"Failed to resume monitoring for '{repo_id}'.")
            )