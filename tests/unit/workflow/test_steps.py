#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for WorkflowSteps."""

from __future__ import annotations

import pytest
from provide.testkit.mocking import AsyncMock, MagicMock, patch

from supsrc.config import LLMConfig, RepositoryConfig, SupsrcConfig
from supsrc.protocols import RepoStatusResult
from supsrc.runtime.workflow.steps import WorkflowSteps
from supsrc.state import RepositoryState, RepositoryStatus


@pytest.fixture
def mock_dependencies():
    """Provide mocked dependencies for WorkflowSteps."""
    config = MagicMock(spec=SupsrcConfig)
    repo_states = {"test_repo": MagicMock(spec=RepositoryState)}
    repo_engine = AsyncMock()
    # Configure operations as a regular MagicMock to avoid coroutine issues
    repo_engine.operations = MagicMock()
    # Default: no file warnings (empty list)
    repo_engine.operations.analyze_files_for_warnings.return_value = []
    repo_engines = {"test_repo": repo_engine}
    tui = MagicMock()
    emit_event_callback = MagicMock()

    return config, repo_states, repo_engines, tui, emit_event_callback


@pytest.fixture
def workflow_steps(mock_dependencies):
    """Provide WorkflowSteps instance with mocked dependencies."""
    config, repo_states, repo_engines, tui, emit_event_callback = mock_dependencies
    return WorkflowSteps(config, repo_states, repo_engines, tui, emit_event_callback)


