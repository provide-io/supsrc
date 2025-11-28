#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for state management modules to improve code coverage."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from supsrc.state.control import (
    LocalStateData,
    RepositoryStateOverride,
    SharedStateData,
    StateData,
    local_state_from_dict,
    local_state_to_dict,
    shared_state_from_dict,
    shared_state_to_dict,
    validate_state_file,
)
from supsrc.state.manager import StateManager
from supsrc.state.monitor import StateMonitor


class TestStateData:
    """Tests for StateData model and serialization."""

    def test_default_state_data_creation(self):
        """Test creating StateData with defaults."""
        state = StateData()
        assert state.paused is False
        assert state.paused_until is None
        assert state.paused_by is None
        assert state.pause_reason is None
        assert state.repositories == {}
        assert state.version == "1.0.0"
        assert state.updated_by is None
        assert state.pid is None

    def test_state_data_with_custom_values(self):
        """Test creating StateData with custom values."""
        now = datetime.now(UTC)
        state = StateData(
            paused=True,
            paused_until=now + timedelta(hours=1),
            paused_by="test_user",
            pause_reason="Manual pause",
            version="2.0.0",
            updated_by="admin",
            pid=12345,
        )
        assert state.paused is True
        assert state.paused_until is not None
        assert state.paused_by == "test_user"
        assert state.pause_reason == "Manual pause"
        assert state.version == "2.0.0"
        assert state.updated_by == "admin"
        assert state.pid == 12345

    def test_state_data_to_dict(self):
        """Test converting StateData to dictionary."""
        now = datetime.now(UTC)
        state = StateData(
            paused=True,
            paused_until=now,
            paused_by="test",
            pause_reason="Testing",
            updated_at=now,
            updated_by="user",
            pid=100,
        )
        result = state.to_dict()

        assert "state" in result
        assert result["state"]["paused"] is True
        assert "paused_until" in result["state"]
        assert result["state"]["paused_by"] == "test"
        assert result["state"]["pause_reason"] == "Testing"

        assert "metadata" in result
        assert result["metadata"]["version"] == "1.0.0"
        assert result["metadata"]["updated_by"] == "user"
        assert result["metadata"]["pid"] == 100

    def test_state_data_from_dict(self):
        """Test creating StateData from dictionary."""
        data = {
            "state": {
                "paused": True,
                "paused_until": "2025-01-01T12:00:00Z",
                "paused_by": "alice",
                "pause_reason": "Maintenance",
                "repositories": {
                    "repo1": {"paused": True, "save_count_disabled": False},
                    "repo2": {
                        "paused": False,
                        "save_count_disabled": True,
                        "inactivity_seconds": 60,
                        "rule_overrides": {"key": "value"},
                    },
                },
            },
            "metadata": {
                "version": "1.0.0",
                "updated_at": "2025-01-01T10:00:00Z",
                "updated_by": "system",
                "pid": 5678,
            },
        }
        state = StateData.from_dict(data)

        assert state.paused is True
        assert state.paused_until is not None
        assert state.paused_by == "alice"
        assert state.pause_reason == "Maintenance"
        assert "repo1" in state.repositories
        assert state.repositories["repo1"].paused is True
        assert "repo2" in state.repositories
        assert state.repositories["repo2"].save_count_disabled is True
        assert state.repositories["repo2"].inactivity_seconds == 60
        assert state.repositories["repo2"].rule_overrides == {"key": "value"}
        assert state.version == "1.0.0"
        assert state.updated_by == "system"
        assert state.pid == 5678

    def test_state_data_is_expired_not_expired(self):
        """Test is_expired when not expired."""
        state = StateData(
            paused=True,
            paused_until=datetime.now(UTC) + timedelta(hours=1),
        )
        assert state.is_expired() is False

    def test_state_data_is_expired_when_expired(self):
        """Test is_expired when expired."""
        state = StateData(
            paused=True,
            paused_until=datetime.now(UTC) - timedelta(hours=1),
        )
        assert state.is_expired() is True

    def test_state_data_is_expired_no_expiry_set(self):
        """Test is_expired when no expiry time set."""
        state = StateData(paused=True, paused_until=None)
        assert state.is_expired() is False

    def test_state_data_is_repo_paused_true(self):
        """Test is_repo_paused when repo is paused."""
        state = StateData(
            repositories={
                "test_repo": RepositoryStateOverride(paused=True),
            }
        )
        assert state.is_repo_paused("test_repo") is True

    def test_state_data_is_repo_paused_false(self):
        """Test is_repo_paused when repo is not paused."""
        state = StateData(
            repositories={
                "test_repo": RepositoryStateOverride(paused=False),
            }
        )
        assert state.is_repo_paused("test_repo") is False

    def test_state_data_is_repo_paused_not_in_overrides(self):
        """Test is_repo_paused when repo has no override."""
        state = StateData(repositories={})
        assert state.is_repo_paused("unknown_repo") is False

    def test_state_data_round_trip_serialization(self):
        """Test that to_dict/from_dict round trip preserves data."""
        original = StateData(
            paused=True,
            paused_until=datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC),
            paused_by="user",
            pause_reason="Test",
            repositories={
                "repo1": RepositoryStateOverride(paused=True, save_count_disabled=False),
            },
            version="1.0.0",
            updated_at=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC),
            updated_by="system",
            pid=1234,
        )

        dict_form = original.to_dict()
        restored = StateData.from_dict(dict_form)

        assert restored.paused == original.paused
        assert restored.paused_until == original.paused_until
        assert restored.paused_by == original.paused_by
        assert restored.pause_reason == original.pause_reason
        assert "repo1" in restored.repositories
        assert restored.repositories["repo1"].paused == original.repositories["repo1"].paused
        assert restored.version == original.version
        assert restored.updated_by == original.updated_by
        assert restored.pid == original.pid


