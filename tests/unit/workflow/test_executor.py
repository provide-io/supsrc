#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for RuntimeWorkflow executor."""

from __future__ import annotations

from provide.testkit.mocking import AsyncMock, MagicMock, patch
import pytest

from supsrc.config import SupsrcConfig
from supsrc.protocols import CommitResult, PushResult, RepoStatusResult, StageResult
from supsrc.runtime.tui_interface import TUIInterface
from supsrc.runtime.workflow.executor import RuntimeWorkflow
from supsrc.state import RepositoryState, RepositoryStatus


@pytest.fixture
def mock_repo_engine() -> AsyncMock:
    """Provides a mock RepositoryEngine with default success values."""
    engine = AsyncMock()
    engine.get_status.return_value = RepoStatusResult(success=True, is_clean=False)
    engine.stage_changes.return_value = StageResult(success=True, files_staged=["file.txt"])
    engine.perform_commit.return_value = CommitResult(success=True, commit_hash="abc1234")
    engine.perform_push.return_value = PushResult(success=True)
    engine.get_summary.return_value = MagicMock(head_commit_message_summary="Summary")
    # Configure operations as a MagicMock with async method for conflict checking
    engine.operations = MagicMock()
    # Default: no file warnings (sync method)
    engine.operations.analyze_files_for_warnings.return_value = []
    # Default: no conflicts (async method)
    engine.operations.check_upstream_conflicts = AsyncMock(
        return_value={"has_conflicts": False, "diverged": False}
    )
    return engine


@pytest.fixture
def runtime_workflow(
    minimal_config: SupsrcConfig,
    mock_repo_engine: AsyncMock,
) -> RuntimeWorkflow:
    """Provides a RuntimeWorkflow instance with mocked dependencies."""
    repo_id = "test_repo_1"
    states = {repo_id: RepositoryState(repo_id=repo_id)}
    engines = {repo_id: mock_repo_engine}
    tui = MagicMock(spec=TUIInterface)
    tui.app = MagicMock()  # Add app attribute for event emission
    return RuntimeWorkflow(minimal_config, states, engines, tui)


