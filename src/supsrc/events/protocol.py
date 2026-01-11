#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Event protocol definition."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Event(Protocol):
    """Protocol for any event in the supsrc system.

    Any class that has these attributes and methods can be used as an event.
    This follows Python's duck typing philosophy.
    """

    timestamp: datetime
    source: str  # Component that generated the event (e.g., 'git', 'monitor', 'rules', 'tui')
    description: str

    def format(self) -> str:
        """Format the event for display in the TUI.

        Returns:
            Formatted string suitable for display
        """
        ...


# 🔼⚙️🔚