class TestRepositoryStateOverride:
    """Tests for RepositoryStateOverride model."""

    def test_default_override_values(self):
        """Test default values for RepositoryStateOverride."""
        override = RepositoryStateOverride()
        assert override.paused is False
        assert override.save_count_disabled is False
        assert override.inactivity_seconds is None
        assert override.rule_overrides == {}

    def test_custom_override_values(self):
        """Test custom values for RepositoryStateOverride."""
        override = RepositoryStateOverride(
            paused=True,
            save_count_disabled=True,
            inactivity_seconds=120,
            rule_overrides={"custom": "value"},
        )
        assert override.paused is True
        assert override.save_count_disabled is True
        assert override.inactivity_seconds == 120
        assert override.rule_overrides == {"custom": "value"}


class TestSharedAndLocalStateData:
    """Tests for SharedStateData and LocalStateData helper models."""

    def test_shared_state_from_dict(self):
        """Test creating SharedStateData from dictionary."""
        data = {
            "state": {
                "paused": True,
                "paused_until": "2025-01-01T12:00:00Z",
                "pause_reason": "Maintenance",
                "repositories": {
                    "repo1": {
                        "paused": True,
                        "save_count_disabled": False,
                        "inactivity_seconds": 120,
                        "rule_overrides": {"key": "value"},
                    }
                },
            },
            "metadata": {"version": "2.0.0"},
        }

        shared = shared_state_from_dict(data)
        assert shared.paused is True
        assert shared.paused_until is not None
        assert shared.pause_reason == "Maintenance"
        assert "repo1" in shared.repositories
        assert shared.repositories["repo1"].paused is True
        assert shared.repositories["repo1"].inactivity_seconds == 120
        assert shared.version == "2.0.0"

    def test_shared_state_from_dict_minimal(self):
        """Test creating SharedStateData with minimal data."""
        data = {"state": {}, "metadata": {}}
        shared = shared_state_from_dict(data)
        assert shared.paused is False
        assert shared.paused_until is None
        assert shared.repositories == {}
        assert shared.version == "2.0.0"

    def test_local_state_from_dict(self):
        """Test creating LocalStateData from dictionary."""
        data = {
            "state": {"paused_by": "alice"},
            "metadata": {
                "updated_at": "2025-01-01T10:00:00Z",
                "updated_by": "system",
                "pid": 12345,
                "local_overrides": {"key": "value"},
            },
        }

        local = local_state_from_dict(data)
        assert local.paused_by == "alice"
        assert local.updated_by == "system"
        assert local.pid == 12345
        assert local.local_overrides == {"key": "value"}

    def test_local_state_from_dict_minimal(self):
        """Test creating LocalStateData with minimal data."""
        data = {"state": {}, "metadata": {}}
        local = local_state_from_dict(data)
        assert local.paused_by is None
        assert local.pid is None
        assert local.local_overrides == {}

    def test_shared_state_to_dict(self):
        """Test converting SharedStateData to dictionary."""
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        shared = SharedStateData(
            paused=True,
            paused_until=now,
            pause_reason="Testing",
            repositories={
                "repo1": RepositoryStateOverride(
                    paused=True,
                    save_count_disabled=True,
                    inactivity_seconds=60,
                    rule_overrides={"key": "value"},
                )
            },
            version="2.0.0",
        )

        result = shared_state_to_dict(shared)

        assert result["state"]["paused"] is True
        assert "paused_until" in result["state"]
        assert result["state"]["pause_reason"] == "Testing"
        assert "repo1" in result["state"]["repositories"]
        assert result["state"]["repositories"]["repo1"]["paused"] is True
        assert result["state"]["repositories"]["repo1"]["inactivity_seconds"] == 60
        assert result["metadata"]["version"] == "2.0.0"

    def test_shared_state_to_dict_minimal(self):
        """Test converting minimal SharedStateData to dictionary."""
        shared = SharedStateData()
        result = shared_state_to_dict(shared)

        assert result["state"]["paused"] is False
        assert "paused_until" not in result["state"]
        assert "pause_reason" not in result["state"]
        assert result["metadata"]["version"] == "2.0.0"

    def test_local_state_to_dict(self):
        """Test converting LocalStateData to dictionary."""
        now = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        local = LocalStateData(
            pid=9999,
            paused_by="bob",
            updated_at=now,
            updated_by="admin",
            local_overrides={"override": "value"},
        )

        result = local_state_to_dict(local)

        assert result["state"]["paused_by"] == "bob"
        assert "updated_at" in result["metadata"]
        assert result["metadata"]["updated_by"] == "admin"
        assert result["metadata"]["pid"] == 9999
        assert result["metadata"]["local_overrides"] == {"override": "value"}

    def test_local_state_to_dict_minimal(self):
        """Test converting minimal LocalStateData to dictionary."""
        local = LocalStateData()
        result = local_state_to_dict(local)

        assert result["state"] == {}
        assert "updated_at" in result["metadata"]
        assert "updated_by" not in result["metadata"]
        assert "pid" not in result["metadata"]

    def test_state_data_from_shared_and_local(self):
        """Test creating StateData from shared and local data."""
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        shared = SharedStateData(
            paused=True,
            paused_until=now,
            pause_reason="Shared reason",
            version="2.0.0",
        )
        local = LocalStateData(
            pid=1234,
            paused_by="local_user",
            updated_by="local_admin",
        )

        state = StateData.from_shared_and_local(shared, local)
        assert state.paused is True
        assert state.paused_until == now
        assert state.pause_reason == "Shared reason"
        assert state.version == "2.0.0"
        assert state.pid == 1234
        assert state.paused_by == "local_user"
        assert state.updated_by == "local_admin"

    def test_state_data_to_shared_state(self):
        """Test extracting SharedStateData from StateData."""
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        state = StateData(
            paused=True,
            paused_until=now,
            pause_reason="Test",
            version="1.0.0",
            pid=1234,
            paused_by="user",
        )

        shared = state.to_shared_state()
        assert shared.paused is True
        assert shared.paused_until == now
        assert shared.pause_reason == "Test"
        assert shared.version == "1.0.0"

    def test_state_data_to_local_state(self):
        """Test extracting LocalStateData from StateData."""
        now = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)
        state = StateData(
            paused=True,
            updated_at=now,
            updated_by="admin",
            pid=5678,
            paused_by="operator",
        )

        local = state.to_local_state()
        assert local.pid == 5678
        assert local.paused_by == "operator"
        assert local.updated_at == now
        assert local.updated_by == "admin"


