#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Helper functions for building repo details content."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from supsrc.state import RepositoryStatus

if TYPE_CHECKING:
    from supsrc.state import RepositoryState


def _format_relative_time(dt: datetime | None) -> str:
    """Format a datetime as a relative time string."""
    if dt is None:
        return "never"

    now = datetime.now(UTC)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    diff = now - dt
    seconds = diff.total_seconds()

    if seconds < 60:
        return "just now"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes}m ago"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours}h ago"
    elif seconds < 604800:
        days = int(seconds / 86400)
        return f"{days}d ago"
    else:
        return dt.strftime("%Y-%m-%d")


def _build_progress_bar(current: int | None, total: int | None, width: int = 40) -> str:
    """Build a text-based progress bar."""
    if current is None or total is None or total == 0:
        return "░" * width

    ratio = min(current / total, 1.0)
    filled = int(width * ratio)
    empty = width - filled
    return "█" * filled + "░" * empty


def _build_timer_bar(seconds_left: int | None, total_seconds: int | None, width: int = 40) -> str:
    """Build a timer progress bar (fills as time runs out)."""
    if seconds_left is None or total_seconds is None or total_seconds == 0:
        return "░" * width + " --"

    elapsed = total_seconds - seconds_left
    ratio = min(elapsed / total_seconds, 1.0)
    filled = int(width * ratio)
    empty = width - filled
    return "█" * filled + "░" * empty + f" {seconds_left}s"


def build_header_section(repo_id: str, state: RepositoryState) -> str:
    """Build the header section with repo name, branch, and status."""
    status_name = state.status.name.replace("_", " ").title()
    branch = state.current_branch or "unknown"
    return f"""{repo_id}
{"═" * 60}

{state.display_status_emoji} {status_name} on 🌿 {branch}"""


def build_timer_section(state: RepositoryState) -> str:
    """Build the timer progress bar section."""
    total_seconds = getattr(state, "_timer_total_seconds", None)
    timer_bar = _build_timer_bar(state.timer_seconds_left, total_seconds)
    return f"""
⏱️  {timer_bar}"""


def build_changes_section(state: RepositoryState) -> str:
    """Build the file changes section."""
    if state.changed_files == 0 and not state.has_uncommitted_changes:
        return """
┌─ Workspace ─────────────────────────────────────────────────┐
│  ✨ Clean - no uncommitted changes                          │
└─────────────────────────────────────────────────────────────┘"""

    return f"""
┌─ Pending Changes ───────────────────────────────────────────┐
│  📁 {state.changed_files:3d} files changed                                       │
│     ➕ Added:    {state.added_files:3d}                                          │
│     ✏️  Modified: {state.modified_files:3d}                                          │
│     ➖ Deleted:  {state.deleted_files:3d}                                          │
└─────────────────────────────────────────────────────────────┘"""  # noqa: RUF001


def build_last_commit_section(state: RepositoryState) -> str:
    """Build the last commit info section."""
    commit_hash = state.last_commit_short_hash or "-------"
    commit_msg = state.last_commit_message_summary or "No commit message"
    commit_time = _format_relative_time(state.last_commit_timestamp)

    # Truncate message if too long
    if len(commit_msg) > 45:
        commit_msg = commit_msg[:42] + "..."

    # Build stats from last committed values
    stats_parts = []
    if state.last_committed_added > 0:
        stats_parts.append(f"+{state.last_committed_added}")
    if state.last_committed_deleted > 0:
        stats_parts.append(f"-{state.last_committed_deleted}")
    stats = " ".join(stats_parts) if stats_parts else ""

    return f"""
┌─ Last Commit ───────────────────────────────────────────────┐
│  {commit_hash}  {commit_msg:<45} │
│  {commit_time:<12} {stats:<46} │
└─────────────────────────────────────────────────────────────┘"""


