#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Main TUI application for supsrc monitoring."""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, ClassVar

from provide.foundation.logger import get_logger
from textual.app import ComposeResult
from textual.containers import Container, Vertical, VerticalScroll
from textual.reactive import var
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane
from textual.worker import Worker

from supsrc.events.collector import EventCollector
from supsrc.events.feed_table import EventFeedTable
from supsrc.runtime.orchestrator import WatchOrchestrator
from supsrc.tui.base_app import TuiAppBase
from supsrc.tui.managers import TimerManager
from supsrc.tui.widgets import (
    DraggableSplitter,
    LogPanel,
    get_tui_log_handler,
    get_tui_output_stream,
)

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
        ("l", "show_logs", "Show Logs Tab"),
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

    #repo-details-scroll, #files-tree-scroll, #history-scroll, #diff-scroll, #about-scroll {
        height: 1fr;
        margin: 0;
        padding: 0;
        scrollbar-gutter: stable;
    }

    #repo-details-content, #files-tree-content, #history-content, #diff-content, #about-content {
        height: auto;
        width: 100%;
        margin: 0;
        padding: 1;
    }

    #log-panel {
        height: 1fr;
        width: 100%;
        margin: 0;
        padding: 0;
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
        self._log_panel: LogPanel | None = None

        # CRITICAL: Redirect stdout/stderr and Foundation logs BEFORE any logging happens
        # This prevents log output from corrupting the TUI display
        self._tui_output_stream = get_tui_output_stream()
        self._original_stdout = sys.stdout
        self._original_stderr = sys.stderr

        # Redirect Foundation's log stream to our TUI stream
        # Loggers are created at import time with the original stderr.
        # We monkeypatch PrintLogger.msg to always use our stream.
        try:
            from provide.foundation.streams import set_log_stream_for_testing

            set_log_stream_for_testing(self._tui_output_stream)

            # Completely reconfigure structlog with PrintLoggerFactory
            # The CLI setup uses stdlib.LoggerFactory with processors that don't work
            # well with PrintLogger. We need to use the correct processors.
            import structlog

            structlog.configure(
                processors=[
                    structlog.contextvars.merge_contextvars,
                    structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.processors.StackInfoRenderer(),
                    structlog.processors.format_exc_info,
                    structlog.processors.UnicodeDecoder(),
                    structlog.dev.ConsoleRenderer(),  # Use ConsoleRenderer for PrintLogger
                ],
                wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
                context_class=dict,
                logger_factory=structlog.PrintLoggerFactory(file=self._tui_output_stream),
                cache_logger_on_first_use=False,  # Don't cache - we need fresh loggers
            )

            # Monkeypatch PrintLogger to use our stream for ALL instances
            # This captures logs from loggers created before the TUI started
            from structlog._output import PrintLogger

            tui_stream = self._tui_output_stream

            def patched_msg(self_logger: PrintLogger, message: str) -> None:
                with self_logger._lock:
                    print(message, file=tui_stream, flush=True)

            PrintLogger.msg = patched_msg  # type: ignore[method-assign]
        except Exception:
            pass  # Foundation redirect failed, fall back to stream capture

        # Redirect both sys.stdout and sys.stderr to capture any direct writes
        # Some libraries or exception handlers write directly to these streams
        sys.stdout = self._tui_output_stream  # type: ignore[assignment]
        sys.stderr = self._tui_output_stream  # type: ignore[assignment]

        # Install TUI log handler early to capture all startup logs
        # Messages are buffered until the widget is ready
        self._tui_log_handler = get_tui_log_handler()
        self._tui_log_handler.set_app(self)
        root_logger = logging.getLogger()
        if self._tui_log_handler not in root_logger.handlers:
            self._tui_log_handler.setLevel(logging.DEBUG)
            root_logger.addHandler(self._tui_log_handler)

        # Reduce noise from Foundation's file operation detection
        # These loggers emit frequent DEBUG/INFO messages about temp file handling
        # that can clutter the Logs tab. Set them to WARNING to only see issues.
        for noisy_logger in [
            "provide.foundation.file.operations.detectors.orchestrator",
            "provide.foundation.file.operations.detectors.auto_flush",
        ]:
            logging.getLogger(noisy_logger).setLevel(logging.WARNING)

        log.info("TUI app initializing - logs will be captured")

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
                with TabPane("Repo Details", id="details-tab"), VerticalScroll(id="repo-details-scroll"):
                    yield Static(
                        "Repository details will appear here when selected",
                        id="repo-details-content",
                    )
                with TabPane("📂 Files", id="files-tab"), VerticalScroll(id="files-tree-scroll"):
                    yield Static(
                        "Select a repository to view changed files",
                        id="files-tree-content",
                    )
                with TabPane("📜 History", id="history-tab"), VerticalScroll(id="history-scroll"):
                    yield Static(
                        "Select a repository to view commit history",
                        id="history-content",
                    )
                with TabPane("📋 Diff", id="diff-tab"), VerticalScroll(id="diff-scroll"):
                    yield Static(
                        "Select a repository to view diff",
                        id="diff-content",
                    )
                with TabPane("About", id="about-tab"), VerticalScroll(id="about-scroll"):
                    yield Static(
                        "Supsrc TUI v1.0\nMonitoring and auto-commit system",
                        id="about-content",
                    )
                with TabPane("📋 Logs", id="logs-tab"):
                    yield LogPanel(id="log-panel")

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

            # Connect the log panel widget to the already-installed handler
            # This flushes any buffered messages from startup
            try:
                self._log_panel = self.query_one("#log-panel", LogPanel)
                self._tui_log_handler.set_widget(self._log_panel)

                # Also connect the TUI output stream to capture Foundation logs
                self._tui_output_stream.set_panel(self._log_panel)

                log.info("Log panel connected - buffered logs flushed")
            except Exception as e:
                log.error("Failed to connect log panel", error=str(e), exc_info=True)

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

    def _update_repo_details_tab(self, repo_id: str, switch_tab: bool = True) -> None:
        """Update the repo details tab with information about the selected repository.

        Args:
            repo_id: The repository ID to show details for.
            switch_tab: If True, switch to the details tab. If False, only update content.
        """
        from supsrc.tui.helpers import build_repo_details

        try:
            details_widget = self.query_one("#repo-details-content", Static)

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

            details_widget.update(details_text)

            # Only switch to the repo details tab if requested
            if switch_tab:
                tabbed_content = self.query_one("TabbedContent", TabbedContent)
                tabbed_content.active = "details-tab"

                # Only set lazy placeholders when switching to a NEW repo
                # Don't reset on periodic state updates (switch_tab=False)
                self._set_tab_lazy_placeholders(repo_id)

        except Exception as e:
            log.error("Failed to update repo details tab", error=str(e), repo_id=repo_id)

    def _set_tab_lazy_placeholders(self, repo_id: str) -> None:
        """Set placeholder content for tabs that will load lazily."""
        try:
            placeholder = "[dim]Switch to this tab to load data...[/dim]"

            files_widget = self.query_one("#files-tree-content", Static)
            files_widget.update(f"[bold]📂 {repo_id}[/bold]\n\n{placeholder}")

            history_widget = self.query_one("#history-content", Static)
            history_widget.update(f"[bold]📜 {repo_id}[/bold]\n\n{placeholder}")

            diff_widget = self.query_one("#diff-content", Static)
            diff_widget.update(f"[bold]📋 {repo_id}[/bold]\n\n{placeholder}")
        except Exception:
            pass

    def _load_tab_for_repo(self, tab_id: str, repo_id: str) -> None:
        """Load data for a specific tab lazily.

        Args:
            tab_id: The tab to load (files-tab, history-tab, diff-tab)
            repo_id: The repository ID to load data for
        """
        # Show loading indicator immediately
        try:
            loading_msg = "[dim]Loading...[/dim]"
            if tab_id == "files-tab":
                self.query_one("#files-tree-content", Static).update(
                    f"[bold]📂 {repo_id}[/bold]\n\n{loading_msg}"
                )
            elif tab_id == "history-tab":
                self.query_one("#history-content", Static).update(
                    f"[bold]📜 {repo_id}[/bold]\n\n{loading_msg}"
                )
            elif tab_id == "diff-tab":
                self.query_one("#diff-content", Static).update(f"[bold]📋 {repo_id}[/bold]\n\n{loading_msg}")
        except Exception:
            pass

        if not self._orchestrator:
            return

        # Get repo config and path
        repo_config = None
        if self._orchestrator.config:
            repo_config = self._orchestrator.config.repositories.get(repo_id)

        if not repo_config or not repo_config.path:
            return

        repo_path = repo_config.path

        # Get the git engine for this repo
        engine = self._orchestrator.repo_engines.get(repo_id)
        if not engine or not hasattr(engine, "operations"):
            return

        # Load only the requested tab
        if tab_id == "files-tab":
            self.run_worker(
                self._update_files_tab(repo_id, repo_path, engine),
                thread=False,
                group="tab_updates",
            )
        elif tab_id == "history-tab":
            self.run_worker(
                self._update_history_tab(repo_id, repo_path, engine),
                thread=False,
                group="tab_updates",
            )
        elif tab_id == "diff-tab":
            self.run_worker(
                self._update_diff_tab(repo_id, repo_path, engine),
                thread=False,
                group="tab_updates",
            )

    def _set_tab_placeholder_content(self, repo_id: str, reason: str) -> None:
        """Set placeholder content for all tabs when data isn't available."""
        try:
            placeholder = f"[yellow]⚠️ {reason}[/yellow]\n\nSelect a repository to view details."

            files_widget = self.query_one("#files-tree-content", Static)
            files_widget.update(f"[bold]📂 {repo_id}[/bold]\n\n{placeholder}")

            history_widget = self.query_one("#history-content", Static)
            history_widget.update(f"[bold]📜 {repo_id}[/bold]\n\n{placeholder}")

            diff_widget = self.query_one("#diff-content", Static)
            diff_widget.update(f"[bold]📋 {repo_id}[/bold]\n\n{placeholder}")
        except Exception:
            pass

    async def _update_files_tab(self, repo_id: str, repo_path: Path, engine: Any) -> None:
        """Update the files tree tab asynchronously."""
        from supsrc.tui.helpers import build_conflict_warning, build_files_tree_content

        try:
            files_widget = self.query_one("#files-tree-content", Static)

            # Get changed files
            files = await engine.operations.get_changed_files_tree(repo_path)

            # Check for conflicts
            conflict_info = await engine.operations.check_upstream_conflicts(repo_path)
            conflict_warning = build_conflict_warning(conflict_info, repo_id)

            # Build content
            content = build_files_tree_content(files, repo_id)
            if conflict_warning:
                content = conflict_warning + "\n" + content

            files_widget.update(content)

        except Exception as e:
            log.error("Failed to update files tab", error=str(e), repo_id=repo_id)
            try:
                files_widget = self.query_one("#files-tree-content", Static)
                files_widget.update(f"[red]Error loading files:[/red] {e}")
            except Exception:
                pass

    async def _update_history_tab(self, repo_id: str, repo_path: Path, engine: Any) -> None:
        """Update the commit history tab asynchronously."""
        from supsrc.tui.helpers import build_history_content

        try:
            history_widget = self.query_one("#history-content", Static)

            # Get commit history
            commits = await engine.operations.get_detailed_commit_history(repo_path, limit=20)

            # Build content
            content = build_history_content(commits, repo_id)
            history_widget.update(content)

        except Exception as e:
            log.error("Failed to update history tab", error=str(e), repo_id=repo_id)
            try:
                history_widget = self.query_one("#history-content", Static)
                history_widget.update(f"[red]Error loading history:[/red] {e}")
            except Exception:
                pass

    async def _update_diff_tab(self, repo_id: str, repo_path: Path, engine: Any) -> None:
        """Update the diff preview tab asynchronously."""
        from supsrc.tui.helpers import build_diff_content

        try:
            diff_widget = self.query_one("#diff-content", Static)

            # Get working diff
            diff_text = await engine.operations.get_working_diff(repo_path, max_lines=500)

            # Build content
            content = build_diff_content(diff_text, repo_id)
            diff_widget.update(content)

        except Exception as e:
            log.error("Failed to update diff tab", error=str(e), repo_id=repo_id, exc_info=True)
            try:
                diff_widget = self.query_one("#diff-content", Static)
                error_content = f"""[bold]📋 {repo_id}[/bold]
[dim]{"═" * 60}[/dim]

[red]Error loading diff:[/red]
{e}

[dim]Check the log for more details.[/dim]"""
                diff_widget.update(error_content)
            except Exception:
                pass

    def watch_show_detail_pane(self, show_detail: bool) -> None:
        """Watch for changes to the show_detail_pane reactive variable.

        Updates CSS classes and widget visibility when toggling the detail pane.
        """
        try:
            # Find the detail pane containers
            detail_container = self.query_one("#detail-pane-container")

            if show_detail:
                detail_container.remove_class("hidden")
                detail_container.add_class("visible")
                log.debug("Detail pane shown")
            else:
                detail_container.add_class("hidden")
                detail_container.remove_class("visible")
                log.debug("Detail pane hidden")

        except Exception as e:
            # Widget may not be ready during initialization
            log.debug("Could not toggle detail pane visibility", error=str(e))

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
