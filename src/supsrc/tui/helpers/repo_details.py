# type: ignore
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


def _escape_rich_markup(text: str) -> str:
    """Escape brackets in text to prevent Rich markup interpretation."""
    return text.replace("[", "\\[")


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
    """Build an alert banner for special states using Rich markup."""
    banners = []

    if state.is_stopped:
        banners.append("[bold yellow]⏹️  MONITORING STOPPED[/bold yellow] - Press [bold]S[/bold] to resume")
    elif state.is_paused:
        banners.append("[bold cyan]⏸️  MONITORING PAUSED[/bold cyan] - Press [bold]Space[/bold] to resume")

    if state.circuit_breaker_triggered:
        reason = _escape_rich_markup(state.circuit_breaker_reason or "Safety check triggered")
        if len(reason) > 50:
            reason = reason[:47] + "..."
        banners.append(f"[bold red]🛑 CIRCUIT BREAKER:[/bold red] {reason}")
        banners.append("   Press [bold]A[/bold] to acknowledge and resume")

    if not banners:
        return ""

    return "\n\n" + "\n".join(banners)


def build_header_section(repo_id: str, state: RepositoryState) -> str:
    """Build the header section with repo name, branch, and status using Rich markup."""
    status_name = state.status.name.replace("_", " ").title()
    branch = state.current_branch or "unknown"

    # Get health score
    score, grade, _ = state.get_health_score()

    # Health color based on score
    if score >= 90:
        health_color = "green"
    elif score >= 70:
        health_color = "yellow"
    elif score >= 50:
        health_color = "orange3"
    else:
        health_color = "red"

    # Build sync status indicator
    sync_status = ""
    if state.has_upstream:
        parts = []
        if state.commits_ahead > 0:
            parts.append(f"[green]↑{state.commits_ahead}[/green]")
        if state.commits_behind > 0:
            parts.append(f"[red]↓{state.commits_behind}[/red]")
        sync_status = f" ({', '.join(parts)})" if parts else " [dim](synced)[/dim]"

    # Build header with Rich markup
    header = f"""[bold]{repo_id}[/bold]  {grade} [{health_color}]Health: {score}%[/{health_color}]
[dim]{"─" * 60}[/dim]

{state.display_status_emoji} [bold]{status_name}[/bold] on [cyan]🌿 {branch}[/cyan]{sync_status}"""

    # Add status banner for special states
    banner = build_status_banner(state)
    if banner:
        header += banner

    return header


def build_health_section(state: RepositoryState) -> str:
    """Build the health score section with issues using Rich markup."""
    score, grade, issues = state.get_health_score()

    if score >= 90 and not issues:
        return ""  # Don't show health section if everything is good

    # Health color
    if score >= 70:
        bar_color = "yellow"
    elif score >= 50:
        bar_color = "orange3"
    else:
        bar_color = "red"

    # Build health bar
    bar_width = 40
    filled = int(bar_width * score / 100)
    empty = bar_width - filled
    bar = f"[{bar_color}]{'█' * filled}[/{bar_color}][dim]{'░' * empty}[/dim]"

    lines = [
        "[bold]Repository Health[/bold]",
        f"  {grade} Score: {score}%  \\[{bar}\\]",
    ]

    if issues:
        lines.append("\n[bold yellow]Issues:[/bold yellow]")
        for issue in issues[:4]:
            lines.append(f"  [yellow]⚠[/yellow]  {_escape_rich_markup(issue)}")
        if len(issues) > 4:
            lines.append(f"  [dim]... and {len(issues) - 4} more issue(s)[/dim]")

    return "\n".join(lines)


def build_timer_section(state: RepositoryState) -> str:
    """Build the timer progress bar section."""
    total_seconds = getattr(state, "_timer_total_seconds", None)
    timer_bar = _build_timer_bar(state.timer_seconds_left, total_seconds)
    return f"\n⏱️  {timer_bar}"


