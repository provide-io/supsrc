#
# SPDX-FileCopyrightText: Copyright (c) provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Filesystem monitoring events."""

from __future__ import annotations

from pathlib import Path

import attrs

from supsrc.events.base import BaseEvent


@attrs.define(frozen=True)
class FileChangeEvent(BaseEvent):
    """Event emitted when a monitored file changes."""

    source: str = attrs.field(default="monitor", init=False)
    repo_id: str = attrs.field(kw_only=True)
    file_path: Path = attrs.field(kw_only=True)
    change_type: str = attrs.field(kw_only=True)  # 'created', 'modified', 'deleted', 'moved'
    dest_path: Path | None = attrs.field(kw_only=True, default=None)  # Destination for 'moved' events

    def format(self) -> str:
        """Format file change event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        emoji_map = {
            "created": "\u2795",  # HEAVY PLUS SIGN
            "modified": "\u270f\ufe0f",  # PENCIL
            "deleted": "\u2796",  # HEAVY MINUS SIGN
            "moved": "\U0001f504",  # COUNTERCLOCKWISE ARROWS BUTTON
        }
        emoji = emoji_map.get(self.change_type, "\U0001f4c4")  # PAGE FACING UP

        # For move events, show source → destination
        if self.change_type == "moved" and self.dest_path:
            return f"[{time_str}] {emoji} [{self.repo_id}] {self.file_path.name} → {self.dest_path.name}"

        return f"[{time_str}] {emoji} [{self.repo_id}] {self.file_path.name} {self.change_type}"


@attrs.define(frozen=True)
class MonitoringStartEvent(BaseEvent):
    """Event emitted when monitoring starts for a repository."""

    source: str = attrs.field(default="monitor", init=False)
    repo_id: str = attrs.field(kw_only=True)
    path: Path = attrs.field(kw_only=True)

    def format(self) -> str:
        """Format monitoring start event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] \U0001f441\ufe0f Started monitoring [{self.repo_id}] at {self.path}"  # EYE


@attrs.define(frozen=True)
class MonitoringStopEvent(BaseEvent):
    """Event emitted when monitoring stops for a repository."""

    source: str = attrs.field(default="monitor", init=False)
    repo_id: str = attrs.field(kw_only=True)

    def format(self) -> str:
        """Format monitoring stop event for display."""
        time_str = self.timestamp.strftime("%H:%M:%S")
        return f"[{time_str}] \U0001f6d1 Stopped monitoring [{self.repo_id}]"  # STOP SIGN


# 🔼⚙️🔚
