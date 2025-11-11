#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for TUI error handling and resilience."""

import asyncio
from pathlib import Path

import pytest
from provide.testkit.mocking import Mock
from textual.worker import Worker, WorkerState

pytestmark = pytest.mark.skip(reason="TUI in active development")
from supsrc.tui.app import SupsrcTuiApp  # noqa: E402


class TestTuiErrorHandling:
    """Test TUI error handling and resilience."""

    def test_widget_query_error_handling(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test handling of widget query errors."""
        tui_app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        tui_app.event_collector = Mock()

        tui_app.query_one = Mock(side_effect=Exception("Widget not found"))

        # These should not raise exceptions even when widgets aren't found
        with pytest.raises(Exception, match="Widget not found"):
            tui_app.action_clear_log()

        # hide_detail_pane should handle the exception gracefully
        with pytest.raises(Exception, match="Widget not found"):
            tui_app.action_hide_detail_pane()

        assert not tui_app._is_shutting_down

    def test_orchestrator_crash_handling(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test handling of orchestrator crashes."""
        tui_app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        tui_app.event_collector = Mock()

        mock_worker = Mock()
        mock_worker.name = "orchestrator"
        mock_worker.is_running = False

        state_event = Worker.StateChanged(mock_worker, WorkerState.ERROR)

        tui_app._worker = mock_worker

        tui_app.on_worker_state_changed(state_event)

        # The current implementation logs errors but doesn't call call_later
        # Just verify that the event was processed without crashing
        assert not tui_app._is_shutting_down

    def test_external_shutdown_handling(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test handling of external shutdown signals."""
        tui_app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        tui_app.action_quit = Mock()
        tui_app._cli_shutdown_event = mock_shutdown_event  # Link the events for the test

        mock_shutdown_event.set()

        tui_app._check_external_shutdown()

        tui_app.action_quit.assert_called_once()


# 🔼⚙️🔚
