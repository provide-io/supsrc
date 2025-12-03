#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Integration tests for console verbose output mode.

This test verifies that the ConsoleEventFormatter correctly displays verbose
details for atomic operations, batch operations, and git events."""

from __future__ import annotations

import asyncio
from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

from supsrc.engines.git.events import GitCommitEvent, GitPushEvent
from supsrc.events.buffer import EventBuffer
from supsrc.events.buffer_events import BufferedFileChangeEvent
from supsrc.events.monitor import FileChangeEvent
from supsrc.output.console_formatter import ConsoleEventFormatter


class TestConsoleVerboseOutput:
    """Test console formatter verbose mode with complex scenarios."""

    @pytest.mark.skip(reason="EventBuffer async timing - covered by test_vscode_atomic_save.py")
    @pytest.mark.asyncio
    async def test_vscode_atomic_save_verbose_output(self):
        """Test verbose output shows atomic save operation sequence."""
        # Capture console output
        output = StringIO()
        console = Console(file=output, width=120, force_terminal=True)

        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,  # Easier to test without ANSI codes
            use_ascii=True,  # ASCII mode for consistent output
            verbose=True,  # Enable verbose mode
        )

        # Create mock callback to capture emitted events
        emitted_events = []

        def capture_event(event):
            emitted_events.append(event)
            formatter.format_and_print(event)

        # Create buffer with smart mode
        buffer = EventBuffer(
            window_ms=100,  # Reduced window for faster tests
            grouping_mode="smart",
            emit_callback=capture_event,
        )

        # Simulate VSCode atomic save pattern
        temp_file = Path("/test/repo/.config.py.tmp.abc123")
        final_file = Path("/test/repo/config.py")
        repo_id = "test_repo"

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

        # Wait for buffer to flush (100ms window + 150ms post-op delay + margin)
        await asyncio.sleep(1.0)

        # Verify event was emitted
        assert len(emitted_events) >= 1, "Expected at least one event to be emitted"

        buffered_event = emitted_events[0]
        assert isinstance(buffered_event, BufferedFileChangeEvent)
        assert buffered_event.operation_type == "atomic_rewrite"

        # Verify verbose output contains operation sequence
        output_text = output.getvalue()

        # Should show operation type
        assert "atomic_rewrite" in output_text, "Verbose output should show operation type"

        # Should show sequence details
        assert "Sequence" in output_text, "Verbose output should show operation sequence"

        # Should show the final file path
        assert "config.py" in output_text, "Verbose output should show final file path"

        # Should show aggregation count
        assert "3 raw events" in output_text or "event" in output_text.lower(), (
            "Verbose output should show event aggregation"
        )

    @pytest.mark.skip(reason="EventBuffer async timing - covered by test_vscode_atomic_save.py")
    @pytest.mark.asyncio
    async def test_batch_operation_verbose_output(self):
        """Test verbose output for batch file operations."""
        output = StringIO()
        console = Console(file=output, width=120, force_terminal=True)

        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,
            use_ascii=True,
            verbose=True,
        )

        emitted_events = []

        def capture_event(event):
            emitted_events.append(event)
            formatter.format_and_print(event)

        buffer = EventBuffer(
            window_ms=100,
            grouping_mode="smart",
            emit_callback=capture_event,
        )

        repo_id = "batch_repo"
        files = [Path(f"/test/repo/file{i}.txt") for i in range(5)]

        # Simulate batch modification
        for file in files:
            buffer.add_event(
                FileChangeEvent(
                    description=f"File modified: {file.name}",
                    repo_id=repo_id,
                    file_path=file,
                    change_type="modified",
                )
            )
            await asyncio.sleep(0.01)

        # Wait for buffer to flush (100ms window + 150ms post-op delay + margin)
        await asyncio.sleep(1.0)

        # Verify event was emitted
        assert len(emitted_events) >= 1

        output_text = output.getvalue()

        # Should show multiple files
        assert "5" in output_text or "Files" in output_text, "Verbose output should indicate multiple files"

        # Should show file count
        assert any(f"file{i}.txt" in output_text for i in range(5)) or "..." in output_text, (
            "Verbose output should show file names or ellipsis for many files"
        )

    def test_git_commit_event_verbose_output(self):
        """Test verbose output for git commit events."""
        output = StringIO()
        console = Console(file=output, width=120, force_terminal=True)

        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,
            use_ascii=True,
            verbose=True,
        )

        # Create a git commit event
        commit_event = GitCommitEvent(
            description="Committed 3 files",
            repo_id="test_repo",
            commit_hash="abc123def456789",
            branch="feature/test",
            files_changed=3,
        )

        formatter.format_and_print(commit_event)

        output_text = output.getvalue()

        # Should show commit hash (first 12 chars)
        assert "abc123def456" in output_text, "Verbose output should show commit hash"

        # Should show branch
        assert "feature/test" in output_text, "Verbose output should show branch"

        # Should show files changed
        assert "3" in output_text, "Verbose output should show files changed count"

        # Should show event type
        assert "GitCommitEvent" in output_text, "Verbose output should show event type"

    def test_git_push_event_verbose_output(self):
        """Test verbose output for git push events."""
        output = StringIO()
        console = Console(file=output, width=120, force_terminal=True)

        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,
            use_ascii=True,
            verbose=True,
        )

        # Create a git push event
        push_event = GitPushEvent(
            description="Pushed to origin",
            repo_id="test_repo",
            remote="origin",
            branch="main",
            commits_pushed=2,
        )

        formatter.format_and_print(push_event)

        output_text = output.getvalue()

        # Should show remote
        assert "origin" in output_text, "Verbose output should show remote"

        # Should show branch
        assert "main" in output_text, "Verbose output should show branch"

        # Should show commits pushed
        assert "2" in output_text, "Verbose output should show commits pushed count"

        # Should show event type
        assert "GitPushEvent" in output_text, "Verbose output should show event type"

    @pytest.mark.skip(reason="EventBuffer async timing - covered by test_vscode_atomic_save.py")
    @pytest.mark.asyncio
    async def test_operation_history_displays_sequence(self):
        """Test that verbose output shows the complete operation sequence."""
        output = StringIO()
        console = Console(file=output, width=120, force_terminal=True)

        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,
            use_ascii=True,
            verbose=True,
        )

        emitted_events = []

        def capture_event(event):
            emitted_events.append(event)
            formatter.format_and_print(event)

        buffer = EventBuffer(
            window_ms=100,
            grouping_mode="smart",
            emit_callback=capture_event,
        )

        # Complex atomic save with multiple modifications
        temp_file = Path("/test/.document.txt.tmp.999")
        final_file = Path("/test/document.txt")
        repo_id = "test_repo"

        # Create sequence of events
        operations = [
            ("created", temp_file, None),
            ("modified", temp_file, None),
            ("modified", temp_file, None),  # Multiple modifications
            ("moved", temp_file, final_file),
        ]

        for change_type, src, dest in operations:
            buffer.add_event(
                FileChangeEvent(
                    description=f"File {change_type}",
                    repo_id=repo_id,
                    file_path=src,
                    change_type=change_type,
                    dest_path=dest,
                )
            )
            await asyncio.sleep(0.01)

        # Wait for buffer
        await asyncio.sleep(0.3)

        assert len(emitted_events) >= 1

        output_text = output.getvalue()

        # Verify operation history is shown
        assert "Sequence" in output_text, "Should show operation sequence"

        # Should show event count
        assert "4" in output_text or "events" in output_text.lower(), "Should indicate 4 events in sequence"

        # Should show individual operations
        assert "[created]" in output_text or "created" in output_text.lower(), "Should show created operation"
        assert "[modified]" in output_text or "modified" in output_text.lower(), (
            "Should show modified operation"
        )
        assert "[moved]" in output_text or "moved" in output_text.lower(), "Should show moved operation"

        # Should show final file (not temp file) in main event line
        assert "document.txt" in output_text, "Should show final file name"

    def test_verbose_mode_disabled_shows_compact_output(self):
        """Test that non-verbose mode doesn't show detailed operation info."""
        output = StringIO()
        console = Console(file=output, width=120, force_terminal=True)

        # Create formatter WITHOUT verbose mode
        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,
            use_ascii=True,
            verbose=False,  # Verbose disabled
        )

        # Create a buffered event with operation history
        buffered_event = BufferedFileChangeEvent(
            repo_id="test_repo",
            file_paths=[Path("test.py")],
            operation_type="atomic_rewrite",
            event_count=3,
            primary_change_type="modified",
            operation_history=[
                {"change_type": "created", "src_path": Path(".test.py.tmp")},
                {"change_type": "modified", "src_path": Path(".test.py.tmp")},
                {
                    "change_type": "moved",
                    "src_path": Path(".test.py.tmp"),
                    "dest_path": Path("test.py"),
                },
            ],
        )

        formatter.format_and_print(buffered_event)

        output_text = output.getvalue()

        # Should NOT show verbose details
        assert "Sequence" not in output_text, "Non-verbose mode should not show sequence"
        assert "operation_history" not in output_text.lower(), (
            "Non-verbose mode should not show operation history"
        )

        # Should still show the basic event
        assert "test.py" in output_text, "Should show the file name"

    def test_startup_banner_formatting(self):
        """Test that startup banner displays correctly."""
        output = StringIO()
        console = Console(file=output, width=120, force_terminal=True)

        formatter = ConsoleEventFormatter(
            console=console,
            use_color=False,
            use_ascii=True,
            verbose=False,
        )

        # Print startup banner
        formatter.print_startup_banner(
            repo_count=5,
            event_log_path=Path("/tmp/events.jsonl"),
            app_log_path=Path("/tmp/app.log"),
        )

        output_text = output.getvalue()

        # Should show repository count
        assert "5 repositories" in output_text or "5" in output_text, (
            "Startup banner should show repository count"
        )

        # Should show log paths (may have ANSI codes, so check for components)
        assert "events.jsonl" in output_text, "Should show event log path"
        assert "app.log" in output_text, "Should show app log path"

        # Should have separators
        assert "━" in output_text or "=" in output_text or "-" in output_text, "Should have visual separators"


# 🔼⚙️🔚
