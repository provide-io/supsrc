#
# supsrc/tui/app.py
#

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

# --- Textual Imports ---
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.reactive import var
from textual.timer import Timer  # <<< Import Timer
from textual.widgets import DataTable, Footer, Header, Static # For placeholder
from textual.widgets import Log as TextualLog
from textual.worker import Worker

# Conditional Var alias removed
# if TYPE_CHECKING:
#     Var = var
# else:
#     Var = object

import structlog

# --- Supsrc Imports ---
from supsrc.runtime.orchestrator import RepositoryStatesMap, WatchOrchestrator
from supsrc.state import RepositoryStatus

log = structlog.get_logger("tui.app")

# --- Custom Messages (Unchanged) ---
class StateUpdate(Message):
    ALLOW_BUBBLE = True
    def __init__(self, repo_states: RepositoryStatesMap) -> None:
        self.repo_states = repo_states
        super().__init__()

class LogMessageUpdate(Message):
     ALLOW_BUBBLE = True
     def __init__(self, repo_id: str | None, level: str, message: str) -> None:
          self.repo_id = repo_id
          self.level = level
          self.message = message
          super().__init__()

class RepoDetailUpdate(Message):
    """Message to update the repo detail pane."""
    ALLOW_BUBBLE = True # Or False if only handled by App
    def __init__(self, repo_id: str, details: dict[str, Any]) -> None:
        self.repo_id = repo_id
        self.details = details # This will contain {"commit_history": [...]}
        super().__init__()


