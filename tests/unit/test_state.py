#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Comprehensive tests for repository state management."""

from provide.testkit.mocking import Mock, patch

from supsrc.state import RepositoryState, RepositoryStatus


class TestRepositoryState:
    """Test repository state management functionality."""

    def test_initial_state(self) -> None:
        """Test initial repository state."""
        state = RepositoryState(repo_id="test-repo")

        assert state.repo_id == "test-repo"
        assert state.status == RepositoryStatus.IDLE
        assert state.last_change_time is None
        assert state.save_count == 0
        assert state.error_message is None
        assert state.inactivity_timer_handle is None
        assert state.display_status_emoji == "▶️"  # Default emoji for IDLE status

    def test_record_change(self) -> None:
        """Test recording file changes."""
        state = RepositoryState(repo_id="test-repo")

        # Record first change
        state.record_change()

        assert state.status == RepositoryStatus.CHANGED
        assert state.save_count == 1
        assert state.last_change_time is not None
        assert state.display_status_emoji == "📝"  # CHANGED emoji

        # Record second change
        first_time = state.last_change_time
        state.record_change()

        assert state.save_count == 2
        assert state.last_change_time > first_time

    def test_update_status(self) -> None:
        """Test status updates and emoji changes."""
        state = RepositoryState(repo_id="test-repo")

        # Test transition to different statuses
        state.update_status(RepositoryStatus.PROCESSING)
        assert state.status == RepositoryStatus.PROCESSING
        assert state.display_status_emoji == "🔄"

        state.update_status(RepositoryStatus.COMMITTING)
        assert state.status == RepositoryStatus.COMMITTING
        assert state.display_status_emoji == "💾"

        state.update_status(RepositoryStatus.ERROR, "Test error")
        assert state.status == RepositoryStatus.ERROR
        assert state.error_message == "Test error"
        assert state.display_status_emoji == "❌"

        # Test recovery from error
        state.update_status(RepositoryStatus.IDLE)
        assert state.status == RepositoryStatus.IDLE
        assert state.error_message is None
        assert state.display_status_emoji == "▶️"  # Default emoji for IDLE status

    def test_reset_after_action(self) -> None:
        """Test state reset after successful actions."""
        state = RepositoryState(repo_id="test-repo")

        # Set up some state
        state.record_change()
        state.record_change()
        state.update_status(RepositoryStatus.COMMITTING)
        state.last_commit_short_hash = "abc123"
        state.action_description = "Committing changes"

        # Reset after action
        state.reset_after_action()

        assert state.status == RepositoryStatus.IDLE
        assert state.save_count == 0
        assert state.action_description is None
        # Commit info should persist
        assert state.last_commit_short_hash == "abc123"

    def test_inactivity_timer_management(self) -> None:
        """Test inactivity timer handling."""
        state = RepositoryState(repo_id="test-repo")

        # Create mock timer handle
        mock_timer = Mock()
        mock_timer.cancel = Mock()

        # Mock asyncio.get_event_loop().time() to avoid event loop requirement
        with patch("asyncio.get_event_loop") as mock_get_loop:
            mock_loop = Mock()
            mock_loop.time.return_value = 12345.0
            mock_get_loop.return_value = mock_loop

            # Set timer
            state.set_inactivity_timer(mock_timer, 60)
            assert state.inactivity_timer_handle == mock_timer
            assert state._timer_total_seconds == 60
            assert state._timer_start_time == 12345.0

        # Cancel timer
        state.cancel_inactivity_timer()
        mock_timer.cancel.assert_called_once()
        assert state.inactivity_timer_handle is None
        assert state._timer_total_seconds is None
        assert state._timer_start_time is None

        # Test canceling when no timer exists
        state.cancel_inactivity_timer()  # Should not raise


class TestRepositoryStatusEnum:
    """Test repository status enumeration."""

    def test_all_statuses_have_emojis(self) -> None:
        """Ensure all status values have corresponding emojis."""
        from supsrc.state import STATUS_EMOJI_MAP

        for status in RepositoryStatus:
            assert status in STATUS_EMOJI_MAP, f"Missing emoji for {status}"


class TestRepositoryStatePreviousStatistics:
    """Test repository state previous statistics functionality."""

    def test_initial_previous_statistics(self) -> None:
        """Test that previous statistics are initialized to zero."""
        state = RepositoryState(repo_id="test-repo")

        assert state.last_committed_changed == 0
        assert state.last_committed_added == 0
        assert state.last_committed_deleted == 0
        assert state.last_committed_modified == 0

    def test_reset_after_action_preserves_statistics(self) -> None:
        """Test that reset_after_action preserves current statistics as previous."""
        state = RepositoryState(repo_id="test-repo")

        # Set up some file changes
        state.changed_files = 5
        state.added_files = 2
        state.deleted_files = 1
        state.modified_files = 2
        state.has_uncommitted_changes = True
        state.save_count = 3

        # Call reset_after_action
        state.reset_after_action()

        # Current statistics should be reset to zero
        assert state.changed_files == 0
        assert state.added_files == 0
        assert state.deleted_files == 0
        assert state.modified_files == 0
        assert state.has_uncommitted_changes is False
        assert state.save_count == 0
        assert state.status == RepositoryStatus.IDLE

        # Previous statistics should preserve the old values
        assert state.last_committed_changed == 5
        assert state.last_committed_added == 2
        assert state.last_committed_deleted == 1
        assert state.last_committed_modified == 2

    def test_multiple_resets_update_previous_statistics(self) -> None:
        """Test that multiple resets update previous statistics correctly."""
        state = RepositoryState(repo_id="test-repo")

        # First commit cycle
        state.changed_files = 3
        state.added_files = 1
        state.deleted_files = 0
        state.modified_files = 2
        state.reset_after_action()

        # Check first preservation
        assert state.last_committed_changed == 3
        assert state.last_committed_added == 1
        assert state.last_committed_deleted == 0
        assert state.last_committed_modified == 2

        # Second commit cycle with different values
        state.changed_files = 7
        state.added_files = 3
        state.deleted_files = 2
        state.modified_files = 2
        state.reset_after_action()

        # Check second preservation (should overwrite previous)
        assert state.last_committed_changed == 7
        assert state.last_committed_added == 3
        assert state.last_committed_deleted == 2
        assert state.last_committed_modified == 2

    def test_reset_after_action_with_zero_values(self) -> None:
        """Test that reset_after_action handles zero values correctly."""
        state = RepositoryState(repo_id="test-repo")

        # All values are already zero (initial state)
        state.reset_after_action()

        # Previous statistics should remain zero
        assert state.last_committed_changed == 0
        assert state.last_committed_added == 0
        assert state.last_committed_deleted == 0
        assert state.last_committed_modified == 0

    def test_reset_after_action_preserves_other_fields(self) -> None:
        """Test that reset_after_action preserves non-statistics fields correctly."""
        state = RepositoryState(repo_id="test-repo")

        # Set up some state that should NOT be reset
        state.total_files = 100
        state.current_branch = "feature-branch"
        state.last_change_time = state.last_change_time  # Keep existing time

        # Set up some file changes
        state.changed_files = 3
        state.added_files = 1
        state.deleted_files = 1
        state.modified_files = 1

        state.reset_after_action()

        # Non-statistics fields should be preserved
        assert state.total_files == 100
        assert state.current_branch == "feature-branch"

        # Previous statistics should be preserved
        assert state.last_committed_changed == 3
        assert state.last_committed_added == 1
        assert state.last_committed_deleted == 1
        assert state.last_committed_modified == 1


# 🔼⚙️🔚
