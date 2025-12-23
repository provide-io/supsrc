#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Integration tests for VSCode atomic save pattern with EventBuffer.

This test verifies that the full stack (supsrc EventBuffer + provide-foundation detectors)
correctly handles VSCode's atomic save pattern and emits events with the correct final
file path, not the temporary file path."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from provide.testkit.mocking import Mock

from supsrc.events.buffer import EventBuffer
from supsrc.events.monitor import FileChangeEvent


def _unique_repo_id() -> str:
    """Generate a unique repo_id for test isolation under parallel execution (pytest-xdist)."""
    return f"test_repo_{uuid.uuid4().hex[:8]}"


class TestVSCodeAtomicSaveIntegration:
    """Test VSCode atomic save pattern through the EventBuffer."""

    @pytest.mark.asyncio
    async def test_vscode_atomic_save_shows_final_file(self):
        """Test that VSCode atomic save shows final file path, not temp file path."""
        mock_callback = Mock()

        # Create buffer with smart mode (uses operation detection)
        buffer = EventBuffer(
            window_ms=500,
            grouping_mode="smart",
            emit_callback=mock_callback,
        )

        # Simulate VSCode editing orchestrator.py
        # VSCode pattern: .orchestrator.py.tmp.84 -> orchestrator.py
        temp_file = Path(".orchestrator.py.tmp.84")
        final_file = Path("orchestrator.py")
        repo_id = _unique_repo_id()

        # Event 1: Create temp file
        buffer.add_event(
            FileChangeEvent(
                description=f"File created: {temp_file.name}",
                repo_id=repo_id,
                file_path=temp_file,
                change_type="created",
            )
        )

        await asyncio.sleep(0.01)

        # Event 2: Modify temp file
        buffer.add_event(
            FileChangeEvent(
                description=f"File modified: {temp_file.name}",
                repo_id=repo_id,
                file_path=temp_file,
                change_type="modified",
            )
        )

        await asyncio.sleep(0.01)

        # Event 3: Move temp to final
        buffer.add_event(
            FileChangeEvent(
                description=f"File moved: {temp_file.name} -> {final_file.name}",
                repo_id=repo_id,
                file_path=temp_file,
                change_type="moved",
                dest_path=final_file,
            )
        )

        # Wait for auto-flush (500ms) + post-operation delay (150ms) + margin
        await asyncio.sleep(0.8)

        # Explicitly flush to ensure all events are processed (best practice from CLAUDE.md)
        buffer.flush_all()

        # Verify callback was called
        assert mock_callback.call_count >= 1, f"Expected at least 1 callback, got {mock_callback.call_count}"

        # Find the emitted event(s) and verify the file path
        all_emitted = [call[0][0] for call in mock_callback.call_args_list]

        # Check that the final file is in the emitted events
        emitted_files = []
        for event in all_emitted:
            if hasattr(event, "file_paths"):
                emitted_files.extend(event.file_paths)
            elif hasattr(event, "file_path"):
                emitted_files.append(event.file_path)

        assert final_file in emitted_files, f"Expected '{final_file}' in emitted files, got {emitted_files}"

        # Verify the temp file is NOT in the emitted events
        assert temp_file not in emitted_files, (
            f"Temp file '{temp_file}' should not be in emitted files, got {emitted_files}"
        )

        # Verify at least one event shows as atomic_rewrite (the operation type)
        operation_types = [getattr(event, "operation_type", None) for event in all_emitted]
        assert "atomic_rewrite" in operation_types, (
            f"Expected 'atomic_rewrite' operation, got {operation_types}"
        )

    @pytest.mark.asyncio
    async def test_vscode_pattern_with_nested_dots(self):
        """Test VSCode pattern with filename containing multiple dots."""
        mock_callback = Mock()

        buffer = EventBuffer(
            window_ms=500,
            grouping_mode="smart",
            emit_callback=mock_callback,
        )

        # File with multiple dots: test.config.py
        temp_file = Path(".test.config.py.tmp.123")
        final_file = Path("test.config.py")
        repo_id = _unique_repo_id()

        # Simulate atomic save
        buffer.add_event(
            FileChangeEvent(
                description=f"File created: {temp_file.name}",
                repo_id=repo_id,
                file_path=temp_file,
                change_type="created",
            )
        )

        await asyncio.sleep(0.01)

        buffer.add_event(
            FileChangeEvent(
                description=f"File moved: {temp_file.name} -> {final_file.name}",
                repo_id=repo_id,
                file_path=temp_file,
                change_type="moved",
                dest_path=final_file,
            )
        )

        # Wait for auto-flush (500ms) + post-operation delay (150ms) + margin
        await asyncio.sleep(0.8)

        # Explicitly flush to ensure all events are processed
        buffer.flush_all()

        # Verify the final file with all dots preserved
        assert mock_callback.call_count >= 1
        all_emitted = [call[0][0] for call in mock_callback.call_args_list]

        emitted_files = []
        for event in all_emitted:
            if hasattr(event, "file_paths"):
                emitted_files.extend(event.file_paths)
            elif hasattr(event, "file_path"):
                emitted_files.append(event.file_path)

        assert final_file in emitted_files, (
            f"Expected '{final_file}' with all dots preserved, got {emitted_files}"
        )

    @pytest.mark.asyncio
    async def test_temp_file_hidden_until_operation_complete(self):
        """Test that temp file events are hidden until the operation completes."""
        mock_callback = Mock()

        buffer = EventBuffer(
            window_ms=500,
            grouping_mode="smart",
            emit_callback=mock_callback,
        )

        temp_file = Path(".test.py.tmp.999")
        final_file = Path("test.py")
        repo_id = _unique_repo_id()

        # Add only temp file creation (incomplete operation)
        buffer.add_event(
            FileChangeEvent(
                description=f"File created: {temp_file.name}",
                repo_id=repo_id,
                file_path=temp_file,
                change_type="created",
            )
        )

        # Temp file modification (still incomplete)
        await asyncio.sleep(0.05)
        buffer.add_event(
            FileChangeEvent(
                description=f"File modified: {temp_file.name}",
                repo_id=repo_id,
                file_path=temp_file,
                change_type="modified",
            )
        )

        # Wait a bit but not enough to trigger auto-flush
        await asyncio.sleep(0.1)

        # No callback yet - temp files are buffered
        assert mock_callback.call_count == 0, (
            "Temp file events should not trigger callback before operation completes"
        )

        # Now complete the operation
        buffer.add_event(
            FileChangeEvent(
                description=f"File moved: {temp_file.name} -> {final_file.name}",
                repo_id=repo_id,
                file_path=temp_file,
                change_type="moved",
                dest_path=final_file,
            )
        )

        # Wait for auto-flush (500ms) + post-operation delay (150ms) + margin
        await asyncio.sleep(0.8)

        # Explicitly flush to ensure all events are processed
        buffer.flush_all()

        # NOW callback should fire with the complete operation
        assert mock_callback.call_count >= 1, "Callback should fire after operation completes"

        # Verify it shows the final file
        all_emitted = [call[0][0] for call in mock_callback.call_args_list]
        emitted_files = []
        for event in all_emitted:
            if hasattr(event, "file_paths"):
                emitted_files.extend(event.file_paths)

        assert final_file in emitted_files

    @pytest.mark.asyncio
    async def test_multiple_vscode_saves_in_sequence(self):
        """Test multiple VSCode atomic saves in sequence."""
        mock_callback = Mock()

        buffer = EventBuffer(
            window_ms=500,
            grouping_mode="smart",
            emit_callback=mock_callback,
        )

        repo_id = _unique_repo_id()

        # First file save
        buffer.add_event(
            FileChangeEvent(
                description="Create temp 1",
                repo_id=repo_id,
                file_path=Path(".file1.py.tmp.1"),
                change_type="created",
            )
        )
        buffer.add_event(
            FileChangeEvent(
                description="Move temp 1",
                repo_id=repo_id,
                file_path=Path(".file1.py.tmp.1"),
                change_type="moved",
                dest_path=Path("file1.py"),
            )
        )

        # Wait for first operation: auto-flush (500ms) + post-operation delay (150ms) + margin
        await asyncio.sleep(0.8)

        # Second file save (space operations apart to avoid bundling)
        await asyncio.sleep(1.0)

        buffer.add_event(
            FileChangeEvent(
                description="Create temp 2",
                repo_id=repo_id,
                file_path=Path(".file2.py.tmp.2"),
                change_type="created",
            )
        )
        buffer.add_event(
            FileChangeEvent(
                description="Move temp 2",
                repo_id=repo_id,
                file_path=Path(".file2.py.tmp.2"),
                change_type="moved",
                dest_path=Path("file2.py"),
            )
        )

        # Wait for second operation: auto-flush (500ms) + post-operation delay (150ms) + margin
        await asyncio.sleep(0.8)

        # Explicitly flush to ensure all events are processed
        buffer.flush_all()

        # Should have at least 2 callbacks
        assert mock_callback.call_count >= 2, (
            f"Expected at least 2 callbacks for 2 operations, got {mock_callback.call_count}"
        )

        # Verify both final files are in the emitted events
        all_emitted = [call[0][0] for call in mock_callback.call_args_list]
        emitted_files = []
        for event in all_emitted:
            if hasattr(event, "file_paths"):
                emitted_files.extend(event.file_paths)

        assert Path("file1.py") in emitted_files
        assert Path("file2.py") in emitted_files

        # Verify no temp files in emitted events
        temp_files = [
            Path(".file1.py.tmp.1"),
            Path(".file2.py.tmp.2"),
        ]
        for temp_file in temp_files:
            assert temp_file not in emitted_files, f"Temp file {temp_file} should not be emitted"

    @pytest.mark.asyncio
    async def test_vscode_pattern_matches_real_world_behavior(self):
        """Test with pattern exactly as VSCode generates it."""
        mock_callback = Mock()

        buffer = EventBuffer(
            window_ms=500,
            grouping_mode="smart",
            emit_callback=mock_callback,
        )

        # Real VSCode pattern from the bug report
        temp_file = Path(".orchestrator.py.tmp.84")
        final_file = Path("orchestrator.py")
        repo_id = _unique_repo_id()

        # Exactly as watchdog would report it
        buffer.add_event(
            FileChangeEvent(
                description="VSCode temp file created",
                repo_id=repo_id,
                file_path=temp_file,
                change_type="created",
            )
        )

        buffer.add_event(
            FileChangeEvent(
                description="VSCode atomic rename",
                repo_id=repo_id,
                file_path=temp_file,
                change_type="moved",
                dest_path=final_file,
            )
        )

        # Wait for auto-flush (500ms) + post-operation delay (150ms) + margin
        await asyncio.sleep(0.8)

        # Explicitly flush to ensure all events are processed
        buffer.flush_all()

        # Critical assertion: final file should be "orchestrator.py" NOT ".orchestrator.py"
        assert mock_callback.call_count >= 1

        all_emitted = [call[0][0] for call in mock_callback.call_args_list]
        emitted_files = []
        for event in all_emitted:
            if hasattr(event, "file_paths"):
                emitted_files.extend(event.file_paths)

        # The bug was: emitted_files contained Path(".orchestrator.py")
        # After fix: should contain Path("orchestrator.py")
        assert final_file in emitted_files, (
            f"Expected 'orchestrator.py' (without leading dot), got {emitted_files}"
        )

        # Make sure the buggy version is NOT present
        buggy_file = Path(".orchestrator.py")
        assert buggy_file not in emitted_files, (
            "Buggy file '.orchestrator.py' (with leading dot) should not be emitted"
        )


# 🔼⚙️🔚
