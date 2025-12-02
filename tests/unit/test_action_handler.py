#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for the ActionHandler component."""

import pytest
from provide.testkit.mocking import AsyncMock, MagicMock

from supsrc.config import SupsrcConfig
from supsrc.protocols import CommitResult, PushResult, RepoStatusResult, StageResult
from supsrc.runtime.action_handler import ActionHandler
from supsrc.runtime.tui_interface import TUIInterface
from supsrc.state import RepositoryState, RepositoryStatus


@pytest.fixture
def mock_repo_engine() -> AsyncMock:
    """Provides a mock RepositoryEngine with default success values."""
    engine = AsyncMock()
    engine.get_status.return_value = RepoStatusResult(success=True, is_clean=False)
    engine.stage_changes.return_value = StageResult(success=True, files_staged=["file.txt"])
    engine.perform_commit.return_value = CommitResult(success=True, commit_hash="abc1234")
    engine.perform_push.return_value = PushResult(success=True)
    # Configure operations as a MagicMock with async method for conflict checking
    engine.operations = MagicMock()
    # Default: no file warnings (sync method)
    engine.operations.analyze_files_for_warnings.return_value = []
    # Default: no conflicts (async method)
    engine.operations.check_upstream_conflicts = AsyncMock(return_value={"has_conflicts": False, "diverged": False})
    return engine


@pytest.fixture
def action_handler(
    minimal_config: SupsrcConfig,
    mock_repo_engine: AsyncMock,
) -> ActionHandler:
    """Provides an ActionHandler instance with mocked dependencies."""
    repo_id = "test_repo_1"
    states = {repo_id: RepositoryState(repo_id=repo_id)}
    engines = {repo_id: mock_repo_engine}
    tui = MagicMock(spec=TUIInterface)
    tui.app = MagicMock()  # Add app attribute for event emission
    return ActionHandler(minimal_config, states, engines, tui)


@pytest.mark.asyncio
class TestActionHandler:
    """Comprehensive tests for the ActionHandler."""

    async def test_execute_full_sequence_success(
        self, action_handler: ActionHandler, mock_repo_engine: AsyncMock
    ):
        """Verify all engine methods are called in a successful workflow."""
        repo_id = "test_repo_1"
        await action_handler.execute_action_sequence(repo_id)

        # Note: get_status is called twice (once for initial status, once for LLM summary)
        assert mock_repo_engine.get_status.call_count >= 1
        mock_repo_engine.stage_changes.assert_called_once()
        mock_repo_engine.perform_commit.assert_called_once()
        mock_repo_engine.perform_push.assert_called_once()
        assert action_handler.repo_states[repo_id].status == RepositoryStatus.IDLE

    async def test_skips_actions_if_repo_is_clean(
        self, action_handler: ActionHandler, mock_repo_engine: AsyncMock
    ):
        """Verify workflow halts if get_status reports the repo is clean."""
        mock_repo_engine.get_status.return_value = RepoStatusResult(success=True, is_clean=True)
        repo_id = "test_repo_1"

        await action_handler.execute_action_sequence(repo_id)

        mock_repo_engine.get_status.assert_called_once()
        mock_repo_engine.stage_changes.assert_not_called()
        mock_repo_engine.perform_commit.assert_not_called()
        mock_repo_engine.perform_push.assert_not_called()
        # When repo is clean, status is EXTERNAL_COMMIT_DETECTED (not IDLE)
        assert (
            action_handler.repo_states[repo_id].status == RepositoryStatus.EXTERNAL_COMMIT_DETECTED
        )

    async def test_aborts_on_status_failure(
        self, action_handler: ActionHandler, mock_repo_engine: AsyncMock
    ):
        """Verify workflow aborts if get_status fails."""
        mock_repo_engine.get_status.return_value = RepoStatusResult(success=False)
        repo_id = "test_repo_1"
        state = action_handler.repo_states[repo_id]

        await action_handler.execute_action_sequence(repo_id)

        assert state.status == RepositoryStatus.ERROR
        mock_repo_engine.stage_changes.assert_not_called()

    async def test_aborts_on_merge_conflict(
        self, action_handler: ActionHandler, mock_repo_engine: AsyncMock
    ):
        """Verify workflow aborts and freezes the repo if conflicts are detected."""
        mock_repo_engine.get_status.return_value = RepoStatusResult(
            success=True, is_conflicted=True
        )
        repo_id = "test_repo_1"
        state = action_handler.repo_states[repo_id]

        await action_handler.execute_action_sequence(repo_id)

        # Should set CONFLICT_DETECTED status (not generic ERROR)
        assert state.status == RepositoryStatus.CONFLICT_DETECTED
        assert state.is_frozen is True
        assert state.freeze_reason == "Merge conflicts detected"
        # Conflict message is in action_description or freeze_reason, not error_message
        assert "conflict" in (state.action_description or state.freeze_reason or "").lower()
        mock_repo_engine.stage_changes.assert_not_called()

    async def test_handles_commit_failure_gracefully(
        self, action_handler: ActionHandler, mock_repo_engine: AsyncMock
    ):
        """Verify a commit failure sets ERROR state and prevents push."""
        mock_repo_engine.perform_commit.return_value = CommitResult(
            success=False, message="Git error"
        )
        repo_id = "test_repo_1"
        state = action_handler.repo_states[repo_id]

        await action_handler.execute_action_sequence(repo_id)

        assert state.status == RepositoryStatus.ERROR
        mock_repo_engine.perform_push.assert_not_called()

    async def test_handles_push_failure_gracefully(
        self, action_handler: ActionHandler, mock_repo_engine: AsyncMock
    ):
        """Verify a push failure is logged but the state still resets."""
        mock_repo_engine.perform_push.return_value = PushResult(
            success=False, message="Connection failed"
        )
        repo_id = "test_repo_1"
        state = action_handler.repo_states[repo_id]

        await action_handler.execute_action_sequence(repo_id)

        # A push failure is not a blocking error; the commit is safe.
        # The state should reset to IDLE.
        assert state.status == RepositoryStatus.IDLE
        action_handler.tui.post_log_update.assert_any_call(
            repo_id, "WARNING", "Push failed: Connection failed"
        )

    async def test_handles_skipped_push(
        self, action_handler: ActionHandler, mock_repo_engine: AsyncMock
    ):
        """Verify a skipped push is handled and state resets."""
        mock_repo_engine.perform_push.return_value = PushResult(success=True, skipped=True)
        repo_id = "test_repo_1"
        state = action_handler.repo_states[repo_id]

        await action_handler.execute_action_sequence(repo_id)

        assert state.status == RepositoryStatus.IDLE
        action_handler.tui.post_log_update.assert_any_call(
            repo_id, "INFO", "Push skipped by configuration."
        )

    async def test_handles_skipped_commit(
        self, action_handler: ActionHandler, mock_repo_engine: AsyncMock
    ):
        """Verify the workflow ends cleanly if commit is skipped (no changes)."""
        mock_repo_engine.perform_commit.return_value = CommitResult(success=True, commit_hash=None)
        repo_id = "test_repo_1"
        state = action_handler.repo_states[repo_id]

        await action_handler.execute_action_sequence(repo_id)

        mock_repo_engine.perform_push.assert_not_called()
        assert state.status == RepositoryStatus.IDLE


# 🔼⚙️🔚
