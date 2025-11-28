#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for TUI accessibility and usability features."""

import asyncio
from pathlib import Path

import pytest
from provide.testkit.mocking import Mock

pytestmark = pytest.mark.skip(reason="TUI in active development")
from supsrc.tui.app import SupsrcTuiApp  # noqa: E402


class TestTuiAccessibility:
    """Test TUI accessibility and usability features."""

    def test_keyboard_bindings(self, mock_config_path: Path, mock_shutdown_event: asyncio.Event) -> None:
        """Test that all keyboard bindings are properly defined."""
        tui_app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        bindings = {binding[0]: binding[1] for binding in tui_app.BINDINGS}

        expected_bindings = {
            "d": "toggle_dark",
            "q": "quit",
            "ctrl+c": "quit",
            "ctrl+l": "clear_log",
            "enter": "select_repo_for_detail",
            "escape": "hide_detail_pane",
            "r": "refresh_details",
            "p": "pause_monitoring",
            "s": "suspend_monitoring",
            "c": "reload_config",
            "h": "show_help",
        }

        for key, action in expected_bindings.items():
            assert key in bindings
            assert bindings[key] == action

    def test_widget_focus_management(self, mock_config_path: Path, mock_shutdown_event: asyncio.Event) -> None:
        """Test proper focus management between widgets."""
        tui_app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        mock_table = Mock()
        tui_app.query_one = Mock(return_value=mock_table)

        tui_app.show_detail_pane = True
        tui_app.action_hide_detail_pane()

        mock_table.focus.assert_called_once()


# 🔼⚙️🔚
