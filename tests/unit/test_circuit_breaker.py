#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for circuit breaker service and related functionality."""

from datetime import UTC, datetime, timedelta

import pytest

from supsrc.config.models import CircuitBreakerConfig
from supsrc.services.circuit_breaker import CircuitBreakerService
from supsrc.state.runtime import RepositoryState, RepositoryStatus


class TestCircuitBreakerConfig:
    """Tests for CircuitBreakerConfig model."""

    def test_default_values(self):
        """Test that default values are set correctly."""
        config = CircuitBreakerConfig()
        assert config.bulk_change_threshold == 50
        assert config.bulk_change_window_ms == 5000
        assert config.bulk_change_auto_pause is True
        assert config.branch_change_detection_enabled is True
        assert config.branch_change_warning_enabled is True
        assert config.branch_with_bulk_change_error is True
        assert config.branch_with_bulk_change_threshold == 20
        assert config.auto_resume_after_bulk_pause_seconds == 0
        assert config.require_manual_acknowledgment is False

    def test_custom_values(self):
        """Test that custom values can be set."""
        config = CircuitBreakerConfig(
            bulk_change_threshold=100,
            bulk_change_window_ms=10000,
            bulk_change_auto_pause=False,
            branch_change_detection_enabled=False,
        )
        assert config.bulk_change_threshold == 100
        assert config.bulk_change_window_ms == 10000
        assert config.bulk_change_auto_pause is False
        assert config.branch_change_detection_enabled is False

    def test_disabled_threshold_zero(self):
        """Test that threshold of 0 disables the feature."""
        config = CircuitBreakerConfig(bulk_change_threshold=0)
        assert config.bulk_change_threshold == 0

    def test_validation_negative_threshold(self):
        """Test that negative threshold raises validation error."""
        with pytest.raises(ValueError, match="non-negative"):
            CircuitBreakerConfig(bulk_change_threshold=-1)

    def test_validation_negative_window(self):
        """Test that negative window raises validation error."""
        with pytest.raises(ValueError, match="positive"):
            CircuitBreakerConfig(bulk_change_window_ms=0)


class TestRepositoryStateBulkChangeTracking:
    """Tests for bulk change tracking in RepositoryState."""

    def test_record_bulk_change_event(self):
        """Test recording a bulk change event."""
        state = RepositoryState(repo_id="test-repo")
        state.record_bulk_change_event("/path/to/file.txt")

        assert state.bulk_change_count == 1
        assert len(state.bulk_change_files) == 1
        assert "/path/to/file.txt" in state.bulk_change_files
        assert state.bulk_change_window_start is not None

    def test_record_multiple_bulk_change_events(self):
        """Test recording multiple bulk change events."""
        state = RepositoryState(repo_id="test-repo")
        state.record_bulk_change_event("/path/to/file1.txt")
        state.record_bulk_change_event("/path/to/file2.txt")
        state.record_bulk_change_event("/path/to/file3.txt")

        assert state.bulk_change_count == 3
        assert len(state.bulk_change_files) == 3

    def test_record_duplicate_file_event(self):
        """Test that duplicate file paths are not counted twice in unique files."""
        state = RepositoryState(repo_id="test-repo")
        state.record_bulk_change_event("/path/to/file.txt")
        state.record_bulk_change_event("/path/to/file.txt")

        assert state.bulk_change_count == 2
        assert len(state.bulk_change_files) == 1  # Unique files

    def test_reset_bulk_change_window(self):
        """Test resetting the bulk change window."""
        state = RepositoryState(repo_id="test-repo")
        state.record_bulk_change_event("/path/to/file.txt")
        assert state.bulk_change_count == 1

        state.reset_bulk_change_window()
        assert state.bulk_change_count == 0
        assert len(state.bulk_change_files) == 0
        assert state.bulk_change_window_start is None