class TestValidateStateFile:
    """Tests for validate_state_file function."""

    def test_valid_state_file(self, tmp_path):
        """Test validating a correct state file."""
        import json

        state_file = tmp_path / "state.json"
        data = {
            "state": {"paused": False},
            "metadata": {"version": "1.0.0"},
        }
        state_file.write_text(json.dumps(data))

        assert validate_state_file(state_file) is True

    def test_invalid_state_file_not_dict(self, tmp_path):
        """Test validating file with non-dict content."""
        state_file = tmp_path / "state.json"
        state_file.write_text("[]")

        assert validate_state_file(state_file) is False

    def test_invalid_state_file_missing_state(self, tmp_path):
        """Test validating file missing 'state' key."""
        import json

        state_file = tmp_path / "state.json"
        data = {"metadata": {"version": "1.0.0"}}
        state_file.write_text(json.dumps(data))

        assert validate_state_file(state_file) is False

    def test_invalid_state_file_missing_metadata(self, tmp_path):
        """Test validating file missing 'metadata' key."""
        import json

        state_file = tmp_path / "state.json"
        data = {"state": {"paused": False}}
        state_file.write_text(json.dumps(data))

        assert validate_state_file(state_file) is False

    def test_invalid_state_file_state_not_dict(self, tmp_path):
        """Test validating file where 'state' is not a dict."""
        import json

        state_file = tmp_path / "state.json"
        data = {"state": [], "metadata": {"version": "1.0.0"}}
        state_file.write_text(json.dumps(data))

        assert validate_state_file(state_file) is False

    def test_invalid_state_file_metadata_not_dict(self, tmp_path):
        """Test validating file where 'metadata' is not a dict."""
        import json

        state_file = tmp_path / "state.json"
        data = {"state": {}, "metadata": []}
        state_file.write_text(json.dumps(data))

        assert validate_state_file(state_file) is False

    def test_invalid_state_file_missing_version(self, tmp_path):
        """Test validating file missing version in metadata."""
        import json

        state_file = tmp_path / "state.json"
        data = {"state": {}, "metadata": {}}
        state_file.write_text(json.dumps(data))

        assert validate_state_file(state_file) is False

    def test_invalid_state_file_bad_json(self, tmp_path):
        """Test validating file with invalid JSON."""
        state_file = tmp_path / "state.json"
        state_file.write_text("{bad json")

        assert validate_state_file(state_file) is False

    def test_invalid_state_file_not_found(self, tmp_path):
        """Test validating non-existent file."""
        state_file = tmp_path / "nonexistent.json"
        assert validate_state_file(state_file) is False


