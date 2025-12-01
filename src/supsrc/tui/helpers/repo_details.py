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


def build_status_banner(state: RepositoryState) -> str:
    """Build an alert banner for special states (stopped, paused, circuit breaker)."""
    banners = []

    if state.is_stopped:
        banners.append("⏹️  MONITORING STOPPED - Press [Shift+Space] or [S] to resume")
    elif state.is_paused:
        banners.append("⏸️  MONITORING PAUSED - Press [Space] or [P] to resume")

    if state.circuit_breaker_triggered:
        reason = state.circuit_breaker_reason or "Safety check triggered"
        if len(reason) > 50:
            reason = reason[:47] + "..."
        banners.append(f"🛑 CIRCUIT BREAKER: {reason}")
        banners.append("   Press [A] to acknowledge and resume")

    if not banners:
        return ""

    # Build a prominent banner box
    banner_content = "\n│  ".join(banners)
    return f"""
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  {banner_content:<58}┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛"""


def build_header_section(repo_id: str, state: RepositoryState) -> str:
    """Build the header section with repo name, branch, and status."""
    status_name = state.status.name.replace("_", " ").title()
    branch = state.current_branch or "unknown"

    # Get health score
    score, grade, _ = state.get_health_score()

    # Build sync status indicator
    sync_status = ""
    if state.has_upstream:
        parts = []
        if state.commits_ahead > 0:
            parts.append(f"↑{state.commits_ahead}")
        if state.commits_behind > 0:
            parts.append(f"↓{state.commits_behind}")
        sync_status = f" ({', '.join(parts)})" if parts else " (synced)"

    # Build header with status banner if needed
    header = f"""{repo_id}  {grade} Health: {score}%
{"═" * 60}

{state.display_status_emoji} {status_name} on 🌿 {branch}{sync_status}"""

    # Add status banner for special states
    banner = build_status_banner(state)
    if banner:
        header += banner

    return header


def build_health_section(state: RepositoryState) -> str:
    """Build the health score section with issues."""
    score, grade, issues = state.get_health_score()

    if score >= 90 and not issues:
        return ""  # Don't show health section if everything is good

    # Build health bar
    bar_width = 40
    filled = int(bar_width * score / 100)
    empty = bar_width - filled
    bar = "█" * filled + "░" * empty

    lines = [
        "┌─ Repository Health ─────────────────────────────────────────┐",
        f"│  {grade} Score: {score:3d}%  [{bar}] │",
    ]

    if issues:
        lines.append("├─ Issues ────────────────────────────────────────────────────┤")
        for issue in issues[:4]:  # Show max 4 issues
            issue_display = issue if len(issue) <= 53 else issue[:50] + "..."
            lines.append(f"│  ⚠️  {issue_display:<53} │")
        if len(issues) > 4:
            lines.append(f"│  ... and {len(issues) - 4} more issue(s){' ' * 36}│")

    lines.append("└─────────────────────────────────────────────────────────────┘")

    return "\n".join(lines)


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


def build_session_stats_section(state: RepositoryState) -> str:
    """Build the session statistics section."""
    duration = state.get_session_duration()
    commits = state.session_commits_count
    files = state.session_files_committed
    pushes = state.session_pushes_count
    events = state.session_events_count

    # Calculate average commits per hour
    if state.session_start_time:
        hours = (datetime.now(UTC) - state.session_start_time).total_seconds() / 3600
        avg_commits = commits / hours if hours > 0 else 0
        avg_commits_str = f"{avg_commits:.1f}/hr"
    else:
        avg_commits_str = "N/A"

    return f"""
┌─ 📊 Session Statistics ────────────────────────────────────┐
│  ⏱️  Duration: {duration:<10}    📤 Commits: {commits:<5}  ({avg_commits_str:<6}) │
│  📁 Files Committed: {files:<5}   🚀 Pushes: {pushes:<5}  📝 Events: {events:<4} │
└─────────────────────────────────────────────────────────────┘"""


