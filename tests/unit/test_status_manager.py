#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for StatusManager to improve runtime module coverage."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock

import pytest

from supsrc.config.models import (
    GlobalConfig,
    InactivityRuleConfig,
    RepositoryConfig,
    SupsrcConfig,
)
from supsrc.runtime.status_manager import StatusManager
from supsrc.state.runtime import RepositoryState


class TestStatusManagerInitialization:
    """Tests for StatusManager initialization."""

    def test_initialization(self):
        """Test StatusManager initializes with required dependencies."""
        repo_states = {}
        repo_engines = {}
        config = Mock(spec=SupsrcConfig)
        callback = Mock()

        manager = StatusManager(repo_states, repo_engines, config, callback)

        assert manager.repo_states is repo_states
        assert manager.repo_engines is repo_engines
        assert manager.config is config
        assert manager.state_update_callback is callback

    def test_initialization_with_empty_dependencies(self):
        """Test StatusManager with empty dicts."""
        manager = StatusManager({}, {}, None, Mock())
        assert manager.repo_states == {}
        assert manager.repo_engines == {}
        assert manager.config is None


class TestSetRepoRefreshingStatus:
    """Tests for set_repo_refreshing_status method."""

    def test_set_refreshing_status_true(self):
        """Test setting refreshing status to True."""
        repo_state = RepositoryState(repo_id="test")
        repo_states = {"test": repo_state}
        callback = Mock()

        manager = StatusManager(repo_states, {}, None, callback)
        manager.set_repo_refreshing_status("test", True)

        assert repo_state.is_refreshing is True
        callback.assert_called_once()

    def test_set_refreshing_status_false(self):
        """Test setting refreshing status to False."""
        repo_state = RepositoryState(repo_id="test")
        repo_state.is_refreshing = True
        repo_states = {"test": repo_state}
        callback = Mock()

        manager = StatusManager(repo_states, {}, None, callback)
        manager.set_repo_refreshing_status("test", False)

        assert repo_state.is_refreshing is False
        callback.assert_called_once()

    def test_set_refreshing_status_nonexistent_repo(self):
        """Test setting refreshing status for nonexistent repository."""
        callback = Mock()
        manager = StatusManager({}, {}, None, callback)

        # Should not raise, just do nothing
        manager.set_repo_refreshing_status("nonexistent", True)
        callback.assert_not_called()

    def test_set_refreshing_status_updates_emoji(self):
        """Test that setting refreshing status updates display emoji."""
        repo_state = RepositoryState(repo_id="test")
        repo_state.is_refreshing = False
        initial_emoji = repo_state.display_status_emoji
        repo_states = {"test": repo_state}

        manager = StatusManager(repo_states, {}, None, Mock())
        manager.set_repo_refreshing_status("test", True)

        # Emoji should be updated (refreshing emoji)
        assert repo_state.is_refreshing is True
        # Verify emoji was updated to refreshing emoji
        assert repo_state.display_status_emoji == "🔄"


