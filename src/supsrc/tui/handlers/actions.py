# src/supsrc/tui/handlers/actions.py

"""
Action handler methods for the TUI application.
"""

from __future__ import annotations

import structlog
from textual.widgets import DataTable, TabbedContent

from supsrc.events.system import UserActionEvent

log = structlog.get_logger("tui.actions")


class ActionHandlerMixin:
    """Mixin containing action handler methods for the TUI."""

    def action_toggle_dark(self) -> None:
        """Toggle between light and dark mode."""
        # Use Textual's theme switching API
        current_theme = getattr(self, "theme", "textual-dark")
        if current_theme == "textual-dark":
            self.theme = "textual-light"
            new_mode = "light"
        else:
            self.theme = "textual-dark"
            new_mode = "dark"
        log.debug("Theme toggled", theme=new_mode)

    def action_clear_log(self) -> None:
        """Clear the event feed."""
        from supsrc.events.feed import EventFeed

        self.query_one("#event-feed", EventFeed).clear()

        # Emit event instead of log message
        event = UserActionEvent(
            description="Event feed cleared",
            action="clear_feed",
        )
        self.event_collector.emit(event)  # type: ignore[arg-type]

    def action_pause_monitoring(self) -> None:
        """Pause/resume monitoring for all repositories."""
        if self._orchestrator:
            if self._orchestrator._is_paused:
                self._orchestrator.resume_monitoring()
                event = UserActionEvent(
                    description="Monitoring resumed for all repositories",
                    action="resume_monitoring",
                )
            else:
                self._orchestrator.pause_monitoring()
                event = UserActionEvent(
                    description="Monitoring paused for all repositories - Press 'p' to resume",
                    action="pause_monitoring",
                )

            self.event_collector.emit(event)  # type: ignore[arg-type]

    def action_suspend_monitoring(self) -> None:
        """Suspend/resume monitoring (stronger than pause)."""
        if self._orchestrator:
            if self._orchestrator._is_suspended:
                self._orchestrator.resume_monitoring()
                event = UserActionEvent(
                    description="Monitoring resumed from suspension",
                    action="resume_suspension",
                )
            else:
                self._orchestrator.suspend_monitoring()
                event = UserActionEvent(
                    description="Monitoring suspended - Press 's' to resume",
                    action="suspend_monitoring",
                )

            self.event_collector.emit(event)  # type: ignore[arg-type]

    async def action_reload_config(self) -> None:
        """Reload configuration from file."""
        from supsrc.events.system import ConfigReloadEvent, ErrorEvent

        # Emit start event
        start_event = UserActionEvent(
            description="Configuration reload initiated",
            action="reload_config_start",
        )
        self.event_collector.emit(start_event)  # type: ignore[arg-type]

        async def _reload():
            if self._orchestrator:
                try:
                    success = await self._orchestrator.reload_config()
                    if success:
                        event = ConfigReloadEvent(
                            description="Configuration reloaded successfully",
                            config_path=str(self._config_path),
                        )
                    else:
                        event = ErrorEvent(
                            description="Configuration reload failed",
                            source="config",
                            error_type="ReloadError",
                        )
                    self.event_collector.emit(event)  # type: ignore[arg-type]
                except Exception as e:
                    event = ErrorEvent(
                        description=f"Error during configuration reload: {e}",
                        source="config",
                        error_type="ReloadException",
                    )
                    self.event_collector.emit(event)  # type: ignore[arg-type]

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
            "i  Repository table shows real-time status, file counts, and timer information."
        )
        # Emit help event instead of log message
        event = UserActionEvent(
            description=help_text,
            action="show_help",
        )
        self.event_collector.emit(event)  # type: ignore[arg-type]

    def action_select_repo_for_detail(self) -> None:
        """Select a repository for detailed view."""
        # Check if we're in the Events tab - if so, don't handle Enter
        try:
            tabbed_content = self.query_one(TabbedContent)
            if tabbed_content.active == "events-tab":
                return  # Let EventFeed handle Enter key
        except Exception:
            pass  # If we can't find tabs, continue with normal behavior

        table = self.query_one("#repository_table", DataTable)
        if table.cursor_coordinate.row < len(table.rows):
            selected_row = table.get_row_at(table.cursor_coordinate.row)
            repo_id = str(selected_row[2])  # Repository name is in column 2

            if repo_id:
                log.debug("Repository selected for detail view", repo_id=repo_id)
                self.selected_repo_id = repo_id
                # Emit repository selection event
                event = UserActionEvent(
                    description=f"Repository '{repo_id}' selected for details",
                    action="select_repository",
                    target=repo_id,
                )
                self.event_collector.emit(event)  # type: ignore[arg-type]
                # Update the repo details tab content
                self._update_repo_details_tab(repo_id)

    def action_hide_detail_pane(self) -> None:
        """Hide the repository detail pane (legacy - now clears selection)."""
        # In the new tabbed interface, this just clears the selection
        self.selected_repo_id = None
        log.debug("Repository selection cleared")
        # Emit clear selection event
        event = UserActionEvent(
            description="Repository selection cleared",
            action="clear_selection",
        )
        self.event_collector.emit(event)  # type: ignore[arg-type]
        # Focus back to the repository table
        self.query_one(DataTable).focus()

    def action_refresh_details(self) -> None:
        """Refresh the currently displayed repository details."""
        if self.selected_repo_id:
            # Emit refresh event
            event = UserActionEvent(
                description=f"Refreshing details for repository '{self.selected_repo_id}'",
                action="refresh_details",
                target=self.selected_repo_id,
            )
            self.event_collector.emit(event)  # type: ignore[arg-type]
            self._update_repo_details_tab(self.selected_repo_id)
        else:
            # Emit warning event
            event = UserActionEvent(
                description="No repository selected to refresh",
                action="refresh_details_failed",
            )
            self.event_collector.emit(event)  # type: ignore[arg-type]

    def action_focus_next(self) -> None:
        """Focus the next panel in the interface."""
        # Simple two-pane navigation: repo table <-> info pane tabs
        try:
            # Check if repository table has focus
            repo_table = self.query_one("#repository_table", DataTable)
            if repo_table.has_focus:
                # Move focus to the tabbed content area - focus the actual tabs bar
                tabbed_content = self.query_one(TabbedContent)
                tabs = tabbed_content.query_one("Tabs")
                tabs.focus()
                log.debug("Focused tabs from repo table")
            else:
                # Move focus back to repository table
                repo_table.focus()
                log.debug("Focused repo table from tabs")
        except Exception as e:
            log.error("Error in focus_next", error=str(e))

    def action_focus_previous(self) -> None:
        """Focus the previous panel in the interface."""
        # Same as focus_next for a two-pane layout
        self.action_focus_next()

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
