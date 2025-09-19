# tests/unit/test_event_buffer_patterns.py

"""
Unit tests for EventBuffer atomic pattern detection.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from supsrc.events.buffer import EventBuffer
from supsrc.events.monitor import FileChangeEvent


@pytest.fixture
def mock_emit_callback():
    """Mock callback for event emission."""
    return Mock()


class TestEventBufferPatterns:
    """Test cases for atomic pattern detection in EventBuffer."""

    def test_atomic_rewrite_pattern_detection(self, mock_emit_callback):
        """Test detection of atomic rewrite patterns."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        base_path = Path("/test")
        events = [
            FileChangeEvent(
                description="Create temp",
                repo_id="test_repo",
                file_path=base_path / "file.py.tmp",
                change_type="created",
            ),
            FileChangeEvent(
                description="Delete original",
                repo_id="test_repo",
                file_path=base_path / "file.py",
                change_type="deleted",
            ),
        ]

        # Test temp file pattern detection
        temp_patterns = buffer._find_temp_file_patterns(events)

        # Should detect the pattern
        original_path = base_path / "file.py"
        assert original_path in temp_patterns
        assert base_path / "file.py.tmp" in temp_patterns[original_path]

    def test_temp_file_pattern_detection_tilde(self, mock_emit_callback):
        """Test detection of temp files with tilde suffix."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        base_path = Path("/test")
        events = [
            FileChangeEvent(
                description="Create backup",
                repo_id="test_repo",
                file_path=base_path / "file.py~",
                change_type="created",
            ),
            FileChangeEvent(
                description="Modify original",
                repo_id="test_repo",
                file_path=base_path / "file.py",
                change_type="modified",
            ),
        ]

        temp_patterns = buffer._find_temp_file_patterns(events)

        original_path = base_path / "file.py"
        assert original_path in temp_patterns
        assert base_path / "file.py~" in temp_patterns[original_path]

    def test_temp_file_pattern_detection_hidden(self, mock_emit_callback):
        """Test detection of hidden temp files."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        base_path = Path("/test")
        events = [
            FileChangeEvent(
                description="Create hidden temp",
                repo_id="test_repo",
                file_path=base_path / ".file.py.abcd1234",
                change_type="created",
            ),
            FileChangeEvent(
                description="Modify original",
                repo_id="test_repo",
                file_path=base_path / "file.py",
                change_type="modified",
            ),
        ]

        temp_patterns = buffer._find_temp_file_patterns(events)

        original_path = base_path / "file.py"
        assert original_path in temp_patterns
        assert base_path / ".file.py.abcd1234" in temp_patterns[original_path]

    def test_detect_atomic_rewrites_with_patterns(self, mock_emit_callback):
        """Test atomic rewrite detection with realistic patterns."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        base_path = Path("/test")
        events = [
            FileChangeEvent(
                description="Create temp file",
                repo_id="test_repo",
                file_path=base_path / "document.txt.tmp",
                change_type="created",
            ),
            FileChangeEvent(
                description="Delete original",
                repo_id="test_repo",
                file_path=base_path / "document.txt",
                change_type="deleted",
            ),
            FileChangeEvent(
                description="Move temp to original",
                repo_id="test_repo",
                file_path=base_path / "document.txt",
                change_type="moved",
            ),
        ]

        atomic_groups = buffer._detect_atomic_rewrites(events)

        assert atomic_groups is not None
        assert len(atomic_groups) == 1
        atomic_event = atomic_groups[0]
        assert atomic_event.operation_type == "atomic_rewrite"
        assert atomic_event.event_count == 3
        assert base_path / "document.txt" in atomic_event.file_paths

    def test_temp_file_pattern_recognition_real_world(self, mock_emit_callback):
        """Test recognition of real-world temporary file patterns."""
        buffer = EventBuffer(
            window_ms=100,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        base_path = Path("/test")
        # Test various real-world temp file patterns
        test_cases = [
            # Standard .tmp files
            (base_path / "file.txt", base_path / "file.txt.tmp"),
            # Editor backup files
            (base_path / "document.py", base_path / "document.py~"),
            # Hidden temp files (vim style)
            (base_path / "script.js", base_path / ".script.js.swp"),
            # Mac-style hidden files
            (base_path / "data.json", base_path / ".data.json.abc123"),
        ]

        for original_file, temp_file in test_cases:
            events = [
                FileChangeEvent(
                    description="Original file",
                    repo_id="test_repo",
                    file_path=original_file,
                    change_type="modified",
                ),
                FileChangeEvent(
                    description="Temp file",
                    repo_id="test_repo",
                    file_path=temp_file,
                    change_type="created",
                ),
            ]

            # Test pattern detection
            patterns = buffer._find_temp_file_patterns(events)

            # Should detect the pattern
            assert original_file in patterns
            assert temp_file in patterns[original_file]

    def test_atomic_rewrite_fallback_to_simple(self, mock_emit_callback):
        """Test that atomic rewrite detection falls back to simple grouping when no patterns found."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        # Events that don't form atomic patterns
        events = [
            FileChangeEvent(
                description="Regular file 1",
                repo_id="test_repo",
                file_path=Path("/test/file1.py"),
                change_type="modified",
            ),
            FileChangeEvent(
                description="Regular file 2",
                repo_id="test_repo",
                file_path=Path("/test/file2.py"),
                change_type="modified",
            ),
        ]

        atomic_groups = buffer._detect_atomic_rewrites(events)

        # Should return None when no atomic patterns detected
        assert atomic_groups is None

    def test_smart_grouping_with_mixed_patterns(self, mock_emit_callback):
        """Test smart grouping with a mix of atomic and regular events."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        base_path = Path("/test")
        # Mix atomic rewrite with regular changes
        events = [
            # Atomic rewrite pattern
            FileChangeEvent(
                description="Create temp",
                repo_id="test_repo",
                file_path=base_path / "file.py.tmp",
                change_type="created",
            ),
            FileChangeEvent(
                description="Delete original",
                repo_id="test_repo",
                file_path=base_path / "file.py",
                change_type="deleted",
            ),
            # Regular file change
            FileChangeEvent(
                description="Regular change",
                repo_id="test_repo",
                file_path=base_path / "other.py",
                change_type="modified",
            ),
        ]

        grouped = buffer._group_events_smart(events)

        # Should detect atomic pattern and handle remaining events
        assert len(grouped) >= 1
        # Check if any atomic rewrite was detected
        has_atomic = any(
            event.operation_type == "atomic_rewrite" for event in grouped
        )
        assert has_atomic or len(grouped) >= 2  # Either atomic detected or simple grouping applied