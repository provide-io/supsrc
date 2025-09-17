#
# src/supsrc/tui/app.py
#
"""
Main TUI application for supsrc monitoring.
"""

import asyncio
from pathlib import Path
from typing import Any, ClassVar

import structlog
from textual.app import ComposeResult
from textual.containers import Container
from textual.reactive import var
from textual.widgets import DataTable, Footer, Header
from textual.widgets import Log as TextualLog

from supsrc.runtime.orchestrator import WatchOrchestrator
from supsrc.tui.base_app import TuiAppBase
from supsrc.tui.managers import TimerManager

log = structlog.get_logger("tui.app")


class SupsrcTuiApp(TuiAppBase):
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
        ("p", "pause_monitoring", "Pause/Resume All"),
        ("s", "suspend_monitoring", "Suspend/Resume All"),
        ("c", "reload_config", "Reload Config"),
        ("h", "show_help", "Show Help"),
        ("tab", "focus_next", "Next Panel"),
        ("shift+tab", "focus_previous", "Previous Panel"),
        ("P", "toggle_repo_pause", "Toggle Repo Pause"),
        ("S", "toggle_repo_stop", "Toggle Repo Stop"),
        ("shift+R", "refresh_repo_status", "Refresh Repo Status"),
        ("G", "resume_repo_monitoring", "Resume Repo Monitoring"),
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
        height: 30%; /* Relative height */
        overflow-y: auto;
        scrollbar-gutter: stable;
        border: round $accent;
        padding: 1;
        margin: 1;
    }

    #event-log {
        max-height: 100%;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }

    #repo_detail_log {
        max-height: 100%;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }

    DataTable {
        height: 100%;
        cursor-background: $primary;
        cursor-foreground: $text;
        scrollbar-gutter: stable;
    }

    Footer {
        dock: bottom;
        height: 3;
    }

    Header {
        dock: top;
        height: 3;
    }
    """

    # Reactive variables
    show_detail_pane: bool = var(False, init=False)
    selected_repo_id: str | None = var(None, init=False)

    def __init__(self, config_path: Path, cli_shutdown_event: asyncio.Event, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._config_path = config_path
        self._cli_shutdown_event = cli_shutdown_event
        self._shutdown_event = asyncio.Event()
        self._orchestrator: WatchOrchestrator | None = None
        self._worker = None
        self._is_shutting_down = False
        self.timer_manager: TimerManager | None = None
        self._is_paused = False
        self._is_suspended = False

    def compose(self) -> ComposeResult:
        """Create child widgets for the app."""
        yield Header()

        # Repository table container
        with Container(id="repository_pane_container"):
            yield DataTable(
                id="repository_table",
                cursor_type="row",
                zebra_stripes=True,
                header_height=2,
                show_row_labels=False,
            )

        # Detail pane container (hidden by default)
        with Container(id="detail_pane_container"):
            yield TextualLog(id="repo_detail_log", highlight=True, markup=True)

        # Global log container
        with Container(id="global_log_container"):
            yield TextualLog(id="event-log", highlight=True, markup=True)

        yield Footer()

    def on_mount(self) -> None:
        """Initialize data table and start the orchestrator."""
        try:
            # Set up the data table
            table = self.query_one(DataTable)
            table.add_columns(
                "Status",
                "Timer",
                "Repository",
                "Branch",
                "Total",
                "Changed",
                "Added",
                "Deleted",
                "Modified",
                "Last Commit",
                "Rule",
            )

            # Initialize timer manager
            self.timer_manager = TimerManager(self)

            # Set up a timer to check for external shutdown every 500ms
            self.set_interval(0.5, self._check_external_shutdown)

            # Set up a timer to update countdowns every second
            self.set_interval(1.0, self._update_countdown_display)

            # Set the main worker
            self._worker = self.run_worker(
                self._run_orchestrator(),
                thread=False,
                group="orchestrator_runner",
                name="orchestrator_main",
            )

            self._update_sub_title("Starting orchestrator...")
            log.info("TUI mounted successfully and orchestrator worker started")

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
        except asyncio.CancelledError:
            log.info("Orchestrator worker was cancelled gracefully.")
        except Exception:
            # The worker state change handler is now responsible for the reaction.
            # Just log the exception here. The TUI will be shut down by the handler.
            log.exception("Orchestrator failed within TUI worker. The app will shut down.")
        finally:
            log.info("Orchestrator worker finished.")

    def _run_repo_details_fetch(self, repo_id: str) -> None:
        """Helper method to run repository details fetch worker."""
        self.run_worker(
            self._fetch_repo_details_worker(repo_id),
            thread=True,
            group="repo_detail_fetcher",
            name=f"fetch_details_{repo_id}",
        )


# 🖥️✨