#
# supsrc/tui/app.py
#
"""
Stabilized TUI application with improved layout and proper timer management.
"""

import asyncio
from pathlib import Path
from typing import Any, ClassVar

import structlog
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.reactive import var
from textual.timer import Timer
from textual.widgets import DataTable, Footer, Header
from textual.widgets import Log as TextualLog
from textual.worker import Worker

from supsrc.runtime.orchestrator import WatchOrchestrator
from supsrc.tui.messages import LogMessageUpdate, RepoDetailUpdate, StateUpdate

log = structlog.get_logger("tui.app")


def get_countdown_display(seconds_left: int | None) -> str:
    """Generate countdown display with hand emojis for last 10 seconds."""
    if seconds_left is None:
        return ""
    
    if seconds_left > 10:
        # Show regular countdown
        minutes = seconds_left // 60
        secs = seconds_left % 60
        if minutes > 0:
            return f"{minutes}:{secs:02d}"
        else:
            return f"{secs}s"
    elif seconds_left == 10:
        return "🙌"  # Both hands open (10)
    elif seconds_left == 9:
        return "🖐️✋"  # 5 + 4
    elif seconds_left == 8:
        return "✋✌️"  # 5 + 3
    elif seconds_left == 7:
        return "✋🤘"  # 5 + 2
    elif seconds_left == 6:
        return "✋☝️"  # 5 + 1
    elif seconds_left == 5:
        return "🖐️"  # One hand (5)
    elif seconds_left == 4:
        return "🖖"  # Four fingers
    elif seconds_left == 3:
        return "🤟"  # Three fingers
    elif seconds_left == 2:
        return "✌️"  # Peace sign (2)
    elif seconds_left == 1:
        return "☝️"  # One finger
    else:
        return "💥"  # Zero/trigger


class TimerManager:
    """Manages application timers with proper lifecycle handling."""

    def __init__(self, app: "SupsrcTuiApp") -> None:
        self.app = app
        self._timers: dict[str, Timer] = {}
        self._logger = log.bind(component="TimerManager")

    def create_timer(
        self, name: str, interval: float, callback: callable, repeat: bool = True
    ) -> Timer:
        """Create a new timer with proper tracking."""
        if name in self._timers:
            self.stop_timer(name)

        timer = self.app.set_interval(interval, callback, name=name)
        self._timers[name] = timer
        self._logger.debug("Timer created", name=name, interval=interval)
        return timer

    def stop_timer(self, name: str) -> bool:
        """Stop a specific timer."""
        if name not in self._timers:
            return False

        timer = self._timers[name]
        try:
            # Check if the timer is active by inspecting its internal handle
            if hasattr(timer, "_Timer__handle") and timer._Timer__handle is not None:
                timer.stop()
            # No need to check is_cancelled, stop() should be idempotent or handle internal state.
            # Textual's stop() method on Timer sets _Timer__handle to None.
        except Exception as e:
            self._logger.error("Error stopping timer", name=name, error=str(e))
            return False
        finally:
            if (
                name in self._timers
            ):  # Re-check as timer.stop() might have already removed it via a callback
                del self._timers[name]
            self._logger.debug("Timer stopped or already inactive", name=name)
            return True

    def stop_all_timers(self) -> None:
        """Stop all managed timers."""
        timer_names = list(self._timers.keys())
        for name in timer_names:
            self.stop_timer(name)
        self._logger.debug("All timers stopped", count=len(timer_names))