class TestRefreshRepositoryStatus:
    """Tests for refresh_repository_status async method."""

    @pytest.fixture
    def setup_manager(self, tmp_path):
        """Create StatusManager with mocked dependencies."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        repo_state = RepositoryState(repo_id="test")
        repo_states = {"test": repo_state}

        repo_engine = AsyncMock()
        repo_engines = {"test": repo_engine}

        repo_config = RepositoryConfig(
            path=repo_path,
            rule=InactivityRuleConfig(period=timedelta(seconds=30)),
        )
        config = SupsrcConfig(
            repositories={"test": repo_config},
            global_config=GlobalConfig(),
        )

        callback = Mock()
        manager = StatusManager(repo_states, repo_engines, config, callback)

        return manager, repo_state, repo_engine, callback

    @pytest.mark.asyncio
    async def test_refresh_repository_status_success(self, setup_manager):
        """Test successful repository status refresh."""
        manager, repo_state, repo_engine, callback = setup_manager

        # Mock status result
        status_result = Mock()
        status_result.success = True
        status_result.total_files = 100
        status_result.changed_files = 5
        status_result.added_files = 2
        status_result.deleted_files = 1
        status_result.modified_files = 2
        status_result.is_clean = False
        status_result.current_branch = "main"
        repo_engine.get_status.return_value = status_result

        # Mock summary result
        summary = Mock()
        summary.head_commit_timestamp = datetime.now(UTC)
        summary.head_commit_hash = "abcdef1234567890"
        summary.head_commit_message_summary = "Latest commit"
        repo_engine.get_summary.return_value = summary

        result = await manager.refresh_repository_status("test")

        assert result is True
        assert repo_state.total_files == 100
        assert repo_state.changed_files == 5
        assert repo_state.added_files == 2
        assert repo_state.deleted_files == 1
        assert repo_state.modified_files == 2
        assert repo_state.has_uncommitted_changes is True
        assert repo_state.current_branch == "main"
        assert repo_state.last_commit_short_hash == "abcdef1"
        assert repo_state.last_commit_message_summary == "Latest commit"
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_refresh_repository_status_missing_state(self, setup_manager):
        """Test refresh when repository state is missing."""
        manager, _, repo_engine, callback = setup_manager
        manager.repo_states = {}

        result = await manager.refresh_repository_status("test")

        assert result is False
        repo_engine.get_status.assert_not_called()
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_repository_status_missing_config(self, setup_manager, tmp_path):
        """Test refresh when repository config is missing."""
        manager, repo_state, repo_engine, callback = setup_manager
        # Create new config without test repository
        empty_config = SupsrcConfig(
            repositories={},
            global_config=GlobalConfig(),
        )
        manager.config = empty_config

        result = await manager.refresh_repository_status("test")

        assert result is False
        repo_engine.get_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_repository_status_missing_engine(self, setup_manager):
        """Test refresh when repository engine is missing."""
        manager, repo_state, _, callback = setup_manager
        manager.repo_engines = {}

        result = await manager.refresh_repository_status("test")

        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_repository_status_get_status_fails(self, setup_manager):
        """Test refresh when get_status returns failure."""
        manager, repo_state, repo_engine, callback = setup_manager

        status_result = Mock()
        status_result.success = False
        status_result.message = "Git error"
        repo_engine.get_status.return_value = status_result

        result = await manager.refresh_repository_status("test")

        assert result is False
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_repository_status_exception_handling(self, setup_manager):
        """Test refresh handles exceptions gracefully."""
        manager, repo_state, repo_engine, callback = setup_manager

        repo_engine.get_status.side_effect = Exception("Unexpected error")

        result = await manager.refresh_repository_status("test")

        assert result is False
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_refresh_repository_status_no_summary_attributes(self, setup_manager):
        """Test refresh when summary lacks optional attributes."""
        manager, repo_state, repo_engine, callback = setup_manager

        status_result = Mock()
        status_result.success = True
        status_result.total_files = 50
        status_result.changed_files = 0
        status_result.added_files = 0
        status_result.deleted_files = 0
        status_result.modified_files = 0
        status_result.is_clean = True
        status_result.current_branch = "develop"
        repo_engine.get_status.return_value = status_result

        # Summary without optional attributes
        summary = Mock(spec=[])  # Empty spec means no attributes
        repo_engine.get_summary.return_value = summary

        result = await manager.refresh_repository_status("test")

        assert result is True
        assert repo_state.total_files == 50
        assert repo_state.current_branch == "develop"
        assert repo_state.has_uncommitted_changes is False
        callback.assert_called_once()


class TestUpdateRepositoryStatistics:
    """Tests for update_repository_statistics async method."""

    @pytest.fixture
    def setup_update(self, tmp_path):
        """Create StatusManager for statistics update tests."""
        repo_path = tmp_path / "test_repo"
        repo_path.mkdir()

        repo_state = RepositoryState(repo_id="test")
        repo_engine = AsyncMock()

        repo_config = RepositoryConfig(
            path=repo_path,
            rule=InactivityRuleConfig(period=timedelta(seconds=30)),
        )
        config = SupsrcConfig(
            repositories={"test": repo_config},
            global_config=GlobalConfig(),
        )

        callback = Mock()
        manager = StatusManager({"test": repo_state}, {"test": repo_engine}, config, callback)

        return manager, repo_state, repo_engine

    @pytest.mark.asyncio
    async def test_update_repository_statistics_success(self, setup_update):
        """Test successful statistics update."""
        manager, repo_state, repo_engine = setup_update

        status_result = Mock()
        status_result.success = True
        status_result.total_files = 200
        status_result.changed_files = 10
        status_result.added_files = 3
        status_result.deleted_files = 2
        status_result.modified_files = 5
        status_result.is_clean = False
        status_result.current_branch = "feature"
        repo_engine.get_status.return_value = status_result

        result = await manager.update_repository_statistics("test", repo_state, repo_engine)

        assert result is True
        assert repo_state.total_files == 200
        assert repo_state.changed_files == 10
        assert repo_state.added_files == 3
        assert repo_state.deleted_files == 2
        assert repo_state.modified_files == 5
        assert repo_state.has_uncommitted_changes is True
        assert repo_state.current_branch == "feature"

    @pytest.mark.asyncio
    async def test_update_repository_statistics_missing_config(self, setup_update):
        """Test update when repository config is missing."""
        manager, repo_state, repo_engine = setup_update
        # Create new config without test repository
        empty_config = SupsrcConfig(
            repositories={},
            global_config=GlobalConfig(),
        )
        manager.config = empty_config

        result = await manager.update_repository_statistics("test", repo_state, repo_engine)

        assert result is False
        repo_engine.get_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_repository_statistics_no_config_object(self, setup_update):
        """Test update when config object is None."""
        manager, repo_state, repo_engine = setup_update
        manager.config = None

        result = await manager.update_repository_statistics("test", repo_state, repo_engine)

        assert result is False

    @pytest.mark.asyncio
    async def test_update_repository_statistics_get_status_fails(self, setup_update):
        """Test update when get_status returns failure."""
        manager, repo_state, repo_engine = setup_update

        status_result = Mock()
        status_result.success = False
        repo_engine.get_status.return_value = status_result

        result = await manager.update_repository_statistics("test", repo_state, repo_engine)

        assert result is False

    @pytest.mark.asyncio
    async def test_update_repository_statistics_exception(self, setup_update):
        """Test update handles exceptions gracefully."""
        manager, repo_state, repo_engine = setup_update

        repo_engine.get_status.side_effect = RuntimeError("Connection error")

        result = await manager.update_repository_statistics("test", repo_state, repo_engine)

        assert result is False

    @pytest.mark.asyncio
    async def test_update_repository_statistics_clean_repo(self, setup_update):
        """Test update for a clean repository."""
        manager, repo_state, repo_engine = setup_update

        status_result = Mock()
        status_result.success = True
        status_result.total_files = 150
        status_result.changed_files = 0
        status_result.added_files = 0
        status_result.deleted_files = 0
        status_result.modified_files = 0
        status_result.is_clean = True
        status_result.current_branch = "main"
        repo_engine.get_status.return_value = status_result

        result = await manager.update_repository_statistics("test", repo_state, repo_engine)

        assert result is True
        assert repo_state.total_files == 150
        assert repo_state.changed_files == 0
        assert repo_state.has_uncommitted_changes is False

    @pytest.mark.asyncio
    async def test_update_repository_statistics_none_values(self, setup_update):
        """Test update when status result has None values."""
        manager, repo_state, repo_engine = setup_update

        status_result = Mock()
        status_result.success = True
        status_result.total_files = None
        status_result.changed_files = None
        status_result.added_files = None
        status_result.deleted_files = None
        status_result.modified_files = None
        status_result.is_clean = True
        status_result.current_branch = "main"
        repo_engine.get_status.return_value = status_result

        result = await manager.update_repository_statistics("test", repo_state, repo_engine)

        assert result is True
        # Should default to 0 when None
        assert repo_state.total_files == 0
        assert repo_state.changed_files == 0
        assert repo_state.added_files == 0
        assert repo_state.deleted_files == 0
        assert repo_state.modified_files == 0


# 🔼⚙️🔚