def build_changes_section(state: RepositoryState) -> str:
    """Build the file changes section using Rich markup."""
    if state.changed_files == 0 and not state.has_uncommitted_changes:
        return """
[bold]Workspace[/bold]
  [green]✨ Clean - no uncommitted changes[/green]"""

    return f"""
[bold]Pending Changes[/bold]
  📁 [bold]{state.changed_files}[/bold] files changed
     [green]➕ Added:    {state.added_files}[/green]
     [blue]✏️  Modified: {state.modified_files}[/blue]
     [red]➖ Deleted:  {state.deleted_files}[/red]"""  # noqa: RUF001


def build_last_commit_section(state: RepositoryState) -> str:
    """Build the last commit info section using Rich markup."""
    commit_hash = state.last_commit_short_hash or "-------"
    commit_msg = _escape_rich_markup(state.last_commit_message_summary or "No commit message")
    commit_time = _format_relative_time(state.last_commit_timestamp)

    # Truncate message if too long
    if len(commit_msg) > 50:
        commit_msg = commit_msg[:47] + "..."

    # Build stats from last committed values
    stats_parts = []
    if state.last_committed_added > 0:
        stats_parts.append(f"[green]+{state.last_committed_added}[/green]")
    if state.last_committed_deleted > 0:
        stats_parts.append(f"[red]-{state.last_committed_deleted}[/red]")
    stats = " ".join(stats_parts) if stats_parts else "[dim]no stats[/dim]"

    return f"""
[bold]Last Commit[/bold]
  [cyan]{commit_hash}[/cyan]  {commit_msg}
  [dim]{commit_time}[/dim]  {stats}"""


def build_rule_section(state: RepositoryState, rule_name: str | None) -> str:
    """Build the rule configuration section using Rich markup."""
    rule_emoji = state.rule_emoji or "📋"
    rule_indicator = state.rule_dynamic_indicator or "waiting"
    rule_display = rule_name or "default"

    return f"""
[bold]Rule[/bold]
  {rule_emoji} [bold]{rule_display}[/bold]  [dim]{rule_indicator}[/dim]
  Saves: [bold]{state.save_count}[/bold]"""


def build_controls_section(state: RepositoryState) -> str:
    """Build the controls/state section using Rich markup."""
    paused = "[green]Yes[/green]" if state.is_paused else "[dim]No[/dim]"
    stopped = "[green]Yes[/green]" if state.is_stopped else "[dim]No[/dim]"
    frozen = "[green]Yes[/green]" if state.is_frozen else "[dim]No[/dim]"

    return f"""
[bold]Controls[/bold]
  ⏸️  Paused: {paused}   ⏹️  Stopped: {stopped}   🧊 Frozen: {frozen}"""


def build_session_stats_section(state: RepositoryState) -> str:
    """Build the session statistics section using Rich markup."""
    duration = state.get_session_duration()
    commits = state.session_commits_count
    files = state.session_files_committed
    pushes = state.session_pushes_count
    events = state.session_events_count

    # Calculate average commits per hour
    if state.session_start_time:
        hours = (datetime.now(UTC) - state.session_start_time).total_seconds() / 3600
        avg_commits = commits / hours if hours > 0 else 0
        avg_commits_str = f"[dim]({avg_commits:.1f}/hr)[/dim]"
    else:
        avg_commits_str = ""

    return f"""
[bold]📊 Session Statistics[/bold]
  ⏱️  Duration: [bold]{duration}[/bold]
  📤 Commits: [bold]{commits}[/bold] {avg_commits_str}   🚀 Pushes: [bold]{pushes}[/bold]
  📁 Files: [bold]{files}[/bold]   📝 Events: [bold]{events}[/bold]"""


def build_remote_sync_section(state: RepositoryState) -> str:
    """Build the remote sync status section using Rich markup."""
    if not state.has_upstream:
        return """
[bold]🌐 Remote Status[/bold]
  [yellow]⚠ No upstream tracking branch configured[/yellow]"""

    upstream = state.upstream_branch or "origin/unknown"
    ahead = state.commits_ahead
    behind = state.commits_behind

    # Build sync status with colors
    if ahead == 0 and behind == 0:
        sync_status = "[green]✅ In sync with remote[/green]"
    elif ahead > 0 and behind == 0:
        sync_status = f"[green]↑ {ahead} commit(s) ahead[/green] - ready to push"
    elif behind > 0 and ahead == 0:
        sync_status = f"[yellow]↓ {behind} commit(s) behind[/yellow] - consider pulling"
    else:
        sync_status = f"[red]↕️  {ahead} ahead, {behind} behind (diverged)[/red]"

    return f"""
[bold]🌐 Remote Status[/bold]
  Tracking: [cyan]{upstream}[/cyan]
  {sync_status}"""


