#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""TODO: Add module docstring."""

from __future__ import annotations

import attrs

from supsrc.events.base import BaseEvent


@attrs.define(frozen=True)
class TimerUpdateEvent(BaseEvent):
    """Event emitted periodically to show timer countdown progress."""

    source: str = attrs.field(default="timer", init=False)
    repo_id: str = attrs.field(kw_only=True)
    seconds_remaining: int = attrs.field(kw_only=True)
    total_seconds: int = attrs.field(kw_only=True)
    rule_name: str | None = attrs.field(kw_only=True, default=None)

    def format(self) -> str:
        """Format timer update event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        rule_info = f" ({self.rule_name})" if self.rule_name else ""
        return f"[{time_str}] ⏱️  [{self.repo_id}] Timer: {self.seconds_remaining}s remaining{rule_info}"


# 🔼⚙️🔚
