# src/supsrc/events/buffer/smart_detector.py

"""
Smart mode event detection using OperationDetector from provide-foundation.
Handles streaming detection, post-operation delays, and operation completion callbacks.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from provide.foundation.file.operations import DetectorConfig, OperationDetector
from provide.foundation.logger import get_logger

from supsrc.events.buffer.converters import convert_to_file_event, create_operation_event
from supsrc.events.buffer_events import BufferedFileChangeEvent
from supsrc.events.monitor import FileChangeEvent

log = get_logger("events.buffer.smart_detector")


class SmartDetectorManager:
    """Manages operation detection using foundation's OperationDetector for smart mode."""

    def __init__(
        self,
        detector_config: DetectorConfig,
        emit_callback: Callable[[BufferedFileChangeEvent], None] | None,
        post_operation_delay_ms: int = 150,
    ):
        """Initialize smart detector manager.

        Args:
            detector_config: Configuration for operation detection
            emit_callback: Callback to emit completed operations
            post_operation_delay_ms: Delay before emitting operations (allows filesystem to settle)
        """
        self.detector_config = detector_config
        self.emit_callback = emit_callback
        self.post_operation_delay_ms = post_operation_delay_ms

        # Per-repo operation detectors
        self._operation_detectors: dict[str, OperationDetector] = {}

        # Sequence counter for streaming detection
        self._sequence_counter: dict[str, int] = {}

        # Post-operation delay buffer
        # Key: f"{repo_id}:{primary_path}" for per-file debouncing
        self._pending_operations: dict[str, BufferedFileChangeEvent] = {}
        self._operation_timers: dict[str, asyncio.TimerHandle] = {}

        log.debug(
            "SmartDetectorManager initialized",
            post_operation_delay_ms=post_operation_delay_ms,
            min_confidence=detector_config.min_confidence,
        )

    def add_event(self, event: FileChangeEvent) -> None:
        """Process a file change event through smart detection.

        Args:
            event: The file change event to process
        """
        repo_id = event.repo_id

        # Get or create detector for this repo
        detector = self._get_or_create_detector(repo_id)

        # Convert to FileEvent and pass to detector
        file_event = convert_to_file_event(event, self._sequence_counter)

        # Use detect_streaming which returns a completed operation or None
        completed_operation = detector.detect_streaming(file_event)

        # If an operation completed, handle it via our callback
        if completed_operation:
            self._on_operation_complete(completed_operation, repo_id)

    def _get_or_create_detector(self, repo_id: str) -> OperationDetector:
        """Get or create operation detector for a repository.

        Args:
            repo_id: Repository identifier

        Returns:
            OperationDetector instance for this repository
        """
        if repo_id not in self._operation_detectors:
            # Create new detector with config
            detector = OperationDetector(config=self.detector_config)
            self._operation_detectors[repo_id] = detector

            # Initialize sequence counter for this repo
            if repo_id not in self._sequence_counter:
                self._sequence_counter[repo_id] = 0

            log.debug("Created operation detector for repo", repo_id=repo_id)

        return self._operation_detectors[repo_id]

    def _on_operation_complete(self, operation: Any, repo_id: str) -> None:
        """Handle completed operation from detector.

        Buffers the operation with a delay before emitting to TUI, allowing
        filesystem/editor to settle and avoiding showing partial state.

        Args:
            operation: The completed FileOperation
            repo_id: Repository identifier
        """
        log.debug(
            "Operation completed",
            operation_type=operation.operation_type.value,
            primary_path=str(operation.primary_path),
            files_affected=str(operation.files_affected) if operation.files_affected else None,
            event_count=operation.event_count,
            repo_id=repo_id,
        )

        # Convert foundation operation to buffered event
        buffered_event = create_operation_event(operation, repo_id)

        log.debug(
            "Created buffered event from operation",
            file_paths=[str(p) for p in buffered_event.file_paths],
            operation_type=buffered_event.operation_type,
            primary_change_type=buffered_event.primary_change_type,
        )

        # Create unique key for per-file debouncing
        # Use first file path as key (most operations have one file)
        primary_file = (
            buffered_event.file_paths[0] if buffered_event.file_paths else Path("unknown")
        )
        operation_key = f"{repo_id}:{primary_file}"

        # Store in pending operations (replaces any existing operation for this file)
        self._pending_operations[operation_key] = buffered_event

        # Cancel existing timer for this operation if any (debouncing)
        if operation_key in self._operation_timers:
            self._operation_timers[operation_key].cancel()
            log.trace("Cancelled existing timer for operation", key=operation_key)

        # Schedule delayed emission
        try:
            loop = asyncio.get_event_loop()
            self._operation_timers[operation_key] = loop.call_later(
                self.post_operation_delay_ms / 1000.0,
                self._emit_operation,
                operation_key,
            )
            log.debug(
                "Scheduled delayed operation emission",
                key=operation_key,
                delay_ms=self.post_operation_delay_ms,
            )
        except RuntimeError:
            # No event loop - emit immediately (e.g., in tests)
            log.warning("No event loop available, emitting operation immediately")
            if self.emit_callback:
                self.emit_callback(buffered_event)

    def _emit_operation(self, operation_key: str) -> None:
        """Emit a pending operation after delay (timer callback).

        Args:
            operation_key: Unique key identifying the operation
        """
        # Retrieve buffered event
        buffered_event = self._pending_operations.get(operation_key)
        if not buffered_event:
            log.warning("Operation not found in pending buffer", key=operation_key)
            return

        log.debug(
            "⏰ Emitting delayed operation",
            key=operation_key,
            file_paths=[str(p) for p in buffered_event.file_paths],
            operation_type=buffered_event.operation_type,
        )

        # Clean up
        del self._pending_operations[operation_key]
        if operation_key in self._operation_timers:
            del self._operation_timers[operation_key]

        # Emit to TUI
        if self.emit_callback:
            self.emit_callback(buffered_event)
        else:
            log.warning("No emit callback available for delayed operation")

    def flush_all(self) -> None:
        """Flush all pending operations immediately.

        This includes:
        - Any buffered post-operation delays
        - Any incomplete operations from the streaming detectors
        """
        # First, flush any pending post-operation delays
        if self._pending_operations:
            log.debug(
                "Flushing pending operations on shutdown", count=len(self._pending_operations)
            )
            for operation_key in list(self._pending_operations.keys()):
                # Cancel timer and emit immediately
                if operation_key in self._operation_timers:
                    self._operation_timers[operation_key].cancel()
                self._emit_operation(operation_key)

        # Flush streaming detectors - emit any incomplete operations
        for repo_id, detector in self._operation_detectors.items():
            pending_operations = detector.flush()

            for operation in pending_operations:
                log.debug(
                    "Flushing incomplete operation on shutdown",
                    repo_id=repo_id,
                    operation_type=operation.operation_type.value,
                    primary_path=str(operation.primary_path),
                    event_count=operation.event_count,
                )

                # Emit the incomplete operation
                buffered_event = create_operation_event(operation, repo_id)
                if self.emit_callback:
                    self.emit_callback(buffered_event)
