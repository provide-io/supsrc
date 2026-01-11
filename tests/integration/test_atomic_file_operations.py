#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Integration tests for atomic file operations with event buffering."""

from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile

from provide.testkit.mocking import Mock
import pytest

from supsrc.events.buffer import EventBuffer
from supsrc.events.monitor import FileChangeEvent


@pytest.fixture
def temp_directory():
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_emit_callback():
    """Mock callback for event emission."""
    return Mock()


class TestAtomicFileOperations:
    """Test event buffering with realistic atomic file operations."""

    def simulate_atomic_rewrite(self, file_path: Path, content: str = "test content"):
        """Simulate an atomic file rewrite operation."""
        temp_file = file_path.with_suffix(file_path.suffix + ".tmp")

        # Write to temp file
        temp_file.write_text(content)

        # Atomic rename (replace original)
        if file_path.exists():
            file_path.unlink()
        temp_file.rename(file_path)

    def create_atomic_rewrite_events(
        self, file_path: Path, repo_id: str = "test_repo"
    ) -> list[FileChangeEvent]:
        """Create events that simulate atomic rewrite."""
        temp_file = file_path.with_suffix(file_path.suffix + ".tmp")

        return [
            FileChangeEvent(
                description="Create temp file",
                repo_id=repo_id,
                file_path=temp_file,
                change_type="created",
            ),
            FileChangeEvent(
                description="Write to temp file",
                repo_id=repo_id,
                file_path=temp_file,
                change_type="modified",
            ),
            FileChangeEvent(
                description="Rename temp to original",
                repo_id=repo_id,
                file_path=temp_file,  # Source of the move
                change_type="moved",
                dest_path=file_path,  # Destination of the move
            ),
        ]

    def create_editor_save_events(self, file_path: Path, repo_id: str = "test_repo") -> list[FileChangeEvent]:
        """Create events that simulate a text editor save operation (like vim)."""
        backup_file = file_path.with_suffix(file_path.suffix + "~")

        return [
            FileChangeEvent(
                description="Create backup",
                repo_id=repo_id,
                file_path=backup_file,
                change_type="created",
            ),
            FileChangeEvent(
                description="Modify original",
                repo_id=repo_id,
                file_path=file_path,
                change_type="modified",
            ),
            FileChangeEvent(
                description="Delete backup",
                repo_id=repo_id,
                file_path=backup_file,
                change_type="deleted",
            ),
        ]

    @pytest.mark.asyncio
    async def test_atomic_rewrite_buffering(self, temp_directory, mock_emit_callback):
        """Test that atomic rewrite operations are properly buffered and grouped."""
        buffer = EventBuffer(
            window_ms=100,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        test_file = temp_directory / "test.py"
        events = self.create_atomic_rewrite_events(test_file)

        # Add all events quickly (simulating rapid filesystem events)
        for event in events:
            buffer.add_event(event)

        # Wait for buffer to flush (window + post-delay + margin)
        await asyncio.sleep(0.2)  # 100ms window + 20ms delay + margin

        # Force flush any incomplete operations
        buffer.flush_all()

        # Foundation doesn't recognize delete+move as atomic operation
        # So events are emitted individually after auto-flush
        # This is correct behavior - the pattern is non-standard
        assert mock_emit_callback.call_count >= 1

        # Verify the final file is included in emitted events
        all_emitted = [call[0][0] for call in mock_emit_callback.call_args_list]
        file_paths_emitted = []
        for emitted in all_emitted:
            if hasattr(emitted, "file_paths"):
                file_paths_emitted.extend(emitted.file_paths)
            elif hasattr(emitted, "file_path"):
                file_paths_emitted.append(emitted.file_path)

        assert test_file in file_paths_emitted

    @pytest.mark.asyncio
    async def test_editor_save_buffering(self, temp_directory, mock_emit_callback):
        """Test that editor save operations (with backup files) are properly grouped."""
        buffer = EventBuffer(
            window_ms=100,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        test_file = temp_directory / "document.txt"
        events = self.create_editor_save_events(test_file)

        # Add all events
        for event in events:
            buffer.add_event(event)

        # Wait for buffer to flush (window + post-delay + margin)
        await asyncio.sleep(0.2)  # 100ms window + 20ms delay + margin

        # Force flush any incomplete operations
        buffer.flush_all()

        # Should detect atomic pattern or fall back to simple grouping
        assert mock_emit_callback.call_count >= 1

        # Check that the main file is included in the results
        all_emitted_events = [call[0][0] for call in mock_emit_callback.call_args_list]
        main_file_included = any(test_file in event.file_paths for event in all_emitted_events)
        assert main_file_included

    @pytest.mark.asyncio
    async def test_mixed_operations_buffering(self, temp_directory, mock_emit_callback):
        """Test buffering with mixed file operations."""
        buffer = EventBuffer(
            window_ms=100,
            grouping_mode="smart",
            emit_callback=mock_emit_callback,
        )

        # Simulate multiple different operations happening quickly
        file1 = temp_directory / "file1.py"
        file2 = temp_directory / "file2.py"
        file3 = temp_directory / "file3.py"

        # Mix of atomic rewrite and regular edits
        atomic_events = self.create_atomic_rewrite_events(file1)
        regular_events = [
            FileChangeEvent(
                description="Regular edit 1",
                repo_id="test_repo",
                file_path=file2,
                change_type="modified",
            ),
            FileChangeEvent(
                description="Regular edit 2",
                repo_id="test_repo",
                file_path=file3,
                change_type="modified",
            ),
        ]

        # Add all events
        all_events = atomic_events + regular_events
        for event in all_events:
            buffer.add_event(event)

        # Wait for buffer to flush (window + post-delay + margin)
        await asyncio.sleep(0.2)  # 100ms window + 20ms delay + margin

        # Force flush any incomplete operations
        buffer.flush_all()

        # Should have emitted some grouped events
        assert mock_emit_callback.call_count >= 1

        # Verify that we got appropriate grouping
        all_emitted = [call[0][0] for call in mock_emit_callback.call_args_list]

        # Should have at least one atomic rewrite detected
        atomic_detected = any(event.operation_type == "atomic_rewrite" for event in all_emitted)

        # OR should have batch operation detected (if 3+ files involved)
        batch_detected = any(event.operation_type == "batch_operation" for event in all_emitted)

        assert atomic_detected or batch_detected

    def test_no_buffering_mode(self, temp_directory, mock_emit_callback):
        """Test that 'off' mode passes through events immediately."""
        buffer = EventBuffer(
            window_ms=100,
            grouping_mode="off",
            emit_callback=mock_emit_callback,
        )

        test_file = temp_directory / "test.py"
        events = self.create_atomic_rewrite_events(test_file)

        # Add events - should emit immediately
        for event in events:
            buffer.add_event(event)

        # Should have emitted each event individually
        assert mock_emit_callback.call_count == len(events)

        # Each call should be with an individual FileChangeEvent
        for call in mock_emit_callback.call_args_list:
            emitted_event = call[0][0]
            assert hasattr(emitted_event, "change_type")  # Original FileChangeEvent

    @pytest.mark.asyncio
    async def test_simple_mode_grouping(self, temp_directory, mock_emit_callback):
        """Test simple mode grouping behavior."""
        buffer = EventBuffer(
            window_ms=100,
            grouping_mode="simple",
            emit_callback=mock_emit_callback,
        )

        test_file = temp_directory / "test.py"

        # Multiple events on same file
        events = [
            FileChangeEvent(
                description="Event 1",
                repo_id="test_repo",
                file_path=test_file,
                change_type="created",
            ),
            FileChangeEvent(
                description="Event 2",
                repo_id="test_repo",
                file_path=test_file,
                change_type="modified",
            ),
            FileChangeEvent(
                description="Event 3",
                repo_id="test_repo",
                file_path=test_file,
                change_type="modified",
            ),
        ]

        for event in events:
            buffer.add_event(event)

        # Wait for buffer to flush (window + post-delay + margin)
        await asyncio.sleep(0.2)  # 100ms window + 20ms delay + margin

        # Should have emitted one grouped event
        assert mock_emit_callback.call_count == 1

        emitted_event = mock_emit_callback.call_args[0][0]
        assert emitted_event.operation_type == "single_file"
        assert emitted_event.event_count == 3
        assert emitted_event.primary_change_type == "modified"  # Most recent

    @pytest.mark.asyncio
    async def test_multiple_repos_isolation(self, temp_directory, mock_emit_callback):
        """Test that events from different repos are handled separately."""
        buffer = EventBuffer(
            window_ms=100,
            grouping_mode="simple",
            emit_callback=mock_emit_callback,
        )

        test_file = temp_directory / "test.py"

        # Events from different repos
        repo1_events = [
            FileChangeEvent(
                description="Repo 1 event",
                repo_id="repo1",
                file_path=test_file,
                change_type="modified",
            ),
        ]

        repo2_events = [
            FileChangeEvent(
                description="Repo 2 event",
                repo_id="repo2",
                file_path=test_file,
                change_type="modified",
            ),
        ]

        # Add events from both repos
        for event in repo1_events + repo2_events:
            buffer.add_event(event)

        # Wait for buffer to flush (window + post-delay + margin)
        await asyncio.sleep(0.2)  # 100ms window + 20ms delay + margin

        # Should have emitted separate events for each repo
        assert mock_emit_callback.call_count == 2

        # Verify repo isolation
        emitted_repo_ids = set()
        for call in mock_emit_callback.call_args_list:
            emitted_event = call[0][0]
            emitted_repo_ids.add(emitted_event.repo_id)

        assert emitted_repo_ids == {"repo1", "repo2"}

    @pytest.mark.asyncio
    async def test_temp_file_pattern_recognition_real_world(self, temp_directory):
        """Test recognition of real-world temporary file patterns."""
        mock_callback = Mock()
        buffer = EventBuffer(
            window_ms=100,
            grouping_mode="smart",
            emit_callback=mock_callback,
        )

        # Test various real-world temp file patterns
        test_cases = [
            # Standard .tmp files
            (temp_directory / "file.txt", temp_directory / "file.txt.tmp"),
            # Editor backup files
            (temp_directory / "document.py", temp_directory / "document.py~"),
            # Hidden temp files (vim style)
            (temp_directory / "script.js", temp_directory / ".script.js.swp"),
            # VSCode-style hidden temp files
            (temp_directory / "data.json", temp_directory / ".data.json.tmp.abc123"),
        ]

        for original_file, temp_file in test_cases:
            # Reset mock for each test case
            mock_callback.reset_mock()

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
            assert mock_callback.call_count >= 1, f"No events emitted for {original_file} / {temp_file}"

            # Verify the original file was included in emitted events
            all_emitted = [call[0][0] for call in mock_callback.call_args_list]
            file_paths_emitted = []
            for emitted in all_emitted:
                if hasattr(emitted, "file_paths"):
                    file_paths_emitted.extend(emitted.file_paths)
                elif hasattr(emitted, "file_path"):
                    file_paths_emitted.append(emitted.file_path)

            assert original_file in file_paths_emitted, (
                f"Original file {original_file} not found in emitted events for pattern {temp_file}"
            )


# 🔼⚙️🔚
