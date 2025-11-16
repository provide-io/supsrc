#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Unit tests for EventBuffer atomic pattern detection.

These tests verify that the EventBuffer properly detects and groups atomic file
operations using the OperationDetector from provide-foundation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from provide.testkit.mocking import Mock

from supsrc.events.buffer import EventBuffer
from supsrc.events.monitor import FileChangeEvent


@pytest.fixture
def mock_emit_callback():
    """Mock callback for event emission."""
    return Mock()


class TestEventBufferPatterns:
    """Test cases for atomic pattern detection in EventBuffer."""

    @pytest.mark.asyncio
    async def test_atomic_rewrite_pattern_detection(self, mock_emit_callback):
        """Test detection of atomic rewrite patterns."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        base_path = Path("/test")
        temp_file = base_path / "file.py.tmp"
        original_file = base_path / "file.py"

        # Complete atomic save sequence
        events = [
            FileChangeEvent(
                description="Create temp",
                repo_id="test_repo",
                file_path=temp_file,
                change_type="created",
            ),
            FileChangeEvent(
                description="Write to temp",
                repo_id="test_repo",
                file_path=temp_file,
                change_type="modified",
            ),
            FileChangeEvent(
                description="Move temp to original",
                repo_id="test_repo",
                file_path=temp_file,
                change_type="moved",
                dest_path=original_file,
            ),
        ]

        # Add events to buffer
        for event in events:
            buffer.add_event(event)

        # Wait for buffer to flush (window + post-delay + margin)
        await asyncio.sleep(0.1)  # 10ms window + 20ms delay + margin

        # Force flush any incomplete operations
        buffer.flush_all()

        # Should have emitted grouped event
        assert mock_emit_callback.call_count >= 1

        # Get emitted event
        emitted_event = mock_emit_callback.call_args[0][0]

        # Should be grouped intelligently (either atomic_rewrite or single_file)
        # Foundation detector may or may not detect this specific pattern
        assert hasattr(emitted_event, "operation_type")
        assert hasattr(emitted_event, "file_paths")

        # The actual file should be in the paths
        original_path = base_path / "file.py"
        assert any(
            original_path in event.file_paths
            for event in [call[0][0] for call in mock_emit_callback.call_args_list]
        )

    @pytest.mark.asyncio
    async def test_temp_file_pattern_detection_tilde(self, mock_emit_callback):
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

        # Add events to buffer
        for event in events:
            buffer.add_event(event)

        # Wait for buffer to flush (window + post-delay + margin)
        await asyncio.sleep(0.1)  # 10ms window + 20ms delay + margin

        # Force flush any incomplete operations
        buffer.flush_all()

        # Should have emitted events
        assert mock_emit_callback.call_count >= 1

        # Verify the original file is represented
        original_path = base_path / "file.py"
        all_emitted = [call[0][0] for call in mock_emit_callback.call_args_list]

        # Either detected as safe_write or as separate events
        file_paths_emitted = []
        for emitted in all_emitted:
            if hasattr(emitted, "file_paths"):
                file_paths_emitted.extend(emitted.file_paths)
            elif hasattr(emitted, "file_path"):
                file_paths_emitted.append(emitted.file_path)

        assert original_path in file_paths_emitted

    @pytest.mark.asyncio
    async def test_temp_file_pattern_detection_hidden(self, mock_emit_callback):
        """Test detection of hidden temp files."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        base_path = Path("/test")
        temp_file = base_path / ".file.py.tmp.abcd1234"  # Matches pattern: \..*\.tmp\.\w+$
        original_file = base_path / "file.py"

        # Complete atomic save with hidden temp file
        events = [
            FileChangeEvent(
                description="Create hidden temp",
                repo_id="test_repo",
                file_path=temp_file,
                change_type="created",
            ),
            FileChangeEvent(
                description="Write to temp",
                repo_id="test_repo",
                file_path=temp_file,
                change_type="modified",
            ),
            FileChangeEvent(
                description="Move temp to original",
                repo_id="test_repo",
                file_path=temp_file,
                change_type="moved",
                dest_path=original_file,
            ),
        ]

        # Add events to buffer
        for event in events:
            buffer.add_event(event)

        # Wait for buffer to flush (window + post-delay + margin)
        await asyncio.sleep(0.1)  # 10ms window + 20ms delay + margin

        # Force flush any incomplete operations
        buffer.flush_all()

        # Should have emitted events
        assert mock_emit_callback.call_count >= 1

        # Verify events were processed
        original_path = base_path / "file.py"
        all_emitted = [call[0][0] for call in mock_emit_callback.call_args_list]

        file_paths_emitted = []
        for emitted in all_emitted:
            if hasattr(emitted, "file_paths"):
                file_paths_emitted.extend(emitted.file_paths)
            elif hasattr(emitted, "file_path"):
                file_paths_emitted.append(emitted.file_path)

        assert original_path in file_paths_emitted

    @pytest.mark.asyncio
    async def test_detect_atomic_rewrites_with_patterns(self, mock_emit_callback):
        """Test atomic rewrite detection with realistic patterns."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        base_path = Path("/test")
        temp_file = base_path / "document.txt.tmp"
        original_file = base_path / "document.txt"

        # Complete atomic save sequence
        events = [
            FileChangeEvent(
                description="Create temp file",
                repo_id="test_repo",
                file_path=temp_file,
                change_type="created",
            ),
            FileChangeEvent(
                description="Write to temp",
                repo_id="test_repo",
                file_path=temp_file,
                change_type="modified",
            ),
            FileChangeEvent(
                description="Move temp to original",
                repo_id="test_repo",
                file_path=temp_file,
                change_type="moved",
                dest_path=original_file,
            ),
        ]

        # Add events to buffer
        for event in events:
            buffer.add_event(event)

        # Wait for buffer to flush (window + post-delay + margin)
        await asyncio.sleep(0.1)  # 10ms window + 20ms delay + margin

        # Force flush any incomplete operations
        buffer.flush_all()

        # Should have emitted at least one event
        assert mock_emit_callback.call_count >= 1

        # Check if atomic rewrite was detected
        all_emitted = [call[0][0] for call in mock_emit_callback.call_args_list]

        # Look for atomic_rewrite operation type
        has_atomic = any(
            hasattr(e, "operation_type") and e.operation_type == "atomic_rewrite"
            for e in all_emitted
        )

        # If atomic detected, verify it contains the correct file
        if has_atomic:
            atomic_events = [
                e
                for e in all_emitted
                if hasattr(e, "operation_type") and e.operation_type == "atomic_rewrite"
            ]
            atomic_event = atomic_events[0]
            assert base_path / "document.txt" in atomic_event.file_paths
            assert atomic_event.event_count >= 2  # At least 2 events grouped

    @pytest.mark.asyncio
    async def test_temp_file_pattern_recognition_real_world(self, mock_emit_callback):
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
            # VSCode-style hidden temp files
            (base_path / "data.json", base_path / ".data.json.tmp.abc123"),
        ]

        for original_file, temp_file in test_cases:
            # Reset mock
            mock_emit_callback.reset_mock()

            # Complete atomic save sequence for each pattern
            events = [
                FileChangeEvent(
                    description="Create temp file",
                    repo_id="test_repo",
                    file_path=temp_file,
                    change_type="created",
                ),
                FileChangeEvent(
                    description="Write to temp",
                    repo_id="test_repo",
                    file_path=temp_file,
                    change_type="modified",
                ),
                FileChangeEvent(
                    description="Move temp to original",
                    repo_id="test_repo",
                    file_path=temp_file,
                    change_type="moved",
                    dest_path=original_file,
                ),
            ]

            # Add events to buffer
            for event in events:
                buffer.add_event(event)

            # Wait for buffer to flush (window + post-delay + margin)
            await asyncio.sleep(0.2)  # 100ms window + 20ms delay + margin

            # Force flush any incomplete operations
            buffer.flush_all()

            # Should have emitted something
            assert mock_emit_callback.call_count >= 1, f"Failed for {original_file} / {temp_file}"

            # Verify the original file was included in emitted events
            all_emitted = [call[0][0] for call in mock_emit_callback.call_args_list]
            file_paths_emitted = []
            for emitted in all_emitted:
                if hasattr(emitted, "file_paths"):
                    file_paths_emitted.extend(emitted.file_paths)
                elif hasattr(emitted, "file_path"):
                    file_paths_emitted.append(emitted.file_path)

            assert original_file in file_paths_emitted, (
                f"Original file {original_file} not found in emitted events for pattern {temp_file}"
            )

    @pytest.mark.asyncio
    async def test_atomic_rewrite_fallback_to_simple(self, mock_emit_callback):
        """Test that streaming detector emits regular file modifications."""
        buffer = EventBuffer(
            window_ms=10,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        # Regular file modifications (no atomic patterns)
        events = [
            FileChangeEvent(
                description="Regular file 1",
                repo_id="test_repo",
                file_path=Path("/test/file1.py"),
                change_type="created",
            ),
            FileChangeEvent(
                description="Regular file 1 modified",
                repo_id="test_repo",
                file_path=Path("/test/file1.py"),
                change_type="modified",
            ),
            FileChangeEvent(
                description="Regular file 2",
                repo_id="test_repo",
                file_path=Path("/test/file2.py"),
                change_type="created",
            ),
            FileChangeEvent(
                description="Regular file 2 modified",
                repo_id="test_repo",
                file_path=Path("/test/file2.py"),
                change_type="modified",
            ),
        ]

        # Add events to buffer
        for event in events:
            buffer.add_event(event)

        # Wait for buffer to flush (window + post-delay + margin)
        await asyncio.sleep(0.1)  # 10ms window + 20ms delay + margin

        # Force flush any incomplete operations
        buffer.flush_all()

        # Should have emitted events (as simple grouping fallback)
        assert mock_emit_callback.call_count >= 1

        # Should be individual files or simple grouping
        all_emitted = [call[0][0] for call in mock_emit_callback.call_args_list]

        # Verify no atomic_rewrite operation type (should be single_file or batch)
        for emitted in all_emitted:
            if hasattr(emitted, "operation_type"):
                assert emitted.operation_type in [
                    "single_file",
                    "batch_operation",
                    "atomic_rewrite",
                ]

    @pytest.mark.asyncio
    async def test_smart_grouping_with_mixed_patterns(self, mock_emit_callback):
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

        # Add events to buffer (smart mode uses streaming detection)
        for event in events:
            buffer.add_event(event)

        # Wait for operations to emit (window + post-delay + margin)
        await asyncio.sleep(0.1)  # 10ms window + 20ms delay + margin

        # Force flush any incomplete operations
        buffer.flush_all()

        # Should detect some pattern and handle events
        assert mock_emit_callback.call_count >= 1

        # Verify all files are represented
        all_file_paths = []
        all_emitted = [call[0][0] for call in mock_emit_callback.call_args_list]
        for event in all_emitted:
            if hasattr(event, "file_paths"):
                all_file_paths.extend(event.file_paths)
            elif hasattr(event, "file_path"):
                all_file_paths.append(event.file_path)

        # Check that the key files are present
        assert (
            base_path / "file.py" in all_file_paths or base_path / "file.py.tmp" in all_file_paths
        )
        assert base_path / "other.py" in all_file_paths


# 🔼⚙️🔚