class TestStateMonitor:
    """Tests for StateMonitor async monitoring."""

    def test_state_monitor_initialization(self):
        """Test StateMonitor initialization."""
        monitor = StateMonitor()
        assert monitor.repo_paths == []
        assert monitor._callbacks == []
        assert monitor._is_running is False
        assert monitor._monitor_task is None

    def test_state_monitor_with_repo_paths(self):
        """Test StateMonitor initialization with paths."""
        paths = [Path("/repo1"), Path("/repo2")]
        monitor = StateMonitor(repo_paths=paths)
        assert monitor.repo_paths == paths

    def test_register_callback(self):
        """Test registering callbacks."""
        monitor = StateMonitor()

        def my_callback(repo_id: str, state: StateData | None) -> None:
            pass

        monitor.register_callback(my_callback)
        assert my_callback in monitor._callbacks

    def test_unregister_callback(self):
        """Test unregistering callbacks."""
        monitor = StateMonitor()

        def my_callback(repo_id: str, state: StateData | None) -> None:
            pass

        monitor.register_callback(my_callback)
        monitor.unregister_callback(my_callback)
        assert my_callback not in monitor._callbacks

    def test_unregister_nonexistent_callback(self):
        """Test unregistering callback that was never registered."""
        monitor = StateMonitor()
        callback = Mock()
        # Should not raise
        monitor.unregister_callback(callback)

    def test_get_current_state_returns_none(self):
        """Test getting state that doesn't exist."""
        monitor = StateMonitor()
        result = monitor.get_current_state("nonexistent")
        assert result is None

    def test_get_current_state_returns_data(self):
        """Test getting state that exists."""
        monitor = StateMonitor()
        state = StateData(paused=True)
        monitor._current_states["test_repo"] = state
        result = monitor.get_current_state("test_repo")
        assert result is state

    def test_is_paused_global_paused(self):
        """Test is_paused when globally paused."""
        monitor = StateMonitor()
        monitor._current_states["global"] = StateData(paused=True)
        assert monitor.is_paused() is True

    def test_is_paused_global_not_paused(self):
        """Test is_paused when globally not paused."""
        monitor = StateMonitor()
        monitor._current_states["global"] = StateData(paused=False)
        assert monitor.is_paused() is False

    def test_is_paused_repo_specific_paused(self):
        """Test is_paused for specific repository."""
        monitor = StateMonitor()
        monitor._current_states["test_repo"] = StateData(
            repositories={"test_repo": RepositoryStateOverride(paused=True)}
        )
        assert monitor.is_paused("test_repo") is True

    def test_is_paused_global_expired(self):
        """Test is_paused when global pause is expired."""
        monitor = StateMonitor()
        monitor._current_states["global"] = StateData(
            paused=True,
            paused_until=datetime.now(UTC) - timedelta(hours=1),
        )
        assert monitor.is_paused() is False

    def test_add_repo_path(self):
        """Test adding repository path."""
        monitor = StateMonitor()
        path = Path("/new/repo")
        monitor.add_repo_path(path)
        assert path in monitor.repo_paths

    def test_add_duplicate_repo_path(self):
        """Test adding duplicate repository path."""
        monitor = StateMonitor()
        path = Path("/repo")
        monitor.add_repo_path(path)
        monitor.add_repo_path(path)
        assert monitor.repo_paths.count(path) == 1

    def test_remove_repo_path(self):
        """Test removing repository path."""
        monitor = StateMonitor()
        path = Path("/repo")
        monitor.add_repo_path(path)
        monitor._current_states["repo"] = StateData()

        monitor.remove_repo_path(path)
        assert path not in monitor.repo_paths
        assert "repo" not in monitor._current_states

    def test_states_equal_same_state(self):
        """Test _states_equal with identical states."""
        monitor = StateMonitor()
        state1 = StateData(paused=True, paused_until=None)
        state2 = StateData(paused=True, paused_until=None)
        assert monitor._states_equal(state1, state2) is True

    def test_states_equal_different_paused(self):
        """Test _states_equal with different paused."""
        monitor = StateMonitor()
        state1 = StateData(paused=True)
        state2 = StateData(paused=False)
        assert monitor._states_equal(state1, state2) is False

    def test_states_equal_different_paused_until(self):
        """Test _states_equal with different paused_until."""
        monitor = StateMonitor()
        now = datetime.now(UTC)
        state1 = StateData(paused=True, paused_until=now)
        state2 = StateData(paused=True, paused_until=now + timedelta(hours=1))
        assert monitor._states_equal(state1, state2) is False

    @pytest.mark.asyncio
    async def test_start_sets_running_flag(self):
        """Test that start sets the running flag."""
        monitor = StateMonitor()
        with patch.object(monitor, "_check_all_files", new_callable=AsyncMock):
            await monitor.start()
            assert monitor._is_running is True
            assert monitor._monitor_task is not None
            await monitor.stop()

    @pytest.mark.asyncio
    async def test_start_already_running(self):
        """Test starting when already running."""
        monitor = StateMonitor()
        monitor._is_running = True
        # Should just return without doing anything
        await monitor.start()

    @pytest.mark.asyncio
    async def test_stop_clears_running_flag(self):
        """Test that stop clears the running flag."""
        monitor = StateMonitor()
        with patch.object(monitor, "_check_all_files", new_callable=AsyncMock):
            await monitor.start()
            await monitor.stop()
            assert monitor._is_running is False

    @pytest.mark.asyncio
    async def test_stop_when_not_running(self):
        """Test stopping when not running."""
        monitor = StateMonitor()
        # Should not raise
        await monitor.stop()

    @pytest.mark.asyncio
    async def test_process_state_change_notifies_callbacks(self):
        """Test that state changes notify callbacks."""
        monitor = StateMonitor()
        called_with = []

        def my_callback(repo_id: str, state_data: StateData | None) -> None:
            called_with.append((repo_id, state_data))

        monitor.register_callback(my_callback)

        state = StateData(paused=True)
        await monitor._process_state_change("test_repo", state)

        assert len(called_with) == 1
        assert called_with[0] == ("test_repo", state)
        assert monitor._current_states["test_repo"] is state

    @pytest.mark.asyncio
    async def test_process_state_change_ignores_duplicate(self):
        """Test that duplicate state changes are ignored."""
        monitor = StateMonitor()
        called_with = []

        def my_callback(repo_id: str, state_data: StateData | None) -> None:
            called_with.append((repo_id, state_data))

        monitor.register_callback(my_callback)

        state = StateData(paused=True)
        monitor._current_states["test_repo"] = state

        # Same state should not trigger callback
        await monitor._process_state_change("test_repo", state)
        assert len(called_with) == 0

    @pytest.mark.asyncio
    async def test_process_state_change_handles_callback_error(self):
        """Test that callback errors are handled gracefully."""
        monitor = StateMonitor()

        def bad_callback(repo_id: str, state: StateData | None) -> None:
            raise ValueError("Test error")

        monitor.register_callback(bad_callback)
        state = StateData(paused=True)

        # Should not raise
        await monitor._process_state_change("test_repo", state)


