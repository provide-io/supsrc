#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Base event implementation using attrs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import attrs


@attrs.define(kw_only=True, frozen=True)
class BaseEvent:
    """Base event implementation with common fields.

    This provides a concrete implementation of the Event protocol that
    other event types can inherit from or use as-is.
    """

    description: str
    timestamp: datetime = attrs.field(factory=datetime.now)
    source: str = attrs.field(init=False)  # Set by subclasses
    metadata: dict[str, Any] = attrs.field(factory=dict)

    def format(self) -> str:
        """Default formatting for display.

        Returns:
            Formatted string with timestamp, source, and description
        """
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] [{self.source}] {self.description}"


# 🔼⚙️🔚
