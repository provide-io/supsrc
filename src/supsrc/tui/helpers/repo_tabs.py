#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#

"""Helper functions for building repository tab content in the TUI."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def _format_file_size(size: int) -> str:
    """Format file size in human-readable format."""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    else:
        return f"{size / (1024 * 1024):.1f}MB"


def _format_relative_time(dt: datetime | None) -> str:
    """Format a datetime as relative time."""
    if not dt:
        return "unknown"

    from datetime import UTC

    now = datetime.now(UTC)
    diff = now - dt

    if diff.days > 365:
        years = diff.days // 365
        return f"{years}y ago"
    elif diff.days > 30:
        months = diff.days // 30
        return f"{months}mo ago"
    elif diff.days > 0:
        return f"{diff.days}d ago"
    elif diff.seconds > 3600:
        hours = diff.seconds // 3600
        return f"{hours}h ago"
    elif diff.seconds > 60:
        minutes = diff.seconds // 60
        return f"{minutes}m ago"
    else:
        return "just now"


def build_files_tree_content(files: list[dict[str, Any]], repo_id: str) -> str:
    """Build the files tree tab content using Rich markup.

    Args:
        files: List of file dictionaries from get_changed_files_tree()
        repo_id: Repository identifier

    Returns:
        Formatted string for display
    """
    if not files:
        return f"""[bold]📂 {repo_id}[/bold]

[green]✨ No changed files detected.[/green]

Working directory is clean."""

    # Group files by directory
    tree: dict[str, list[dict[str, Any]]] = {}
    for f in files:
        path = f["path"]
        parts = path.rsplit("/", 1)
        if len(parts) == 1:
            directory = "."
            filename = parts[0]
        else:
            directory = parts[0]
            filename = parts[1]

        if directory not in tree:
            tree[directory] = []
        tree[directory].append({**f, "filename": filename})

    # Build output
    lines = [
        f"[bold]📂 {repo_id}[/bold]",
        "[dim]" + "─" * 60 + "[/dim]",
        "",
    ]

    # Summary counts
    staged = sum(1 for f in files if f.get("is_staged"))
    unstaged = len(files) - staged
    binary_count = sum(1 for f in files if f.get("is_binary"))
    large_count = sum(1 for f in files if f.get("is_large"))

    lines.append(f"📊 {len(files)} changed files ({staged} staged, {unstaged} unstaged)")

    # Add warnings
    warnings = []
    if binary_count > 0:
        warnings.append(f"⚠️  {binary_count} binary file(s)")
    if large_count > 0:
        warnings.append(f"⚠️  {large_count} large file(s) (>1MB)")

    if warnings:
        lines.append("")
        lines.extend(warnings)

    lines.append("")
    lines.append("─" * 60)

    # Status icons with colors
    status_colors = {
        "added": "[green]",
        "modified": "[blue]",
        "deleted": "[red]",
        "renamed": "[yellow]",
        "untracked": "[dim]",
        "changed": "[cyan]",
    }
    status_end = "[/]"

    # Display files by directory
    for directory in sorted(tree.keys()):
        if directory != ".":
            lines.append(f"\n📁 {directory}/")
            indent = "   "
        else:
            lines.append("\n📁 (root)")
            indent = "   "

        for f in sorted(tree[directory], key=lambda x: x["filename"]):
            icon = f["icon"]
            status = f["status"]
            filename = f["filename"]
            size_str = _format_file_size(f["size"])
            staged_mark = "●" if f.get("is_staged") else "○"

            color = status_colors.get(status, "")
            end = status_end if color else ""

            # Build file line with warnings
            file_line = f"{indent}{staged_mark} {color}{icon} {filename}{end}"

            extras = []
            if f.get("is_binary"):
                extras.append("[yellow]BIN[/yellow]")
            if f.get("is_large"):
                extras.append(f"[red]{size_str}[/red]")
            elif f["size"] > 0:
                extras.append(f"[dim]{size_str}[/dim]")

            if extras:
                file_line += f"  {' '.join(extras)}"

            lines.append(file_line)

    lines.append("")
    lines.append("─" * 60)
    lines.append("● = staged  ○ = unstaged  [A]dd  [M]odified  [D]eleted  [R]enamed  [?]untracked")

    return "\n".join(lines)


def build_history_content(commits: list[dict[str, Any]], repo_id: str) -> str:
    """Build the commit history tab content.

    Args:
        commits: List of commit dictionaries from get_detailed_commit_history()
        repo_id: Repository identifier

    Returns:
        Formatted string for display
    """
    if not commits:
        return f"📜 {repo_id}\n\nNo commit history available."

    lines = [
        f"📜 {repo_id} - Commit History",
        "═" * 60,
        "",
    ]

    for i, commit in enumerate(commits):
        if i > 0:
            lines.append("")

        # Commit header
        hash_str = commit.get("hash", "???????")
        timestamp = commit.get("timestamp")
        time_str = _format_relative_time(timestamp) if timestamp else "unknown"
        author = commit.get("author", "Unknown")

        lines.append(f"[bold cyan]{hash_str}[/bold cyan] - {time_str}")
        lines.append(f"   Author: {author}")

        # Stats
        added = commit.get("added", 0)
        deleted = commit.get("deleted", 0)
        modified = commit.get("modified", 0)

        if added or deleted or modified:
            stats = []
            if added:
                stats.append(f"[green]+{added}[/green]")
            if deleted:
                stats.append(f"[red]-{deleted}[/red]")
            if modified:
                stats.append(f"[blue]~{modified}[/blue]")
            lines.append(f"   Files: {' '.join(stats)}")

        # Message
        message = commit.get("message", "No message")
        lines.append(f"   {message}")

    return "\n".join(lines)


def build_diff_content(diff_text: str, repo_id: str) -> str:
    """Build the diff tab content with Rich markup.

    The diff_text is already formatted by get_working_diff() with Rich markup,
    so we just add a header and pass through the content.

    Args:
        diff_text: Formatted diff text from get_working_diff() with Rich markup
        repo_id: Repository identifier

    Returns:
        Formatted string for display with diff highlighting
    """
    # Handle empty/no changes cases
    if not diff_text:
        return f"""[bold]📋 {repo_id}[/bold]