class SupsrcTuiApp(App):
    """A stabilized Textual app to monitor supsrc repositories."""

    TITLE = "Supsrc Watcher"
    SUB_TITLE = "Monitoring filesystem events..."
    BINDINGS: ClassVar[list] = [
        ("d", "toggle_dark", "Toggle Dark Mode"),
        ("q", "quit", "Quit Application"),
        ("ctrl+c", "quit", "Quit Application"),
        ("ctrl+l", "clear_log", "Clear Log"),
        ("enter", "select_repo_for_detail", "View Details"),
        ("escape", "hide_detail_pane", "Hide Details"),
        ("r", "refresh_details", "Refresh Details"),
        ("p", "pause_monitoring", "Pause/Resume Monitoring"),
        ("s", "suspend_monitoring", "Suspend Monitoring"),
        ("c", "reload_config", "Reload Config"),
        ("h", "show_help", "Show Help"),
        ("tab", "focus_next", "Next Panel"),
        ("shift+tab", "focus_previous", "Previous Panel"),
    ]

    # Updated CSS for better layout
    CSS = """
    Screen {
        layout: vertical;
        overflow: hidden;
    }

    #repository_pane_container { /* Was #table_container */
        height: 40%; /* Initial height, can be adjusted by watch_show_detail_pane */
        overflow-y: auto;
        scrollbar-gutter: stable;
        border: round $accent;
        padding: 1;
        margin: 1;
    }

    #detail_pane_container { /* Was #detail_container */
        display: none; /* Hidden by default */
        height: 30%; /* Height when visible, adjusted by watch_show_detail_pane */
        overflow-y: auto;
        scrollbar-gutter: stable;
        border: round $accent;
        padding: 1;
        margin: 1;
    }

    #global_log_container { /* Was #log_container */
        height: 1fr; /* Takes remaining space */
        overflow-y: auto;
        scrollbar-gutter: stable;
        border: round $accent;
        padding: 1;
        margin: 1;
    }

    #status_container {
        height: 3; /* Fixed height for status messages */
        border: round $accent;
        padding: 1;
        margin: 1;
    }

    DataTable > .datatable--header {
        background: $accent-darken-2;
        color: $text;
    }

    DataTable > .datatable--cursor {
        background: $accent;
        color: $text;
    }

    /* .panel-title can be removed if no longer used, or kept if it is.
       For now, I'll keep it commented out as its usage is unclear
       in the new layout. If it was used for titles within the old #left_panel
       or #right_panel, it might not be needed directly on these new containers.
    .panel-title {
        text-style: bold;
        color: $accent;
    }
    */
    """

    # Reactive variables
    repo_states_data: dict[str, Any] = var({})
    show_detail_pane: bool = var(False)
    selected_repo_id: str | None = var(None)

    def __init__(self, config_path: Path, cli_shutdown_event: asyncio.Event, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._config_path = config_path
        self._orchestrator: WatchOrchestrator | None = None
        self._shutdown_event = asyncio.Event()
        self._cli_shutdown_event = cli_shutdown_event
        self._worker: Worker | None = None
        self._timer_manager = TimerManager(self)
        self._is_shutting_down = False
        self._is_paused = False
        self._is_suspended = False

    def compose(self) -> ComposeResult:
        """Compose the TUI layout with improved structure."""
        yield Header()

        # Repositories Table (Top)
        with Container(id="repository_pane_container"):
            yield DataTable(id="repo-table", zebra_stripes=True)

        # Repository Details (Middle, initially hidden)
        # This container's display style will be controlled by `watch_show_detail_pane`
        with Container(id="detail_pane_container"):
            yield TextualLog(id="repo_detail_log", highlight=False)

        # Global Event Log (Bottom)
        with Container(id="global_log_container"):
            yield TextualLog(id="event-log", highlight=True, max_lines=1000)

        # Status Log (just above Footer or integrated if simple enough)
        # For now, place it in its own container above the footer.
        with Container(id="status_container"):
            yield TextualLog(id="status_log", highlight=False, max_lines=3)

        yield Footer()

    def on_mount(self) -> None:
        """Initialize the TUI with proper error handling."""
        try:
            log.info("TUI Mounted. Initializing UI components.")
            self._update_sub_title("Initializing...")

            # Initialize table
            table = self.query_one(DataTable)
            table.cursor_type = "row"
            table.add_columns(
                "📊",  # Status emoji header
                "⏱️",   # Timer/countdown column
                "Repository",
                "Last Change",
                "Rule",
            )

            # Initialize logs
            log_widget = self.query_one("#event-log", TextualLog)
            log_widget.wrap = True
            log_widget.markup = True

            repo_detail_log_widget = self.query_one("#repo_detail_log", TextualLog)
            repo_detail_log_widget.wrap = True

            status_log_widget = self.query_one("#status_log", TextualLog)
            status_log_widget.write_line("[bold green]Supsrc TUI Started[/]")
            status_log_widget.write_line(
                "Press [bold]Tab[/] to navigate, [bold]Enter[/] for details, [bold]Q[/] to quit"
            )

            # Start orchestrator worker
            log.info("Starting orchestrator worker...")
            self._worker = self.run_worker(
                self._run_orchestrator, thread=True, group="orchestrator"
            )

            # Start shutdown check timer
            self._timer_manager.create_timer(
                "shutdown_check",
                0.5,
                self._check_external_shutdown,
                repeat=True,
            )
            
            # Start countdown update timer
            self._timer_manager.create_timer(
                "countdown_update",
                1.0,
                self._update_countdown_display,
                repeat=True,
            )

            self._update_sub_title("Monitoring...")

        except Exception as e:
            log.exception("Error during TUI mount")
            self._update_sub_title(f"Initialization Error: {e}")

    async def _run_orchestrator(self) -> None:
        """Run the orchestrator with comprehensive error handling."""
        log.info("Orchestrator worker started.")
        try:
            self._orchestrator = WatchOrchestrator(
                self._config_path, self._shutdown_event, app=self
            )
            await self._orchestrator.run()
        except Exception as e:
            log.exception("Orchestrator failed within TUI worker")
            if not self._is_shutting_down:
                self.call_later(
                    self.post_message,
                    LogMessageUpdate(None, "CRITICAL", f"Orchestrator CRASHED: {e}"),
                )
                self._update_sub_title("Orchestrator CRASHED!")
                # Auto-quit on orchestrator failure
                await asyncio.sleep(1.0)
                self.call_later(self.action_quit)
        finally:
            log.info("Orchestrator worker finished.")

    def _check_external_shutdown(self) -> None:
        """Check for external shutdown signals and quit if detected."""
        if self._cli_shutdown_event.is_set() and not self._is_shutting_down:
            log.warning("External shutdown detected (CLI signal). Triggering quit.")
            self.action_quit()
    
    def _update_countdown_display(self) -> None:
        """Update countdown displays for all repositories."""
        try:
            if hasattr(self, "_orchestrator") and self._orchestrator:
                # Update countdown for each repository state
                for repo_state in self._orchestrator.repo_states.values():
                    repo_state.update_timer_countdown()
                
                # Trigger a state update to refresh the display
                states_snapshot = {
                    repo_id: attrs.asdict(state)
                    for repo_id, state in self._orchestrator.repo_states.items()
                }
                self.post_message(StateUpdate(states_snapshot))
        except Exception as e:
            log.debug(f"Error updating countdown: {e}")

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        log.debug("Worker state changed", worker=event.worker.name, state=event.state)
        if (
            event.worker == self._worker
            and event.state in ("SUCCESS", "ERROR")
            and not self._is_shutting_down
        ):
            log.info(f"Orchestrator worker stopped: {event.state}")
            self.call_later(self.action_quit)

    async def _fetch_repo_details_worker(self, repo_id: str) -> None:
        """Worker to fetch repository details."""
        if not self._orchestrator:
            return

        try:
            log.debug(f"Fetching details for {repo_id}")
            details = await self._orchestrator.get_repository_details(repo_id)
            self.post_message(RepoDetailUpdate(repo_id, details))
        except Exception as e:
            log.error(f"Error fetching repo details for {repo_id}", error=str(e))
            error_details = {"commit_history": [f"[bold red]Error loading details: {e}[/]"]}
            self.post_message(RepoDetailUpdate(repo_id, error_details))

    # Watch Methods
    def watch_show_detail_pane(self, show_detail: bool) -> None:
        """Update layout when detail pane visibility changes."""
        try:
            detail_pane_container = self.query_one("#detail_pane_container", Container)  # New ID

            if show_detail:
                detail_pane_container.styles.display = "block"
            else:
                detail_pane_container.styles.display = "none"
        except Exception as e:
            log.error("Error updating detail pane visibility", error=str(e))  # Updated log message

    # Action Methods
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

    def action_toggle_dark(self) -> None:
        """Toggle dark mode."""
        try:
            self.screen.dark = not self.screen.dark
        except Exception as e:
            log.error("Failed to toggle dark mode", error=str(e))

    def action_clear_log(self) -> None:
        """Clear the event log."""
        try:
            self.query_one("#event-log", TextualLog).clear()
            self.post_message(LogMessageUpdate(None, "INFO", "Log cleared."))
        except Exception as e:
            log.error("Failed to clear TUI log", error=str(e))

    def action_pause_monitoring(self) -> None:
        """Toggle pause state for monitoring."""
        self._is_paused = not self._is_paused

        if self._is_paused:
            self._update_sub_title("⏸️  Monitoring PAUSED")
            self.post_message(
                LogMessageUpdate(None, "WARNING", "⏸️  Monitoring PAUSED - Press 'p' to resume")
            )
            # Tell orchestrator to pause
            if self._orchestrator:
                self._orchestrator.pause_monitoring()
        else:
            self._update_sub_title("▶️  Monitoring RESUMED")
            self.post_message(LogMessageUpdate(None, "INFO", "▶️  Monitoring RESUMED"))
            # Tell orchestrator to resume
            if self._orchestrator:
                self._orchestrator.resume_monitoring()

    def action_suspend_monitoring(self) -> None:
        """Suspend monitoring (stronger than pause)."""
        if not self._is_suspended:
            self._is_suspended = True
            self._update_sub_title("⏹️  Monitoring SUSPENDED")
            self.post_message(
                LogMessageUpdate(None, "WARNING", "⏹️  Monitoring SUSPENDED - Press 's' to resume")
            )
            # Tell orchestrator to suspend
            if self._orchestrator:
                self._orchestrator.suspend_monitoring()
        else:
            self._is_suspended = False
            self._update_sub_title("▶️  Monitoring RESUMED from suspension")
            self.post_message(
                LogMessageUpdate(None, "INFO", "▶️  Monitoring RESUMED from suspension")
            )
            # Tell orchestrator to resume from suspension
            if self._orchestrator:
                self._orchestrator.resume_monitoring()

    def action_reload_config(self) -> None:
        """Reload configuration file."""
        self.post_message(LogMessageUpdate(None, "INFO", "🔄 Reloading configuration..."))
        if self._orchestrator:
            # Create async task to reload config
            async def _reload():
                success = await self._orchestrator.reload_config()
                if success:
                    self.post_message(
                        LogMessageUpdate(None, "SUCCESS", "✅ Configuration reloaded successfully")
                    )
                else:
                    self.post_message(
                        LogMessageUpdate(None, "ERROR", "❌ Configuration reload failed")
                    )

            asyncio.create_task(_reload())

    def action_show_help(self) -> None:
        """Show help information about emojis and shortcuts."""
        help_text = """
🔄 EMOJI MEANINGS:
  ⏸️  - Paused (monitoring temporarily halted)
  ⏹️  - Suspended (monitoring stopped)
  ▶️  - Running/Active
  🔄 - Processing/Reloading
  ⏳ - Inactivity timer running
  ⏲️  - Timer active
  ✅ - Success/Completed
  ❌ - Error/Failed
  ⚠️  - Warning
  💾 - Committing changes
  🚀 - Pushing to remote
  ⏱️  - Timing/Duration
  🔼⚙️ - Auto-commit marker

📋 KEYBOARD SHORTCUTS:
  h     - Show this help
  p     - Pause/Resume monitoring
  s     - Suspend monitoring (stops watchers)
  c     - Reload configuration (90s pause)
  d     - Toggle dark mode
  q     - Quit application
  Ctrl+C - Quit application
  Ctrl+L - Clear event log
  Enter  - View repository details
  Escape - Hide details pane
  r     - Refresh repository details
  Tab    - Focus next panel
  Shift+Tab - Focus previous panel

💡 NOTES:
  • Pause keeps watchers active but queues events
  • Suspend stops watchers completely
  • Config reload pauses for 90 seconds
  • Use 'p' to quickly pause/resume
"""
        self.post_message(LogMessageUpdate(None, "INFO", help_text))

    def action_quit(self) -> None:
        """Quit the application gracefully."""
        if self._is_shutting_down:
            return

        self._is_shutting_down = True
        log.info("Quit action triggered.")
        self._update_sub_title("Quitting...")

        # Signal orchestrator shutdown
        if not self._shutdown_event.is_set():
            self._shutdown_event.set()

        # Stop all timers
        self._timer_manager.stop_all_timers()

        # Give worker time to react
        import time
        time.sleep(0.5)

        # Cancel worker
        if self._worker and self._worker.is_running:
            log.info("Cancelling orchestrator worker...")
            try:
                self._worker.cancel()
            except Exception as e:
                log.error(f"Error cancelling worker: {e}", exc_info=True)

        log.info("Exiting TUI application.")
        self.exit(0)
        import sys
        sys.exit(0)

    # Message Handlers
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
                try:
                    table.remove_row(key_to_remove)
                except Exception:
                    # Row may have already been removed
                    pass

            # Update/add rows
            for repo_id_obj, state in message.repo_states.items():
                repo_id_str = str(repo_id_obj)

                # Format display data
                status_display = state.display_status_emoji
                timer_display = get_countdown_display(state.timer_seconds_left)
                repository_display = repo_id_str
                last_change_display = (
                    state.last_change_time.strftime("%Y-%m-%d %H:%M:%S")
                    if state.last_change_time
                    else "N/A"
                )

                rule_emoji = state.rule_emoji or ""
                rule_indicator = state.rule_dynamic_indicator or "N/A"
                rule_display = f"{rule_emoji} {rule_indicator}".strip()

                row_data = (
                    status_display,
                    timer_display,
                    repository_display,
                    last_change_display,
                    rule_display,
                )

                if repo_id_str in table.rows:
                    # Update existing row by removing and re-adding
                    table.remove_row(repo_id_str)
                    table.add_row(*row_data, key=repo_id_str)
                else:
                    table.add_row(*row_data, key=repo_id_str)

        except Exception as e:
            log.error("Failed to update TUI table", error=str(e))

    def on_log_message_update(self, message: LogMessageUpdate) -> None:
        """Handle log message updates."""
        try:
            log_widget = self.query_one("#event-log", TextualLog)
            # The message.message from TextualLogHandler should now be pre-formatted
            # with Rich markup by the ConsoleRenderer.
            log_widget.write_line(message.message)
        except Exception as e:
            # Using the app's own logger here is fine for TUI-specific errors.
            log.error(
                "Failed to write to TUI log widget",
                error=str(e),
                raw_message_level=message.level,
                raw_message_content=message.message,
            )

    def on_repo_detail_update(self, message: RepoDetailUpdate) -> None:
        """Handle repository detail updates."""
        if self.show_detail_pane and message.repo_id == self.selected_repo_id:
            try:
                detail_log = self.query_one("#repo_detail_log", TextualLog)
                detail_log.clear()

                commit_history = message.details.get("commit_history", [])
                if not commit_history:
                    detail_log.write_line("No commit history found or an error occurred.")
                else:
                    detail_log.write_line(f"[b]Commit History for {message.repo_id}:[/b]\n")
                    for entry in commit_history:
                        detail_log.write_line(entry)
            except Exception as e:
                log.error("Error updating repo details", error=str(e))

    # Helper Methods
    def _update_sub_title(self, text: str) -> None:
        """Update subtitle safely."""
        try:
            self.sub_title = text
        except Exception as e:
            log.warning("Failed to update TUI sub-title", error=str(e))

    def _get_level_style(self, level_name: str) -> str:
        """Get style for log level."""
        level = level_name.upper()
        styles = {
            "CRITICAL": "bold white on red",
            "ERROR": "bold red",
            "WARNING": "yellow",
            "INFO": "green",
            "DEBUG": "dim blue",
            "SUCCESS": "bold green",
        }
        return styles.get(level, "white")


# 🖥️✨
