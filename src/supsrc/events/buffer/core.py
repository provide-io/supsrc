# src/supsrc/events/buffer/core.py

"""
Core EventBuffer class for buffering and grouping filesystem events.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from provide.foundation.file.operations import DetectorConfig
from provide.foundation.logger import get_logger

from supsrc.events.buffer.converters import create_single_event_group
from supsrc.events.buffer.grouping import group_events_simple
from supsrc.events.buffer.smart_detector import SmartDetectorManager
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

log = get_logger("events.buffer")


class EventBuffer:
    """Buffers and groups filesystem events to reduce TUI log spam.

    Supports three modes:
    - OFF: Pass events through immediately without buffering
    - SIMPLE: Time-window buffering with basic file grouping
    - SMART: Advanced grouping using OperationDetector from provide-foundation
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
        # Active timer handles for each repo
        self._timers: dict[str, asyncio.TimerHandle] = {}

        # Smart mode detector manager
        self._smart_detector: SmartDetectorManager | None = None

        # Initialize smart mode if configured
        if grouping_mode == GROUPING_MODE_SMART:
            detector_config = DetectorConfig(
                time_window_ms=window_ms,
                min_confidence=DEFAULT_MIN_CONFIDENCE,
                temp_patterns=DEFAULT_TEMP_FILE_PATTERNS,
            )
            self._smart_detector = SmartDetectorManager(
                detector_config=detector_config,
                emit_callback=emit_callback,
                post_operation_delay_ms=150,  # 150ms delay for filesystem settling
            )
            log.debug(
                "Smart mode enabled with detector manager",
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
            event: The file change event to add
        """
        log.trace(
            "Event received",
            repo_id=event.repo_id,
            file_path=str(event.file_path),
            change_type=event.change_type,
            grouping_mode=self.grouping_mode,
        )

        # Mode 1: OFF - Pass through immediately
        if self.grouping_mode == GROUPING_MODE_OFF:
            log.trace("Passing through unbuffered event", file_path=str(event.file_path))
            if self.emit_callback:
                self.emit_callback(event)
            return

        # Mode 2: SMART - Use smart detector
        if self.grouping_mode == GROUPING_MODE_SMART and self._smart_detector:
            self._smart_detector.add_event(event)
            return

        # Mode 3: SIMPLE - Use time-window buffering
        repo_id = event.repo_id
        self._buffers[repo_id].append(event)

        # Cancel any existing timer for this repo
        if repo_id in self._timers:
            self._timers[repo_id].cancel()

        # Set new timer to flush after window
        loop = asyncio.get_event_loop()
        self._timers[repo_id] = loop.call_later(
            self.window_ms / 1000.0, self._flush_buffer, repo_id
        )

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
        # Flush smart detector if enabled
        if self._smart_detector:
            self._smart_detector.flush_all()

        # Flush time-window buffers (for simple mode)
        repo_ids = list(self._buffers.keys())
        for repo_id in repo_ids:
            if repo_id in self._timers:
                self._timers[repo_id].cancel()
            self._flush_buffer(repo_id)