def build_rule_section(state: RepositoryState, rule_name: str | None) -> str:
    """Build the rule configuration section."""
    rule_emoji = state.rule_emoji or "📋"
    rule_indicator = state.rule_dynamic_indicator or "waiting"
    rule_display = rule_name or "default"

    return f"""
┌─ Rule ──────────────────────────────────────────────────────┐
│  {rule_emoji} {rule_display:<20}  {rule_indicator:<30} │
│  Saves: {state.save_count:<5}                                              │
└─────────────────────────────────────────────────────────────┘"""


def build_controls_section(state: RepositoryState) -> str:
    """Build the controls/state section."""
    paused = "✅ Yes" if state.is_paused else "❌ No"
    stopped = "✅ Yes" if state.is_stopped else "❌ No"
    frozen = "✅ Yes" if state.is_frozen else "❌ No"

    return f"""
┌─ Controls ──────────────────────────────────────────────────┐
│  ⏸️  Paused: {paused:<8}  ⏹️  Stopped: {stopped:<8}  🧊 Frozen: {frozen:<6} │
└─────────────────────────────────────────────────────────────┘"""


def build_error_section(state: RepositoryState) -> str:
    """Build the error details section (only for ERROR status)."""
    if state.status != RepositoryStatus.ERROR:
        return ""

    error_msg = state.error_message or "Unknown error"
    # Word wrap error message
    wrapped_lines = []
    words = error_msg.split()
    current_line = ""
    for word in words:
        if len(current_line) + len(word) + 1 <= 55:
            current_line += (" " if current_line else "") + word
        else:
            wrapped_lines.append(current_line)
            current_line = word
    if current_line:
        wrapped_lines.append(current_line)

    error_content = "\n│  ".join(wrapped_lines[:3])  # Max 3 lines

    return f"""
┌─ ⚠️  Error Details ─────────────────────────────────────────┐
│  {error_content:<57} │
├─────────────────────────────────────────────────────────────┤
│  🔧 Actions: [R] Retry  [A] Acknowledge  [I] Ignore         │
└─────────────────────────────────────────────────────────────┘"""


def build_circuit_breaker_section(state: RepositoryState) -> str:
    """Build the circuit breaker section (only when triggered)."""
    if not state.circuit_breaker_triggered:
        return ""

    reason = state.circuit_breaker_reason or "Bulk changes detected"
    file_count = len(state.bulk_change_files)

    # Show first few files
    files_preview = ", ".join(state.bulk_change_files[:3])
    if len(files_preview) > 50:
        files_preview = files_preview[:47] + "..."
    if file_count > 3:
        files_preview += f" +{file_count - 3} more"

    return f"""
┌─ 🛑 Circuit Breaker Activated ──────────────────────────────┐
│  Reason: {reason:<50} │
│  Files affected: {file_count:<42} │
│  {files_preview:<57} │
├─────────────────────────────────────────────────────────────┤
│  [A] Acknowledge & Resume   [S] Stay Paused                 │
└─────────────────────────────────────────────────────────────┘"""


def build_keyboard_hints() -> str:
    """Build the keyboard shortcuts hint section."""
    return """
───────────────────────────────────────────────────────────────
[Space] Pause Repo  [S] Stop  [R] Refresh  [A] Ack  [Esc] Back"""


def build_repo_details(repo_id: str, state: RepositoryState, rule_name: str | None) -> str:
    """Build the complete repo details content based on current state."""
    sections = [
        build_header_section(repo_id, state),
        build_timer_section(state),
    ]

    # Add status-specific sections first (most important)
    if state.status == RepositoryStatus.ERROR:
        sections.append(build_error_section(state))
    elif state.circuit_breaker_triggered:
        sections.append(build_circuit_breaker_section(state))

    # Standard sections
    sections.extend(
        [
            build_changes_section(state),
            build_last_commit_section(state),
            build_rule_section(state, rule_name),
            build_controls_section(state),
            build_keyboard_hints(),
        ]
    )

    return "\n".join(sections)


# 🔼⚙️🔚
