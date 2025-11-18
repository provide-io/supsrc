#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Repository action handler methods for the TUI application."""

from __future__ import annotations

from provide.foundation.logger import get_logger
from textual.widgets import DataTable

from supsrc.tui.messages import LogMessageUpdate

log = get_logger(__name__)


class RepoActionHandlerMixin:
    """Mixin containing repository-specific action handler methods for the TUI."""

    def action_select_repo_for_detail(self) -> None:
        """Select a repository (simplified - no detail pane)."""
        try:
            table = self.query_one("#repository_table", DataTable)
            # Get the row key using coordinate_to_cell_key
            try:
                cell_key = table.coordinate_to_cell_key((table.cursor_row, 0))
                row_key = cell_key.row_key
                self.selected_repo_id = str(row_key.value) if row_key else None
            except Exception:
                self.selected_repo_id = None

            if self.selected_repo_id:
                self.post_message(
                    LogMessageUpdate(None, "INFO", f"📍 Selected repository: '{self.selected_repo_id}'")
                )
        except Exception as e:
            log.error("Error selecting repo", error=str(e))

    def action_hide_detail_pane(self) -> None:
        """Legacy action - no longer used in simplified layout."""
        pass

    def action_refresh_details(self) -> None:
        """Legacy action - no longer used in simplified layout."""
        pass

    def _get_selected_repo_id(self) -> str | None:
        """Helper to get the ID of the currently selected repository."""
        try:
            table = self.query_one("#repository_table", DataTable)
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
                LogMessageUpdate(None, "WARNING", "No repository selected or orchestrator not ready.")
            )
            return

        success = self._orchestrator.toggle_repository_pause(repo_id)
        if success:
            # The UI will update naturally through regular state update cycles
            # No need to force immediate update which causes cursor jumping

            repo_state = self._orchestrator.repo_states.get(repo_id)
            if repo_state and repo_state.is_paused:
                self.post_message(LogMessageUpdate(None, "INFO", f"⏸️ Repository '{repo_id}' paused."))
            else:
                self.post_message(LogMessageUpdate(None, "INFO", f"▶️ Repository '{repo_id}' resumed."))
        else:
            self.post_message(LogMessageUpdate(None, "ERROR", f"Failed to toggle pause for '{repo_id}'."))

    async def action_toggle_repo_stop(self) -> None:
        """Toggle stop state for the selected repository."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(
                LogMessageUpdate(None, "WARNING", "No repository selected or orchestrator not ready.")
            )
            return

        success = await self._orchestrator.toggle_repository_stop(repo_id)
        if success:
            repo_state = self._orchestrator.repo_states.get(repo_id)
            if repo_state and repo_state.is_stopped:
                self.post_message(
                    LogMessageUpdate(None, "INFO", f"⏹️ Repository '{repo_id}' stopped from monitoring.")
                )
            else:
                self.post_message(
                    LogMessageUpdate(None, "INFO", f"▶️ Repository '{repo_id}' resumed monitoring.")
                )
        else:
            self.post_message(LogMessageUpdate(None, "ERROR", f"Failed to toggle stop for '{repo_id}'."))

    async def action_refresh_repo_status(self) -> None:
        """Force refresh status for the selected repository."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(
                LogMessageUpdate(None, "WARNING", "No repository selected or orchestrator not ready.")
            )
            return

        self._orchestrator.set_repo_refreshing_status(repo_id, True)
        self.post_message(LogMessageUpdate(None, "INFO", f"🔄 Refreshing status for '{repo_id}'..."))
        success = await self._orchestrator.refresh_repository_status(repo_id)
        self._orchestrator.set_repo_refreshing_status(repo_id, False)
        if success:
            self.post_message()
        else:
            self.post_message(LogMessageUpdate(None, "ERROR", f"❌ Failed to refresh status for '{repo_id}'."))

    async def action_resume_repo_monitoring(self) -> None:
        """Resume monitoring for the selected repository (unpause/unstop)."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(
                LogMessageUpdate(None, "WARNING", "No repository selected or orchestrator not ready.")
            )
            return

        # First try to unpause
        paused_success = self._orchestrator.toggle_repository_pause(repo_id)
        # Then try to unstop
        stopped_success = await self._orchestrator.toggle_repository_stop(repo_id)

        if paused_success or stopped_success:
            self.post_message(LogMessageUpdate(None, "INFO", f"▶️ Repository '{repo_id}' monitoring resumed."))
        else:
            self.post_message(LogMessageUpdate(None, "ERROR", f"Failed to resume monitoring for '{repo_id}'."))

    async def action_acknowledge_circuit_breaker(self) -> None:
        """Acknowledge and reset circuit breaker for the selected repository."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(
                LogMessageUpdate(None, "WARNING", "No repository selected or orchestrator not ready.")
            )
            return

        # Get the repository state
        repo_state = self._orchestrator.repo_states.get(repo_id)
        if not repo_state:
            self.post_message(LogMessageUpdate(None, "ERROR", f"Repository '{repo_id}' not found."))
            return

        # Check if circuit breaker is triggered
        if not repo_state.circuit_breaker_triggered:
            self.post_message(
                LogMessageUpdate(None, "INFO", f"✅ Repository '{repo_id}' circuit breaker is not triggered.")
            )
            return

        # Get the reason before resetting
        reason = repo_state.circuit_breaker_reason or "Unknown reason"

        # Reset the circuit breaker
        success = self._orchestrator.acknowledge_circuit_breaker(repo_id)

        if success:
            self.post_message(
                LogMessageUpdate(
                    None,
                    "INFO",
                    f"✅ Circuit breaker acknowledged for '{repo_id}'. Reason was: {reason[:50]}...",
                )
            )
        else:
            self.post_message(
                LogMessageUpdate(None, "ERROR", f"❌ Failed to acknowledge circuit breaker for '{repo_id}'.")
            )


# 🔼⚙️🔚
