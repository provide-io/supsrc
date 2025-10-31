#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Utility functions for the TUI application."""

from __future__ import annotations

from datetime import UTC, datetime


def get_countdown_display(seconds_left: int | None) -> str:
    """Generate countdown display with hand emojis for last 10 seconds."""
    if seconds_left is None:
        return ""

    if seconds_left > 10:
        # Show regular countdown
        minutes = seconds_left // 60
        secs = seconds_left % 60
        if minutes > 0:
            return f"{minutes}:{secs:02d}"
        else:
            return f"{secs}s"
    elif seconds_left == 10:
        return "🙌"  # Both hands open (10)
    elif seconds_left == 9:
        return "🖐️✋"  # 5 + 4
    elif seconds_left == 8:
        return "✋✌️"  # 5 + 3
    elif seconds_left == 7:
        return "✋🤘"  # 5 + 2
    elif seconds_left == 6:
        return "✋☝️"  # 5 + 1
    elif seconds_left == 5:
        return "🖐️"  # One hand (5)
    elif seconds_left == 4:
        return "🖖"  # Four fingers
    elif seconds_left == 3:
        return "🤟"  # Three fingers
    elif seconds_left == 2:
        return "✌️"  # Peace sign (2)
    elif seconds_left == 1:
        return "☝️"  # One finger
    else:
        return "💥"  # Zero/trigger


def format_last_commit_time(last_change_time, threshold_hours=3):
    """Format last commit time as relative or absolute based on age."""
    if not last_change_time:
        return "Never"

    now = datetime.now(UTC)
    delta = now - last_change_time
    total_seconds = int(delta.total_seconds())

    # If older than threshold, show full date
    if delta.total_seconds() > (threshold_hours * 3600):
        return last_change_time.strftime("%Y-%m-%d %H:%M:%S")

    # Otherwise show relative time
    if total_seconds < 60:
        return f"{total_seconds}s ago"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        return f"{minutes}m ago"
    else:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        if minutes > 0:
            return f"{hours}h {minutes}m ago"
        else:
            return f"{hours}h ago"


# 🔼⚙️🔚
