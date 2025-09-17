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
from textual.reactive import var
from textual.widgets import DataTable, Footer, Header, Label, Static, TabbedContent, TabPane
from textual.widgets import Log as TextualLog

from supsrc.runtime.orchestrator import WatchOrchestrator
from supsrc.tui.base_app import TuiAppBase
from supsrc.tui.managers import TimerManager
from supsrc.tui.messages import LogMessageUpdate
from textual.containers import Container, Horizontal, Vertical
from supsrc.tui.widgets import DraggableSplitter

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
        ("t", "test_log_messages", "Test Log Messages"),
    ]

    # Simple 2-pane layout
    CSS = """
    Screen {
        layout: vertical;
    }

    #main_container {
        height: 100%;
        layout: vertical;
    }

    #repository_section {
        height: 60%;
        border: round #888888;
        margin: 0 1;
        padding: 0;
    }

    #log_section {
        height: 35%;
        border: round #888888;
        margin: 0 1;
        padding: 0;
    }

    #splitter_line {
        height: 1;
        background: #444444;
        text-align: center;
        margin: 0;
        padding: 0;
    }

    #splitter_line:hover {
        background: #666666;
    }

    .main-section {
        padding: 0;
        overflow: auto;
        scrollbar-gutter: stable;
    }

    DataTable {
        height: 100%;
        scrollbar-gutter: stable;
    }

    #event-log {
        height: 100%;
        scrollbar-gutter: stable;
    }

    Footer {
        dock: bottom;
        height: 2;
    }

    Header {
        dock: top;
        height: 1;
    }

    /* Tab styling */
    TabbedContent {
        height: 100%;
    }

    TabPane {
        padding: 0;
    }

    Tabs {
        background: #333333;
        color: #ffffff;
        height: 1;
        dock: top;
    }

    Tab {
        background: #444444;
        color: #aaaaaa;
        margin: 0 1;
        padding: 0 1;
    }

    Tab.-active {
        background: #0066cc;
        color: #ffffff;
    }

    Tab:hover {
        background: #555555;
        color: #ffffff;
    }
    """

    # Reactive variables
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

        # Simple vertical layout with two sections
        with Vertical(id="main_container"):
            # Top section: Repository table
            with Container(id="repository_section", classes="main-section"):
                yield DataTable(
                    id="repository_table",
                    cursor_type="row",
                    zebra_stripes=True,
                    header_height=1,
                    show_row_labels=False,
                )

            # Draggable splitter
            yield DraggableSplitter(id="splitter_line")

            # Bottom section: Info pane with tabs
            with Container(id="log_section", classes="main-section"):
                with TabbedContent(initial="logs-tab"):
                    with TabPane("Logs", id="logs-tab"):
                        yield TextualLog(id="event-log", highlight=True)
                    with TabPane("Repo Details", id="details-tab"):
                        yield Label(
                            "Repository details will appear here when selected",
                            id="repo-details-content",
                        )
                    with TabPane("About", id="about-tab"):
                        yield Label(
                            "Supsrc TUI v1.0\nMonitoring and auto-commit system", id="about-content"
                        )

        yield Footer()

    def on_mount(self) -> None:
        """Initialize data table and start the orchestrator."""
        # Foundation/structlog logging is already set up by the CLI
        log.info("🐛 TUI on_mount starting - debug info will go to Foundation logger")

        try:
            # Set up the data table
            table = self.query_one("#repository_table", DataTable)
            table.add_columns(
                "📊",  # Status emoji header
                "⏱️",  # Timer/countdown column
                "Repository",
                "Branch",
                "📁",  # Total files
                "📝",  # Changed files count
                "➕",  # Added files
                "➖",  # Deleted files
                "✏️",  # Modified files
                "Last Commit",
                "Rule",
            )

            # Initialize timer manager
            self.timer_manager = TimerManager(self)

            # Initialize the event log widget
            try:
                log_widget = self.query_one("#event-log", TextualLog)
                log_widget.write_line("[bold green]✅ Event log initialized[/bold green]")
                log.debug("Event log widget initialized successfully")
            except Exception as e:
                log.error("Failed to initialize log widget", error=str(e))

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

    def _update_repo_details_tab(self, repo_id: str) -> None:
        """Update the repo details tab with information about the selected repository."""
        try:
            details_label = self.query_one("#repo-details-content", Label)

            # Get repository information if orchestrator is available
            if self._orchestrator and hasattr(self._orchestrator, "_repository_states"):
                repo_state = self._orchestrator._repository_states.get(repo_id)
                if repo_state:
                    details_text = f"""📍 Repository: {repo_id}
🌿 Branch: {repo_state.current_branch or "unknown"}
📊 Status: {repo_state.display_status_emoji} {repo_state.status.name}
📁 Total files: {repo_state.total_files}
📝 Changed files: {repo_state.changed_files}
➕ Added: {repo_state.added_files}
➖ Deleted: {repo_state.deleted_files}
✏️ Modified: {repo_state.modified_files}
⏱️ Timer: {repo_state.timer_seconds_left}s remaining
🔄 Last updated: {repo_state.last_updated.strftime("%Y-%m-%d %H:%M:%S") if repo_state.last_updated else "never"}

🎯 Rule: {repo_state.rule_name or "default"}
⏸️ Paused: {"Yes" if repo_state.is_paused else "No"}
⏹️ Stopped: {"Yes" if repo_state.is_stopped else "No"}"""
                else:
                    details_text = f"📍 Repository: {repo_id}\n\n⚠️ No state information available"
            else:
                details_text = f"📍 Repository: {repo_id}\n\n⚠️ Orchestrator not ready"

            details_label.update(details_text)

            # Switch to the repo details tab
            tabbed_content = self.query_one(TabbedContent)
            tabbed_content.active = "details-tab"

        except Exception as e:
            log.error("Failed to update repo details tab", error=str(e), repo_id=repo_id)

    def action_test_log_messages(self) -> None:
        """Test action to manually trigger log messages."""
        import datetime

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        # Post several test messages
        self.post_message(LogMessageUpdate(None, "INFO", f"🧪 Test message {timestamp}"))
        self.post_message(LogMessageUpdate("test-repo", "DEBUG", f"🔍 Debug message {timestamp}"))
        self.post_message(LogMessageUpdate(None, "WARNING", f"⚠️ Warning message {timestamp}"))
        self.post_message(
            LogMessageUpdate("another-repo", "ERROR", f"❌ Error message {timestamp}")
        )

        # Also write directly to log widget to test
        try:
            log_widget = self.query_one("#event-log", TextualLog)
            log_widget.write_line(f"[bold yellow]Direct write test {timestamp}[/bold yellow]")
        except Exception as e:
            log.error("Failed direct log write test", error=str(e))

    def on_log_message_update(self, message: LogMessageUpdate) -> None:
        """Handle log message updates."""
        try:
            log_widget = self.query_one("#event-log", TextualLog)
            # Format message with repo name if available
            formatted_message = (
                f"[{message.repo_id}] {message.message}" if message.repo_id else message.message
            )
            log_widget.write_line(formatted_message)
        except Exception as e:
            # Log errors but don't crash the app
            log.error(
                "Failed to write to TUI log widget",
                error=str(e),
                raw_message_level=message.level,
                raw_message_content=message.message,
            )


# 🖥️✨