class TestRepositoryStateBranchTracking:
    """Tests for branch change tracking in RepositoryState."""

    def test_check_branch_changed_first_time(self):
        """Test that first branch check stores the branch without triggering change."""
        state = RepositoryState(repo_id="test-repo")
        assert state.previous_branch is None

        changed = state.check_branch_changed("main")
        assert changed is False
        assert state.previous_branch == "main"

    def test_check_branch_changed_same_branch(self):
        """Test that same branch returns False."""
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"

        changed = state.check_branch_changed("main")
        assert changed is False

    def test_check_branch_changed_different_branch(self):
        """Test that different branch returns True."""
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"

        changed = state.check_branch_changed("feature-branch")
        assert changed is True

    def test_update_branch(self):
        """Test updating the tracked branch."""
        state = RepositoryState(repo_id="test-repo")
        state.update_branch("main")
        assert state.previous_branch == "main"

        state.update_branch("develop")
        assert state.previous_branch == "develop"


class TestRepositoryStateCircuitBreaker:
    """Tests for circuit breaker state management."""

    def test_trigger_circuit_breaker(self):
        """Test triggering a circuit breaker."""
        state = RepositoryState(repo_id="test-repo")
        state.trigger_circuit_breaker(
            "Test reason", RepositoryStatus.BULK_CHANGE_PAUSED
        )

        assert state.circuit_breaker_triggered is True
        assert state.circuit_breaker_reason == "Test reason"
        assert state.status == RepositoryStatus.BULK_CHANGE_PAUSED

    def test_reset_circuit_breaker(self):
        """Test resetting a circuit breaker."""
        state = RepositoryState(repo_id="test-repo")
        state.trigger_circuit_breaker(
            "Test reason", RepositoryStatus.BULK_CHANGE_PAUSED
        )
        state.bulk_change_count = 50

        state.reset_circuit_breaker()
        assert state.circuit_breaker_triggered is False
        assert state.circuit_breaker_reason is None
        assert state.bulk_change_count == 0

    def test_reset_circuit_breaker_not_triggered(self):
        """Test resetting when circuit breaker is not triggered."""
        state = RepositoryState(repo_id="test-repo")
        state.reset_circuit_breaker()
        assert state.circuit_breaker_triggered is False


