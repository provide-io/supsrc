# src/supsrc/events/buffer/__init__.py

"""
Event buffering and grouping system for reducing TUI event log spam.
"""

from __future__ import annotations

from supsrc.events.buffer.core import EventBuffer
from supsrc.events.buffer_events import BufferedFileChangeEvent

__all__ = ["BufferedFileChangeEvent", "EventBuffer"]
