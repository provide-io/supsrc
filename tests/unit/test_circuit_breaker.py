#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Tests for circuit breaker service and related functionality."""

from datetime import UTC, datetime, timedelta

import pytest

from supsrc.config.models import CircuitBreakerConfig
from supsrc.services.circuit_breaker import (
    BranchChangeError,
    BulkChangeError,
    CircuitBreakerError,
    CircuitBreakerMetrics,
    CircuitBreakerService,
)
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
        state.trigger_circuit_breaker("Test reason", RepositoryStatus.BULK_CHANGE_PAUSED)

        assert state.circuit_breaker_triggered is True
        assert state.circuit_breaker_reason == "Test reason"
        assert state.status == RepositoryStatus.BULK_CHANGE_PAUSED

    def test_reset_circuit_breaker(self):
        """Test resetting a circuit breaker."""
        state = RepositoryState(repo_id="test-repo")
        state.trigger_circuit_breaker("Test reason", RepositoryStatus.BULK_CHANGE_PAUSED)
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


class TestCircuitBreakerMetrics:
    """Tests for CircuitBreakerMetrics data class."""

    def test_default_initialization(self):
        """Test metrics initialize with default values."""
        metrics = CircuitBreakerMetrics()
        assert metrics.bulk_change_triggers == 0
        assert metrics.branch_change_triggers == 0
        assert metrics.combined_triggers == 0
        assert metrics.auto_recoveries == 0
        assert metrics.manual_acknowledgments == 0
        assert metrics.total_events_blocked == 0
        assert metrics.total_events_processed == 0
        assert metrics.last_trigger_time is None
        assert metrics.last_trigger_reason is None
        assert metrics.last_trigger_type is None
        assert metrics.triggers_in_last_hour == 0
        assert metrics.last_hour_reset is not None

    def test_to_dict_with_defaults(self):
        """Test converting default metrics to dictionary."""
        metrics = CircuitBreakerMetrics()
        result = metrics.to_dict()

        assert result["bulk_change_triggers"] == 0
        assert result["branch_change_triggers"] == 0
        assert result["combined_triggers"] == 0
        assert result["auto_recoveries"] == 0
        assert result["manual_acknowledgments"] == 0
        assert result["total_events_blocked"] == 0
        assert result["total_events_processed"] == 0
        assert result["last_trigger_time"] is None
        assert result["last_trigger_reason"] is None
        assert result["last_trigger_type"] is None
        assert result["triggers_in_last_hour"] == 0

    def test_to_dict_with_values(self):
        """Test converting populated metrics to dictionary."""
        now = datetime.now(UTC)
        metrics = CircuitBreakerMetrics(
            bulk_change_triggers=5,
            branch_change_triggers=2,
            combined_triggers=1,
            auto_recoveries=3,
            manual_acknowledgments=4,
            total_events_blocked=100,
            total_events_processed=500,
            last_trigger_time=now,
            last_trigger_reason="Test reason",
            last_trigger_type="bulk_change",
            triggers_in_last_hour=8,
        )
        result = metrics.to_dict()

        assert result["bulk_change_triggers"] == 5
        assert result["branch_change_triggers"] == 2
        assert result["combined_triggers"] == 1
        assert result["auto_recoveries"] == 3
        assert result["manual_acknowledgments"] == 4
        assert result["total_events_blocked"] == 100
        assert result["total_events_processed"] == 500
        assert result["last_trigger_time"] == now.isoformat()
        assert result["last_trigger_reason"] == "Test reason"
        assert result["last_trigger_type"] == "bulk_change"
        assert result["triggers_in_last_hour"] == 8