# --- The Textual Application ---
class SupsrcTuiApp(App):
    """A Textual app to monitor supsrc repositories."""

    TITLE = "Supsrc Watcher"
    SUB_TITLE = "Monitoring filesystem events..."
    BINDINGS = [
        ("d", "toggle_dark", "Toggle Dark Mode"),
        ("q", "quit", "Quit Application"),
        ("ctrl+l", "clear_log", "Clear Log"),
        ("enter", "select_repo_for_detail", "View Details"),
        ("escape", "hide_detail_pane", "Hide Details"),
    ]
    CSS = """
    Screen {
        layout: vertical; /* Header, main_content, Footer */
        overflow-y: hidden; /* Prevent screen scroll */
    }
    #main_content_area { /* New container to hold panes */
        layout: vertical;
        height: 1fr; /* Take remaining space */
        overflow-y: hidden;
    }
    #table_container {
        height: 60%; /* Initial height for repo table */
        overflow-y: auto;
        scrollbar-gutter: stable;
        border: round $accent;
        padding: 1;
    }
    #detail_container {
        display: none; /* Initially hidden */
        height: 30%;   /* Height when visible */
        overflow-y: auto;
        scrollbar-gutter: stable;
        border: round $accent;
        padding: 1;
        margin-top: 1;
    }
    #global_log_container {
        height: 40%; /* Initial height for global log */
        overflow-y: auto;
        scrollbar-gutter: stable;
        border: round $accent;
        padding: 1;
        margin-top: 1; /* Margin from table or detail view */
    }
    /* Keep existing DataTable styles for header/cursor */
    DataTable > .datatable--header {
        background: $accent-darken-2;
        color: $text;
    }
    DataTable > .datatable--cursor {
        background: $accent;
        color: $text;
    }
    """

    # Reactive variables directly using type hints and var()
    repo_states_data: dict[str, Any] = var({})
    show_detail_pane: bool = var(False)
    selected_repo_id: str | None = var(None)

    # __init__ - Add timer attribute
    def __init__(
        self,
        config_path: Path,
        cli_shutdown_event: asyncio.Event,
        **kwargs: Any
        ) -> None:
        super().__init__(**kwargs)
        self._config_path = config_path
        self._orchestrator: WatchOrchestrator | None = None
        self._shutdown_event = asyncio.Event()
        self._cli_shutdown_event = cli_shutdown_event
        self._worker: Worker | None = None
        self._shutdown_check_timer: Timer | None = None # <<< Store timer object

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main_content_area"):
            with Container(id="table_container"):
                yield DataTable(id="repo-table", zebra_stripes=True)
            with Container(id="detail_container"):
                yield TextualLog(id="repo_detail_log", highlight=False)
            with Container(id="global_log_container"):
                yield TextualLog(id="event-log", highlight=True, max_lines=1000)
        yield Footer()

    def on_mount(self) -> None:
        # (Implementation unchanged from last correction)
        log.info("TUI Mounted. Initializing UI components.")
        self._update_sub_title("Initializing...")
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.add_columns("Status", "Repository", "Last Change", "Rule", "Current Action", "Last Commit / Message")
        log_widget = self.query_one("#event-log", TextualLog) # Query specifically for the global log
        log_widget.wrap = True
        log_widget.markup = True

        # Configure the repo_detail_log
        repo_detail_log_widget = self.query_one("#repo_detail_log", TextualLog)
        repo_detail_log_widget.wrap = True
        
        log.info("Starting orchestrator worker...")
        self._worker = self.run_worker(self._run_orchestrator, thread=True, group="orchestrator")
        # --- FIX HERE: Store the timer object ---
        self._shutdown_check_timer = self.set_interval(0.5, self._check_external_shutdown, name="ExternalShutdownCheck")
        # --------------------------------------
        self._update_sub_title("Monitoring...")

    # _run_orchestrator remains the same
    async def _run_orchestrator(self) -> None:
        # (Implementation unchanged)
        log.info("Orchestrator worker started.")
        self._orchestrator = WatchOrchestrator(self._config_path, self._shutdown_event, app=self)
        try: await self._orchestrator.run()
        except Exception as e:
             log.exception("Orchestrator failed within TUI worker")
             self.call_later(self.post_message, LogMessageUpdate(None, "CRITICAL", f"Orchestrator CRASHED: {e}"))
             self._update_sub_title("Orchestrator CRASHED!")
        finally:
            log.info("Orchestrator worker finished.")
            if not self._shutdown_event.is_set() and not self._cli_shutdown_event.is_set():
                 log.warning("Orchestrator stopped unexpectedly, requesting TUI quit.")
                 self._update_sub_title("Orchestrator Stopped.")
                 self.call_later(self.action_quit)

    # _check_external_shutdown remains the same
    async def _check_external_shutdown(self) -> None:
         # (Implementation unchanged)
         if self._cli_shutdown_event.is_set() and not self._shutdown_event.is_set():
              log.warning("External shutdown detected (CLI signal), stopping TUI and orchestrator.")
              self._update_sub_title("Shutdown requested...")
              await self.action_quit()

    # on_worker_state_changed remains the same
    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        # (Implementation unchanged)
        log.debug(f"Worker {event.worker.name!r} state changed to {event.state!r}")
        if event.worker == self._worker and event.state in ("SUCCESS", "ERROR"):
             log.info(f"Orchestrator worker stopped with state: {event.state!r}")
             if not self._shutdown_event.is_set() and not self._cli_shutdown_event.is_set():
                 self.call_later(self.action_quit)

    async def _fetch_repo_details_worker(self, repo_id: str) -> None:
        """Worker to fetch repository details from the orchestrator."""
        if self._orchestrator:
            log.debug(f"TUI worker: Fetching details for {repo_id}")
            try:
                details = await self._orchestrator.get_repository_details(repo_id)
                self.post_message(RepoDetailUpdate(repo_id, details))
                log.debug(f"TUI worker: Posted RepoDetailUpdate for {repo_id}")
            except Exception as e:
                log.error(f"TUI worker: Error fetching repo details for {repo_id}", error=str(e), exc_info=True)
                # Post an update to show error in detail pane
                error_details = {"commit_history": [f"[bold red]Error loading details: {e}[/]"]}
                self.post_message(RepoDetailUpdate(repo_id, error_details))

    # --- Watch Methods for Reactive Vars ---
    def watch_show_detail_pane(self, show_detail: bool) -> None:
        """Called when show_detail_pane changes."""
        detail_container = self.query_one("#detail_container", Container)
        table_container = self.query_one("#table_container", Container)
        global_log_container = self.query_one("#global_log_container", Container)

        if show_detail:
            detail_container.styles.display = "block"
            # Adjusted heights for 3-pane view based on subtask description
            table_container.styles.height = "40%" 
            detail_container.styles.height = "30%" # Matches CSS
            global_log_container.styles.height = "30%" 
        else:
            detail_container.styles.display = "none"
            table_container.styles.height = "60%" # Matches CSS
            global_log_container.styles.height = "40%" # Matches CSS

    # --- Action Methods ---
    def action_select_repo_for_detail(self) -> None:
        """Show detail pane for the selected repository."""
        table = self.query_one(DataTable)
        # Textual's DataTable `cursor_row` is the index, `get_row_key` gets the key at that index
        try:
            row_key = table.get_row_key(table.cursor_row)
            if row_key is not None:
                self.selected_repo_id = str(row_key)
                self.show_detail_pane = True
                # Update placeholder in detail view - Replaced by worker logic
                # detail_placeholder = self.query_one("#detail_content_placeholder", Static)
                # detail_placeholder.update(f"Details for Repository ID: [b]{self.selected_repo_id}[/b]")
                
                if self._orchestrator and self.selected_repo_id:
                    # Clear previous content if any
                    self.query_one("#repo_detail_log", TextualLog).clear()
                    self.query_one("#repo_detail_log", TextualLog).write_line(f"Fetching details for [b]{self.selected_repo_id}[/b]...")
                    
                    self.run_worker(
                        self._fetch_repo_details_worker(self.selected_repo_id),
                        thread=True, # Can run in thread as it involves a potentially blocking git call via orchestrator
                        group="repo_detail_fetcher",
                        name=f"fetch_details_{self.selected_repo_id}"
                    )
                # Optionally, focus something in the detail pane if it becomes interactive
                # self.query_one("#detail_container").focus() 
        except Exception as e:
            log.error("Error selecting repo for detail", error=str(e), exc_info=True)


    def action_hide_detail_pane(self) -> None:
        """Hide the detail pane and return to 2-pane view."""
        if self.show_detail_pane:
            self.show_detail_pane = False
            self.selected_repo_id = None
            try:
                self.query_one("#repo_detail_log", TextualLog).clear()
            except Exception as e:
                log.error("Error clearing detail log on hide", error=str(e))
            self.query_one(DataTable).focus()


    def action_toggle_dark(self) -> None:
        # (Implementation unchanged)
        try: self.screen.dark = not self.screen.dark
        except Exception as e: log.error("Failed to toggle dark mode", error=str(e))
    def action_clear_log(self) -> None:
        # (Implementation unchanged)
        try: self.query_one(TextualLog).clear(); self.post_message(LogMessageUpdate(None, "INFO", "Log cleared."))
        except Exception as e: log.error("Failed to clear TUI log", error=str(e))

    async def action_quit(self) -> None:
        """Action to quit the application."""
        log.info("Quit action triggered."); self._update_sub_title("Quitting...")
        if not self._shutdown_event.is_set(): self._shutdown_event.set() # Signal orchestrator

        # --- FIX HERE: Stop the timer object ---
        if self._shutdown_check_timer:
            try:
                self._shutdown_check_timer.stop()
                log.debug("Stopped external shutdown check timer.")
            except Exception as e:
                log.error("Error stopping shutdown check timer", error=str(e))
        # --------------------------------------

        await asyncio.sleep(0.3) # Give worker time to react
        if self._worker and self._worker.is_running:
             log.info("Attempting to cancel orchestrator worker...")
             try: await self._worker.cancel()
             except Exception: log.exception("Error during worker cancel")
        log.info("Exiting TUI application."); self.exit(0)


    # --- Message Handlers (remain the same) ---
    def on_state_update(self, message: StateUpdate) -> None:
        # (Implementation unchanged)
        log.debug(
            "TUI: on_state_update received",
            data_keys=list(message.repo_states.keys()),
            num_repos_received=len(message.repo_states)
        )
        # log.debug("TUI received state update", num_repos=len(message.repo_states)) # Original, slightly less info
        try:
            table = self.query_one(DataTable)
            current_keys = set(table.rows.keys())
            incoming_keys = set(message.repo_states.keys())
            for key_to_remove in current_keys - incoming_keys:
                 if table.is_valid_row_key(key_to_remove): table.remove_row(key_to_remove)
            for repo_id_obj, state in message.repo_states.items():
                repo_id_str = str(repo_id_obj)

                # Status column: Uses the pre-calculated emoji
                status_display = state.display_status_emoji

                # Repository column:
                repository_display = repo_id_str

                # Last Change column: Format the timestamp
                last_change_display = state.last_change_time.strftime("%Y-%m-%d %H:%M:%S") if state.last_change_time else "N/A"
                
                # Rule column (new combination)
                rule_emoji_display = state.rule_emoji if state.rule_emoji else ""
                rule_indicator_display = state.rule_dynamic_indicator if state.rule_dynamic_indicator else "N/A"
                rule_display = f"{rule_emoji_display} {rule_indicator_display}".strip()

                # Current Action column (new) with progress bar
                action_display = state.action_description if state.action_description else ""
                if state.action_description and state.action_progress_total is not None and state.action_progress_completed is not None:
                    total = state.action_progress_total
                    completed = state.action_progress_completed
                    if total > 0: # Avoid division by zero if total is 0
                        percentage = (completed / total) * 100
                        bar_width = 10 # Define a fixed width for the textual bar
                        filled_width = int(bar_width * completed // total)
                        bar_text = "❚" * filled_width + "-" * (bar_width - filled_width)
                        action_display = f"{state.action_description} [{bar_text}] {percentage:.0f}%"
                    else: # Handle cases like total is 0 or indeterminate progress where completed might be 0
                        if completed == total : # if 0/0 treat as 100% or just completed
                           action_display = f"{state.action_description} [Done]"
                        else: # indeterminate or starting
                           action_display = f"{state.action_description} [...]" 
                elif state.action_description:
                    # If no progress data, just show the description
                    action_display = state.action_description
                else:
                    action_display = "" # No action, empty string


                # Last Commit / Message column:
                commit_hash_display = state.last_commit_short_hash if state.last_commit_short_hash else "-------"
                commit_msg_summary = state.last_commit_message_summary if state.last_commit_message_summary else "No commit info"
                # Truncate commit message summary if it's too long
                commit_msg_display = commit_msg_summary # Assign before potential truncation
                if len(commit_msg_display) > 30:
                    commit_msg_display = commit_msg_display[:27] + "..."
                last_commit_display = f"{commit_hash_display} - {commit_msg_display}"
                if not state.last_commit_short_hash and not state.last_commit_message_summary:
                    last_commit_display = "N/A" # Display N/A if both parts are missing

                row_data = (
                    status_display,
                    repository_display,
                    last_change_display,
                    rule_display,          # New combined field for "Rule"
                    action_display,        # New field for "Current Action"
                    last_commit_display
                )
                
                if table.is_valid_row_key(repo_id_str):
                    table.update_row(repo_id_str, *row_data, update_width=False)
                else:
                    table.add_row(*row_data, key=repo_id_str)
        except Exception as e: log.error("Failed to update TUI table", error=str(e))

    def on_log_message_update(self, message: LogMessageUpdate) -> None:
         # (Implementation unchanged)
         try:
             log_widget = self.query_one(TextualLog)
             prefix = f"[dim]({message.repo_id or 'SYSTEM'})[/dim] "
             level_style = self._get_level_style(message.level)
             level_prefix = f"[{level_style}]{message.level.upper():<8}[/]"
             log_widget.write_line(f"{level_prefix} {prefix}{message.message}")
         except Exception as e: log.error("Failed to write to TUI log", error=str(e))

    def on_repo_detail_update(self, message: RepoDetailUpdate) -> None:
        """Handles updates to the repository detail pane."""
        log.debug(f"TUI received RepoDetailUpdate for {message.repo_id}")
        # Only update if the detail pane is visible and for the currently selected repo
        if self.show_detail_pane and message.repo_id == self.selected_repo_id:
            detail_log = self.query_one("#repo_detail_log", TextualLog)
            detail_log.clear()
            
            commit_history = message.details.get("commit_history", [])
            if not commit_history:
                detail_log.write_line("No commit history found or an error occurred.")
            else:
                detail_log.write_line(f"[b]Commit History for {message.repo_id}:[/b]\n")
                for entry in commit_history:
                    # Assuming entries are already formatted strings from GitEngine
                    detail_log.write_line(entry) 
        elif not self.show_detail_pane:
            log.debug(f"Detail pane not visible, ignoring RepoDetailUpdate for {message.repo_id}")
        else: # Mismatch between message.repo_id and self.selected_repo_id
            log.debug(f"Ignoring stale RepoDetailUpdate for {message.repo_id} (current: {self.selected_repo_id})")

    # --- Helper Methods (remain the same) ---
    def _update_sub_title(self, text: str) -> None:
        try: self.sub_title = text
        except Exception as e: log.warning("Failed to update TUI sub-title", error=str(e))
    # def _get_status_style_and_icon(self, status: RepositoryStatus) -> tuple[str, str]:
    #     # (Implementation unchanged)
    #     match status:
    #         case RepositoryStatus.IDLE: return ("dim", "✅")
    #         case RepositoryStatus.CHANGED: return ("yellow", "📝")
    #         case RepositoryStatus.TRIGGERED: return ("blue", "⏳")
    #         case RepositoryStatus.PROCESSING: return ("cyan", "⚙️")
    #         case RepositoryStatus.STAGING: return ("magenta", "➕")
    #         case RepositoryStatus.COMMITTING: return ("green", "💾")
    #         case RepositoryStatus.PUSHING: return ("bright_blue", "🚀")
    #         case RepositoryStatus.ERROR: return ("bold red", "❌")
    #         case _: return ("", "❓")
    def _get_level_style(self, level_name: str) -> str:
         # (Implementation unchanged)
         level = level_name.upper()
         if level == "CRITICAL": return "bold white on red"
         if level == "ERROR": return "bold red"
         if level == "WARNING": return "yellow"
         if level == "INFO": return "green"
         if level == "DEBUG": return "dim blue"
         if level == "SUCCESS": return "bold green"
         return "white"

# if __name__ == "__main__": remains the same
if __name__ == "__main__":
    try:
        test_config = Path(__file__).parent.parent.parent.parent / "examples" / "supsrc.conf"
        if not test_config.is_file(): pass
        else:
            dummy_shutdown = asyncio.Event()
            app_instance = SupsrcTuiApp(config_path=test_config, cli_shutdown_event=dummy_shutdown)
            app_instance.run()
    except NameError: pass
    except ImportError: pass

# 🔼⚙️
