#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for git-specific events without importing git dependencies."""

from datetime import datetime

import attrs

from supsrc.events.base import BaseEvent


@attrs.define
class MockGitCommitEvent(BaseEvent):
    """Mock GitCommitEvent for testing."""

    source: str = attrs.field(default="git", init=False)
    commit_hash: str = attrs.field(kw_only=True)
    branch: str = attrs.field(kw_only=True)
    files_changed: int = attrs.field(kw_only=True)

    def format(self) -> str:
        """Format commit event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return (
            f"[{time_str}] 📝 Committed {self.files_changed} files [{self.commit_hash[:7]}] on {self.branch}"
        )


def test_mock_git_commit_event_creation() -> None:
    """Test creating a mock GitCommitEvent."""
    event = MockGitCommitEvent(
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


def test_mock_git_commit_event_format() -> None:
    """Test mock GitCommitEvent formatting."""
    event = MockGitCommitEvent(
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


# 🔼⚙️🔚
