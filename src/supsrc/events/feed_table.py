# src/supsrc/events/feed_table.py

"""
Legacy import module for EventFeedTable widget.

This module provides backward compatibility by re-exporting the EventFeedTable
from the new package structure.
"""

from __future__ import annotations

# Import from new package structure for backward compatibility
from supsrc.events.feed_table.widget import EventFeedTable

__all__ = ["EventFeedTable"]
