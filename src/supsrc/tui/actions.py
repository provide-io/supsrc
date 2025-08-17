"""TUI action handlers - extracted to reduce app.py size."""

import asyncio
from typing import TYPE_CHECKING

import structlog
from textual.worker import Worker

from supsrc.state import RepositoryStatus
if TYPE_CHECKING:
    from supsrc.tui.app import SupsrcTuiApp
    from textual.widgets import TextualLog

from supsrc.tui.messages import LogMessageUpdate, RepoDetailRequest, StateUpdate

log = structlog.get_logger("tui.actions")


class TUIActions:
    """Mixin class containing all TUI action methods."""
    
    def __init__(self: "SupsrcTuiApp"):
        """Initialize actions (this is a mixin, so self is SupsrcTuiApp)."""
        super().__init__()
    
    # Repository Actions
    
    async def action_toggle_repo_pause(self: "SupsrcTuiApp") -> None:
        """Toggle pause state for the selected repository."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(LogMessageUpdate(None, "WARNING", "No repository selected or orchestrator not ready."))
            return

        success = self._orchestrator.toggle_repository_pause(repo_id)
        if success:
            # Force an immediate state update to ensure UI reflects the change
            if self._orchestrator:
                self.post_message(StateUpdate(self._orchestrator.repo_states))
            
            repo_state = self._orchestrator.repo_states.get(repo_id)
            if repo_state and repo_state.is_paused:
                self.post_message(LogMessageUpdate(None, "INFO", f"⏸️ Repository '{repo_id}' paused."))
            else:
                self.post_message(LogMessageUpdate(None, "INFO", f"▶️ Repository '{repo_id}' resumed."))
        else:
            self.post_message(LogMessageUpdate(None, "ERROR", f"Failed to toggle pause for '{repo_id}'."))

    async def action_toggle_repo_stop(self: "SupsrcTuiApp") -> None:
        """Toggle stop state for the selected repository."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(LogMessageUpdate(None, "WARNING", "No repository selected or orchestrator not ready."))
            return

        success = await self._orchestrator.toggle_repository_stop(repo_id)
        if success:
            repo_state = self._orchestrator.repo_states.get(repo_id)
            if repo_state and repo_state.is_stopped:
                self.post_message(LogMessageUpdate(None, "INFO", f"⏹️ Repository '{repo_id}' stopped."))
            else:
                self.post_message(LogMessageUpdate(None, "INFO", f"▶️ Repository '{repo_id}' resumed."))
        else:
            self.post_message(LogMessageUpdate(None, "ERROR", f"Failed to toggle stop for '{repo_id}'."))

    async def action_refresh_repo_status(self: "SupsrcTuiApp") -> None:
        """Force refresh status for the selected repository."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(LogMessageUpdate(None, "WARNING", "No repository selected or orchestrator not ready."))
            return

        self._orchestrator.set_repo_refreshing_status(repo_id, True)
        self.post_message(LogMessageUpdate(None, "INFO", f"🔄 Refreshing status for '{repo_id}'..."))
        success = await self._orchestrator.refresh_repository_status(repo_id)
        self._orchestrator.set_repo_refreshing_status(repo_id, False)
        if success:
            self.post_message(LogMessageUpdate(None, "INFO", f"✅ Status for '{repo_id}' refreshed."))
        else:
            self.post_message(LogMessageUpdate(None, "ERROR", f"❌ Failed to refresh status for '{repo_id}'."))

    async def action_resume_repo_monitoring(self: "SupsrcTuiApp") -> None:
        """Resume monitoring for the selected repository (unpause/unstop)."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(LogMessageUpdate(None, "WARNING", "No repository selected or orchestrator not ready."))
            return

        success = await self._orchestrator.resume_repository_monitoring(repo_id)
        if success:
            self.post_message(LogMessageUpdate(None, "INFO", f"▶️ Repository '{repo_id}' resumed monitoring."))
        else:
            self.post_message(LogMessageUpdate(None, "ERROR", f"Failed to resume monitoring for '{repo_id}'."))
    
    async def action_trigger_repo_action(self: "SupsrcTuiApp") -> None:
        """Manually trigger a commit action for the selected repository."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(LogMessageUpdate(None, "WARNING", "No repository selected."))
            return
        
        self.post_message(LogMessageUpdate(None, "INFO", f"⚡ Triggering commit for '{repo_id}'..."))
        success = await self._orchestrator.trigger_repository_action(repo_id)
        if success:
            self.post_message(LogMessageUpdate(None, "INFO", f"✅ Action triggered for '{repo_id}'."))
        else:
            self.post_message(LogMessageUpdate(None, "ERROR", f"❌ Failed to trigger action for '{repo_id}'."))
    
    async def action_clear_repo_error(self: "SupsrcTuiApp") -> None:
        """Clear error state for the selected repository."""
        repo_id = self._get_selected_repo_id()
        if not repo_id or not self._orchestrator:
            self.post_message(LogMessageUpdate(None, "WARNING", "No repository selected."))
            return
        
        repo_state = self._orchestrator.repo_states.get(repo_id)
        if not repo_state:
            return
        
        # Clear error and frozen states
        if repo_state.status == RepositoryStatus.ERROR:
            repo_state.error_message = None
            repo_state.update_status(RepositoryStatus.IDLE)
        
        if repo_state.is_frozen:
            repo_state.is_frozen = False
            repo_state.freeze_reason = None
        
        self._orchestrator._post_tui_state_update()
        self.post_message(LogMessageUpdate(None, "INFO", f"🔧 Cleared error state for '{repo_id}'."))

    # View Actions
    
    def action_select_repo_for_detail(self: "SupsrcTuiApp") -> None:
        """Show details for the selected repository."""
        repo_id = self._get_selected_repo_id()
        if repo_id:
            log.debug(f"Showing details for {repo_id}")
            self.selected_repo_id = repo_id
            self.show_detail_pane = True
            worker = self.run_worker(
                self._fetch_repo_details_worker(repo_id),
                thread=True,
                group="details",
            )
            self.post_message(LogMessageUpdate(None, "INFO", f"Loading details for {repo_id}..."))

    def action_hide_detail_pane(self: "SupsrcTuiApp") -> None:
        """Hide the detail pane."""
        try:
            self.show_detail_pane = False
            self.selected_repo_id = None
            log.debug("Detail pane hidden")
            self.post_message(LogMessageUpdate(None, "INFO", "Detail pane hidden."))
        except Exception as e:
            log.error("Error hiding detail pane", error=str(e))

    def action_refresh_details(self: "SupsrcTuiApp") -> None:
        """Refresh the current detail view."""
        if self.show_detail_pane and self.selected_repo_id:
            self.post_message(RepoDetailRequest(self.selected_repo_id))
            self.post_message(LogMessageUpdate(None, "INFO", f"Refreshing details for {self.selected_repo_id}..."))

    # Global Actions
    
    def action_clear_log(self: "SupsrcTuiApp") -> None:
        """Clear the event log."""
        try:
            log_widget = self.query_one("#event-log", TextualLog)
            log_widget.clear()
            self.post_message(LogMessageUpdate(None, "INFO", "Log cleared."))
        except Exception as e:
            log.error("Failed to clear TUI log", error=str(e))

    def action_pause_monitoring(self: "SupsrcTuiApp") -> None:
        """Toggle pause state for monitoring."""
        self._is_paused = not self._is_paused
        if self._is_paused:
            self._update_sub_title("⏸️ Paused")
            if self._orchestrator:
                self._orchestrator.pause_monitoring()
            self.post_message(LogMessageUpdate(None, "INFO", "⏸️ Monitoring paused for all repositories."))
        else:
            self._update_sub_title("▶️ Running")
            if self._orchestrator:
                self._orchestrator.resume_monitoring()
            self.post_message(LogMessageUpdate(None, "INFO", "▶️ Monitoring resumed for all repositories."))

    async def action_reload_config(self: "SupsrcTuiApp") -> None:
        """Reload the configuration file."""
        if not self._orchestrator:
            self.post_message(LogMessageUpdate(None, "ERROR", "Orchestrator not initialized."))
            return
        
        self.post_message(LogMessageUpdate(None, "INFO", "Reloading configuration..."))
        success = await self._orchestrator.reload_config()
        if success:
            self.post_message(LogMessageUpdate(None, "INFO", "✅ Configuration reloaded successfully."))
        else:
            self.post_message(LogMessageUpdate(None, "ERROR", "❌ Failed to reload configuration."))

    def action_show_help(self: "SupsrcTuiApp") -> None:
        """Show help information."""
        help_text = """
[bold cyan]Supsrc TUI Help[/]

[yellow]Navigation:[/]
• Tab/Shift+Tab - Navigate between panels
• ↑↓ - Select repository
• Enter - View repository details
• Escape - Hide detail pane

[yellow]Repository Actions:[/]
• P - Pause/Resume repository
• S - Stop/Start monitoring
• Shift+R - Refresh repository status
• G - Resume monitoring (clear pause/stop)
• T - Trigger commit action now
• E - Clear error state

[yellow]Global Actions:[/]
• Space - Pause/Resume all monitoring
• C - Reload configuration
• Ctrl+L - Clear log
• D - Toggle dark mode
• Q/Ctrl+C - Quit

[yellow]Status Indicators:[/]
• ▶️ - Running normally
• ⏸️ - Paused
• ⏹️ - Stopped
• 🔄 - Processing
• ❌ - Error
• 📝 - Has changes
• 🎯 - Triggered
        """
        self.post_message(LogMessageUpdate(None, "INFO", help_text))

# Imports are at the top of the file