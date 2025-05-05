#
# supsrc/tui/app.py
#

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from textual.app import App, ComposeResult, Autopilot
from textual.containers import Container, VerticalScroll
from textual.widgets import Header, Footer, DataTable, Log as TextualLog
from textual.worker import Worker, get_current_worker
from textual.message import Message

import structlog

# Import orchestrator and state/config types
from supsrc.runtime.orchestrator import WatchOrchestrator, RepositoryStatesMap
from supsrc.state import RepositoryStatus, RepositoryState
from supsrc.config import SupsrcConfig # For type hinting

log = structlog.get_logger("tui.app")

# Define custom messages for TUI updates
class StateUpdate(Message):
    """Message containing the latest repository states."""
    def __init__(self, repo_states: RepositoryStatesMap) -> None:
        self.repo_states = repo_states
        super().__init__()

class LogMessageUpdate(Message):
     """Message containing a log entry for the TUI log widget."""
     def __init__(self, repo_id: Optional[str], level: str, message: str) -> None:
          self.repo_id = repo_id
          self.level = level
          self.message = message
          super().__init__()


class SupsrcTuiApp(App[None]):
    """A Textual app to monitor supsrc repositories."""

    TITLE = "Supsrc Watcher"
    BINDINGS = [
        ("d", "toggle_dark", "Toggle dark mode"),
        ("q", "quit", "Quit"),
    ]
    CSS_PATH = "app.css" # Optional: Define CSS for layout

    def __init__(
        self,
        config_path: Path,
        cli_shutdown_event: asyncio.Event, # Event from CLI for external shutdown trigger
        **kwargs: Any
        ) -> None:
        super().__init__(**kwargs)
        self.config_path = config_path
        self.orchestrator: Optional[WatchOrchestrator] = None
        self._shutdown_event = asyncio.Event() # Internal event for orchestrator
        self._cli_shutdown_event = cli_shutdown_event # External event
        self._repo_states_cache: RepositoryStatesMap = {} # Cache last known states

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()
        with Container():
            yield DataTable(id="repo-table")
            yield TextualLog(id="event-log", highlight=True, wrap=True, max_lines=500)
        yield Footer()

    def on_mount(self) -> None:
        """Called when the app is mounted."""
        log.info("TUI Mounted. Initializing UI components and starting orchestrator worker.")
        # Setup table
        table = self.query_one(DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("ID", "Status", "Last Change", "Save Count", "Error")

        # Start the orchestrator in a background worker thread
        self.run_worker(self._run_orchestrator, thread=True, group="orchestrator")

        # Monitor the external shutdown event from the CLI
        self.set_interval(0.5, self._check_external_shutdown)


    async def _run_orchestrator(self) -> None:
        """Runs the WatchOrchestrator logic."""
        log.info("Orchestrator worker started.")
        # Pass the internal shutdown event to the orchestrator
        self.orchestrator = WatchOrchestrator(self.config_path, self._shutdown_event)
        try:
            # We need to modify the orchestrator or consumer to post updates
            # For now, we assume it runs and we periodically poll its state
            # A better approach is direct message posting from orchestrator/consumer
            await self.orchestrator.run()
        except Exception as e:
             log.exception("Orchestrator failed within TUI worker")
             # Post an error message to the TUI log
             self.post_message(LogMessageUpdate(None, "CRITICAL", f"Orchestrator crashed: {e}"))
        finally:
            log.info("Orchestrator worker finished.")
            # Ensure TUI quits if orchestrator stops unexpectedly
            if not self._shutdown_event.is_set():
                 self.call_later(self.action_quit) # Schedule quit on main thread

    async def _check_external_shutdown(self) -> None:
         """Checks if the CLI requested shutdown."""
         if self._cli_shutdown_event.is_set() and not self._shutdown_event.is_set():
              log.warning("External shutdown detected (CLI signal), stopping TUI and orchestrator.")
              self._shutdown_event.set() # Signal orchestrator to stop
              await self.action_quit() # Request app quit

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Log worker state changes."""
        log.debug(f"Worker {event.worker.name!r} state changed to {event.state!r}")
        # If orchestrator worker stops, initiate quit
        if event.worker.group == "orchestrator" and event.state == "SUCCESS":
             log.info("Orchestrator worker completed normally. Quitting TUI.")
             self.call_later(self.action_quit)


    # --- Action Methods ---
    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.dark = not self.dark

    async def action_quit(self) -> None:
        """Action to quit the application."""
        log.info("Quit action triggered.")
        if not self._shutdown_event.is_set():
             self._shutdown_event.set() # Signal orchestrator if not already stopping
        # Allow some time for orchestrator cleanup before force exiting worker
        await asyncio.sleep(0.2)
        await self.workers.cancel_group(self, "orchestrator", force=True)
        self.exit()

    # --- Message Handlers ---
    def on_state_update(self, message: StateUpdate) -> None:
        """Update the DataTable when state information arrives."""
        log.debug("Received state update message", num_repos=len(message.repo_states))
        table = self.query_one(DataTable)
        # Cache states for potential redraws or other logic
        self._repo_states_cache = message.repo_states

        # Basic update: clear and redraw (can be optimized)
        current_cursor = table.cursor_row
        current_keys = {row_key.value for row_key, _ in table.rows.items()}
        incoming_keys = set(message.repo_states.keys())

        # Remove rows for repos that no longer exist (e.g., config changed?)
        for key_to_remove in current_keys - incoming_keys:
             if table.is_valid_row_key(key_to_remove):
                  table.remove_row(key_to_remove)

        # Add or update rows
        for repo_id, state in message.repo_states.items():
            last_change_str = state.last_change_time.strftime("%Y-%m-%d %H:%M:%S %Z") if state.last_change_time else "-"
            error_str = state.error_message or ""
            status_style = self._get_status_style(state.status)

            row_data = (
                f"[{status_style}]{state.status.name}[/]",
                last_change_str,
                str(state.save_count),
                error_str[:50] + ('...' if len(error_str) > 50 else '') # Truncate error
            )

            if table.is_valid_row_key(repo_id):
                 table.update_row(repo_id, *row_data, update_width=True)
            else:
                 table.add_row(*row_data, key=repo_id, label=repo_id) # Add new repo row

        # Restore cursor if possible
        if table.row_count > 0:
            table.cursor_row = min(current_cursor, table.row_count - 1) if current_cursor >= 0 else 0


    def on_log_message_update(self, message: LogMessageUpdate) -> None:
         """Write a log message to the TUI Log widget."""
         log_widget = self.query_one(TextualLog)
         prefix = f"[{message.repo_id}] " if message.repo_id else ""
         level_prefix = f"[{message.level.upper()}]"
         # Add styling later if desired
         log_widget.write_line(f"{level_prefix} {prefix}{message.message}")


    # --- Helper Methods ---
    def _get_status_style(self, status: RepositoryStatus) -> str:
        """Return a Rich style string based on status."""
        match status:
            case RepositoryStatus.IDLE: return "dim"
            case RepositoryStatus.CHANGED: return "yellow"
            case RepositoryStatus.COMMITTING | RepositoryStatus.PUSHING | RepositoryStatus.PROCESSING | RepositoryStatus.STAGING | RepositoryStatus.TRIGGERED: return "blue" # Consolidate action states
            case RepositoryStatus.ERROR: return "bold red"
            case _: return ""


# --- Mock: How orchestrator would post updates (needs integration) ---
async def post_updates_from_orchestrator(app: SupsrcTuiApp, orchestrator: WatchOrchestrator):
     """Example task showing how orchestrator could send updates to the TUI."""
     while not orchestrator.shutdown_event.is_set():
          await asyncio.sleep(1) # Check periodically
          if orchestrator.repo_states:
               # Important: Send a *copy* of the states to avoid race conditions
               # or potential mutation issues if the state objects themselves are mutable
               # and modified concurrently by the orchestrator thread.
               # Using attrs.asdict or deepcopy might be safer depending on state object complexity.
               # For this example, assume creating a new dict from items is sufficient if states are simple.
               states_copy = dict(orchestrator.repo_states.items())
               try:
                    # Use call_from_thread for thread safety if worker runs in separate thread
                    # If running within Textual's managed worker system, call_later might be okay.
                    app.call_later(app.post_message, StateUpdate(states_copy))
               except Exception as e:
                    log.error("Failed to post state update to TUI", error=str(e))

          # Example: How to post a log message
          # Assume some condition triggers this
          # app.call_later(app.post_message, LogMessageUpdate("some-repo", "info", "Commit successful!"))

# Add CSS file `src/supsrc/tui/app.css` (Optional)
# Example:
# Screen { layout: vertical; }
# Container { height: 1fr; border: round $accent; }
# DataTable { height: 1fr; }
# event-log { height: 10; border-top: thick $accent; }

# 🔼⚙️
