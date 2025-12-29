#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for TUI integration scenarios."""

import asyncio
from pathlib import Path

from provide.testkit.mocking import AsyncMock, Mock
import pytest

pytestmark = pytest.mark.skip(reason="TUI in active development")
from supsrc.tui.app import SupsrcTuiApp  # noqa: E402


class TestTuiIntegration:
    """Test TUI integration scenarios."""

    @pytest.fixture
    def mock_orchestrator(self) -> Mock:
        """Create a mock orchestrator for TUI testing."""
        orchestrator = Mock()
        orchestrator.get_repository_details = AsyncMock()
        return orchestrator

    async def test_repo_detail_fetching(
        self,
        mock_config_path: Path,
        mock_shutdown_event: asyncio.Event,
        mock_orchestrator: Mock,
    ) -> None:
        """Test repository detail fetching workflow."""
        tui_app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        tui_app._orchestrator = mock_orchestrator

        mock_orchestrator.get_repository_details.return_value = {
            "commit_history": ["abc123 - Test commit", "def456 - Another commit"]
        }

        tui_app.query_one = Mock()
        mock_detail_log = Mock()
        tui_app.query_one.return_value = mock_detail_log
        tui_app.post_message = Mock()

        await tui_app._fetch_repo_details_worker("test-repo")

        mock_orchestrator.get_repository_details.assert_called_once_with("test-repo")

        tui_app.post_message.assert_called_once()
        posted_message = tui_app.post_message.call_args[0][0]
        assert hasattr(posted_message, "repo_id")
        assert posted_message.repo_id == "test-repo"

    async def test_repo_detail_error_handling(
        self,
        mock_config_path: Path,
        mock_shutdown_event: asyncio.Event,
        mock_orchestrator: Mock,
    ) -> None:
        """Test error handling in repository detail fetching."""
        tui_app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        tui_app._orchestrator = mock_orchestrator

        mock_orchestrator.get_repository_details.side_effect = Exception("Test error")

        tui_app.post_message = Mock()

        await tui_app._fetch_repo_details_worker("test-repo")

        tui_app.post_message.assert_called_once()
        posted_message = tui_app.post_message.call_args[0][0]
        assert "Error loading details" in str(posted_message.details)

    def test_action_select_repo_for_detail(
        self, mock_config_path: Path, mock_shutdown_event: asyncio.Event
    ) -> None:
        """Test repository selection for detail view."""
        tui_app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)
        tui_app._orchestrator = Mock()
        tui_app.event_collector = Mock()

        # Mock the data table with sample data
        mock_table = Mock()
        mock_table.cursor_coordinate.row = 0
        mock_table.rows = [{"id": "row1"}]  # Simulate one row
        mock_table.get_row_at = Mock(
            return_value=(
                "🟢",
                "5s",
                "test-repo",
                "main",
                "42",
                "2",
                "1",
                "0",
                "1",
                "abc123",
                "Auto",
            )
        )

        tui_app.query_one = Mock(return_value=mock_table)
        tui_app._update_repo_details_tab = Mock()

        tui_app.action_select_repo_for_detail()

        assert tui_app.selected_repo_id == "test-repo"
        tui_app._update_repo_details_tab.assert_called_once_with("test-repo")
        tui_app.event_collector.emit.assert_called_once()

    def test_action_hide_detail_pane(self, mock_config_path: Path, mock_shutdown_event: asyncio.Event) -> None:
        """Test hiding the detail pane."""
        tui_app = SupsrcTuiApp(mock_config_path, mock_shutdown_event)

        tui_app.selected_repo_id = "test-repo"
        tui_app.event_collector = Mock()

        mock_table = Mock()
        tui_app.query_one = Mock(return_value=mock_table)

        tui_app.action_hide_detail_pane()

        assert tui_app.selected_repo_id is None
        mock_table.focus.assert_called_once()
        tui_app.event_collector.emit.assert_called_once()


# 🔼⚙️🔚