def build_error_section(state: RepositoryState) -> str:
    """Build the error details section using Rich markup (only for ERROR status)."""
    if state.status != RepositoryStatus.ERROR:
        return ""

    error_msg = _escape_rich_markup(state.error_message or "Unknown error")

    return f"""
[bold red]⚠️  Error Details[/bold red]
  [red]{error_msg}[/red]

  🔧 Actions: [bold]R[/bold] Retry  [bold]A[/bold] Acknowledge  [bold]I[/bold] Ignore"""


def build_circuit_breaker_section(state: RepositoryState) -> str:
    """Build the circuit breaker section using Rich markup (only when triggered)."""
    if not state.circuit_breaker_triggered:
        return ""

    reason = _escape_rich_markup(state.circuit_breaker_reason or "Bulk changes detected")

    # Check for file warnings (large/binary files)
    if state.file_warnings:
        return _build_file_warnings_circuit_breaker(state, reason)

    # Standard bulk change circuit breaker
    file_count = len(state.bulk_change_files)

    # Show first few files (escape file paths)
    files_preview = ", ".join(_escape_rich_markup(f) for f in state.bulk_change_files[:3])
    if len(files_preview) > 50:
        files_preview = files_preview[:47] + "..."
    if file_count > 3:
        files_preview += f" +{file_count - 3} more"

    return f"""
[bold red]🛑 Circuit Breaker Activated[/bold red]
  [yellow]Reason:[/yellow] {reason}
  [yellow]Files affected:[/yellow] {file_count}
  [dim]{files_preview}[/dim]

  [bold]A[/bold] Acknowledge & Resume   [bold]S[/bold] Stay Paused"""


def _build_file_warnings_circuit_breaker(state: RepositoryState, reason: str) -> str:
    """Build circuit breaker section with file warnings using Rich markup.

    Note: reason is already escaped when passed in.
    """
    warnings = state.file_warnings
    large_files = [w for w in warnings if w.get("type") == "large_file"]
    binary_files = [w for w in warnings if w.get("type") == "binary_file"]

    lines = [
        "[bold red]🛑 Circuit Breaker: File Warnings[/bold red]",
        f"  [yellow]Reason:[/yellow] {reason}",
    ]

    # Large files section
    if large_files:
        lines.append("\n[bold]📦 Large Files[/bold]")
        for lf in large_files[:3]:
            path = _escape_rich_markup(lf.get("path", "unknown"))
            size_mb = lf.get("size", 0) / 1_000_000
            path_display = path if len(path) <= 45 else "..." + path[-42:]
            lines.append(f"  [cyan]{path_display}[/cyan] [dim]({size_mb:.2f} MB)[/dim]")
        if len(large_files) > 3:
            lines.append(f"  [dim]... and {len(large_files) - 3} more large file(s)[/dim]")

    # Binary files section
    if binary_files:
        lines.append("\n[bold]🔒 Binary Files[/bold]")
        for bf in binary_files[:3]:
            path = _escape_rich_markup(bf.get("path", "unknown"))
            size_kb = bf.get("size", 0) / 1000
            path_display = path if len(path) <= 45 else "..." + path[-42:]
            lines.append(f"  [cyan]{path_display}[/cyan] [dim]({size_kb:.1f} KB)[/dim]")
        if len(binary_files) > 3:
            lines.append(f"  [dim]... and {len(binary_files) - 3} more binary file(s)[/dim]")

    lines.append("\n  [bold]A[/bold] Acknowledge & Commit   [bold]S[/bold] Skip These Files")

    return "\n".join(lines)


def build_keyboard_hints() -> str:
    """Build the keyboard shortcuts hint section using Rich markup."""
    return """
[dim]─────────────────────────────────────────────────────────────[/dim]
[bold]Space[/bold] Pause  [bold]S[/bold] Stop  [bold]R[/bold] Refresh  [bold]A[/bold] Ack  [bold]Esc[/bold] Back"""


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