class TestCircuitBreakerExceptions:
    """Tests for circuit breaker exception classes."""

    def test_circuit_breaker_error_base(self):
        """Test base CircuitBreakerError exception."""
        error = CircuitBreakerError("Test message", "test-repo", "test_type")
        assert str(error) == "Test message"
        assert error.repo_id == "test-repo"
        assert error.trigger_type == "test_type"

    def test_bulk_change_error(self):
        """Test BulkChangeError with specific attributes."""
        error = BulkChangeError("my-repo", 75, 50, 5000)
        assert error.repo_id == "my-repo"
        assert error.trigger_type == "bulk_change"
        assert error.file_count == 75
        assert error.threshold == 50
        assert error.window_ms == 5000
        assert "my-repo" in str(error)
        assert "75 files" in str(error)
        assert "5000ms" in str(error)
        assert "threshold: 50" in str(error)

    def test_bulk_change_error_inheritance(self):
        """Test BulkChangeError inherits from CircuitBreakerError."""
        error = BulkChangeError("test-repo", 100, 50, 5000)
        assert isinstance(error, CircuitBreakerError)
        assert isinstance(error, Exception)

    def test_branch_change_error(self):
        """Test BranchChangeError with specific attributes."""
        error = BranchChangeError("my-repo", "main", "feature-branch", 25)
        assert error.repo_id == "my-repo"
        assert error.trigger_type == "branch_change_with_bulk"
        assert error.old_branch == "main"
        assert error.new_branch == "feature-branch"
        assert error.file_count == 25
        assert "my-repo" in str(error)
        assert "main" in str(error)
        assert "feature-branch" in str(error)
        assert "25 file" in str(error)

    def test_branch_change_error_inheritance(self):
        """Test BranchChangeError inherits from CircuitBreakerError."""
        error = BranchChangeError("test-repo", "old", "new", 10)
        assert isinstance(error, CircuitBreakerError)
        assert isinstance(error, Exception)


