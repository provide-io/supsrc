#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Pilot-based TUI tests using Textual's built-in testing framework.

These tests use app.run_test() to run the TUI in headless mode and interact
with it using the Pilot object, providing a "virtual browser" experience."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from provide.testkit.mocking import AsyncMock, Mock
from textual.widgets import DataTable

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
    state1 = RepositoryState(repo_id="repo1")
    state1.last_change_time = None
    state1.rule_emoji = "⏳"
    state1.rule_dynamic_indicator = "Waiting"
    state1.action_description = None
    state1.last_commit_short_hash = "abc123"
    state1.last_commit_message_summary = "Test commit"
    state1.has_uncommitted_changes = True
    state1.current_branch = "main"
    state1.total_files = 100
    state1.changed_files = 5
    state1.added_files = 2
    state1.deleted_files = 1
    state1.modified_files = 2
    state1.timer_seconds_left = 25

    state2 = RepositoryState(repo_id="repo2")
    state2.display_status_emoji = "🔄"
    state2.current_branch = "feature/test"
    state2.total_files = 50
    state2.changed_files = 0
    state2.timer_seconds_left = 10

    return {"repo1": state1, "repo2": state2}


class TestTuiPilotBasic:
    """Basic TUI functionality tests using Pilot."""

    @pytest.mark.asyncio
    async def test_app_initialization_and_layout(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test that the app initializes properly and has the expected layout."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async with app.run_test() as pilot:
            await pilot.pause()  # Let the app initialize
            # Check that the main widgets are present
            assert app.query_one("#repository_table", DataTable) is not None
            assert app.query_one("#event-feed") is not None

            # Check that the table has the expected columns
            table = app.query_one("#repository_table", DataTable)
            assert len(table.columns) == 11  # Expected number of columns

            # Verify tab structure
            assert app.query_one("#events-tab") is not None
            assert app.query_one("#details-tab") is not None
            assert app.query_one("#about-tab") is not None

    @pytest.mark.asyncio
    async def test_keyboard_navigation(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test basic keyboard navigation."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async with app.run_test() as pilot:
            # Test tab navigation
            await pilot.press("tab")
            await pilot.pause()

            # Test focus changes (should not crash)
            await pilot.press("shift+tab")
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_help_action(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test the help action."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()

        async with app.run_test() as pilot:
            # Press 'h' to show help
            await pilot.press("h")
            await pilot.pause()

            # Verify that help event was emitted
            app.event_collector.emit.assert_called()
            call_args = app.event_collector.emit.call_args[0][0]
            assert call_args.action == "show_help"
            assert "Keyboard Shortcuts" in call_args.description


class TestTuiPilotStateUpdates:
    """Test state updates and data display using Pilot."""

    @pytest.mark.asyncio
    async def test_repository_table_updates(
        self,
        mock_config_path: Path,
        mock_shutdown_event: asyncio.Event,
        sample_repo_states: dict[str, RepositoryState],
    ) -> None:
        """Test that repository table updates correctly with state data."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async with app.run_test() as pilot:
            table = app.query_one("#repository_table", DataTable)

            # Initially empty
            assert table.row_count == 0

            # Simulate state update
            from supsrc.tui.messages import StateUpdate

            app.post_message(StateUpdate(sample_repo_states))
            await pilot.pause()

            # Should now have rows for each repository
            assert table.row_count == 2

            # Check that data is displayed (get first row)
            if table.row_count > 0:
                row_data = table.get_row_at(0)
                # Should contain repo data
                assert any("repo" in str(cell) for cell in row_data)

    @pytest.mark.asyncio
    async def test_event_feed_updates(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test that event feed receives and displays log messages."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async with app.run_test() as pilot:
            event_feed = app.query_one("#event-feed")

            # Send a log message
            from supsrc.tui.messages import LogMessageUpdate

            test_message = LogMessageUpdate("Test message", "INFO")
            app.post_message(test_message)
            await pilot.pause()

            # Event feed should have received the message
            # (The exact verification depends on EventFeed implementation)
            assert event_feed is not None

    @pytest.mark.asyncio
    async def test_clear_log_action(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test the clear log action using keyboard shortcut."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()

        async with app.run_test() as pilot:
            # Press Ctrl+L to clear log
            await pilot.press("ctrl+l")
            await pilot.pause()

            # Verify that clear event was emitted
            app.event_collector.emit.assert_called()
            call_args = app.event_collector.emit.call_args[0][0]
            assert call_args.action == "clear_feed"


class TestTuiPilotRepositorySelection:
    """Test repository selection and detail pane functionality."""

    @pytest.mark.asyncio
    async def test_repository_selection(
        self,
        mock_config_path: Path,
        mock_shutdown_event: asyncio.Event,
        sample_repo_states: dict[str, RepositoryState],
    ) -> None:
        """Test selecting a repository for detail view."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()
        app._update_repo_details_tab = Mock()

        async with app.run_test() as pilot:
            # Add some data to the table first
            from supsrc.tui.messages import StateUpdate

            app.post_message(StateUpdate(sample_repo_states))
            await pilot.pause()

            # Focus the repository table
            table = app.query_one("#repository_table", DataTable)
            table.focus()
            await pilot.pause()

            # Press Enter to select repository
            await pilot.press("enter")
            await pilot.pause()

            # Should have selected a repository
            assert app.selected_repo_id is not None

            # Should have emitted selection event
            if app.event_collector.emit.called:
                call_args = app.event_collector.emit.call_args[0][0]
                assert call_args.action == "select_repository"

    @pytest.mark.asyncio
    async def test_hide_detail_pane(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test hiding the detail pane with Escape key."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()
        app.selected_repo_id = "test-repo"

        async with app.run_test() as pilot:
            # Press Escape to hide detail pane
            await pilot.press("escape")
            await pilot.pause()

            # Should have cleared selection
            assert app.selected_repo_id is None

            # Should have emitted clear selection event
            app.event_collector.emit.assert_called()
            call_args = app.event_collector.emit.call_args[0][0]
            assert call_args.action == "clear_selection"


class TestTuiPilotMonitoringControls:
    """Test monitoring control actions."""

    @pytest.mark.asyncio
    async def test_pause_monitoring_action(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test pause/resume monitoring action."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()

        # Mock orchestrator
        mock_orchestrator = Mock()
        mock_orchestrator._is_paused = False
        app._orchestrator = mock_orchestrator

        async with app.run_test() as pilot:
            # Press 'p' to pause monitoring
            await pilot.press("p")
            await pilot.pause()

            # Should have called pause on orchestrator
            mock_orchestrator.pause_monitoring.assert_called_once()

            # Should have emitted pause event
            app.event_collector.emit.assert_called()
            call_args = app.event_collector.emit.call_args[0][0]
            assert call_args.action == "pause_monitoring"

    @pytest.mark.asyncio
    async def test_suspend_monitoring_action(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test suspend/resume monitoring action."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()

        # Mock orchestrator
        mock_orchestrator = Mock()
        mock_orchestrator._is_suspended = False
        app._orchestrator = mock_orchestrator

        async with app.run_test() as pilot:
            # Press 's' to suspend monitoring
            await pilot.press("s")
            await pilot.pause()

            # Should have called suspend on orchestrator
            mock_orchestrator.suspend_monitoring.assert_called_once()

            # Should have emitted suspend event
            app.event_collector.emit.assert_called()
            call_args = app.event_collector.emit.call_args[0][0]
            assert call_args.action == "suspend_monitoring"


class TestTuiPilotAsyncOperations:
    """Test async operations and worker handling."""

    @pytest.mark.asyncio
    async def test_config_reload_action(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test config reload action."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()
        app.run_worker = Mock()

        # Mock orchestrator
        mock_orchestrator = AsyncMock()
        mock_orchestrator.reload_config.return_value = True
        app._orchestrator = mock_orchestrator

        async with app.run_test() as pilot:
            # Press 'c' to reload config
            await pilot.press("c")
            await pilot.pause()

            # Should have started config reload worker
            app.run_worker.assert_called_once()

            # Should have emitted start event
            app.event_collector.emit.assert_called()
            call_args = app.event_collector.emit.call_args[0][0]
            assert call_args.action == "reload_config_start"

    @pytest.mark.asyncio
    async def test_app_shutdown_handling(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test proper app shutdown."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        # Mock timer manager
        app.timer_manager = Mock()
        app.timer_manager.stop_all_timers = Mock()

        async with app.run_test() as pilot:
            # Test that app can be created and shutdown cleanly
            await pilot.pause()

            # Manually trigger quit action
            app.action_quit()

            # Should have set shutdown event
            assert mock_shutdown_event.is_set()

            # Should have stopped timers
            app.timer_manager.stop_all_timers.assert_called_once()


class TestTuiPilotErrorHandling:
    """Test error handling and resilience."""

    @pytest.mark.asyncio
    async def test_missing_widgets_handling(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test that the app handles missing widgets gracefully."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async with app.run_test() as pilot:
            # App should initialize even if some widgets aren't found
            # (This tests overall resilience)
            await pilot.pause()

            # Try pressing keys that might cause widget lookups
            await pilot.press("h")  # Help
            await pilot.press("escape")  # Hide detail
            await pilot.pause()

            # App should still be running
            assert not app.is_headless  # App should still be active in test mode

    @pytest.mark.asyncio
    async def test_rapid_key_presses(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test handling of rapid key presses."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()

        async with app.run_test() as pilot:
            # Send rapid key presses
            for _ in range(5):
                await pilot.press("h")

            await pilot.pause()

            # App should handle all events without crashing
            # event_collector should have been called multiple times
            assert app.event_collector.emit.call_count >= 5


# 🔼⚙️🔚
