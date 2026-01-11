#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for the refactored WatchOrchestrator component."""

import asyncio
from pathlib import Path

from provide.testkit.mocking import AsyncMock, MagicMock, patch
import pytest

from supsrc.config import SupsrcConfig
from supsrc.engines.git import GitEngine
from supsrc.runtime.orchestrator import WatchOrchestrator
from supsrc.state import RepositoryState


@pytest.fixture
def mock_orchestrator(minimal_config: SupsrcConfig) -> WatchOrchestrator:
    """Provides a WatchOrchestrator with a shutdown event."""
    with patch("supsrc.runtime.orchestrator.load_config") as mock_load:
        mock_load.return_value = minimal_config
        orchestrator = WatchOrchestrator(
            config_path=Path("fake.conf"),
            shutdown_event=asyncio.Event(),
        )
        orchestrator.config = minimal_config
        return orchestrator


@pytest.mark.asyncio
class TestOrchestratorLifecycle:
    """Tests for the lifecycle management of the orchestrator."""

    @patch("supsrc.runtime.orchestrator.TUIInterface")
    @patch("supsrc.runtime.orchestrator.ActionHandler")
    @patch("supsrc.runtime.orchestrator.EventProcessor")
    @patch("supsrc.runtime.orchestrator.MonitoringCoordinator")
    async def test_run_initializes_all_components(
        self,
        mock_monitoring_service: MagicMock,
        mock_event_processor: MagicMock,
        mock_action_handler: MagicMock,
        mock_tui_interface: MagicMock,
        minimal_config: SupsrcConfig,
    ):
        """Verify that run() instantiates all runtime components."""
        mock_processor_instance = AsyncMock()
        mock_processor_instance.run.return_value = None
        mock_event_processor.return_value = mock_processor_instance

        mock_monitor_instance = MagicMock()
        mock_monitor_instance.setup_monitoring = MagicMock()
        mock_monitor_instance.setup_config_watcher = MagicMock()
        mock_monitor_instance.start_services = AsyncMock(return_value=True)
        mock_monitor_instance.stop_services = AsyncMock()
        mock_monitoring_service.return_value = mock_monitor_instance

        with patch("supsrc.runtime.orchestrator.load_config", return_value=minimal_config):
            shutdown_event = asyncio.Event()
            orchestrator = WatchOrchestrator(Path("fake.conf"), shutdown_event)

            async def run_and_shutdown():
                run_task = asyncio.create_task(orchestrator.run())
                await asyncio.sleep(0.01)
                shutdown_event.set()
                await run_task

            await run_and_shutdown()

        mock_tui_interface.assert_called_once()
        mock_action_handler.assert_called_once()
        mock_event_processor.assert_called_once()
        mock_monitoring_service.assert_called_once()
        mock_monitor_instance.setup_monitoring.assert_called_once()
        mock_monitor_instance.start_services.assert_called_once()
        mock_processor_instance.run.assert_called_once()
        mock_monitor_instance.stop_services.assert_called_once()

    async def test_initialize_repositories_success(self, mock_orchestrator: WatchOrchestrator):
        """Test that repositories are initialized correctly from config."""
        mock_tui = MagicMock()
        # Use real repository manager but mock the git operations
        from supsrc.runtime.repository_manager import RepositoryManager

        mock_orchestrator.repository_manager = RepositoryManager(
            mock_orchestrator.repo_states, mock_orchestrator.repo_engines
        )

        # Mock the git engine creation and status operations to avoid file system ops
        with patch("supsrc.runtime.repository_manager.GitEngine") as mock_git_engine:
            mock_engine = MagicMock()
            mock_engine.get_summary.return_value = MagicMock(
                head_commit_hash=None, is_empty=True, head_ref_name="UNBORN"
            )
            mock_engine.get_status.return_value = MagicMock(
                success=True,
                total_files=0,
                changed_files=0,
                added_files=0,
                deleted_files=0,
                modified_files=0,
                is_clean=True,
                current_branch="main",
            )
            mock_git_engine.return_value = mock_engine

            await mock_orchestrator.repository_manager.initialize_repositories(
                mock_orchestrator.config, mock_tui
            )

        assert "test_repo_1" in mock_orchestrator.repo_states
        assert "test_repo_1" in mock_orchestrator.repo_engines
        state = mock_orchestrator.repo_states["test_repo_1"]
        assert state.repo_id == "test_repo_1"

    async def test_get_repository_details(self, mock_orchestrator: WatchOrchestrator):
        """Test the public API for retrieving repo details for the TUI."""
        repo_id = "test_repo_1"
        mock_engine = AsyncMock(spec=GitEngine)
        mock_engine.get_commit_history.return_value = ["commit1", "commit2"]
        mock_orchestrator.repo_engines = {repo_id: mock_engine}
        mock_orchestrator.config.repositories[repo_id] = MagicMock()  # Ensure config exists

        # Set up repository manager for delegation
        from supsrc.runtime.repository_manager import RepositoryManager

        mock_orchestrator.repository_manager = RepositoryManager(
            mock_orchestrator.repo_states, mock_orchestrator.repo_engines
        )

        details = await mock_orchestrator.get_repository_details(repo_id)

        assert "commit_history" in details
        assert details["commit_history"] == ["commit1", "commit2"]
        mock_engine.get_commit_history.assert_called_once()


class TestOrchestratorFeatures:
    """Tests for specific orchestrator features like pausing."""

    def test_toggle_repository_pause(self, mock_orchestrator: WatchOrchestrator):
        """Verify that toggling a repository's pause state works correctly."""
        repo_id = "test_repo_1"
        # Ensure the repo exists in the orchestrator's state
        mock_orchestrator.repo_states[repo_id] = RepositoryState(repo_id=repo_id)
        mock_orchestrator.repo_states[repo_id]

        # Mock the repository manager
        from unittest.mock import MagicMock

        mock_repo_manager = MagicMock()
        mock_repo_manager.toggle_repository_pause.return_value = True
        mock_orchestrator.repository_manager = mock_repo_manager

        # Act & Assert (Pause)
        result = mock_orchestrator.toggle_repository_pause(repo_id)
        assert result is True
        mock_repo_manager.toggle_repository_pause.assert_called_with(repo_id)


# 🔼⚙️🔚
