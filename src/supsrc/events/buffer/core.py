#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Core event buffer orchestration for reducing TUI event log spam."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from provide.foundation.file.operations import DetectorConfig
from provide.foundation.logger import get_logger

from supsrc.events.buffer.converters import create_single_event_group
from supsrc.events.buffer.grouping import group_events_simple
from supsrc.events.buffer.streaming import StreamingOperationHandler
from supsrc.events.defaults import (
    DEFAULT_BUFFER_WINDOW_MS,
    DEFAULT_GROUPING_MODE,
    DEFAULT_MIN_CONFIDENCE,
    DEFAULT_TEMP_FILE_PATTERNS,
    GROUPING_MODE_OFF,
    GROUPING_MODE_SIMPLE,
    GROUPING_MODE_SMART,
)
from supsrc.events.monitor import FileChangeEvent

log = get_logger("events.buffer.core")


class EventBuffer:
    """Buffers and groups filesystem events to reduce TUI log spam.

    Supports three grouping modes:
    - "off": Pass-through, no buffering
    - "simple": Time-window buffering with file-based grouping
    - "smart": Streaming operation detection with atomic save hiding
    """

    def __init__(
        self,
        window_ms: int = DEFAULT_BUFFER_WINDOW_MS,
        grouping_mode: str = DEFAULT_GROUPING_MODE,
        emit_callback: Any = None,
    ):
        """Initialize the event buffer.

        Args:
            window_ms: Buffering window in milliseconds
            grouping_mode: "off", "simple", or "smart"
            emit_callback: Function to call when emitting buffered events
        """
        self.window_ms = window_ms
        self.grouping_mode = grouping_mode
        self.emit_callback = emit_callback

        # Buffered events by repo_id (for simple mode)
        self._buffers: dict[str, list[FileChangeEvent]] = defaultdict(list)
        # Active timer handles for each repo (for simple mode)
        self._timers: dict[str, asyncio.TimerHandle] = {}

        # Streaming handler for smart mode
        self._streaming_handler: StreamingOperationHandler | None = None
        self._fallback_loop: asyncio.AbstractEventLoop | None = None

        # Initialize smart mode if enabled
        if grouping_mode == GROUPING_MODE_SMART:
            detector_config = DetectorConfig(
                time_window_ms=window_ms,
                min_confidence=DEFAULT_MIN_CONFIDENCE,
                temp_patterns=DEFAULT_TEMP_FILE_PATTERNS,
            )
            self._streaming_handler = StreamingOperationHandler(
                detector_config=detector_config,
                emit_callback=emit_callback,
            )
            log.debug(
                "Smart mode enabled with streaming detection",
                time_window_ms=window_ms,
                min_confidence=DEFAULT_MIN_CONFIDENCE,
                temp_patterns_count=len(DEFAULT_TEMP_FILE_PATTERNS),
            )
        else:
            log.debug(
                "Smart mode disabled",
                grouping_mode=grouping_mode,
            )

        log.debug("EventBuffer initialized", window_ms=window_ms, grouping_mode=grouping_mode)

    def add_event(self, event: FileChangeEvent) -> None:
        """Add a file change event to the buffer.

        Args:
            event: File change event to buffer
        """
        log.trace(
            "Event received",
            repo_id=event.repo_id,
            file_path=str(event.file_path),
            change_type=event.change_type,
            grouping_mode=self.grouping_mode,
        )

        # OFF MODE: Pass through immediately without buffering
        if self.grouping_mode == GROUPING_MODE_OFF:
            log.trace("Passing through unbuffered event", file_path=str(event.file_path))
            if self.emit_callback:
                self.emit_callback(event)
            return

        # SMART MODE: Use streaming detection
        if self.grouping_mode == GROUPING_MODE_SMART and self._streaming_handler:
            self._streaming_handler.handle_event(event)
            return

        # SIMPLE MODE: Use time-window buffering
        repo_id = event.repo_id
        self._buffers[repo_id].append(event)

        # Cancel any existing timer for this repo
        if repo_id in self._timers:
            self._timers[repo_id].cancel()

        # Set new timer to flush after window
        loop = self._get_loop()
        self._timers[repo_id] = loop.call_later(self.window_ms / 1000.0, self._flush_buffer, repo_id)

        log.debug(
            "Event added to buffer",
            repo_id=repo_id,
            file_path=str(event.file_path),
            change_type=event.change_type,
            buffer_size=len(self._buffers[repo_id]),
        )

    def _flush_buffer(self, repo_id: str) -> None:
        """Flush buffered events for a repository (simple mode).

        Args:
            repo_id: Repository identifier
        """
        events = self._buffers.pop(repo_id, [])
        if repo_id in self._timers:
            del self._timers[repo_id]

        if not events:
            return

        log.debug("Flushing event buffer", repo_id=repo_id, event_count=len(events))

        # Group events based on the configured mode
        if self.grouping_mode == GROUPING_MODE_SIMPLE:
            log.debug("Using simple event grouping")
            grouped_events = group_events_simple(events)
        else:
            # Fallback - treat as individual events
            log.debug("Using individual event mode")
            grouped_events = [create_single_event_group(e) for e in events]

        log.debug(
            "Event grouping complete",
            input_events=len(events),
            output_groups=len(grouped_events),
            grouping_mode=self.grouping_mode,
        )

        # Emit grouped events
        if self.emit_callback:
            for i, grouped_event in enumerate(grouped_events):
                log.trace(
                    "Emitting grouped event",
                    index=i,
                    operation_type=grouped_event.operation_type,
                    file_paths=[str(p) for p in grouped_event.file_paths],
                    event_count=grouped_event.event_count,
                )
                self.emit_callback(grouped_event)
        else:
            log.warning("No emit callback available, grouped events not emitted")

    def flush_all(self) -> None:
        """Flush all pending buffers immediately.

        For smart grouping, also flushes any incomplete operations from the
        streaming detectors, showing temp files if they never completed.
        """
        # Flush smart mode handler
        if self._streaming_handler:
            self._streaming_handler.flush_all()

        # Flush time-window buffers (for simple mode)
        repo_ids = list(self._buffers.keys())
        for repo_id in repo_ids:
            if repo_id in self._timers:
                self._timers[repo_id].cancel()
            self._flush_buffer(repo_id)

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Return the running event loop or create a fallback loop."""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            if self._fallback_loop is None or self._fallback_loop.is_closed():
                self._fallback_loop = asyncio.new_event_loop()
            return self._fallback_loop


# 🔼⚙️🔚
