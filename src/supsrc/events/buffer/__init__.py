# src/supsrc/events/buffer/__init__.py

"""
Event buffering and grouping system for reducing TUI event log spam.

NOTE: For backward compatibility during migration, we're importing from buffer_legacy.
The new module structure is in buffer/core.py, buffer/grouping.py, buffer/smart_detector.py,
and buffer/converters.py, but tests still reference internal methods.
"""

from __future__ import annotations

from supsrc.events.buffer_events import BufferedFileChangeEvent

# Use the fixed legacy buffer implementation for now
from supsrc.events.buffer_legacy import EventBuffer

__all__ = ["BufferedFileChangeEvent", "EventBuffer"]
