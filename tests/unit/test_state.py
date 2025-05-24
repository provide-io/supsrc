#
# tests/unit/test_state.py
#
"""
Comprehensive tests for repository state management.
"""

from unittest.mock import Mock

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
        assert state.display_status_emoji == "🧼"  # IDLE emoji

    def test_record_change(self) -> None:
        """Test recording file changes."""
        state = RepositoryState(repo_id="test-repo")

        # Record first change
        state.record_change()

        assert state.status == RepositoryStatus.CHANGED
        assert state.save_count == 1
        assert state.last_change_time is not None
        assert state.display_status_emoji == "✏️"  # CHANGED emoji

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
        assert state.display_status_emoji == "🧼"

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
        assert state.last_change_time is None
        assert state.action_description is None
        # Commit info should persist
        assert state.last_commit_short_hash == "abc123"

    def test_inactivity_timer_management(self) -> None:
        """Test inactivity timer handling."""
        state = RepositoryState(repo_id="test-repo")

        # Create mock timer handle
        mock_timer = Mock()
        mock_timer.cancel = Mock()

        # Set timer
        state.set_inactivity_timer(mock_timer)
        assert state.inactivity_timer_handle == mock_timer

        # Cancel timer
        state.cancel_inactivity_timer()
        mock_timer.cancel.assert_called_once()
        assert state.inactivity_timer_handle is None

        # Test canceling when no timer exists
        state.cancel_inactivity_timer()  # Should not raise

    def test_timer_replacement(self) -> None:
        """Test timer replacement when setting new timer."""
        state = RepositoryState(repo_id="test-repo")

        # Create mock timers
        old_timer = Mock()
        old_timer.cancel = Mock()
        new_timer = Mock()

        # Set first timer
        state.set_inactivity_timer(old_timer)

        # Set new timer (should cancel old one)
        state.set_inactivity_timer(new_timer)

        old_timer.cancel.assert_called_once()
        assert state.inactivity_timer_handle == new_timer

    def test_status_no_change_optimization(self) -> None:
        """Test that identical status updates are optimized."""
        state = RepositoryState(repo_id="test-repo")
        initial_status = state.status

        # Update to same status
        state.update_status(RepositoryStatus.IDLE)

        # Should remain the same
        assert state.status == initial_status


class TestRepositoryStatusEnum:
    """Test repository status enumeration."""

    def test_all_statuses_have_emojis(self) -> None:
        """Ensure all status values have corresponding emojis."""
        from supsrc.state import STATUS_EMOJI_MAP

        for status in RepositoryStatus:
            assert status in STATUS_EMOJI_MAP, f"Missing emoji for {status}"

    def test_emoji_uniqueness(self) -> None:
        """Test that status emojis are reasonably unique."""
        from supsrc.state import STATUS_EMOJI_MAP

        emojis = list(STATUS_EMOJI_MAP.values())

        # Allow some duplication but not complete duplication
        unique_emojis = set(emojis)
        assert len(unique_emojis) >= len(emojis) * 0.7


class TestStateFieldValidation:
    """Test state field validation and edge cases."""

    def test_action_progress_validation(self) -> None:
        """Test action progress field handling."""
        state = RepositoryState(repo_id="test-repo")

        # Test progress tracking
        state.action_progress_total = 100
        state.action_progress_completed = 50

        assert state.action_progress_total == 100
        assert state.action_progress_completed == 50

        # Test reset
        state.action_progress_total = None
        state.action_progress_completed = None

        assert state.action_progress_total is None
        assert state.action_progress_completed is None

    def test_commit_info_persistence(self) -> None:
        """Test that commit information persists across resets."""
        state = RepositoryState(repo_id="test-repo")

        # Set commit info
        state.last_commit_short_hash = "abc123"
        state.last_commit_message_summary = "Test commit"

        # Reset should not clear commit info
        state.reset_after_action()

        assert state.last_commit_short_hash == "abc123"
        assert state.last_commit_message_summary == "Test commit"

    def test_rule_info_management(self) -> None:
        """Test rule-related field management."""
        state = RepositoryState(repo_id="test-repo")

        # Set rule info
        state.rule_emoji = "⏳"
        state.rule_dynamic_indicator = "Waiting..."
        state.active_rule_description = "Inactivity rule"

        # Verify fields are set
        assert state.rule_emoji == "⏳"
        assert state.rule_dynamic_indicator == "Waiting..."
        assert state.active_rule_description == "Inactivity rule"

        # Reset should clear rule info
        state.reset_after_action()

        assert state.rule_emoji is None
        assert state.rule_dynamic_indicator is None
        assert state.active_rule_description is None

# 🧪📊