class TestCircuitBreakerServiceMetrics:
    """Tests for metrics collection in CircuitBreakerService."""

    def test_service_initializes_with_metrics(self):
        """Test service initializes with fresh metrics."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        assert service.metrics is not None
        assert isinstance(service.metrics, CircuitBreakerMetrics)
        assert service.metrics.bulk_change_triggers == 0

    def test_get_metrics_returns_metrics_object(self):
        """Test get_metrics returns the metrics instance."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        metrics = service.get_metrics()
        assert metrics is service.metrics

    def test_reset_metrics_clears_all_counters(self):
        """Test reset_metrics creates fresh metrics."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)

        # Populate metrics
        service.metrics.bulk_change_triggers = 10
        service.metrics.auto_recoveries = 5
        service.metrics.total_events_processed = 1000

        service.reset_metrics()

        assert service.metrics.bulk_change_triggers == 0
        assert service.metrics.auto_recoveries == 0
        assert service.metrics.total_events_processed == 0

    def test_bulk_change_trigger_records_metrics(self):
        """Test that bulk change trigger updates metrics."""
        config = CircuitBreakerConfig(bulk_change_threshold=3)
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        # Trigger the circuit breaker
        for i in range(3):
            service.check_and_update_bulk_change(state, f"/path/file{i}.txt")

        assert service.metrics.bulk_change_triggers == 1
        assert service.metrics.last_trigger_type == "bulk_change"
        assert service.metrics.last_trigger_time is not None
        assert "Bulk change detected" in service.metrics.last_trigger_reason

    def test_branch_change_trigger_records_metrics(self):
        """Test that branch change trigger updates metrics."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"

        service.check_branch_change(state, "feature")

        assert service.metrics.branch_change_triggers == 1
        assert service.metrics.last_trigger_type == "branch_change"

    def test_combined_trigger_records_metrics(self):
        """Test that combined branch+bulk trigger updates metrics."""
        config = CircuitBreakerConfig(
            branch_with_bulk_change_error=True,
            branch_with_bulk_change_threshold=5,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"

        # Add bulk files
        for i in range(10):
            state.bulk_change_files.append(f"/path/file{i}.txt")

        service.check_branch_change(state, "feature")

        assert service.metrics.combined_triggers == 1
        assert service.metrics.last_trigger_type == "combined"

    def test_events_blocked_counter_increments(self):
        """Test that blocked events are counted."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.circuit_breaker_triggered = True
        state.update_status(RepositoryStatus.BULK_CHANGE_PAUSED)

        # Try to process events when circuit breaker is active
        service.should_process_event(state)
        service.should_process_event(state)

        assert service.metrics.total_events_blocked == 2

    def test_events_processed_counter_increments(self):
        """Test that processed events are counted."""
        config = CircuitBreakerConfig(bulk_change_threshold=100)
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        # Process events without triggering
        for i in range(5):
            service.check_and_update_bulk_change(state, f"/path/file{i}.txt")

        assert service.metrics.total_events_processed == 5

    def test_hourly_metrics_reset_after_one_hour(self):
        """Test that hourly trigger count resets after one hour."""
        config = CircuitBreakerConfig(bulk_change_threshold=2)
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        # First trigger
        service.check_and_update_bulk_change(state, "/path/file1.txt")
        service.check_and_update_bulk_change(state, "/path/file2.txt")
        assert service.metrics.triggers_in_last_hour == 1

        # Simulate time passing (more than 1 hour)
        service.metrics.last_hour_reset = datetime.now(UTC) - timedelta(hours=1, minutes=1)

        # Reset state and trigger again
        state = RepositoryState(repo_id="test-repo-2")
        service.check_and_update_bulk_change(state, "/path/file3.txt")
        service.check_and_update_bulk_change(state, "/path/file4.txt")

        # Should have reset hourly counter
        assert service.metrics.triggers_in_last_hour == 1


class TestCircuitBreakerAutoRecovery:
    """Tests for auto-recovery functionality."""

    def test_auto_recovery_task_scheduled(self):
        """Test that auto-recovery is scheduled when configured."""
        config = CircuitBreakerConfig(
            bulk_change_threshold=2,
            auto_resume_after_bulk_pause_seconds=60,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        # Trigger circuit breaker
        service.check_and_update_bulk_change(state, "/path/file1.txt")
        service.check_and_update_bulk_change(state, "/path/file2.txt")

        assert "test-repo" in service._auto_recovery_tasks
        recovery_time = service._auto_recovery_tasks["test-repo"]
        expected = datetime.now(UTC) + timedelta(seconds=60)
        # Allow 1 second tolerance
        assert abs((recovery_time - expected).total_seconds()) < 1

    def test_auto_recovery_not_scheduled_when_disabled(self):
        """Test that auto-recovery is not scheduled when seconds is 0."""
        config = CircuitBreakerConfig(
            bulk_change_threshold=2,
            auto_resume_after_bulk_pause_seconds=0,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        service.check_and_update_bulk_change(state, "/path/file1.txt")
        service.check_and_update_bulk_change(state, "/path/file2.txt")

        assert "test-repo" not in service._auto_recovery_tasks

    def test_check_auto_recovery_not_due(self):
        """Test check_auto_recovery returns False when not due."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.circuit_breaker_triggered = True

        # Schedule recovery in future
        future_time = datetime.now(UTC) + timedelta(seconds=60)
        service._auto_recovery_tasks["test-repo"] = future_time

        result = service.check_auto_recovery(state)
        assert result is False
        assert state.circuit_breaker_triggered is True

    def test_check_auto_recovery_due(self):
        """Test check_auto_recovery resets when due."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.trigger_circuit_breaker("Test", RepositoryStatus.BULK_CHANGE_PAUSED)

        # Schedule recovery in past
        past_time = datetime.now(UTC) - timedelta(seconds=1)
        service._auto_recovery_tasks["test-repo"] = past_time

        result = service.check_auto_recovery(state)
        assert result is True
        assert state.circuit_breaker_triggered is False
        assert state.status == RepositoryStatus.IDLE
        assert "test-repo" not in service._auto_recovery_tasks
        assert service.metrics.auto_recoveries == 1

    def test_check_auto_recovery_no_task(self):
        """Test check_auto_recovery returns False when no task scheduled."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        result = service.check_auto_recovery(state)
        assert result is False

    def test_should_process_event_triggers_auto_recovery(self):
        """Test should_process_event checks for auto-recovery."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.trigger_circuit_breaker("Test", RepositoryStatus.BULK_CHANGE_PAUSED)

        # Schedule recovery in past
        past_time = datetime.now(UTC) - timedelta(seconds=1)
        service._auto_recovery_tasks["test-repo"] = past_time

        # Should auto-recover and allow processing
        result = service.should_process_event(state)
        assert result is True
        assert state.circuit_breaker_triggered is False

    def test_get_circuit_breaker_summary_includes_auto_recovery(self):
        """Test summary includes auto-recovery information."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        # Schedule recovery in future
        future_time = datetime.now(UTC) + timedelta(seconds=30)
        service._auto_recovery_tasks["test-repo"] = future_time

        summary = service.get_circuit_breaker_summary(state)
        assert summary["auto_recovery_scheduled"] is True
        assert summary["auto_recovery_in_seconds"] > 0
        assert summary["auto_recovery_in_seconds"] <= 30

    def test_get_circuit_breaker_summary_no_auto_recovery(self):
        """Test summary indicates no auto-recovery when not scheduled."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        summary = service.get_circuit_breaker_summary(state)
        assert summary["auto_recovery_scheduled"] is False
        assert "auto_recovery_in_seconds" not in summary


class TestCircuitBreakerAcknowledgment:
    """Tests for enhanced acknowledgment functionality."""

    def test_manual_acknowledgment_increments_counter(self):
        """Test that manual acknowledgment increments counter."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.trigger_circuit_breaker("Test", RepositoryStatus.BULK_CHANGE_PAUSED)

        service.acknowledge_circuit_breaker(state, auto_recovery=False)

        assert service.metrics.manual_acknowledgments == 1
        assert service.metrics.auto_recoveries == 0

    def test_auto_recovery_increments_counter(self):
        """Test that auto-recovery increments counter."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.trigger_circuit_breaker("Test", RepositoryStatus.BULK_CHANGE_PAUSED)

        service.acknowledge_circuit_breaker(state, auto_recovery=True)

        assert service.metrics.auto_recoveries == 1
        assert service.metrics.manual_acknowledgments == 0

    def test_acknowledgment_cleans_up_auto_recovery_task(self):
        """Test that acknowledgment removes scheduled auto-recovery."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.trigger_circuit_breaker("Test", RepositoryStatus.BULK_CHANGE_PAUSED)

        # Schedule recovery
        service._auto_recovery_tasks["test-repo"] = datetime.now(UTC) + timedelta(seconds=60)

        # Manual acknowledge
        service.acknowledge_circuit_breaker(state, auto_recovery=False)

        # Task should be cleaned up
        assert "test-repo" not in service._auto_recovery_tasks


class TestCircuitBreakerRequireManualAcknowledgment:
    """Tests for require_manual_acknowledgment feature."""

    def test_bulk_change_raises_exception_when_required(self):
        """Test that BulkChangeError is raised when manual ack required."""
        config = CircuitBreakerConfig(
            bulk_change_threshold=2,
            require_manual_acknowledgment=True,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        service.check_and_update_bulk_change(state, "/path/file1.txt")

        with pytest.raises(BulkChangeError) as exc_info:
            service.check_and_update_bulk_change(state, "/path/file2.txt")

        assert exc_info.value.repo_id == "test-repo"
        assert exc_info.value.file_count == 2
        assert exc_info.value.threshold == 2

    def test_bulk_change_no_exception_when_not_required(self):
        """Test no exception when manual ack not required."""
        config = CircuitBreakerConfig(
            bulk_change_threshold=2,
            require_manual_acknowledgment=False,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        service.check_and_update_bulk_change(state, "/path/file1.txt")

        # Should not raise
        triggered = service.check_and_update_bulk_change(state, "/path/file2.txt")
        assert triggered is True

    def test_branch_change_with_bulk_raises_exception_when_required(self):
        """Test BranchChangeError raised when manual ack required."""
        config = CircuitBreakerConfig(
            branch_with_bulk_change_error=True,
            branch_with_bulk_change_threshold=2,
            require_manual_acknowledgment=True,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"

        # Add bulk files
        state.bulk_change_files = ["/path/file1.txt", "/path/file2.txt", "/path/file3.txt"]

        with pytest.raises(BranchChangeError) as exc_info:
            service.check_branch_change(state, "feature")

        assert exc_info.value.repo_id == "test-repo"
        assert exc_info.value.old_branch == "main"
        assert exc_info.value.new_branch == "feature"
        assert exc_info.value.file_count == 3

    def test_branch_change_no_exception_when_not_required(self):
        """Test no exception when manual ack not required."""
        config = CircuitBreakerConfig(
            branch_with_bulk_change_error=True,
            branch_with_bulk_change_threshold=2,
            require_manual_acknowledgment=False,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"
        state.bulk_change_files = ["/path/file1.txt", "/path/file2.txt", "/path/file3.txt"]

        # Should not raise
        changed, triggered = service.check_branch_change(state, "feature")
        assert changed is True
        assert triggered is True


class TestCircuitBreakerEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_metrics_accumulate_correctly(self):
        """Test that metrics accumulate across multiple triggers."""
        config = CircuitBreakerConfig(bulk_change_threshold=2)
        service = CircuitBreakerService(config)

        # Multiple trigger cycles
        for cycle in range(3):
            state = RepositoryState(repo_id=f"repo-{cycle}")
            service.check_and_update_bulk_change(state, f"/path/file{cycle}a.txt")
            service.check_and_update_bulk_change(state, f"/path/file{cycle}b.txt")

        assert service.metrics.bulk_change_triggers == 3
        assert service.metrics.triggers_in_last_hour == 3

    def test_exception_with_empty_branch_name(self):
        """Test BranchChangeError handles empty branch names."""
        error = BranchChangeError("repo", "", "feature", 10)
        assert error.old_branch == ""
        assert "'' to 'feature'" in str(error)

    def test_exception_with_long_branch_names(self):
        """Test exceptions handle long branch names."""
        long_name = "feature/" + "x" * 200
        error = BranchChangeError("repo", "main", long_name, 5)
        assert long_name in str(error)

    def test_bulk_change_error_with_zero_threshold(self):
        """Test BulkChangeError message with edge case values."""
        error = BulkChangeError("repo", 100, 1, 1)
        assert "100 files" in str(error)
        assert "1ms" in str(error)
        assert "threshold: 1" in str(error)

    def test_multiple_repos_independent_auto_recovery(self):
        """Test auto-recovery tasks are independent per repository."""
        config = CircuitBreakerConfig(
            bulk_change_threshold=2,
            auto_resume_after_bulk_pause_seconds=30,
        )
        service = CircuitBreakerService(config)

        # Trigger for two different repos
        state1 = RepositoryState(repo_id="repo-1")
        state2 = RepositoryState(repo_id="repo-2")

        service.check_and_update_bulk_change(state1, "/path/file1.txt")
        service.check_and_update_bulk_change(state1, "/path/file2.txt")

        service.check_and_update_bulk_change(state2, "/path/file3.txt")
        service.check_and_update_bulk_change(state2, "/path/file4.txt")

        assert "repo-1" in service._auto_recovery_tasks
        assert "repo-2" in service._auto_recovery_tasks
        assert len(service._auto_recovery_tasks) == 2

    def test_acknowledge_removes_only_specific_repo_recovery(self):
        """Test acknowledging one repo doesn't affect another."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)

        # Set up auto-recovery for two repos
        service._auto_recovery_tasks["repo-1"] = datetime.now(UTC) + timedelta(seconds=60)
        service._auto_recovery_tasks["repo-2"] = datetime.now(UTC) + timedelta(seconds=60)

        state1 = RepositoryState(repo_id="repo-1")
        state1.trigger_circuit_breaker("Test", RepositoryStatus.BULK_CHANGE_PAUSED)

        service.acknowledge_circuit_breaker(state1)

        assert "repo-1" not in service._auto_recovery_tasks
        assert "repo-2" in service._auto_recovery_tasks

    def test_metrics_to_dict_preserves_all_fields(self):
        """Test that to_dict includes all expected fields."""
        metrics = CircuitBreakerMetrics()
        result = metrics.to_dict()

        expected_keys = {
            "bulk_change_triggers",
            "branch_change_triggers",
            "combined_triggers",
            "auto_recoveries",
            "manual_acknowledgments",
            "total_events_blocked",
            "total_events_processed",
            "last_trigger_time",
            "last_trigger_reason",
            "last_trigger_type",
            "triggers_in_last_hour",
        }
        assert set(result.keys()) == expected_keys

    def test_hourly_reset_updates_timestamp(self):
        """Test that hourly reset updates the timestamp."""
        config = CircuitBreakerConfig(bulk_change_threshold=2)
        service = CircuitBreakerService(config)

        # Set old reset time
        old_reset = datetime.now(UTC) - timedelta(hours=2)
        service.metrics.last_hour_reset = old_reset

        state = RepositoryState(repo_id="test-repo")
        service.check_and_update_bulk_change(state, "/path/file1.txt")
        service.check_and_update_bulk_change(state, "/path/file2.txt")

        # Reset time should be updated
        assert service.metrics.last_hour_reset > old_reset

    def test_consecutive_triggers_same_repo(self):
        """Test handling consecutive triggers for the same repo."""
        config = CircuitBreakerConfig(bulk_change_threshold=2)
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        # First trigger
        service.check_and_update_bulk_change(state, "/path/file1.txt")
        service.check_and_update_bulk_change(state, "/path/file2.txt")

        # Acknowledge and reset
        service.acknowledge_circuit_breaker(state)

        # Second trigger
        service.check_and_update_bulk_change(state, "/path/file3.txt")
        service.check_and_update_bulk_change(state, "/path/file4.txt")

        assert service.metrics.bulk_change_triggers == 2
        assert service.metrics.manual_acknowledgments == 1

    def test_auto_recovery_summary_shows_zero_when_passed(self):
        """Test summary shows 0 seconds when recovery time is past."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        # Schedule recovery in past
        past_time = datetime.now(UTC) - timedelta(seconds=10)
        service._auto_recovery_tasks["test-repo"] = past_time

        summary = service.get_circuit_breaker_summary(state)
        assert summary["auto_recovery_scheduled"] is True
        assert summary["auto_recovery_in_seconds"] == 0


class TestCircuitBreakerIntegrationScenarios:
    """Tests for complex integration scenarios."""

    def test_full_lifecycle_bulk_change_with_auto_recovery(self):
        """Test complete lifecycle: trigger -> auto-recover -> trigger again."""
        config = CircuitBreakerConfig(
            bulk_change_threshold=2,
            auto_resume_after_bulk_pause_seconds=1,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        # Trigger circuit breaker
        service.check_and_update_bulk_change(state, "/path/file1.txt")
        service.check_and_update_bulk_change(state, "/path/file2.txt")

        assert state.circuit_breaker_triggered is True
        assert service.metrics.bulk_change_triggers == 1

        # Simulate time passing and auto-recovery
        service._auto_recovery_tasks["test-repo"] = datetime.now(UTC) - timedelta(seconds=1)
        service.check_auto_recovery(state)

        assert state.circuit_breaker_triggered is False
        assert service.metrics.auto_recoveries == 1

        # Trigger again
        service.check_and_update_bulk_change(state, "/path/file3.txt")
        service.check_and_update_bulk_change(state, "/path/file4.txt")

        assert state.circuit_breaker_triggered is True
        assert service.metrics.bulk_change_triggers == 2

    def test_branch_change_during_bulk_change_window(self):
        """Test branch change detected while bulk changes are accumulating."""
        config = CircuitBreakerConfig(
            bulk_change_threshold=100,
            branch_with_bulk_change_error=True,
            branch_with_bulk_change_threshold=5,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"

        # Accumulate bulk changes
        for i in range(10):
            service.check_and_update_bulk_change(state, f"/path/file{i}.txt")

        # Then branch changes
        changed, triggered = service.check_branch_change(state, "feature")

        assert changed is True
        assert triggered is True
        assert state.status == RepositoryStatus.BRANCH_CHANGE_ERROR
        assert service.metrics.combined_triggers == 1

    def test_metrics_consistency_across_operations(self):
        """Test metrics remain consistent through various operations."""
        config = CircuitBreakerConfig(bulk_change_threshold=2)
        service = CircuitBreakerService(config)

        # Process some events
        state1 = RepositoryState(repo_id="repo-1")
        service.check_and_update_bulk_change(state1, "/path/file1.txt")
        assert service.metrics.total_events_processed == 1

        # Trigger circuit breaker
        service.check_and_update_bulk_change(state1, "/path/file2.txt")
        assert service.metrics.bulk_change_triggers == 1

        # Block events
        service.should_process_event(state1)
        assert service.metrics.total_events_blocked == 1

        # Acknowledge
        service.acknowledge_circuit_breaker(state1)
        assert service.metrics.manual_acknowledgments == 1

        # Reset and verify
        old_metrics = service.get_metrics().to_dict()
        service.reset_metrics()
        new_metrics = service.get_metrics().to_dict()

        assert old_metrics["bulk_change_triggers"] == 1
        assert new_metrics["bulk_change_triggers"] == 0

    def test_exception_after_trigger_preserves_state(self):
        """Test that exception raising preserves circuit breaker state."""
        config = CircuitBreakerConfig(
            bulk_change_threshold=2,
            require_manual_acknowledgment=True,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        service.check_and_update_bulk_change(state, "/path/file1.txt")

        with pytest.raises(BulkChangeError):
            service.check_and_update_bulk_change(state, "/path/file2.txt")

        # State should still be triggered
        assert state.circuit_breaker_triggered is True
        assert state.status == RepositoryStatus.BULK_CHANGE_PAUSED
        # Metrics should be updated
        assert service.metrics.bulk_change_triggers == 1

    def test_should_process_event_with_warning_allows_processing(self):
        """Test that warning state allows event processing but maintains warning."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.previous_branch = "main"

        # Trigger warning
        service.check_branch_change(state, "feature")
        assert state.status == RepositoryStatus.BRANCH_CHANGE_WARNING

        # Should allow processing
        should_process = service.should_process_event(state)
        assert should_process is True
        assert service.metrics.total_events_processed == 1

        # Warning should still be active
        assert state.circuit_breaker_triggered is True

    def test_window_expiry_resets_file_list(self):
        """Test that window expiry clears the file list."""
        config = CircuitBreakerConfig(
            bulk_change_threshold=10,
            bulk_change_window_ms=100,
        )
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        # Add some files
        for i in range(5):
            service.check_and_update_bulk_change(state, f"/path/file{i}.txt")

        assert len(state.bulk_change_files) == 5

        # Expire window
        state.bulk_change_window_start = datetime.now(UTC) - timedelta(milliseconds=200)

        # New file should reset
        service.check_and_update_bulk_change(state, "/path/newfile.txt")

        assert len(state.bulk_change_files) == 1
        assert state.bulk_change_count == 1


class TestCircuitBreakerExceptionMessageFormatting:
    """Tests for exception message formatting and readability."""

    def test_bulk_change_error_message_is_actionable(self):
        """Test that error message provides clear action guidance."""
        error = BulkChangeError("my-repo", 50, 30, 5000)
        message = str(error)

        # Should contain key information
        assert "my-repo" in message
        assert "50 files" in message
        assert "30" in message  # threshold
        assert "5000ms" in message

        # Should be actionable
        assert "review" in message.lower() or "Review" in message

    def test_branch_change_error_message_is_actionable(self):
        """Test that error message provides clear action guidance."""
        error = BranchChangeError("my-repo", "develop", "main", 15)
        message = str(error)

        # Should contain key information
        assert "my-repo" in message
        assert "develop" in message
        assert "main" in message
        assert "15" in message

        # Should be actionable
        assert "verify" in message.lower() or "Verify" in message

    def test_exception_repo_id_accessible(self):
        """Test that repo_id is easily accessible from exception."""
        error = BulkChangeError("specific-repo", 10, 5, 1000)

        with pytest.raises(CircuitBreakerError) as exc_info:
            raise error

        assert exc_info.value.repo_id == "specific-repo"
        assert exc_info.value.trigger_type == "bulk_change"


class TestCircuitBreakerMetricsEdgeCases:
    """Tests for metrics edge cases."""

    def test_metrics_last_hour_reset_on_initialization(self):
        """Test that last_hour_reset is set on initialization."""
        before = datetime.now(UTC)
        metrics = CircuitBreakerMetrics()
        after = datetime.now(UTC)

        assert before <= metrics.last_hour_reset <= after

    def test_metrics_to_dict_handles_none_timestamp(self):
        """Test to_dict correctly handles None timestamp."""
        metrics = CircuitBreakerMetrics(last_trigger_time=None)
        result = metrics.to_dict()
        assert result["last_trigger_time"] is None

    def test_metrics_to_dict_formats_timestamp_correctly(self):
        """Test to_dict formats timestamp as ISO format."""
        specific_time = datetime(2025, 1, 15, 10, 30, 45, tzinfo=UTC)
        metrics = CircuitBreakerMetrics(last_trigger_time=specific_time)
        result = metrics.to_dict()

        assert result["last_trigger_time"] == "2025-01-15T10:30:45+00:00"

    def test_multiple_hourly_resets(self):
        """Test multiple hourly resets work correctly."""
        config = CircuitBreakerConfig(bulk_change_threshold=1)
        service = CircuitBreakerService(config)

        # First hour
        service.metrics.last_hour_reset = datetime.now(UTC) - timedelta(hours=2)
        state1 = RepositoryState(repo_id="repo-1")
        service.check_and_update_bulk_change(state1, "/path/file1.txt")
        assert service.metrics.triggers_in_last_hour == 1

        # Simulate another hour passing
        service.metrics.last_hour_reset = datetime.now(UTC) - timedelta(hours=1, minutes=1)
        state2 = RepositoryState(repo_id="repo-2")
        service.check_and_update_bulk_change(state2, "/path/file2.txt")

        # Should have reset again
        assert service.metrics.triggers_in_last_hour == 1  # Reset, then incremented


class TestCircuitBreakerEventBlockingBehavior:
    """Tests for event blocking behavior details."""

    def test_already_triggered_blocks_bulk_change_count(self):
        """Test that already triggered CB doesn't increment bulk change count."""
        config = CircuitBreakerConfig(bulk_change_threshold=10)
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")

        # Manually trigger
        state.circuit_breaker_triggered = True

        # Try to record changes
        triggered = service.check_and_update_bulk_change(state, "/path/file.txt")

        assert triggered is True
        assert state.bulk_change_count == 0
        assert service.metrics.total_events_blocked == 1

    def test_blocked_events_tracked_in_metrics(self):
        """Test that multiple blocked events are tracked."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.circuit_breaker_triggered = True
        state.update_status(RepositoryStatus.BRANCH_CHANGE_ERROR)

        # Block multiple events
        for _ in range(10):
            service.should_process_event(state)

        assert service.metrics.total_events_blocked == 10

    def test_processed_events_in_warning_state(self):
        """Test that events in warning state are counted as processed."""
        config = CircuitBreakerConfig()
        service = CircuitBreakerService(config)
        state = RepositoryState(repo_id="test-repo")
        state.circuit_breaker_triggered = True
        state.update_status(RepositoryStatus.BRANCH_CHANGE_WARNING)

        service.should_process_event(state)

        assert service.metrics.total_events_processed == 1
        assert service.metrics.total_events_blocked == 0


# 🔼⚙️🔚
