# type: ignore
#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Action handler methods for the TUI application."""

from __future__ import annotations

from provide.foundation.logger import get_logger
from textual.widgets import DataTable, TabbedContent

from supsrc.events.system import UserActionEvent

log = get_logger(__name__)


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
        """Clear the event feed and log panel."""
        import contextlib

        from supsrc.events.feed_table import EventFeedTable
        from supsrc.tui.widgets import LogPanel

        # Clear event feed
        with contextlib.suppress(Exception):
            self.query_one("#event-feed", EventFeedTable).clear()

        # Clear log panel
        with contextlib.suppress(Exception):
            self.query_one("#log-panel", LogPanel).clear_logs()

        # Emit event instead of log message
        event = UserActionEvent(
            description="Event feed and log panel cleared",
            action="clear_feed",
        )
        self.event_collector.emit(event)

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

            self.event_collector.emit(event)

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

            self.event_collector.emit(event)

    async def action_reload_config(self) -> None:
        """Reload configuration from file."""
        from supsrc.events.system import ConfigReloadEvent, ErrorEvent

        # Emit start event
        start_event = UserActionEvent(
            description="Configuration reload initiated",
            action="reload_config_start",
        )
        self.event_collector.emit(start_event)

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
                    self.event_collector.emit(event)
                except Exception as e:
                    event = ErrorEvent(
                        description=f"Error during configuration reload: {e}",
                        source="config",
                        error_type="ReloadException",
                    )
                    self.event_collector.emit(event)

        self.run_worker(_reload)

    def action_show_help(self) -> None:
        """Show help information."""
        help_text = (
            "🔑 Keyboard Shortcuts:\\n"
            "• [bold]d[/bold] - Toggle dark mode\\n"
            "• [bold]q[/bold] - Quit application\\n"
            "• [bold]^l[/bold] - Clear event log\\n"
            "• [bold]p[/bold] - Pause/resume monitoring\\n"
            "• [bold]s[/bold] - Suspend/resume monitoring\\n"
            "• [bold]c[/bold] - Reload configuration\\n"
            "• [bold]h[/bold] - Show this help\\n"
            "• [bold]Enter[/bold] - View repository details\\n"
            "• [bold]Escape[/bold] - Hide detail pane\\n"
            "\\n"
            "🖱️  Repository Actions (select repo first):\\n"
            "• [bold]Space/P[/bold] - Toggle repository pause\\n"
            "• [bold]Shift+Space/S[/bold] - Toggle repository stop\\n"
            "• [bold]Shift+R[/bold] - Refresh repository status\\n"
            "• [bold]G[/bold] - Resume repository monitoring\\n"
            "• [bold red]a[/bold red] - Acknowledge circuit breaker (🛑)\\n"
            "\\n"
            "🛑 Circuit Breaker: When triggered, select the repo and press [bold]a[/bold] to acknowledge."
        )
        # Emit help event instead of log message
        event = UserActionEvent(
            description=help_text,
            action="show_help",
        )
        self.event_collector.emit(event)

    def action_select_repo_for_detail(self) -> None:
        """Select a repository for detailed view."""
        # Check if we're in the Events tab - if so, don't handle Enter
        try:
            tabbed_content = self.query_one(TabbedContent)
            if tabbed_content.active == "events-tab":
                return  # Let EventFeedTable handle Enter key
        except Exception:
            pass  # If we can't find tabs, continue with normal behavior

        table = self.query_one("#repository_table", DataTable)
        if table.cursor_row < table.row_count:
            selected_row = table.get_row_at(table.cursor_row)
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
                self.event_collector.emit(event)
                # Update the repo details tab content (this also switches to the tab)
                self._update_repo_details_tab(repo_id)

                # Focus the details tab content for keyboard navigation
                try:
                    details_content = self.query_one("#repo-details-content")
                    details_content.focus()
                    log.debug("Focused repo details content")
                except Exception as focus_err:
                    log.debug("Could not focus details content", error=str(focus_err))

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
        self.event_collector.emit(event)
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
            self.event_collector.emit(event)
            self._update_repo_details_tab(self.selected_repo_id)
        else:
            # Emit warning event
            event = UserActionEvent(
                description="No repository selected to refresh",
                action="refresh_details_failed",
            )
            self.event_collector.emit(event)

    def action_focus_next(self) -> None:
        """Focus the next panel in the interface."""
        # Simple two-pane navigation: repo table <-> info pane content
        try:
            # Check if repository table has focus
            repo_table = self.query_one("#repository_table", DataTable)
            if repo_table.has_focus:
                # Move focus to the content of the currently active tab
                tabbed_content = self.query_one(TabbedContent)
                active_tab = tabbed_content.active

                if active_tab == "events-tab":
                    # Focus the EventFeedTable widget directly
                    event_feed = self.query_one("#event-feed")
                    event_feed.focus()
                    log.debug("Focused EventFeedTable content from repo table")
                else:
                    # For other tabs, focus the tabs bar for tab switching
                    tabs = tabbed_content.query_one("Tabs")
                    tabs.focus()
                    log.debug(f"Focused tabs bar from repo table (active: {active_tab})")
            else:
                # Move focus back to repository table
                repo_table.focus()
                log.debug("Focused repo table from tab content")
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

    def action_show_logs(self) -> None:
        """Switch to the Logs tab."""
        try:
            tabbed_content = self.query_one(TabbedContent)
            tabbed_content.active = "logs-tab"
            log.debug("Switched to logs tab")
        except Exception as e:
            log.error("Failed to switch to logs tab", error=str(e))


# 🔼⚙️🔚