[dim]{"═" * 60}[/dim]

[green]✨ No uncommitted changes to show.[/green]

Working directory is clean."""

    if diff_text == "No changes detected.":
        return f"""[bold]📋 {repo_id}[/bold]
[dim]{"═" * 60}[/dim]

[green]✨ No uncommitted changes to show.[/green]

Working directory is clean."""

    # Handle error messages
    if diff_text.startswith("Error getting diff:") or diff_text.startswith("Repository is empty"):
        return f"""[bold]📋 {repo_id}[/bold]
[dim]{"═" * 60}[/dim]

[yellow]⚠️ {diff_text}[/yellow]"""

    # The diff_text from get_working_diff() is already formatted with Rich markup
    # Just add a header and return
    header = f"""[bold]📋 {repo_id} - Working Directory Diff[/bold]
[dim]{"═" * 60}[/dim]
"""

    return header + diff_text


def build_conflict_warning(conflict_info: dict[str, Any], repo_id: str) -> str:
    """Build a conflict/upstream warning message.

    Args:
        conflict_info: Dictionary from check_upstream_conflicts()
        repo_id: Repository identifier

    Returns:
        Warning message string or empty string if no issues
    """
    if not conflict_info:
        return ""

    lines = []

    # Check for merge conflicts
    if conflict_info.get("has_conflicts"):
        lines.append("🚨 MERGE CONFLICTS DETECTED")
        conflict_files = conflict_info.get("conflict_files", [])
        if conflict_files:
            lines.append(f"   Files: {', '.join(conflict_files[:5])}")
            if len(conflict_files) > 5:
                lines.append(f"   ... and {len(conflict_files) - 5} more")
        lines.append("")

    # Check for divergence
    if conflict_info.get("diverged"):
        ahead = conflict_info.get("ahead", 0)
        behind = conflict_info.get("behind", 0)
        lines.append("⚠️  BRANCH HAS DIVERGED")
        lines.append(f"   {ahead} commit(s) ahead, {behind} commit(s) behind upstream")
        lines.append("   Consider pulling and rebasing before pushing")
        lines.append("")

    # Just behind
    elif conflict_info.get("behind", 0) > 0:
        behind = conflict_info.get("behind", 0)
        lines.append(f"⚠️  Branch is {behind} commit(s) behind upstream")
        lines.append("   Consider pulling before pushing")
        lines.append("")

    return "\n".join(lines) if lines else ""


def build_file_warnings_content(warnings: list[dict[str, Any]]) -> str:
    """Build warnings display for large/binary files.

    Args:
        warnings: List of warning dictionaries from analyze_files_for_warnings()

    Returns:
        Formatted warning string
    """
    if not warnings:
        return ""

    lines = ["", "⚠️  File Warnings:", "─" * 40]

    for warning in warnings:
        warn_type = warning.get("type", "unknown")
        message = warning.get("message", "Unknown warning")

        if warn_type == "large_file":
            lines.append(f"   📦 {message}")
        elif warn_type == "binary_file":
            lines.append(f"   🔒 {message}")
        else:
            lines.append(f"   ❓ {message}")

    lines.append("")
    return "\n".join(lines)


# 🔼⚙️🔚