def build_remote_sync_section(state: RepositoryState) -> str:
    """Build the remote sync status section."""
    if not state.has_upstream:
        return """
┌─ 🌐 Remote Status ──────────────────────────────────────────┐
│  ⚠️  No upstream tracking branch configured                  │
└─────────────────────────────────────────────────────────────┘"""

    upstream = state.upstream_branch or "origin/unknown"
    ahead = state.commits_ahead
    behind = state.commits_behind

    # Build sync status
    if ahead == 0 and behind == 0:
        sync_status = "✅ In sync with remote"
        sync_indicator = "═" * 40
    elif ahead > 0 and behind == 0:
        sync_status = f"↑ {ahead} commit(s) ahead"
        sync_indicator = "▶" * min(ahead, 40)
    elif behind > 0 and ahead == 0:
        sync_status = f"↓ {behind} commit(s) behind"
        sync_indicator = "◀" * min(behind, 40)
    else:
        sync_status = f"↕️  {ahead} ahead, {behind} behind (diverged)"
        sync_indicator = "▶" * min(ahead, 20) + "│" + "◀" * min(behind, 19)

    return f"""
┌─ 🌐 Remote Status ──────────────────────────────────────────┐
│  Tracking: {upstream:<48} │
│  {sync_status:<57} │
│  [{sync_indicator:<40}] │
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

    # Check for file warnings (large/binary files)
    if state.file_warnings:
        return _build_file_warnings_circuit_breaker(state, reason)

    # Standard bulk change circuit breaker
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


def _build_file_warnings_circuit_breaker(state: RepositoryState, reason: str) -> str:
    """Build circuit breaker section with file warnings (large/binary files)."""
    warnings = state.file_warnings
    large_files = [w for w in warnings if w.get("type") == "large_file"]
    binary_files = [w for w in warnings if w.get("type") == "binary_file"]

    lines = [
        "┌─ 🛑 Circuit Breaker: File Warnings ────────────────────────┐",
        f"│  Reason: {reason:<50} │",
    ]

    # Large files section
    if large_files:
        lines.append("├─ 📦 Large Files ─────────────────────────────────────────────┤")
        for lf in large_files[:3]:
            path = lf.get("path", "unknown")
            size_mb = lf.get("size", 0) / 1_000_000
            path_display = path if len(path) <= 40 else "..." + path[-37:]
            lines.append(f"│  {path_display:<40} ({size_mb:>6.2f} MB) │")
        if len(large_files) > 3:
            lines.append(f"│  ... and {len(large_files) - 3} more large file(s){' ' * 27}│")

    # Binary files section
    if binary_files:
        lines.append("├─ 🔒 Binary Files ────────────────────────────────────────────┤")
        for bf in binary_files[:3]:
            path = bf.get("path", "unknown")
            size_kb = bf.get("size", 0) / 1000
            path_display = path if len(path) <= 40 else "..." + path[-37:]
            lines.append(f"│  {path_display:<40} ({size_kb:>6.1f} KB) │")
        if len(binary_files) > 3:
            lines.append(f"│  ... and {len(binary_files) - 3} more binary file(s){' ' * 26}│")

    lines.extend(
        [
            "├─────────────────────────────────────────────────────────────┤",
            "│  [A] Acknowledge & Commit   [S] Skip These Files           │",
            "└─────────────────────────────────────────────────────────────┘",
        ]
    )

    return "\n".join(lines)


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

    # Health section (shows only if issues exist)
    health_section = build_health_section(state)
    if health_section:
        sections.append(health_section)

    # Standard sections
    sections.extend(
        [
            build_changes_section(state),
            build_remote_sync_section(state),
            build_session_stats_section(state),
            build_last_commit_section(state),
            build_rule_section(state, rule_name),
            build_controls_section(state),
            build_keyboard_hints(),
        ]
    )

    return "\n".join(sections)


# 🔼⚙️🔚