class TestStateManager:
    """Tests for StateManager coordination class."""

    def test_state_manager_initialization(self):
        """Test StateManager initialization."""
        manager = StateManager()
        assert manager.repo_paths == []
        assert manager._monitor is None
        assert manager._repo_states == {}

    def test_state_manager_with_repo_paths(self):
        """Test StateManager initialization with paths."""
        paths = [Path("/repo1"), Path("/repo2")]
        manager = StateManager(repo_paths=paths)
        assert manager.repo_paths == paths

    def test_register_repository_state(self):
        """Test registering repository state."""
        from supsrc.state.runtime import RepositoryState

        manager = StateManager()
        repo_state = RepositoryState(repo_id="test")
        manager.register_repository_state("test", repo_state)
        assert "test" in manager._repo_states
        assert manager._repo_states["test"] is repo_state

    def test_unregister_repository_state(self):
        """Test unregistering repository state."""
        from supsrc.state.runtime import RepositoryState

        manager = StateManager()
        repo_state = RepositoryState(repo_id="test")
        manager.register_repository_state("test", repo_state)
        manager.unregister_repository_state("test")
        assert "test" not in manager._repo_states

    def test_unregister_nonexistent_repository(self):
        """Test unregistering repository that doesn't exist."""
        manager = StateManager()
        # Should not raise
        manager.unregister_repository_state("nonexistent")

    def test_is_paused_no_monitor(self):
        """Test is_paused when monitor not started."""
        manager = StateManager()
        assert manager.is_paused() is False

    def test_is_paused_with_mock_monitor(self):
        """Test is_paused delegates to monitor."""
        manager = StateManager()
        mock_monitor = Mock()
        mock_monitor.is_paused.return_value = True
        manager._monitor = mock_monitor

        assert manager.is_paused("test") is True
        mock_monitor.is_paused.assert_called_once_with("test")

    def test_add_repository(self):
        """Test adding repository to manager."""
        manager = StateManager()
        path = Path("/new/repo")
        manager.add_repository(path)
        assert path in manager.repo_paths

    def test_add_duplicate_repository(self):
        """Test adding duplicate repository."""
        manager = StateManager()
        path = Path("/repo")
        manager.add_repository(path)
        manager.add_repository(path)
        assert manager.repo_paths.count(path) == 1

    def test_remove_repository(self):
        """Test removing repository from manager."""
        from supsrc.state.runtime import RepositoryState

        manager = StateManager()
        path = Path("/repo")
        manager.add_repository(path)
        repo_state = RepositoryState(repo_id="repo")
        manager._repo_states["repo"] = repo_state

        manager.remove_repository(path)
        assert path not in manager.repo_paths
        assert "repo" not in manager._repo_states

    def test_remove_nonexistent_repository(self):
        """Test removing repository that doesn't exist."""
        manager = StateManager()
        path = Path("/nonexistent")
        # Should not raise
        manager.remove_repository(path)

    def test_apply_state_to_repositories_global_pause(self):
        """Test applying global pause to repositories."""
        from supsrc.state.runtime import RepositoryState

        manager = StateManager()
        repo_state = RepositoryState(repo_id="test")
        manager._repo_states["test"] = repo_state

        state_data = StateData(paused=True, paused_until=datetime.now(UTC) + timedelta(hours=1))
        manager._apply_state_to_repositories("global", state_data)

        assert repo_state.is_paused is True
        assert repo_state.pause_until is not None

    def test_apply_state_to_repositories_global_resume(self):
        """Test applying global resume to repositories."""
        from supsrc.state.runtime import RepositoryState

        manager = StateManager()
        repo_state = RepositoryState(repo_id="test")
        repo_state.is_paused = True
        manager._repo_states["test"] = repo_state

        state_data = StateData(paused=False)
        manager._apply_state_to_repositories("global", state_data)

        assert repo_state.is_paused is False
        assert repo_state.pause_until is None

    def test_apply_state_to_repositories_specific_repo(self):
        """Test applying state to specific repository."""
        from supsrc.state.runtime import RepositoryState

        manager = StateManager()
        repo_state = RepositoryState(repo_id="test")
        manager._repo_states["test"] = repo_state

        state_data = StateData(repositories={"test": RepositoryStateOverride(paused=True)})
        manager._apply_state_to_repositories("test", state_data)

        assert repo_state.is_paused is True

    def test_apply_state_to_nonexistent_repo(self):
        """Test applying state to repository that doesn't exist."""
        manager = StateManager()
        state_data = StateData(repositories={"test": RepositoryStateOverride(paused=True)})
        # Should not raise
        manager._apply_state_to_repositories("test", state_data)

    def test_clear_state_overrides_global(self):
        """Test clearing global state overrides."""
        from supsrc.state.runtime import RepositoryState

        manager = StateManager()
        repo_state = RepositoryState(repo_id="test")
        repo_state.is_paused = True
        repo_state.pause_until = datetime.now(UTC)
        manager._repo_states["test"] = repo_state

        manager._clear_state_overrides("global")

        assert repo_state.is_paused is False
        assert repo_state.pause_until is None

    def test_clear_state_overrides_specific_repo(self):
        """Test clearing specific repository state overrides."""
        from supsrc.state.runtime import RepositoryState

        manager = StateManager()
        repo_state = RepositoryState(repo_id="test")
        repo_state.is_paused = True
        manager._repo_states["test"] = repo_state

        manager._clear_state_overrides("test")

        assert repo_state.is_paused is False

    def test_on_state_change_global(self):
        """Test callback for global state change."""
        from supsrc.state.runtime import RepositoryState

        manager = StateManager()
        repo_state = RepositoryState(repo_id="test")
        manager._repo_states["test"] = repo_state

        state_data = StateData(paused=True)
        manager._on_state_change("global", state_data)

        assert repo_state.is_paused is True

    def test_on_state_change_with_none_state(self):
        """Test callback when state is cleared (None)."""
        from supsrc.state.runtime import RepositoryState

        manager = StateManager()
        repo_state = RepositoryState(repo_id="test")
        repo_state.is_paused = True
        manager._repo_states["test"] = repo_state

        manager._on_state_change("global", None)

        assert repo_state.is_paused is False

    @pytest.mark.asyncio
    async def test_start_initializes_monitor(self):
        """Test that start initializes monitor."""
        manager = StateManager()
        with patch("supsrc.state.monitor.StateMonitor") as mock_monitor:
            mock_instance = AsyncMock()
            mock_monitor.return_value = mock_instance

            await manager.start()

            mock_monitor.assert_called_once()
            mock_instance.register_callback.assert_called_once()
            mock_instance.start.assert_called_once()
            assert manager._monitor is mock_instance

    @pytest.mark.asyncio
    async def test_start_already_started(self):
        """Test start when already started."""
        manager = StateManager()
        manager._monitor = Mock()

        # Should just return
        await manager.start()

    @pytest.mark.asyncio
    async def test_stop_stops_monitor(self):
        """Test that stop stops monitor."""
        manager = StateManager()
        mock_monitor = AsyncMock()
        manager._monitor = mock_monitor

        await manager.stop()

        mock_monitor.stop.assert_called_once()
        assert manager._monitor is None

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self):
        """Test stop when not started."""
        manager = StateManager()
        # Should not raise
        await manager.stop()

    def test_pause_no_repo_path_found(self):
        """Test pause when repo path not found."""
        manager = StateManager(repo_paths=[])
        result = manager.pause(repo_id="nonexistent")
        assert result is False

    def test_resume_no_repo_path_found(self):
        """Test resume when repo path not found."""
        manager = StateManager(repo_paths=[])
        result = manager.resume(repo_id="nonexistent")
        assert result is False

    def test_get_state_info_no_state_file(self):
        """Test get_state_info when no state file exists."""
        manager = StateManager()
        with patch("supsrc.state.file.StateFile") as mock_state_file:
            mock_state_file.load.return_value = None

            info = manager.get_state_info()

            assert info["paused"] is False
            assert info["state_file_exists"] is False

    def test_get_state_info_with_state_file(self):
        """Test get_state_info with existing state file."""
        manager = StateManager()
        now = datetime.now(UTC)
        state_data = StateData(
            paused=True,
            paused_until=now + timedelta(hours=1),
            pause_reason="Test pause",
            updated_by="admin",
            updated_at=now,
        )

        with patch("supsrc.state.file.StateFile") as mock_state_file:
            mock_state_file.load.return_value = state_data

            info = manager.get_state_info()

            assert info["state_file_exists"] is True
            assert info["paused"] is True
            assert info["pause_reason"] == "Test pause"
            assert info["updated_by"] == "admin"
            assert info["is_expired"] is False

    def test_get_state_info_for_specific_repo(self):
        """Test get_state_info for specific repository."""
        manager = StateManager(repo_paths=[Path("/test/repo")])

        state_data = StateData(
            repositories={
                "repo": RepositoryStateOverride(paused=True, save_count_disabled=True, inactivity_seconds=60)
            },
            updated_at=datetime.now(UTC),
        )

        with patch("supsrc.state.file.StateFile") as mock_state_file:
            mock_state_file.load.return_value = state_data

            info = manager.get_state_info(repo_id="repo")

            assert "repository_overrides" in info
            assert info["repository_overrides"]["paused"] is True
            assert info["repository_overrides"]["save_count_disabled"] is True
            assert info["repository_overrides"]["inactivity_seconds"] == 60

    def test_pause_context_manager(self, tmp_path):
        """Test pause context manager."""
        manager = StateManager()
        with (
            patch.object(manager, "pause", return_value=True) as mock_pause,
            patch.object(manager, "resume") as mock_resume,
        ):
            with manager.pause_context(repo_id="test", duration=60, reason="Testing", updated_by="user"):
                pass

            mock_pause.assert_called_once_with("test", 60, "Testing", "user")
            mock_resume.assert_called_once_with("test")

    def test_pause_context_manager_pause_failed(self):
        """Test pause context manager when pause fails."""
        manager = StateManager()
        with (
            patch.object(manager, "pause", return_value=False) as mock_pause,
            patch.object(manager, "resume") as mock_resume,
        ):
            with manager.pause_context():
                pass

            mock_pause.assert_called_once()
            # Resume should not be called if pause failed
            mock_resume.assert_not_called()


# 🔼⚙️🔚
