#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Visual regression tests using pytest-textual-snapshot.

These tests capture SVG screenshots of the TUI and compare them against
previous runs to catch visual regressions automatically."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from supsrc.state import RepositoryState
from supsrc.tui.app import SupsrcTuiApp

pytestmark = pytest.mark.skip(reason="TUI in active development")


@pytest.fixture
def mock_config_path() -> Path:
    """Mock configuration path for TUI testing."""
    return Path("/mock/config.conf")


@pytest.fixture
def mock_shutdown_event() -> asyncio.Event:
    """Mock shutdown event for TUI testing."""
    return asyncio.Event()


@pytest.fixture
def sample_repo_states() -> dict[str, RepositoryState]:
    """Create sample repository states for testing."""
    state1 = RepositoryState(repo_id="test-repo-1")
    state1.last_change_time = None
    state1.rule_emoji = "⏳"
    state1.rule_dynamic_indicator = "25s"
    state1.action_description = None
    state1.last_commit_short_hash = "abc123"
    state1.last_commit_message_summary = "Initial commit"
    state1.has_uncommitted_changes = True
    state1.current_branch = "main"
    state1.total_files = 42
    state1.changed_files = 3
    state1.added_files = 1
    state1.deleted_files = 1
    state1.modified_files = 1
    state1.timer_seconds_left = 25

    state2 = RepositoryState(repo_id="test-repo-2")
    state2.display_status_emoji = "🔄"
    state2.current_branch = "feature/test"
    state2.total_files = 15
    state2.changed_files = 0
    state2.timer_seconds_left = 10
    state2.rule_dynamic_indicator = "10s"
    state2.last_commit_short_hash = "def456"
    state2.last_commit_message_summary = "Add new feature"

    return {"test-repo-1": state1, "test-repo-2": state2}


class TestTuiSnapshots:
    """Visual regression tests using snapshot testing."""

    def test_empty_app_layout(
        self, snap_compare, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test the visual layout of an empty application."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        # Snapshot the empty app layout
        assert snap_compare(app)

    def test_app_with_repository_data(
        self,
        snap_compare,
        mock_config_path: Path,
        mock_shutdown_event: asyncio.Event,
        sample_repo_states: dict[str, RepositoryState],
    ) -> None:
        """Test the visual layout with repository data displayed."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async def setup_data(pilot):
            """Setup the app with test data."""
            # Add repository data to the app
            from supsrc.tui.messages import StateUpdate

            app.post_message(StateUpdate(sample_repo_states))
            # Give time for the update to process
            await pilot.pause()

        # Run the app with data and take snapshot
        assert snap_compare(app, run_before=setup_data)

    def test_app_with_events_tab_active(
        self, snap_compare, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test the visual layout with events tab active."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async def add_log_messages(pilot):
            """Add some log messages to the event feed."""
            from supsrc.tui.messages import LogMessageUpdate

            # Add a few different types of log messages
            app.post_message(LogMessageUpdate("Repository monitoring started", "INFO"))
            app.post_message(LogMessageUpdate("File change detected", "DEBUG"))
            app.post_message(LogMessageUpdate("Git commit successful", "INFO"))
            app.post_message(LogMessageUpdate("Timer started for repository", "DEBUG"))

            # Give time for messages to be displayed
            await pilot.pause()

        # Snapshot with event feed populated
        assert snap_compare(app, run_before=add_log_messages)

    def test_app_with_details_tab_active(
        self,
        snap_compare,
        mock_config_path: Path,
        mock_shutdown_event: asyncio.Event,
        sample_repo_states: dict[str, RepositoryState],
    ) -> None:
        """Test the visual layout with details tab active and a repository selected."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async def select_repository(pilot):
            """Setup data and select a repository."""
            from supsrc.tui.messages import StateUpdate

            # Add repository data
            app.post_message(StateUpdate(sample_repo_states))

            # Select a repository (this would normally be done through UI interaction)
            app.selected_repo_id = "test-repo-1"

            # Switch to details tab
            tabbed_content = app.query_one("TabbedContent")
            tabbed_content.active = "details-tab"

            # Give time for the update to process
            await pilot.pause()

        # Snapshot with repository selected and details tab active
        assert snap_compare(app, run_before=select_repository)

    def test_app_with_about_tab_active(
        self, snap_compare, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test the visual layout with about tab active."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async def switch_to_about(pilot):
            """Switch to the about tab."""
            tabbed_content = app.query_one("TabbedContent")
            tabbed_content.active = "about-tab"
            await pilot.pause()

        # Snapshot with about tab active
        assert snap_compare(app, run_before=switch_to_about)

    def test_app_layout_responsiveness_small(
        self, snap_compare, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test app layout at a smaller terminal size."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        # Test at a smaller terminal size (80x24 is traditional small terminal)
        assert snap_compare(app, terminal_size=(80, 24))

    def test_app_layout_responsiveness_large(
        self, snap_compare, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test app layout at a larger terminal size."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        # Test at a larger terminal size
        assert snap_compare(app, terminal_size=(120, 40))

    def test_app_with_many_repositories(
        self, snap_compare, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test the visual layout with many repositories to test scrolling."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async def add_many_repositories(pilot):
            """Add many repositories to test table scrolling."""
            states = {}
            for i in range(10):
                state = RepositoryState(repo_id=f"repo-{i:02d}")
                state.current_branch = "main" if i % 3 == 0 else f"feature/branch-{i}"
                state.total_files = 10 + i * 5
                state.changed_files = i % 4
                state.timer_seconds_left = 30 - i
                state.rule_dynamic_indicator = f"{30 - i}s"
                state.last_commit_short_hash = f"abc{i:03d}"
                state.last_commit_message_summary = f"Commit message {i}"
                states[f"repo-{i:02d}"] = state

            from supsrc.tui.messages import StateUpdate

            app.post_message(StateUpdate(states))
            await pilot.pause()

        # Snapshot with many repositories
        assert snap_compare(app, run_before=add_many_repositories)

    def test_app_dark_mode_toggle(
        self, snap_compare, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test the visual appearance after toggling dark mode."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async def toggle_dark_mode(pilot):
            """Toggle dark mode and add some data."""
            # Toggle dark mode (this simulates pressing 'd')
            app.action_toggle_dark()

            # Add some data to see the visual difference
            state = RepositoryState(repo_id="sample-repo")
            state.current_branch = "main"
            state.total_files = 25
            state.timer_seconds_left = 15

            from supsrc.tui.messages import StateUpdate

            app.post_message(StateUpdate({"sample-repo": state}))
            await pilot.pause()

        # Snapshot with dark mode toggled
        assert snap_compare(app, run_before=toggle_dark_mode)


# 🔼⚙️🔚