class TestCircuitBreakerService:
    """Tests for CircuitBreakerService."""

    def test_initialization(self):
        """Test service initialization."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        assert service.config == config

    def test_check_bulk_change_disabled(self):
        """Test that bulk change check is disabled when threshold is 0."""
        config = CircuitBreakerConfig(bulk_change_threshold=0)
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        triggered = service.check_and_update_bulk_change(state, "/path/to/file.txt")
        assert triggered is False
        assert state.bulk_change_count == 0

    def test_check_bulk_change_under_threshold(self):
        """Test that circuit breaker is not triggered under threshold."""
        config = CircuitBreakerConfig(bulk_change_threshold=10)
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        for i in range(9):
            triggered = service.check_and_update_bulk_change(state, f"/path/to/file{i}.txt")
            assert triggered is False

        assert state.bulk_change_count == 9
        assert state.circuit_breaker_triggered is False

    def test_check_bulk_change_at_threshold(self):
        """Test that circuit breaker triggers at threshold."""
        config = CircuitBreakerConfig(bulk_change_threshold=10)
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        for i in range(9):
            service.check_and_update_bulk_change(state, f"/path/to/file{i}.txt")

        triggered = service.check_and_update_bulk_change(state, "/path/to/file9.txt")
        assert triggered is True
        assert state.circuit_breaker_triggered is True
        assert state.status == RepositoryStatus.BULK_CHANGE_PAUSED

    def test_check_bulk_change_auto_pause_disabled(self):
        """Test that auto-pause can be disabled."""
        config = CircuitBreakerConfig(
            bulk_change_threshold=10,
            bulk_change_auto_pause=False,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        for i in range(10):
            service.check_and_update_bulk_change(state, f"/path/to/file{i}.txt")

        assert state.circuit_breaker_triggered is False
        assert state.status != RepositoryStatus.BULK_CHANGE_PAUSED

    def test_check_bulk_change_window_expiry(self):
        """Test that window expiry resets the count."""
        config = CircuitBreakerConfig(
            bulk_change_threshold=10,
            bulk_change_window_ms=100,  # Very short window
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        # Add some changes
        for i in range(5):
            service.check_and_update_bulk_change(state, f"/path/to/file{i}.txt")

        # Simulate window expiry
        state.bulk_change_window_start = datetime.now(UTC) - timedelta(milliseconds=200)

        # Next change should reset the window
        triggered = service.check_and_update_bulk_change(state, "/path/to/newfile.txt")
        assert triggered is False
        assert state.bulk_change_count == 1  # Reset to 1

    def test_check_bulk_change_already_triggered(self):
        """Test that already triggered circuit breaker blocks further processing."""
        config = CircuitBreakerConfig(bulk_change_threshold=10)
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        state.circuit_breaker_triggered = True

        triggered = service.check_and_update_bulk_change(state, "/path/to/file.txt")
        assert triggered is True
        assert state.bulk_change_count == 0  # Should not increment


class TestCircuitBreakerServiceBranchChange:
    """Tests for branch change detection in CircuitBreakerService."""

    def test_branch_change_detection_disabled(self):
        """Test that branch change detection can be disabled."""
        config = CircuitBreakerConfig(branch_change_detection_enabled=False)
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"

        changed, triggered = service.check_branch_change(state, "feature")
        assert changed is False
        assert triggered is False
        assert state.previous_branch == "feature"  # Still updated

    def test_branch_change_no_change(self):
        """Test when branch has not changed."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"

        changed, triggered = service.check_branch_change(state, "main")
        assert changed is False
        assert triggered is False

    def test_branch_change_warning_only(self):
        """Test branch change triggers warning state."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"

        changed, triggered = service.check_branch_change(state, "feature")
        assert changed is True
        assert triggered is True
        assert state.status == RepositoryStatus.BRANCH_CHANGE_WARNING
        assert "main" in state.circuit_breaker_reason
        assert "feature" in state.circuit_breaker_reason

    def test_branch_change_warning_disabled(self):
        """Test that branch change warning can be disabled."""
        config = CircuitBreakerConfig(branch_change_warning_enabled=False)
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"

        changed, triggered = service.check_branch_change(state, "feature")
        assert changed is True
        assert triggered is False
        assert state.status != RepositoryStatus.BRANCH_CHANGE_WARNING

    def test_branch_change_with_bulk_files_error(self):
        """Test branch change with bulk files triggers error state."""
        config = CircuitBreakerConfig(
            branch_with_bulk_change_error=True,
            branch_with_bulk_change_threshold=10,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"

        # Simulate bulk files changed
        for i in range(15):
            state.bulk_change_files.append(f"/path/to/file{i}.txt")

        changed, triggered = service.check_branch_change(state, "feature")
        assert changed is True
        assert triggered is True
        assert state.status == RepositoryStatus.BRANCH_CHANGE_ERROR
        assert "15 files" in state.circuit_breaker_reason

    def test_branch_change_with_bulk_files_under_threshold(self):
        """Test branch change with bulk files under threshold triggers warning only."""
        config = CircuitBreakerConfig(
            branch_with_bulk_change_error=True,
            branch_with_bulk_change_threshold=20,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"

        # Simulate some files changed (under threshold)
        for i in range(10):
            state.bulk_change_files.append(f"/path/to/file{i}.txt")

        changed, triggered = service.check_branch_change(state, "feature")
        assert changed is True
        assert triggered is True
        # Should be warning, not error
        assert state.status == RepositoryStatus.BRANCH_CHANGE_WARNING

    def test_branch_change_already_triggered(self):
        """Test that already triggered circuit breaker blocks processing."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"
        state.circuit_breaker_triggered = True

        changed, triggered = service.check_branch_change(state, "feature")
        assert changed is False
        assert triggered is True


