#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Comprehensive tests for the Git engine implementation."""

from pathlib import Path
import subprocess

import pygit2
import pytest

from supsrc.config import GlobalConfig
from supsrc.engines.git import GitEngine, GitRepoSummary
from supsrc.protocols import CommitResult, PushResult, RepoStatusResult, StageResult
from supsrc.state import RepositoryState


@pytest.fixture
def git_engine() -> GitEngine:
    """Create a GitEngine instance for testing."""
    return GitEngine()


@pytest.fixture
def mock_repo_state() -> RepositoryState:
    """Create a mock repository state for testing."""
    return RepositoryState(repo_id="test-repo")


@pytest.fixture
def mock_global_config() -> GlobalConfig:
    """Create a mock global configuration for testing."""
    return GlobalConfig()


@pytest.fixture
def git_repo_path(tmp_path: Path) -> Path:
    """Create a temporary Git repository for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pytest.skip("Git not available for testing")

    # Initialize repository
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    # Configure Git user for unit testing (disable GPG signing to avoid issues)
    subprocess.run(["git", "config", "user.name", "Git Engine Test User"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.email", "gitengine@supsrc.example.com"], cwd=repo_path, check=True)
    # Disable GPG signing to prevent tests from failing if user has global GPG config
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "gpg.program", ""], cwd=repo_path, check=True)

    # Create initial commit
    (repo_path / "README.md").write_text("Initial commit")
    subprocess.run(["git", "add", "README.md"], cwd=repo_path, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=repo_path, check=True)

    return repo_path


class TestGitEngine:
    """Test GitEngine functionality."""

    async def test_get_summary_normal_repo(self, git_engine: GitEngine, git_repo_path: Path) -> None:
        """Test getting summary from a normal repository."""
        summary = await git_engine.get_summary(git_repo_path)

        assert isinstance(summary, GitRepoSummary)
        assert not summary.is_empty
        assert summary.head_ref_name in ["main", "master"]  # Git defaults vary
        assert summary.head_commit_hash is not None
        assert len(summary.head_commit_hash) == 40  # Full SHA
        assert summary.head_commit_message_summary == "Initial commit"

    async def test_get_summary_nonexistent_repo(self, git_engine: GitEngine, tmp_path: Path) -> None:
        """Test getting summary from a non-existent repository."""
        nonexistent_path = tmp_path / "nonexistent"

        summary = await git_engine.get_summary(nonexistent_path)

        assert summary.head_ref_name == "ERROR"
        assert "Repository not found" in summary.head_commit_message_summary

    async def test_get_status_clean_repo(
        self,
        git_engine: GitEngine,
        git_repo_path: Path,
        mock_repo_state: RepositoryState,
        mock_global_config: GlobalConfig,
    ) -> None:
        """Test getting status from a clean repository."""
        config = {"type": "supsrc.engines.git"}

        result = await git_engine.get_status(mock_repo_state, config, mock_global_config, git_repo_path)

        assert isinstance(result, RepoStatusResult)
        assert result.success
        assert result.is_clean
        assert not result.has_staged_changes
        assert not result.has_unstaged_changes
        assert not result.has_untracked_changes
        assert not result.is_conflicted

    async def test_get_status_with_changes(
        self,
        git_engine: GitEngine,
        git_repo_path: Path,
        mock_repo_state: RepositoryState,
        mock_global_config: GlobalConfig,
    ) -> None:
        """Test getting status from a repository with changes."""
        config = {"type": "supsrc.engines.git"}

        # Create an untracked file
        (git_repo_path / "new_file.txt").write_text("New content")

        # Modify existing file
        (git_repo_path / "README.md").write_text("Modified content")

        result = await git_engine.get_status(mock_repo_state, config, mock_global_config, git_repo_path)

        assert result.success
        assert not result.is_clean
        assert result.has_untracked_changes
        assert result.has_unstaged_changes
        assert not result.has_staged_changes

    async def test_stage_changes_all(
        self,
        git_engine: GitEngine,
        git_repo_path: Path,
        mock_repo_state: RepositoryState,
        mock_global_config: GlobalConfig,
    ) -> None:
        """Test staging all changes."""
        config = {"type": "supsrc.engines.git"}

        # Create changes
        (git_repo_path / "new_file.txt").write_text("New content")
        (git_repo_path / "README.md").write_text("Modified content")

        result = await git_engine.stage_changes(
            None, mock_repo_state, config, mock_global_config, git_repo_path
        )

        assert isinstance(result, StageResult)
        assert result.success
        assert len(result.files_staged) == 2
        assert "new_file.txt" in result.files_staged
        assert "README.md" in result.files_staged

    async def test_perform_commit_success(
        self,
        git_engine: GitEngine,
        git_repo_path: Path,
        mock_repo_state: RepositoryState,
        mock_global_config: GlobalConfig,
    ) -> None:
        """Test successful commit operation."""
        config = {
            "type": "supsrc.engines.git",
            "commit_message_template": "Test commit: {{timestamp}}",
        }

        # Create a file and stage it using pygit2 directly to ensure
        # the index is in a known state for the commit test.
        (git_repo_path / "new_file.txt").write_text("New content")
        repo = pygit2.Repository(pygit2.discover_repository(str(git_repo_path)))
        repo.index.add("new_file.txt")
        repo.index.write()

        result = await git_engine.perform_commit(
            "Test commit: {{timestamp}}",
            mock_repo_state,
            config,
            mock_global_config,
            git_repo_path,
        )

        assert isinstance(result, CommitResult)
        assert result.success
        assert result.commit_hash is not None

    async def test_perform_commit_no_changes(
        self,
        git_engine: GitEngine,
        git_repo_path: Path,
        mock_repo_state: RepositoryState,
        mock_global_config: GlobalConfig,
    ) -> None:
        """Test commit with no staged changes."""
        config = {"type": "supsrc.engines.git"}

        result = await git_engine.perform_commit(
            "Test commit", mock_repo_state, config, mock_global_config, git_repo_path
        )

        assert result.success
        assert result.commit_hash is None
        assert "No changes" in result.message

    async def test_perform_push_disabled(
        self,
        git_engine: GitEngine,
        git_repo_path: Path,
        mock_repo_state: RepositoryState,
        mock_global_config: GlobalConfig,
    ) -> None:
        """Test push when auto_push is disabled."""
        config = {"type": "supsrc.engines.git", "auto_push": False}

        result = await git_engine.perform_push(mock_repo_state, config, mock_global_config, git_repo_path)

        assert isinstance(result, PushResult)
        assert result.success
        assert result.skipped
        assert "disabled" in result.message

    async def test_get_status_merge_in_progress(
        self,
        git_engine: GitEngine,
        git_repo_path: Path,
        mock_repo_state: RepositoryState,
        mock_global_config: GlobalConfig,
    ) -> None:
        """Test status detection when merge is in progress."""
        config = {"type": "supsrc.engines.git"}

        # Simulate merge in progress by creating MERGE_HEAD file
        git_dir = git_repo_path / ".git"
        (git_dir / "MERGE_HEAD").write_text("0000000000000000000000000000000000000000")

        result = await git_engine.get_status(mock_repo_state, config, mock_global_config, git_repo_path)

        assert result.success
        assert result.is_merge_in_progress
        assert not result.is_rebase_in_progress
        assert not result.is_cherry_pick_in_progress
        assert not result.is_revert_in_progress

        # Clean up
        (git_dir / "MERGE_HEAD").unlink()

    async def test_get_status_rebase_in_progress(
        self,
        git_engine: GitEngine,
        git_repo_path: Path,
        mock_repo_state: RepositoryState,
        mock_global_config: GlobalConfig,
    ) -> None:
        """Test status detection when rebase is in progress."""
        config = {"type": "supsrc.engines.git"}

        # Simulate rebase in progress by creating REBASE_MERGE directory
        git_dir = git_repo_path / ".git"
        (git_dir / "REBASE_MERGE").mkdir()

        result = await git_engine.get_status(mock_repo_state, config, mock_global_config, git_repo_path)

        assert result.success
        assert not result.is_merge_in_progress
        assert result.is_rebase_in_progress
        assert not result.is_cherry_pick_in_progress
        assert not result.is_revert_in_progress

        # Clean up
        (git_dir / "REBASE_MERGE").rmdir()

    async def test_get_status_rebase_apply_in_progress(
        self,
        git_engine: GitEngine,
        git_repo_path: Path,
        mock_repo_state: RepositoryState,
        mock_global_config: GlobalConfig,
    ) -> None:
        """Test status detection when rebase-apply is in progress."""
        config = {"type": "supsrc.engines.git"}

        # Simulate rebase-apply in progress by creating rebase-apply directory
        git_dir = git_repo_path / ".git"
        (git_dir / "rebase-apply").mkdir()

        result = await git_engine.get_status(mock_repo_state, config, mock_global_config, git_repo_path)

        assert result.success
        assert not result.is_merge_in_progress
        assert result.is_rebase_in_progress
        assert not result.is_cherry_pick_in_progress
        assert not result.is_revert_in_progress

        # Clean up
        (git_dir / "rebase-apply").rmdir()

    async def test_get_status_cherry_pick_in_progress(
        self,
        git_engine: GitEngine,
        git_repo_path: Path,
        mock_repo_state: RepositoryState,
        mock_global_config: GlobalConfig,
    ) -> None:
        """Test status detection when cherry-pick is in progress."""
        config = {"type": "supsrc.engines.git"}

        # Simulate cherry-pick in progress by creating CHERRY_PICK_HEAD file
        git_dir = git_repo_path / ".git"
        (git_dir / "CHERRY_PICK_HEAD").write_text("0000000000000000000000000000000000000000")

        result = await git_engine.get_status(mock_repo_state, config, mock_global_config, git_repo_path)

        assert result.success
        assert not result.is_merge_in_progress
        assert not result.is_rebase_in_progress
        assert result.is_cherry_pick_in_progress
        assert not result.is_revert_in_progress

        # Clean up
        (git_dir / "CHERRY_PICK_HEAD").unlink()

    async def test_get_status_revert_in_progress(
        self,
        git_engine: GitEngine,
        git_repo_path: Path,
        mock_repo_state: RepositoryState,
        mock_global_config: GlobalConfig,
    ) -> None:
        """Test status detection when revert is in progress."""
        config = {"type": "supsrc.engines.git"}

        # Simulate revert in progress by creating REVERT_HEAD file
        git_dir = git_repo_path / ".git"
        (git_dir / "REVERT_HEAD").write_text("0000000000000000000000000000000000000000")

        result = await git_engine.get_status(mock_repo_state, config, mock_global_config, git_repo_path)

        assert result.success
        assert not result.is_merge_in_progress
        assert not result.is_rebase_in_progress
        assert not result.is_cherry_pick_in_progress
        assert result.is_revert_in_progress

        # Clean up
        (git_dir / "REVERT_HEAD").unlink()

    async def test_get_status_multiple_special_states(
        self,
        git_engine: GitEngine,
        git_repo_path: Path,
        mock_repo_state: RepositoryState,
        mock_global_config: GlobalConfig,
    ) -> None:
        """Test status detection when multiple special states exist (edge case)."""
        config = {"type": "supsrc.engines.git"}

        # Simulate both merge and cherry-pick in progress (unlikely but possible)
        git_dir = git_repo_path / ".git"
        (git_dir / "MERGE_HEAD").write_text("0000000000000000000000000000000000000000")
        (git_dir / "CHERRY_PICK_HEAD").write_text("0000000000000000000000000000000000000000")

        result = await git_engine.get_status(mock_repo_state, config, mock_global_config, git_repo_path)

        assert result.success
        assert result.is_merge_in_progress
        assert result.is_cherry_pick_in_progress

        # Clean up
        (git_dir / "MERGE_HEAD").unlink()
        (git_dir / "CHERRY_PICK_HEAD").unlink()


# 🔼⚙️🔚