@pytest.mark.asyncio
class TestWorkflowSteps:
    """Test suite for WorkflowSteps class."""

    async def test_execute_status_check_success(self, workflow_steps, mock_dependencies):
        """Test successful status check execution."""
        _, repo_states, repo_engines, tui, _ = mock_dependencies
        repo_id = "test_repo"

        # Setup mocks
        repo_state = repo_states[repo_id]
        repo_config = MagicMock(spec=RepositoryConfig)
        repo_engine = repo_engines[repo_id]

        workflow_steps.config.repositories = {repo_id: repo_config}
        workflow_steps.config.global_config = MagicMock()

        # Mock successful status result
        status_result = RepoStatusResult(
            success=True,
            is_clean=False,
            is_conflicted=False,
            total_files=10,
            changed_files=3,
            added_files=1,
            deleted_files=1,
            modified_files=1,
            current_branch="main",
        )
        repo_engine.get_status.return_value = status_result

        result = await workflow_steps.execute_status_check(repo_id)

        assert result is True
        repo_state.update_status.assert_called_with(RepositoryStatus.PROCESSING)
        repo_engine.get_status.assert_called_once()
        tui.post_state_update.assert_called()

        # Verify repository statistics were updated
        assert repo_state.total_files == 10
        assert repo_state.changed_files == 3
        assert repo_state.added_files == 1
        assert repo_state.deleted_files == 1
        assert repo_state.modified_files == 1
        assert repo_state.has_uncommitted_changes is True
        assert repo_state.current_branch == "main"

    async def test_execute_status_check_failure(self, workflow_steps, mock_dependencies):
        """Test status check execution with failure."""
        _, repo_states, repo_engines, _, emit_event = mock_dependencies
        repo_id = "test_repo"

        # Setup mocks
        repo_state = repo_states[repo_id]
        repo_config = MagicMock(spec=RepositoryConfig)
        repo_engine = repo_engines[repo_id]

        workflow_steps.config.repositories = {repo_id: repo_config}
        workflow_steps.config.global_config = MagicMock()

        # Mock failed status result
        status_result = RepoStatusResult(
            success=False,
            message="Git command failed",
            is_clean=False,
            is_conflicted=False,
        )
        repo_engine.get_status.return_value = status_result

        result = await workflow_steps.execute_status_check(repo_id)

        assert result is False
        repo_state.update_status.assert_called_with(
            RepositoryStatus.ERROR, "Status check failed: Git command failed"
        )
        emit_event.assert_called_once()

    async def test_execute_status_check_conflict_detected(self, workflow_steps, mock_dependencies):
        """Test status check execution with conflict detection."""
        _, repo_states, repo_engines, _, emit_event = mock_dependencies
        repo_id = "test_repo"

        # Setup mocks
        repo_state = repo_states[repo_id]
        repo_config = MagicMock(spec=RepositoryConfig)
        repo_engine = repo_engines[repo_id]

        workflow_steps.config.repositories = {repo_id: repo_config}
        workflow_steps.config.global_config = MagicMock()

        # Mock conflicted status result
        status_result = RepoStatusResult(
            success=True,
            is_clean=False,
            is_conflicted=True,
        )
        repo_engine.get_status.return_value = status_result

        result = await workflow_steps.execute_status_check(repo_id)

        assert result is False
        repo_state.update_status.assert_called_with(
            RepositoryStatus.CONFLICT_DETECTED, "Repo has conflicts."
        )
        assert repo_state.is_frozen is True
        assert repo_state.freeze_reason == "Merge conflicts detected"
        assert emit_event.call_count == 2  # ConflictDetectedEvent and RepositoryFrozenEvent

    async def test_execute_status_check_external_commit(self, workflow_steps, mock_dependencies):
        """Test status check execution with external commit detection."""
        _, repo_states, repo_engines, _, emit_event = mock_dependencies
        repo_id = "test_repo"

        # Setup mocks
        repo_state = repo_states[repo_id]
        repo_config = MagicMock(spec=RepositoryConfig)
        repo_engine = repo_engines[repo_id]

        workflow_steps.config.repositories = {repo_id: repo_config}
        workflow_steps.config.global_config = MagicMock()

        # Mock clean status result (external commit)
        status_result = RepoStatusResult(
            success=True,
            is_clean=True,
            is_conflicted=False,
        )
        repo_engine.get_status.return_value = status_result

        result = await workflow_steps.execute_status_check(repo_id)

        assert result is False
        repo_state.update_status.assert_called_with(
            RepositoryStatus.EXTERNAL_COMMIT_DETECTED, "Changes committed externally"
        )
        emit_event.assert_called_once()

    async def test_execute_staging_success(self, workflow_steps, mock_dependencies):
        """Test successful staging execution."""
        _, repo_states, repo_engines, _, _ = mock_dependencies
        repo_id = "test_repo"

        # Setup mocks
        repo_state = repo_states[repo_id]
        repo_config = MagicMock(spec=RepositoryConfig)
        repo_engine = repo_engines[repo_id]

        workflow_steps.config.repositories = {repo_id: repo_config}
        workflow_steps.config.global_config = MagicMock()

        # Mock successful staging result
        from supsrc.protocols import StageResult

        stage_result = StageResult(success=True, files_staged=["file1.txt", "file2.txt"])
        repo_engine.stage_changes.return_value = stage_result

        result = await workflow_steps.execute_staging(repo_id)

        # execute_staging now returns tuple of (success, files_list)
        success, files = result
        assert success is True
        assert files == ["file1.txt", "file2.txt"]
        repo_state.update_status.assert_called_with(RepositoryStatus.STAGING)
        repo_engine.stage_changes.assert_called_once()

    async def test_execute_staging_failure(self, workflow_steps, mock_dependencies):
        """Test staging execution with failure."""
        _, repo_states, repo_engines, _, emit_event = mock_dependencies
        repo_id = "test_repo"

        # Setup mocks
        repo_state = repo_states[repo_id]
        repo_config = MagicMock(spec=RepositoryConfig)
        repo_engine = repo_engines[repo_id]

        workflow_steps.config.repositories = {repo_id: repo_config}
        workflow_steps.config.global_config = MagicMock()

        # Mock failed staging result
        from supsrc.protocols import StageResult

        stage_result = StageResult(success=False, message="Staging failed")
        repo_engine.stage_changes.return_value = stage_result

        result = await workflow_steps.execute_staging(repo_id)

        # execute_staging now returns tuple of (success, files_list)
        success, files = result
        assert success is False
        assert files is None
        repo_state.update_status.assert_called_with(
            RepositoryStatus.ERROR, "Staging failed: Staging failed"
        )
        emit_event.assert_called_once()

    async def test_execute_llm_pipeline_review_veto(self, workflow_steps, mock_dependencies):
        """Test LLM pipeline execution with review veto."""
        _, repo_states, _, _, emit_event = mock_dependencies
        repo_id = "test_repo"

        # Setup mocks
        repo_state = repo_states[repo_id]
        llm_config = MagicMock(spec=LLMConfig)
        llm_config.review_changes = True
        llm_config.run_tests = False
        llm_config.generate_commit_message = False

        llm_provider = AsyncMock()
        llm_provider.review_changes.return_value = (True, "Code quality issues detected")

        staged_diff = "diff content"

        should_continue, commit_message = await workflow_steps.execute_llm_pipeline(
            repo_id, llm_config, llm_provider, staged_diff
        )

        assert should_continue is False
        assert commit_message == ""
        repo_state.update_status.assert_called_with(
            RepositoryStatus.ERROR, "LLM Review Veto: Code quality issues detected"
        )
        emit_event.assert_called_once()

    async def test_execute_llm_pipeline_test_failure(self, workflow_steps, mock_dependencies):
        """Test LLM pipeline execution with test failure."""
        _, repo_states, _, _, emit_event = mock_dependencies
        repo_id = "test_repo"

        # Setup mocks
        repo_state = repo_states[repo_id]
        repo_config = MagicMock(spec=RepositoryConfig)
        repo_config.path = "/test/repo"

        workflow_steps.config.repositories = {repo_id: repo_config}

        llm_config = MagicMock(spec=LLMConfig)
        llm_config.review_changes = False
        llm_config.run_tests = True
        llm_config.test_command = "pytest"
        llm_config.analyze_test_failures = False
        llm_config.generate_commit_message = False

        llm_provider = AsyncMock()
        staged_diff = "diff content"

        # Mock test failure
        with patch("supsrc.runtime.workflow.steps.TestRunner.run_tests") as mock_run_tests:
            mock_run_tests.return_value = (1, "Tests failed", "Error output")

            should_continue, commit_message = await workflow_steps.execute_llm_pipeline(
                repo_id, llm_config, llm_provider, staged_diff
            )

        assert should_continue is False
        assert commit_message == ""
        repo_state.update_status.assert_called_with(
            RepositoryStatus.ERROR, "Tests Failed: Test run failed."
        )
        emit_event.assert_called_once()

    async def test_execute_llm_pipeline_success_with_message_generation(
        self, workflow_steps, mock_dependencies
    ):
        """Test successful LLM pipeline execution with commit message generation."""
        _, repo_states, _, _, _ = mock_dependencies
        repo_id = "test_repo"

        # Setup mocks
        repo_state = repo_states[repo_id]
        llm_config = MagicMock(spec=LLMConfig)
        llm_config.review_changes = False
        llm_config.run_tests = False
        llm_config.generate_commit_message = True
        llm_config.use_conventional_commit = True

        llm_provider = AsyncMock()
        llm_provider.generate_commit_message.return_value = "feat: add new feature"

        staged_diff = "diff content"

        should_continue, commit_message = await workflow_steps.execute_llm_pipeline(
            repo_id, llm_config, llm_provider, staged_diff
        )

        assert should_continue is True
        assert commit_message == "feat: add new feature\n\n{{change_summary}}"
        repo_state.update_status.assert_called_with(RepositoryStatus.GENERATING_COMMIT)
        llm_provider.generate_commit_message.assert_called_once_with(staged_diff, True)

    async def test_execute_staging_blocks_on_large_file_warning(
        self, workflow_steps, mock_dependencies
    ):
        """Test staging is blocked when large file warnings are detected."""
        _, repo_states, repo_engines, tui, emit_event = mock_dependencies
        repo_id = "test_repo"

        # Setup mocks
        repo_state = repo_states[repo_id]
        repo_config = MagicMock(spec=RepositoryConfig)
        repo_engine = repo_engines[repo_id]

        workflow_steps.config.repositories = {repo_id: repo_config}
        workflow_steps.config.global_config = MagicMock()
        workflow_steps.config.global_config.large_file_threshold_bytes = 1_000_000

        # Mock large file warning
        repo_engine.operations.analyze_files_for_warnings.return_value = [
            {"path": "large_model.bin", "type": "large_file", "size": 5_000_000}
        ]

        result = await workflow_steps.execute_staging(repo_id)

        # Should block staging and trigger circuit breaker
        success, files = result
        assert success is False
        assert files is None

        # Verify circuit breaker was triggered
        repo_state.trigger_circuit_breaker.assert_called_once()
        call_args = repo_state.trigger_circuit_breaker.call_args
        assert "large file" in call_args[0][0].lower()  # reason mentions large file
        assert call_args[0][1] == RepositoryStatus.BULK_CHANGE_PAUSED

        # Verify event was emitted
        emit_event.assert_called_once()

        # Verify stage_changes was NOT called
        repo_engine.stage_changes.assert_not_called()

    async def test_execute_staging_blocks_on_binary_file_warning(
        self, workflow_steps, mock_dependencies
    ):
        """Test staging is blocked when binary file warnings are detected."""
        _, repo_states, repo_engines, tui, emit_event = mock_dependencies
        repo_id = "test_repo"

        # Setup mocks
        repo_state = repo_states[repo_id]
        repo_config = MagicMock(spec=RepositoryConfig)
        repo_engine = repo_engines[repo_id]

        workflow_steps.config.repositories = {repo_id: repo_config}
        workflow_steps.config.global_config = MagicMock()
        workflow_steps.config.global_config.large_file_threshold_bytes = 1_000_000

        # Mock binary file warning
        repo_engine.operations.analyze_files_for_warnings.return_value = [
            {"path": "image.png", "type": "binary_file", "size": 50_000}
        ]

        result = await workflow_steps.execute_staging(repo_id)

        # Should block staging and trigger circuit breaker
        success, files = result
        assert success is False
        assert files is None

        # Verify circuit breaker was triggered
        repo_state.trigger_circuit_breaker.assert_called_once()
        call_args = repo_state.trigger_circuit_breaker.call_args
        assert "binary file" in call_args[0][0].lower()  # reason mentions binary file
        assert call_args[0][1] == RepositoryStatus.BULK_CHANGE_PAUSED

        # Verify stage_changes was NOT called
        repo_engine.stage_changes.assert_not_called()

    async def test_execute_staging_blocks_on_multiple_warnings(
        self, workflow_steps, mock_dependencies
    ):
        """Test staging is blocked when multiple file warnings are detected."""
        _, repo_states, repo_engines, tui, emit_event = mock_dependencies
        repo_id = "test_repo"

        # Setup mocks
        repo_state = repo_states[repo_id]
        repo_config = MagicMock(spec=RepositoryConfig)
        repo_engine = repo_engines[repo_id]

        workflow_steps.config.repositories = {repo_id: repo_config}
        workflow_steps.config.global_config = MagicMock()
        workflow_steps.config.global_config.large_file_threshold_bytes = 1_000_000

        # Mock multiple warnings
        repo_engine.operations.analyze_files_for_warnings.return_value = [
            {"path": "large_model.bin", "type": "large_file", "size": 5_000_000},
            {"path": "image.png", "type": "binary_file", "size": 50_000},
        ]

        result = await workflow_steps.execute_staging(repo_id)

        # Should block staging
        success, files = result
        assert success is False

        # Verify circuit breaker was triggered with both warning types
        repo_state.trigger_circuit_breaker.assert_called_once()
        call_args = repo_state.trigger_circuit_breaker.call_args
        reason = call_args[0][0].lower()
        assert "large file" in reason
        assert "binary file" in reason


# 🔼⚙️🔚
