#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Main TUI application for supsrc monitoring."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, ClassVar

from provide.foundation.logger import get_logger
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.reactive import var
from textual.widgets import DataTable, Footer, Header, Label, TabbedContent, TabPane
from textual.worker import Worker

from supsrc.events.collector import EventCollector
from supsrc.events.feed_table import EventFeedTable
from supsrc.runtime.orchestrator import WatchOrchestrator
from supsrc.tui.base_app import TuiAppBase
from supsrc.tui.managers import TimerManager
from supsrc.tui.widgets import DraggableSplitter

log = get_logger(__name__)


def _cleanup_console_handlers() -> None:
    """Remove all console/stream handlers from all loggers.

    This prevents any logging output from corrupting the TUI display.
    Called periodically to catch handlers added after initialization.
    """
    # Remove from root logger
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)

    # Remove from all named loggers
    for logger_name in list(logging.Logger.manager.loggerDict.keys()):
        try:
            named_logger = logging.getLogger(logger_name)
            for handler in named_logger.handlers[:]:
                if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                    named_logger.removeHandler(handler)
        except Exception:
            pass


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
        ("space", "toggle_repo_pause", "Toggle Repo Pause"),
        ("P", "toggle_repo_pause", "Toggle Repo Pause"),
        ("shift+space", "toggle_repo_stop", "Toggle Repo Stop"),
        ("S", "toggle_repo_stop", "Toggle Repo Stop"),
        ("shift+R", "refresh_repo_status", "Refresh Repo Status"),
        ("G", "resume_repo_monitoring", "Resume Repo Monitoring"),
        ("a", "acknowledge_circuit_breaker", "Ack Circuit Breaker"),
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
        min-height: 15;
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

    /* Repository table column sizing */
    #repository_table {
        width: 100%;
    }

    #event-feed {
        height: 1fr;
        margin: 0;
        padding: 0;
        border: none;
        scrollbar-gutter: stable;
    }

    #repo-details-content, #about-content {
        height: 1fr;
        margin: 0;
        padding: 1;
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
        layout: vertical;
    }

    TabPane {
        padding: 0;
        height: 1fr;
        overflow: auto;
    }

    Tabs {
        background: #333333;
        color: #ffffff;
        height: 1;
        dock: top;
        margin: 0;
        padding: 0;
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
    selected_repo_id = var(None, init=False)  # type: ignore[assignment]
    repo_states_data: dict[str, Any] = var({})  # type: ignore[assignment]
    show_detail_pane = var(False)

    def __init__(self, config_path: Path, cli_shutdown_event: asyncio.Event, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._config_path = config_path
        self._cli_shutdown_event = cli_shutdown_event
        self._shutdown_event = asyncio.Event()
        self._orchestrator: WatchOrchestrator | None = None  # type: ignore[assignment]
        self._worker: Worker[None] | None = None
        self._countdown_task: Worker[None] | None = None
        self._is_shutting_down = False
        self.timer_manager: TimerManager | None = None
        self._timer_manager = TimerManager(self)
        self._is_paused = False
        self._is_suspended = False
        self.event_collector = EventCollector()
        self._event_feed: EventFeedTable | None = None

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
            with (
                Container(id="log_section", classes="main-section"),
                TabbedContent(initial="events-tab"),
            ):
                with TabPane("Events", id="events-tab"):
                    yield EventFeedTable(id="event-feed")
                with TabPane("Repo Details", id="details-tab"):
                    yield Label(
                        "Repository details will appear here when selected",
                        id="repo-details-content",
                    )
                with TabPane("About", id="about-tab"):
                    yield Label("Supsrc TUI v1.0\nMonitoring and auto-commit system", id="about-content")

        yield Footer()

    def _setup_table_columns(self, table: DataTable) -> None:
        """Set up table columns with simpler, more predictable widths."""
        # Use simpler fixed widths that work well for most terminal sizes
        # Focus on making sure all columns fit and are readable

        table.add_column("📊", width=2)  # Status emoji (reduced from 3)
        table.add_column("⏱️", width=4)  # Timer/countdown - 4 characters as requested
        table.add_column("Repository", width=20)  # Repository name (increased to 20)
        table.add_column("Branch")  # Branch name - auto-size with truncation handling
        table.add_column("📁", width=4)  # Total tracked files
        table.add_column("📝", width=3)  # Changed files (reduced from 4)
        table.add_column("\u2795", width=2)  # Added files (reduced from 4)
        table.add_column("\u2796", width=2)  # Deleted files (reduced from 4)
        table.add_column("✏️", width=3)  # Modified files (reduced from 4)
        table.add_column("Last Commit", width=19)  # yyyy-mm-dd hh:mm:ss (increased from 18)
        table.add_column("Rule", width=10)  # Rule indicator (reduced from 12)

    def on_mount(self) -> None:
        """Initialize data table and start the orchestrator."""
        # CRITICAL: Clean up any console handlers that might corrupt the TUI
        # This is a safety measure in case handlers were added after CLI setup
        _cleanup_console_handlers()

        # Set up periodic cleanup to catch handlers added during runtime
        self.set_interval(5.0, _cleanup_console_handlers)

        log.info("TUI on_mount starting")

        try:
            # Set up the data table with column configurations
            table = self.query_one("#repository_table", DataTable)

            # Add columns with calculated widths
            self._setup_table_columns(table)

            # Initialize timer manager
            self.timer_manager = TimerManager(self)

            # Initialize the event feed widget
            try:
                self._event_feed = self.query_one("#event-feed", EventFeedTable)
                self.event_collector.subscribe(self._event_feed.add_event)
                log.info(
                    "Event feed widget found and subscribed to event collector",
                    handler_count=len(self.event_collector._handlers),
                )

                # Create a welcome event
                from supsrc.events.system import UserActionEvent

                welcome_event = UserActionEvent(
                    description="TUI started successfully",
                    action="start",
                )
                self.event_collector.emit(welcome_event)  # type: ignore[arg-type]
                log.info("Welcome event emitted to test event feed")
            except Exception as e:
                log.error("Failed to initialize event feed widget", error=str(e), exc_info=True)

            # Set up a timer to check for external shutdown every 500ms
            self.set_interval(0.5, self._check_external_shutdown)

            # Set up a timer to update countdowns every second - use asyncio instead of Textual set_interval
            try:
                # Start an async task for periodic countdown updates
                self._countdown_task = self.run_worker(
                    self._periodic_countdown_updater(),
                    thread=False,
                    group="countdown_updater",
                    name="countdown_timer",
                )
                log.debug("Countdown timer task started successfully")
            except Exception as e:
                log.error("Failed to create countdown task", error=str(e))

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

    async def _periodic_countdown_updater(self) -> None:
        """Async task to update countdown displays every second."""
        log.info("Countdown updater task started.")
        try:
            while not self._shutdown_event.is_set():
                # Update countdown displays
                self._update_countdown_display()
                # Wait 1 second before next update
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            log.info("Countdown updater task was cancelled gracefully.")
        except Exception:
            log.exception("Countdown updater task failed.")
        finally:
            log.info("Countdown updater task finished.")

    async def _run_orchestrator(self) -> None:
        """Run the orchestrator with comprehensive error handling."""
        log.info("Orchestrator worker started.")
        try:
            self._orchestrator = WatchOrchestrator(self._config_path, self._shutdown_event, app=self)
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
        from supsrc.tui.helpers import build_repo_details

        try:
            details_label = self.query_one("#repo-details-content", Label)

            # Get repository information if orchestrator is available
            if self._orchestrator and hasattr(self._orchestrator, "repo_states"):
                repo_state = self._orchestrator.repo_states.get(repo_id)
                if repo_state:
                    rule_name = getattr(repo_state, "rule_name", None) or "default"
                    details_text = build_repo_details(repo_id, repo_state, rule_name)
                else:
                    details_text = f"""📍 {repo_id}
{"═" * 60}

⚠️  No state information available

The repository may still be initializing or the orchestrator
has not yet collected state information for this repository."""
            else:
                details_text = f"""📍 {repo_id}
{"═" * 60}

⚠️  Orchestrator not ready

The monitoring system is still starting up. Please wait a
moment for the orchestrator to initialize."""

            details_label.update(details_text)

            # Switch to the repo details tab
            tabbed_content = self.query_one("TabbedContent", TabbedContent)
            tabbed_content.active = "details-tab"

        except Exception as e:
            log.error("Failed to update repo details tab", error=str(e), repo_id=repo_id)

    def watch_show_detail_pane(self, show_detail: bool) -> None:
        """Watch for changes to the show_detail_pane reactive variable."""
        # This method would typically update CSS or widget visibility
        # For now, it's a placeholder to satisfy test expectations
        pass

    def action_test_log_messages(self) -> None:
        """Test action to manually trigger events."""
        import datetime

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")

        # Emit test events using the event system
        from pathlib import Path

        from supsrc.engines.git.events import GitCommitEvent
        from supsrc.events.monitor import FileChangeEvent
        from supsrc.events.system import ErrorEvent, UserActionEvent

        test_events = [
            UserActionEvent(
                description=f"Test user action {timestamp}",
                action="test",
            ),
            FileChangeEvent(
                description=f"Test file modified {timestamp}",
                repo_id="test-repo",
                file_path=Path("test_file.py"),
                change_type="modified",
            ),
            GitCommitEvent(
                description=f"Test commit {timestamp}",
                commit_hash="abc123",
                branch="main",
                files_changed=3,
                repo_id="test-repo",
            ),
            ErrorEvent(
                description=f"Test error message {timestamp}",
                source="test",
                error_type="TestError",
                repo_id="test-repo",
            ),
        ]

        for event in test_events:
            self.event_collector.emit(event)  # type: ignore[arg-type]


# 🖥️✨

# 🔼⚙️🔚
