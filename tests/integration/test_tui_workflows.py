#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Integration tests for complete TUI user workflows.

These tests simulate real user interactions and workflows to ensure
the TUI functions correctly for end-to-end scenarios."""

from __future__ import annotations

import asyncio
from pathlib import Path

from provide.testkit.mocking import AsyncMock, Mock
import pytest
from textual.widgets import DataTable, TabbedContent

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
def mock_app_setup():
    """Setup proper mocks for the TUI app to avoid common issues."""

    def setup_app(app: SupsrcTuiApp) -> tuple[Mock, Mock]:
        # Better mocking for event collector
        mock_event_collector = Mock()
        mock_event_collector._handlers = []  # Empty list for len() call
        mock_event_collector.emit = Mock()
        app.event_collector = mock_event_collector

        # Mock orchestrator with proper attributes
        mock_orchestrator = Mock()
        mock_orchestrator._is_paused = False
        mock_orchestrator._is_suspended = False
        mock_orchestrator.repo_states = {}  # Empty dict for iteration
        app._orchestrator = mock_orchestrator

        return mock_event_collector, mock_orchestrator

    return setup_app


@pytest.fixture
def sample_repo_states() -> dict[str, RepositoryState]:
    """Create sample repository states for testing."""
    state1 = RepositoryState(repo_id="project-alpha")
    state1.last_change_time = None
    state1.rule_emoji = "⏳"
    state1.rule_dynamic_indicator = "30s"
    state1.action_description = None
    state1.last_commit_short_hash = "abc123"
    state1.last_commit_message_summary = "Add new feature"
    state1.has_uncommitted_changes = True
    state1.current_branch = "main"
    state1.total_files = 150
    state1.changed_files = 5
    state1.added_files = 2
    state1.deleted_files = 1
    state1.modified_files = 2
    state1.timer_seconds_left = 30
    state1.is_paused = False

    state2 = RepositoryState(repo_id="project-beta")
    state2.display_status_emoji = "🔄"
    state2.current_branch = "feature/authentication"
    state2.total_files = 75
    state2.changed_files = 3
    state2.timer_seconds_left = 15
    state2.rule_dynamic_indicator = "15s"
    state2.last_commit_short_hash = "def456"
    state2.last_commit_message_summary = "Update auth system"
    state2.is_paused = False

    state3 = RepositoryState(repo_id="project-gamma")
    state3.display_status_emoji = "⏸️"
    state3.current_branch = "develop"
    state3.total_files = 200
    state3.changed_files = 0
    state3.timer_seconds_left = 0
    state3.is_paused = True

    return {
        "project-alpha": state1,
        "project-beta": state2,
        "project-gamma": state3,
    }


class TestTuiUserWorkflows:
    """Integration tests for complete user workflows."""

    @pytest.mark.asyncio
    async def test_complete_repository_monitoring_workflow(
        self,
        mock_app_setup,
        mock_config_path: Path,
        mock_shutdown_event: asyncio.Event,
        sample_repo_states: dict[str, RepositoryState],
    ) -> None:
        """Test a complete workflow of monitoring repositories."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        mock_app_setup(app)

        async with app.run_test() as pilot:
            # 1. Start with empty app
            table = app.query_one("#repository_table", DataTable)
            assert table.row_count == 0

            # 2. Add repository data (simulates orchestrator providing data)
            from supsrc.tui.messages import StateUpdate

            app.post_message(StateUpdate(sample_repo_states))
            await pilot.pause()

            # 3. Verify repositories are displayed
            assert table.row_count == 3

            # 4. Navigate to first repository
            table.focus()
            await pilot.pause()

            # 5. Select repository for details
            await pilot.press("enter")
            await pilot.pause()

            # Should have selected a repository
            assert app.selected_repo_id is not None

            # 6. View repository details
            await pilot.press("tab")  # Navigate to info section
            await pilot.pause()

            # 7. Switch to details tab
            tabbed_content = app.query_one(TabbedContent)
            assert tabbed_content.active in ["events-tab", "details-tab", "about-tab"]

            # 8. Check help functionality
            await pilot.press("h")
            await pilot.pause()

            # Should have emitted help event
            app.event_collector.emit.assert_called()

            # 9. Clear log
            await pilot.press("ctrl+l")
            await pilot.pause()

            # Should have emitted clear event
            assert any(call[0][0].action == "clear_feed" for call in app.event_collector.emit.call_args_list)

    @pytest.mark.asyncio
    async def test_monitoring_control_workflow(
        self,
        mock_config_path: Path,
        mock_shutdown_event: asyncio.Event,
        sample_repo_states: dict[str, RepositoryState],
    ) -> None:
        """Test pausing and resuming monitoring."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()

        # Mock orchestrator
        mock_orchestrator = Mock()
        mock_orchestrator._is_paused = False
        mock_orchestrator._is_suspended = False
        app._orchestrator = mock_orchestrator

        async with app.run_test() as pilot:
            # Add repository data
            from supsrc.tui.messages import StateUpdate

            app.post_message(StateUpdate(sample_repo_states))
            await pilot.pause()

            # 1. Pause all monitoring
            await pilot.press("p")
            await pilot.pause()

            # Should have called pause on orchestrator
            mock_orchestrator.pause_monitoring.assert_called_once()

            # 2. Resume monitoring (press 'p' again)
            mock_orchestrator._is_paused = True  # Simulate paused state
            await pilot.press("p")
            await pilot.pause()

            # Should have called resume on orchestrator
            mock_orchestrator.resume_monitoring.assert_called_once()

            # 3. Suspend monitoring (stronger than pause)
            await pilot.press("s")
            await pilot.pause()

            # Should have called suspend on orchestrator
            mock_orchestrator.suspend_monitoring.assert_called_once()

            # 4. Resume from suspension
            mock_orchestrator._is_suspended = True  # Simulate suspended state
            await pilot.press("s")
            await pilot.pause()

            # Should have called resume again
            assert mock_orchestrator.resume_monitoring.call_count == 2

    @pytest.mark.asyncio
    async def test_repository_selection_and_navigation_workflow(
        self,
        mock_config_path: Path,
        mock_shutdown_event: asyncio.Event,
        sample_repo_states: dict[str, RepositoryState],
    ) -> None:
        """Test selecting repositories and navigating between them."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()
        app._update_repo_details_tab = Mock()

        async with app.run_test() as pilot:
            # Add repository data
            from supsrc.tui.messages import StateUpdate

            app.post_message(StateUpdate(sample_repo_states))
            await pilot.pause()

            table = app.query_one("#repository_table", DataTable)

            # 1. Focus table and select first repository
            table.focus()
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()

            first_selected = app.selected_repo_id
            assert first_selected is not None

            # 2. Navigate to different repository using arrow keys
            await pilot.press("down")
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()

            second_selected = app.selected_repo_id
            # Should have selected a different repository
            assert second_selected != first_selected

            # 3. Clear selection with Escape
            await pilot.press("escape")
            await pilot.pause()

            assert app.selected_repo_id is None

            # 4. Navigate through tabs
            await pilot.press("tab")  # Move to info section
            await pilot.pause()

            # Try to switch between tabs (if focused on tab bar)
            await pilot.press("left")
            await pilot.press("right")
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_configuration_reload_workflow(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test configuration reload workflow."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()
        app.run_worker = Mock()

        # Mock orchestrator
        mock_orchestrator = AsyncMock()
        mock_orchestrator.reload_config.return_value = True
        app._orchestrator = mock_orchestrator

        async with app.run_test() as pilot:
            # 1. Trigger config reload
            await pilot.press("c")
            await pilot.pause()

            # Should have started config reload worker
            app.run_worker.assert_called_once()

            # Should have emitted start event
            app.event_collector.emit.assert_called()
            call_args = app.event_collector.emit.call_args[0][0]
            assert call_args.action == "reload_config_start"

    @pytest.mark.asyncio
    async def test_dark_mode_toggle_workflow(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test dark mode toggle workflow."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async with app.run_test() as pilot:
            # Get initial theme
            initial_theme = getattr(app, "theme", "textual-dark")

            # 1. Toggle dark mode
            await pilot.press("d")
            await pilot.pause()

            # Theme should have changed
            current_theme = getattr(app, "theme", "textual-dark")
            assert current_theme != initial_theme

            # 2. Toggle again to return to original
            await pilot.press("d")
            await pilot.pause()

            # Should be back to original theme
            final_theme = getattr(app, "theme", "textual-dark")
            assert final_theme == initial_theme

    @pytest.mark.asyncio
    async def test_event_feed_interaction_workflow(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test interacting with the event feed."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()

        async with app.run_test() as pilot:
            # 1. Add log messages to event feed
            from supsrc.tui.messages import LogMessageUpdate

            app.post_message(LogMessageUpdate("Repository monitoring started", "INFO"))
            app.post_message(LogMessageUpdate("File change detected", "DEBUG"))
            app.post_message(LogMessageUpdate("Git commit successful", "INFO"))
            await pilot.pause()

            # 2. Navigate to events tab (should be default)
            tabbed_content = app.query_one(TabbedContent)
            tabbed_content.active = "events-tab"
            await pilot.pause()

            # 3. Clear the event feed
            await pilot.press("ctrl+l")
            await pilot.pause()

            # Should have emitted clear event
            app.event_collector.emit.assert_called()

    @pytest.mark.asyncio
    async def test_error_recovery_workflow(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test that the app recovers gracefully from errors."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()

        async with app.run_test() as pilot:
            # 1. Simulate rapid interactions that might cause errors
            rapid_actions = ["h", "d", "ctrl+l", "tab", "escape", "enter"]

            for action in rapid_actions:
                await pilot.press(action)
                # Don't pause between actions to test rapid input handling

            await pilot.pause()

            # App should still be responsive
            await pilot.press("h")  # Help should still work
            await pilot.pause()

            # Should have received help event
            app.event_collector.emit.assert_called()

    @pytest.mark.asyncio
    async def test_shutdown_workflow(self, mock_config_path: Path, mock_shutdown_event: asyncio.Event) -> None:
        """Test proper application shutdown."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        # Mock timer manager
        app.timer_manager = Mock()
        app.timer_manager.stop_all_timers = Mock()

        async with app.run_test() as pilot:
            # Normal operation
            await pilot.pause()

            # Test shutdown via quit action (not via key press as it would exit the test)
            app.action_quit()

            # Should have set shutdown event
            assert mock_shutdown_event.is_set()

            # Should have stopped timers
            app.timer_manager.stop_all_timers.assert_called_once()

    @pytest.mark.asyncio
    async def test_keyboard_shortcuts_comprehensive(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test all keyboard shortcuts work correctly."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        app.event_collector = Mock()

        # Mock orchestrator for monitoring controls
        mock_orchestrator = Mock()
        mock_orchestrator._is_paused = False
        mock_orchestrator._is_suspended = False
        app._orchestrator = mock_orchestrator

        async with app.run_test() as pilot:
            # Test all major keyboard shortcuts
            shortcuts_to_test = [
                "h",  # Help
                "d",  # Toggle dark mode
                "ctrl+l",  # Clear log
                "p",  # Pause monitoring
                "s",  # Suspend monitoring
                "tab",  # Focus next
                "shift+tab",  # Focus previous
            ]

            for shortcut in shortcuts_to_test:
                await pilot.press(shortcut)
                await pilot.pause()

            # All shortcuts should have been processed without errors
            # (exact verification depends on mock calls)
            assert app.event_collector.emit.call_count > 0


# 🔼⚙️🔚
