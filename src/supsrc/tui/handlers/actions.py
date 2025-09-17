# src/supsrc/tui/handlers/actions.py

"""
Action handler methods for the TUI application.
"""

from __future__ import annotations

import structlog
from textual.widgets import DataTable
from textual.widgets import Log as TextualLog

from supsrc.tui.messages import LogMessageUpdate

log = structlog.get_logger("tui.actions")


class ActionHandlerMixin:
    """Mixin containing action handler methods for the TUI."""

    def action_toggle_dark(self) -> None:
        """Toggle between light and dark mode."""
        self.dark = not self.dark
        log.debug("Dark mode toggled", dark_mode=self.dark)

    def action_clear_log(self) -> None:
        """Clear the event log."""
        self.query_one("#event-log", TextualLog).clear()
        self.post_message(LogMessageUpdate(None, "INFO", "Log cleared."))

    def action_pause_monitoring(self) -> None:
        """Pause/resume monitoring for all repositories."""
        if self._orchestrator:
            if self._orchestrator._is_paused:
                self._orchestrator.resume_monitoring()
                self.post_message(
                    LogMessageUpdate(None, "INFO", "▶️  Monitoring RESUMED")
                )
            else:
                self._orchestrator.pause_monitoring()
                self.post_message(
                    LogMessageUpdate(None, "WARNING", "⏸️  Monitoring PAUSED - Press 'p' to resume")
                )

    def action_suspend_monitoring(self) -> None:
        """Suspend/resume monitoring (stronger than pause)."""
        if self._orchestrator:
            if self._orchestrator._is_paused:  # Using same flag for now
                self._orchestrator.resume_monitoring()
                self.post_message(
                    LogMessageUpdate(None, "INFO", "▶️  Monitoring RESUMED from suspension")
                )
            else:
                self._orchestrator.suspend_monitoring()
                self.post_message(
                    LogMessageUpdate(None, "WARNING", "⏹️  Monitoring SUSPENDED - Press 's' to resume")
                )

    async def action_reload_config(self) -> None:
        """Reload configuration from file."""
        self.post_message(LogMessageUpdate(None, "INFO", "🔄 Reloading configuration..."))

        async def _reload():
            if self._orchestrator:
                try:
                    success = await self._orchestrator.reload_config()
                    if success:
                        self.post_message(
                            LogMessageUpdate(None, "SUCCESS", "✅ Configuration reloaded successfully")
                        )
                    else:
                        self.post_message(
                            LogMessageUpdate(None, "ERROR", "❌ Configuration reload failed")
                        )
                except Exception as e:
                    self.post_message(LogMessageUpdate(None, "ERROR", f"❌ Error reloading: {e}"))

        self.run_worker(_reload)

    def action_show_help(self) -> None:
        """Show help information."""
        help_text = (
            "🔑 Keyboard Shortcuts:\\n"
            "• [bold]d[/] - Toggle dark mode\\n"
            "• [bold]q[/] - Quit application\\n"
            "• [bold]^l[/] - Clear event log\\n"
            "• [bold]p[/] - Pause/resume monitoring\\n"
            "• [bold]s[/] - Suspend/resume monitoring\\n"
            "• [bold]r[/] - Reload configuration\\n"
            "• [bold]h[/] - Show this help\\n"
            "• [bold]Enter[/] - View repository details\\n"
            "• [bold]Escape[/] - Hide detail pane\\n"
            "• [bold]F5[/] - Refresh selected repo\\n"
            "\\n"
            "🖱️  Repository Table Actions:\\n"
            "• [bold]Space[/] - Toggle repository pause\\n"
            "• [bold]Shift+Space[/] - Toggle repository stop\\n"
            "• [bold]F5[/] - Refresh repository status\\n"
            "• [bold]Shift+F5[/] - Resume repository monitoring\\n"
            "\\n"
            "ℹ️  Repository table shows real-time status, file counts, and timer information."
        )
        self.post_message(LogMessageUpdate(None, "INFO", help_text))

    def action_select_repo_for_detail(self) -> None:
        """Select a repository for detailed view."""
        table = self.query_one(DataTable)
        if table.cursor_coordinate.row < len(table.rows):
            selected_row = table.get_row_at(table.cursor_coordinate.row)
            repo_id = str(selected_row[2])  # Repository name is in column 2

            if repo_id:
                log.debug("Repository selected for detail view", repo_id=repo_id)
                self.post_message(
                    LogMessageUpdate(
                        None,
                        "INFO",
                        f"📖 Loading details for '{repo_id}'. Use 'Escape' to hide details.",
                    )
                )
                self.show_detail_pane = True
                self._run_repo_details_fetch(repo_id)

    def action_hide_detail_pane(self) -> None:
        """Hide the repository detail pane."""
        if self.show_detail_pane:
            self.show_detail_pane = False
            log.debug("Detail pane hidden")
            # Clear the detail log when hiding
            self.query_one("#repo_detail_log", TextualLog).clear()
            self.query_one(DataTable).focus()

    def action_refresh_details(self) -> None:
        """Refresh the currently displayed repository details."""
        if self.show_detail_pane:
            repo_id = self._get_selected_repo_id()
            if repo_id:
                self._run_repo_details_fetch(repo_id)

    def action_quit(self) -> None:
        """Quit the application."""
        log.info("Quit action triggered")
        if self._cli_shutdown_event:
            self._cli_shutdown_event.set()

        # Stop all timers before exiting
        if self.timer_manager:
            self.timer_manager.stop_all_timers()
            log.debug("All timers stopped during quit")

        self.exit()