class TestRuntimeWorkflow:
    """Comprehensive tests for the RuntimeWorkflow."""

    @pytest.mark.asyncio
    async def test_execute_full_sequence_success(
        self, runtime_workflow: RuntimeWorkflow, mock_repo_engine: AsyncMock
    ):
        """Verify all engine methods are called in a successful workflow."""
        repo_id = "test_repo_1"
        await runtime_workflow.execute_action_sequence(repo_id)

        # Verify each step was called
        mock_repo_engine.get_status.assert_called()
        mock_repo_engine.stage_changes.assert_called()
        mock_repo_engine.perform_commit.assert_called()
        mock_repo_engine.perform_push.assert_called()

        # Verify final repository state
        repo_state = runtime_workflow.repo_states[repo_id]
        assert repo_state.last_commit_short_hash == "abc1234"

    async def test_execute_sequence_missing_dependencies(self, runtime_workflow: RuntimeWorkflow):
        """Test handling of missing repository dependencies."""
        repo_id = "nonexistent_repo"
        await runtime_workflow.execute_action_sequence(repo_id)

        # Should handle gracefully and log error
        runtime_workflow.tui.post_log_update.assert_called_with(
            repo_id, "ERROR", "Action failed: Missing state/config/engine."
        )

    async def test_execute_sequence_status_failure(
        self, runtime_workflow: RuntimeWorkflow, mock_repo_engine: AsyncMock
    ):
        """Test workflow stops when status check fails."""
        repo_id = "test_repo_1"

        # Mock status failure
        mock_repo_engine.get_status.return_value = RepoStatusResult(
            success=False, message="Git error", is_clean=False, is_conflicted=False
        )

        await runtime_workflow.execute_action_sequence(repo_id)

        # Should stop after status check
        mock_repo_engine.get_status.assert_called()
        mock_repo_engine.stage_changes.assert_not_called()
        mock_repo_engine.perform_commit.assert_not_called()

        # Verify error state
        repo_state = runtime_workflow.repo_states[repo_id]
        assert repo_state.status == RepositoryStatus.ERROR

    @pytest.mark.asyncio
    async def test_execute_sequence_external_commit_detected(
        self, runtime_workflow: RuntimeWorkflow, mock_repo_engine: AsyncMock
    ):
        """Test workflow handles external commit detection."""
        repo_id = "test_repo_1"

        # Mock clean repository (external commit)
        mock_repo_engine.get_status.return_value = RepoStatusResult(
            success=True, is_clean=True, is_conflicted=False
        )

        await runtime_workflow.execute_action_sequence(repo_id)

        # Should stop after status check
        mock_repo_engine.get_status.assert_called()
        mock_repo_engine.stage_changes.assert_not_called()

        # Verify external commit detected state
        repo_state = runtime_workflow.repo_states[repo_id]
        assert repo_state.status == RepositoryStatus.EXTERNAL_COMMIT_DETECTED

    async def test_execute_sequence_staging_failure(
        self, runtime_workflow: RuntimeWorkflow, mock_repo_engine: AsyncMock
    ):
        """Test workflow stops when staging fails."""
        repo_id = "test_repo_1"

        # Mock staging failure
        mock_repo_engine.stage_changes.return_value = StageResult(success=False, message="Staging error")

        await runtime_workflow.execute_action_sequence(repo_id)

        # Should stop after staging
        mock_repo_engine.stage_changes.assert_called()
        mock_repo_engine.perform_commit.assert_not_called()

        # Verify error state
        repo_state = runtime_workflow.repo_states[repo_id]
        assert repo_state.status == RepositoryStatus.ERROR

    @pytest.mark.asyncio
    async def test_execute_sequence_commit_failure(
        self, runtime_workflow: RuntimeWorkflow, mock_repo_engine: AsyncMock
    ):
        """Test workflow handles commit failure."""
        repo_id = "test_repo_1"

        # Mock commit failure
        mock_repo_engine.perform_commit.return_value = CommitResult(success=False, message="Commit error")

        await runtime_workflow.execute_action_sequence(repo_id)

        # Should complete workflow but with error state
        mock_repo_engine.perform_commit.assert_called()
        mock_repo_engine.perform_push.assert_not_called()

        # Verify error state
        repo_state = runtime_workflow.repo_states[repo_id]
        assert repo_state.status == RepositoryStatus.ERROR

    @pytest.mark.asyncio
    async def test_execute_sequence_push_failure(
        self, runtime_workflow: RuntimeWorkflow, mock_repo_engine: AsyncMock
    ):
        """Test workflow handles push failure gracefully."""
        repo_id = "test_repo_1"

        # Mock push failure
        mock_repo_engine.perform_push.return_value = PushResult(success=False, message="Push error")

        await runtime_workflow.execute_action_sequence(repo_id)

        # Should complete workflow despite push failure
        mock_repo_engine.perform_push.assert_called()

        # Verify successful commit despite push failure
        repo_state = runtime_workflow.repo_states[repo_id]
        assert repo_state.last_commit_short_hash == "abc1234"

    async def test_execute_sequence_no_commit_hash(
        self, runtime_workflow: RuntimeWorkflow, mock_repo_engine: AsyncMock
    ):
        """Test workflow handles commit with no hash (e.g., no changes)."""
        repo_id = "test_repo_1"

        # Mock commit with no hash
        mock_repo_engine.perform_commit.return_value = CommitResult(success=True, commit_hash=None)

        await runtime_workflow.execute_action_sequence(repo_id)

        # Should reset state and not proceed to push
        mock_repo_engine.perform_push.assert_not_called()

        # Verify state was reset
        repo_state = runtime_workflow.repo_states[repo_id]
        assert repo_state.last_commit_short_hash is None

    def test_emit_event_with_event_collector(self, runtime_workflow: RuntimeWorkflow):
        """Test event emission with standalone event collector."""
        mock_event_collector = MagicMock()
        runtime_workflow.event_collector = mock_event_collector

        test_event = MagicMock()
        runtime_workflow._emit_event(test_event)

        mock_event_collector.emit.assert_called_once_with(test_event)

    def test_emit_event_with_tui_event_collector(self, runtime_workflow: RuntimeWorkflow):
        """Test event emission with TUI event collector."""
        mock_tui_event_collector = MagicMock()
        runtime_workflow.tui.app.event_collector = mock_tui_event_collector

        test_event = MagicMock()
        runtime_workflow._emit_event(test_event)

        mock_tui_event_collector.emit.assert_called_once_with(test_event)

    def test_emit_event_no_collector(self, runtime_workflow: RuntimeWorkflow):
        """Test event emission when no event collector is available."""
        # Remove event collectors
        runtime_workflow.event_collector = None
        del runtime_workflow.tui.app.event_collector

        test_event = MagicMock()
        # Should not raise an error
        runtime_workflow._emit_event(test_event)

    @pytest.mark.asyncio
    async def test_delayed_reset_after_external_commit(self, runtime_workflow: RuntimeWorkflow):
        """Test delayed reset after external commit detection."""
        repo_state = runtime_workflow.repo_states["test_repo_1"]

        # Mock the sleep to avoid actual delay in tests
        with patch("asyncio.sleep") as mock_sleep:
            await runtime_workflow._delayed_reset_after_external_commit(repo_state)

        mock_sleep.assert_called_once_with(2.0)
        runtime_workflow.tui.post_state_update.assert_called()

    @pytest.mark.asyncio
    async def test_execute_sequence_with_exception(
        self, runtime_workflow: RuntimeWorkflow, mock_repo_engine: AsyncMock
    ):
        """Test workflow handles unexpected exceptions gracefully."""
        repo_id = "test_repo_1"

        # Mock an exception during status check
        mock_repo_engine.get_status.side_effect = Exception("Unexpected error")

        await runtime_workflow.execute_action_sequence(repo_id)

        # Should handle exception and set error state
        repo_state = runtime_workflow.repo_states[repo_id]
        assert repo_state.status == RepositoryStatus.ERROR
        assert "Action failure" in repo_state.error_message

    async def test_llm_provider_failure_handling(
        self, runtime_workflow: RuntimeWorkflow, mock_repo_engine: AsyncMock
    ):
        """Test workflow handles LLM provider initialization failure."""
        repo_id = "test_repo_1"

        # Enable LLM but make provider creation fail
        repo_config = runtime_workflow.config.repositories[repo_id]
        repo_config.llm = MagicMock()
        repo_config.llm.enabled = True

        # Mock LLM provider manager to return None
        runtime_workflow._llm_manager.get_llm_provider = MagicMock(return_value=None)

        await runtime_workflow.execute_action_sequence(repo_id)

        # Should handle LLM failure and set error state
        repo_state = runtime_workflow.repo_states[repo_id]
        assert repo_state.status == RepositoryStatus.ERROR
        assert "LLM provider failed" in repo_state.error_message

    @pytest.mark.asyncio
    async def test_push_blocked_on_merge_conflict_detection(
        self, runtime_workflow: RuntimeWorkflow, mock_repo_engine: AsyncMock
    ):
        """Test push is blocked when merge conflicts are detected with upstream."""
        repo_id = "test_repo_1"

        # Configure conflict detection to return conflicts
        mock_repo_engine.operations.check_upstream_conflicts = AsyncMock(
            return_value={
                "has_conflicts": True,
                "conflict_files": ["src/main.py", "src/utils.py"],
                "diverged": False,
            }
        )

        await runtime_workflow.execute_action_sequence(repo_id)

        # Commit should have succeeded
        mock_repo_engine.perform_commit.assert_called_once()

        # Push should NOT have been called (blocked by conflict detection)
        mock_repo_engine.perform_push.assert_not_called()

        # Verify circuit breaker was triggered (status may be reset but flag persists)
        repo_state = runtime_workflow.repo_states[repo_id]
        assert repo_state.circuit_breaker_triggered is True
        assert "conflict" in repo_state.circuit_breaker_reason.lower()

    @pytest.mark.asyncio
    async def test_push_blocked_on_branch_divergence(
        self, runtime_workflow: RuntimeWorkflow, mock_repo_engine: AsyncMock
    ):
        """Test push is blocked when branch has diverged from upstream."""
        repo_id = "test_repo_1"

        # Configure conflict detection to return divergence
        mock_repo_engine.operations.check_upstream_conflicts = AsyncMock(
            return_value={
                "has_conflicts": False,
                "diverged": True,
                "ahead": 3,
                "behind": 5,
            }
        )

        await runtime_workflow.execute_action_sequence(repo_id)

        # Commit should have succeeded
        mock_repo_engine.perform_commit.assert_called_once()

        # Push should NOT have been called (blocked by divergence)
        mock_repo_engine.perform_push.assert_not_called()

        # Verify circuit breaker was triggered (status may be reset but flag persists)
        repo_state = runtime_workflow.repo_states[repo_id]
        assert repo_state.circuit_breaker_triggered is True
        assert "diverged" in repo_state.circuit_breaker_reason.lower()

    @pytest.mark.asyncio
    async def test_push_proceeds_when_no_conflicts(
        self, runtime_workflow: RuntimeWorkflow, mock_repo_engine: AsyncMock
    ):
        """Test push proceeds normally when no conflicts or divergence detected."""
        repo_id = "test_repo_1"

        # Configure conflict detection to return no issues
        mock_repo_engine.operations.check_upstream_conflicts = AsyncMock(
            return_value={
                "has_conflicts": False,
                "diverged": False,
                "ahead": 1,
                "behind": 0,
            }
        )

        await runtime_workflow.execute_action_sequence(repo_id)

        # Both commit and push should have been called
        mock_repo_engine.perform_commit.assert_called_once()
        mock_repo_engine.perform_push.assert_called_once()

        # Verify no circuit breaker
        repo_state = runtime_workflow.repo_states[repo_id]
        assert repo_state.circuit_breaker_triggered is False


# 🔼⚙️🔚
