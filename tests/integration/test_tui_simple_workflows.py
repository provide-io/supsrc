#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Simple integration tests for TUI user workflows.

These tests focus on basic user interactions that work reliably."""

from __future__ import annotations

import asyncio
from pathlib import Path

from provide.testkit.mocking import Mock
import pytest

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


class TestSimpleTuiWorkflows:
    """Simple integration tests for TUI workflows."""

    @pytest.mark.asyncio
    async def test_app_startup_and_basic_navigation(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test basic app startup and navigation."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        # Setup minimal mocking to avoid errors
        mock_event_collector = Mock()
        mock_event_collector._handlers = []
        mock_event_collector.emit = Mock()
        app.event_collector = mock_event_collector

        async with app.run_test() as pilot:
            # App should start successfully
            await pilot.pause()

            # Basic navigation should work
            await pilot.press("tab")
            await pilot.pause()

            await pilot.press("shift+tab")
            await pilot.pause()

            # Help should work
            await pilot.press("h")
            await pilot.pause()

            # Should have emitted help event
            mock_event_collector.emit.assert_called()

    @pytest.mark.asyncio
    async def test_dark_mode_toggle(self, mock_config_path: Path, mock_shutdown_event: asyncio.Event) -> None:
        """Test dark mode toggle functionality."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async with app.run_test() as pilot:
            # Get initial theme
            initial_theme = getattr(app, "theme", "textual-dark")

            # Toggle dark mode
            await pilot.press("d")
            await pilot.pause()

            # Theme should have changed
            current_theme = getattr(app, "theme", "textual-dark")
            assert current_theme != initial_theme

    @pytest.mark.asyncio
    async def test_clear_log_action(self, mock_config_path: Path, mock_shutdown_event: asyncio.Event) -> None:
        """Test clear log action."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        # Setup event collector mock
        mock_event_collector = Mock()
        mock_event_collector._handlers = []
        mock_event_collector.emit = Mock()
        app.event_collector = mock_event_collector

        async with app.run_test() as pilot:
            # Clear log action
            await pilot.press("ctrl+l")
            await pilot.pause()

            # Should have emitted clear event
            mock_event_collector.emit.assert_called()

    @pytest.mark.asyncio
    async def test_keyboard_shortcuts_basic(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test basic keyboard shortcuts work without crashing."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        # Setup minimal mocking
        mock_event_collector = Mock()
        mock_event_collector._handlers = []
        mock_event_collector.emit = Mock()
        app.event_collector = mock_event_collector

        async with app.run_test() as pilot:
            # Test shortcuts that should not cause errors
            shortcuts = ["h", "d", "ctrl+l", "tab", "escape"]

            for shortcut in shortcuts:
                await pilot.press(shortcut)
                await pilot.pause()

            # App should still be responsive
            await pilot.press("h")
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_widget_focus_and_interaction(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test widget focus and basic interactions."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        async with app.run_test() as pilot:
            # Should be able to query main widgets
            table = app.query_one("#repository_table")
            assert table is not None

            event_feed = app.query_one("#event-feed")
            assert event_feed is not None

            # Focus should work
            table.focus()
            await pilot.pause()

            # Tab navigation should work
            await pilot.press("tab")
            await pilot.pause()

    @pytest.mark.asyncio
    async def test_app_shutdown_cleanup(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test that app shuts down cleanly."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        # Mock timer manager
        app.timer_manager = Mock()
        app.timer_manager.stop_all_timers = Mock()

        async with app.run_test() as pilot:
            await pilot.pause()

            # Test quit action (not via key as it would exit)
            app.action_quit()

            # Should have set shutdown event
            assert mock_shutdown_event.is_set()

            # Should have stopped timers
            app.timer_manager.stop_all_timers.assert_called_once()

    @pytest.mark.asyncio
    async def test_rapid_key_presses_stability(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test that rapid key presses don't crash the app."""
        app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        # Setup minimal mocking
        mock_event_collector = Mock()
        mock_event_collector._handlers = []
        mock_event_collector.emit = Mock()
        app.event_collector = mock_event_collector

        async with app.run_test() as pilot:
            # Rapid key presses
            for _ in range(5):
                await pilot.press("h")
                await pilot.press("d")
                await pilot.press("tab")

            await pilot.pause()

            # App should still be responsive
            await pilot.press("h")
            await pilot.pause()

            # Should have handled multiple events
            assert mock_event_collector.emit.call_count > 0


# 🔼⚙️🔚
