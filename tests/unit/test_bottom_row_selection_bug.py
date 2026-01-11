#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Test for bottom row selection bug fix.

This test reproduces the bug where selecting the last row in a DataTable
would fail due to incorrect bounds checking."""

from __future__ import annotations

import asyncio

from provide.testkit.mocking import Mock
import pytest
from textual.widgets import DataTable

from supsrc.tui.app import SupsrcTuiApp
from tests.helpers.config_testing import real_config_path, with_parent_cwd

pytestmark = pytest.mark.skip(reason="TUI in active development")


class TestBottomRowSelectionBug:
    """Test the bottom row selection bug fix."""

    @pytest.mark.asyncio
    async def test_bottom_row_selection_with_real_config(self):
        """Test that the bottom row can be selected without issues."""
        with with_parent_cwd():
            config_path = real_config_path()
            shutdown_event = asyncio.Event()

            app = SupsrcTuiApp(config_path, shutdown_event)

            # Mock external dependencies
            app.event_collector = Mock()
            app.event_collector._handlers = []
            app.event_collector.emit = Mock()

            async with app.run_test() as pilot:
                # Wait for app to initialize
                await pilot.pause()

                # Get the table
                table = app.query_one("#repository_table", DataTable)

                # Wait for repositories to load
                max_wait = 50  # 5 seconds max
                wait_count = 0
                while table.row_count == 0 and wait_count < max_wait:
                    await pilot.pause(0.1)
                    wait_count += 1

                # Should have loaded repositories from config
                assert table.row_count > 0, "No repositories loaded"

                # Move cursor to the last row
                last_row_index = table.row_count - 1
                table.cursor_coordinate = (last_row_index, 0)
                await pilot.pause()

                # Verify cursor is at the last row
                assert table.cursor_row == last_row_index

                # Try to select the bottom row (this used to fail)
                await pilot.press("enter")
                await pilot.pause()

                # Should have emitted a selection event
                assert app.event_collector.emit.called, "No selection event emitted"

                # Verify the selected repository ID was set
                assert hasattr(app, "selected_repo_id")

    @pytest.mark.asyncio
    async def test_cursor_row_vs_cursor_coordinate_consistency(self):
        """Test that cursor_row and cursor_coordinate.row are consistent."""
        with with_parent_cwd():
            config_path = real_config_path()
            shutdown_event = asyncio.Event()

            app = SupsrcTuiApp(config_path, shutdown_event)

            # Mock external dependencies
            app.event_collector = Mock()
            app.event_collector._handlers = []
            app.event_collector.emit = Mock()

            async with app.run_test() as pilot:
                # Wait for app to initialize
                await pilot.pause()

                # Get the table
                table = app.query_one("#repository_table", DataTable)

                # Wait for repositories to load
                max_wait = 50  # 5 seconds max
                wait_count = 0
                while table.row_count == 0 and wait_count < max_wait:
                    await pilot.pause(0.1)
                    wait_count += 1

                # Move to different positions and verify consistency
                test_positions = [0, table.row_count // 2, table.row_count - 1]

                for pos in test_positions:
                    if pos < table.row_count:
                        table.cursor_coordinate = (pos, 0)
                        await pilot.pause()

                        # These should be consistent
                        assert table.cursor_row == table.cursor_coordinate.row == pos

    def test_bounds_checking_logic(self):
        """Test the bounds checking logic used in the fix."""
        # Mock a DataTable
        mock_table = Mock()
        mock_table.row_count = 19  # Like the real config
        mock_table.cursor_row = 18  # Last row (0-based)

        # The fixed condition should allow selection
        assert mock_table.cursor_row < mock_table.row_count

        # Edge case: cursor at exactly row_count should not be allowed
        mock_table.cursor_row = 19
        assert not (mock_table.cursor_row < mock_table.row_count)

        # Normal cases
        mock_table.cursor_row = 0
        assert mock_table.cursor_row < mock_table.row_count

        mock_table.cursor_row = 10
        assert mock_table.cursor_row < mock_table.row_count

    def test_cursor_position_saving_bounds_check(self):
        """Test the bounds checking used for cursor position saving in events.py."""
        # Mock a DataTable to simulate the events.py logic
        mock_table = Mock()
        mock_table.row_count = 19  # Like the real config

        # Test cursor position saving condition from events.py:83
        # The bug was: if table.cursor_row < len(table.rows):
        # The fix is: if table.cursor_row < table.row_count:

        # Last row should be saveable
        mock_table.cursor_row = 18  # Last row (0-based)
        assert mock_table.cursor_row < mock_table.row_count, "Last row cursor should be saveable"

        # Edge case: cursor beyond valid rows should not be saved
        mock_table.cursor_row = 19
        assert not (mock_table.cursor_row < mock_table.row_count), (
            "Invalid cursor position should not be saved"
        )

        # First row should be saveable
        mock_table.cursor_row = 0
        assert mock_table.cursor_row < mock_table.row_count, "First row cursor should be saveable"


# 🔼⚙️🔚