class TestCircuitBreakerServiceHelpers:
    """Tests for helper methods in CircuitBreakerService."""

    def test_should_process_event_normal(self):
        """Test that normal state allows event processing."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        assert service.should_process_event(state) is True

    def test_should_process_event_bulk_paused(self):
        """Test that bulk pause state blocks event processing."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.circuit_breaker_triggered = True
        state.update_status(RepositoryStatus.BULK_CHANGE_PAUSED)

        assert service.should_process_event(state) is False

    def test_should_process_event_branch_error(self):
        """Test that branch error state blocks event processing."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.circuit_breaker_triggered = True
        state.update_status(RepositoryStatus.BRANCH_CHANGE_ERROR)

        assert service.should_process_event(state) is False

    def test_should_process_event_branch_warning(self):
        """Test that branch warning state allows event processing."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.circuit_breaker_triggered = True
        state.update_status(RepositoryStatus.BRANCH_CHANGE_WARNING)

        assert service.should_process_event(state) is True

    def test_acknowledge_circuit_breaker(self):
        """Test acknowledging and resetting circuit breaker."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.trigger_circuit_breaker("Test", RepositoryStatus.BULK_CHANGE_PAUSED)

        service.acknowledge_circuit_breaker(state)
        assert state.circuit_breaker_triggered is False
        assert state.status == RepositoryStatus.IDLE

    def test_acknowledge_circuit_breaker_not_triggered(self):
        """Test acknowledging when not triggered does nothing."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        service.acknowledge_circuit_breaker(state)
        assert state.circuit_breaker_triggered is False
        assert state.status == RepositoryStatus.IDLE

    def test_get_circuit_breaker_summary(self):
        """Test getting circuit breaker summary."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.current_branch = "main"
        state.previous_branch = "develop"
        state.bulk_change_count = 25
        state.bulk_change_files = [f"/path/to/file{i}.txt" for i in range(25)]

        summary = service.get_circuit_breaker_summary(state)
        assert summary["triggered"] is False
        assert summary["reason"] is None
        assert summary["status"] == "IDLE"
        assert summary["bulk_change_count"] == 25
        assert summary["unique_files_in_window"] == 25
        assert summary["current_branch"] == "main"
        assert summary["previous_branch"] == "develop"

    def test_get_circuit_breaker_summary_triggered(self):
        """Test getting summary when circuit breaker is triggered."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.trigger_circuit_breaker("Test reason", RepositoryStatus.BULK_CHANGE_PAUSED)

        summary = service.get_circuit_breaker_summary(state)
        assert summary["triggered"] is True
        assert summary["reason"] == "Test reason"
        assert summary["status"] == "BULK_CHANGE_PAUSED"


class TestRepositoryStatusEmoji:
    """Tests for circuit breaker status emoji mapping."""

    def test_bulk_change_paused_emoji(self):
        """Test emoji for bulk change paused status."""
        from supsrc.state.runtime import STATUS_EMOJI_MAP

        assert STATUS_EMOJI_MAP[RepositoryStatus.BULK_CHANGE_PAUSED] == "🛑"

    def test_branch_change_warning_emoji(self):
        """Test emoji for branch change warning status."""
        from supsrc.state.runtime import STATUS_EMOJI_MAP

        assert STATUS_EMOJI_MAP[RepositoryStatus.BRANCH_CHANGE_WARNING] == "⚠️"

    def test_branch_change_error_emoji(self):
        """Test emoji for branch change error status."""
        from supsrc.state.runtime import STATUS_EMOJI_MAP

        assert STATUS_EMOJI_MAP[RepositoryStatus.BRANCH_CHANGE_ERROR] == "🚨"


# 🔼⚙️🔚
