# tests/unit/events/test_git_events.py

"""
Tests for git-specific events.
"""

from datetime import datetime

from supsrc.engines.git.events import GitBranchEvent, GitCommitEvent, GitPushEvent, GitStageEvent


def test_git_commit_event_creation() -> None:
    """Test creating a GitCommitEvent."""
    event = GitCommitEvent(
        description="Auto-commit performed",
        commit_hash="abc123def456",
        branch="main",
        files_changed=3,
    )

    assert event.source == "git"
    assert event.description == "Auto-commit performed"
    assert event.commit_hash == "abc123def456"
    assert event.branch == "main"
    assert event.files_changed == 3
    assert isinstance(event.timestamp, datetime)


def test_git_commit_event_format() -> None:
    """Test GitCommitEvent formatting."""
    event = GitCommitEvent(
        description="Test commit",
        commit_hash="abc123def456",
        branch="feature-branch",
        files_changed=5,
    )

    formatted = event.format()
    assert "📝" in formatted  # Commit emoji
    assert "5 files" in formatted
    assert "abc123d" in formatted  # Shortened hash
    assert "feature-branch" in formatted


def test_git_push_event_creation() -> None:
    """Test creating a GitPushEvent."""
    event = GitPushEvent(
        description="Pushed to remote",
        remote="origin",
        branch="main",
        commits_pushed=2,
    )

    assert event.source == "git"
    assert event.remote == "origin"
    assert event.branch == "main"
    assert event.commits_pushed == 2


def test_git_push_event_format() -> None:
    """Test GitPushEvent formatting."""
    event = GitPushEvent(
        description="Push complete",
        remote="upstream",
        branch="develop",
        commits_pushed=3,
    )

    formatted = event.format()
    assert "🚀" in formatted  # Push emoji
    assert "3 commits" in formatted
    assert "upstream/develop" in formatted


def test_git_stage_event_creation() -> None:
    """Test creating a GitStageEvent."""
    files = ["src/main.py", "tests/test_main.py", "README.md"]
    event = GitStageEvent(
        description="Files staged",
        files_staged=files,
    )

    assert event.source == "git"
    assert event.files_staged == files


def test_git_stage_event_format() -> None:
    """Test GitStageEvent formatting."""
    event = GitStageEvent(
        description="Staging complete",
        files_staged=["file1.py", "file2.py"],
    )

    formatted = event.format()
    assert "📋" in formatted  # Stage emoji
    assert "2 files" in formatted


def test_git_stage_event_empty_files() -> None:
    """Test GitStageEvent with no files."""
    event = GitStageEvent(description="No files to stage")

    formatted = event.format()
    assert "0 files" in formatted


def test_git_branch_event_creation() -> None:
    """Test creating a GitBranchEvent."""
    event = GitBranchEvent(
        description="Branch switched",
        old_branch="main",
        new_branch="feature-x",
    )

    assert event.source == "git"
    assert event.old_branch == "main"
    assert event.new_branch == "feature-x"


def test_git_branch_event_format_with_old_branch() -> None:
    """Test GitBranchEvent formatting when switching from a branch."""
    event = GitBranchEvent(
        description="Switched branches",
        old_branch="main",
        new_branch="feature-y",
    )

    formatted = event.format()
    assert "🌿" in formatted  # Branch emoji
    assert "Switched from main to feature-y" in formatted


def test_git_branch_event_format_no_old_branch() -> None:
    """Test GitBranchEvent formatting when no old branch (initial checkout)."""
    event = GitBranchEvent(
        description="Initial branch",
        old_branch=None,
        new_branch="main",
    )

    formatted = event.format()
    assert "🌿" in formatted  # Branch emoji
    assert "On branch main" in formatted
    assert "Switched from" not in formatted


def test_all_git_events_have_git_source() -> None:
    """Test that all git events have 'git' as source."""
    commit_event = GitCommitEvent(
        description="Test",
        commit_hash="abc123",
        branch="main",
        files_changed=1,
    )

    push_event = GitPushEvent(
        description="Test",
        remote="origin",
        branch="main",
        commits_pushed=1,
    )

    stage_event = GitStageEvent(description="Test")

    branch_event = GitBranchEvent(
        description="Test",
        old_branch="main",
        new_branch="feature",
    )

    assert commit_event.source == "git"
    assert push_event.source == "git"
    assert stage_event.source == "git"
    assert branch_event.source == "git"
