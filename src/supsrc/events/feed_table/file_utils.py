#
# SPDX-FileCopyrightText: Copyright (c) 2025 provide.io llc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#


from __future__ import annotations

from pathlib import Path

"""Utilities for formatting file paths in the event feed table."""


class FilePathFormatter:
    """Handles formatting of file paths for display."""

    @staticmethod
    def get_files_summary_short(file_paths: list[Path]) -> str:
        """Get a short summary of multiple file paths for the File column with Rich markup."""
        if not file_paths:
            return "-"

        if len(file_paths) == 1:
            # Single file - show directory prefix dimmed
            file_path = file_paths[0]
            if file_path.parent.name and file_path.parent.name != ".":
                return f"[dim]{file_path.parent}/[/]{file_path.name}"
            else:
                return f"[dim]./[/]{file_path.name}"

        # Try to find common directory
        str_paths = [str(p) for p in file_paths]

        # Find common prefix
        common_prefix = ""
        if len(str_paths) > 1:
            min_path = min(str_paths)
            max_path = max(str_paths)

            for i, char in enumerate(min_path):
                if i < len(max_path) and char == max_path[i]:
                    common_prefix += char
                else:
                    break

            # Clean up to end at directory boundary
            if "/" in common_prefix:
                common_prefix = common_prefix.rsplit("/", 1)[0] + "/"

        # Create short summary with color coding
        if len(file_paths) <= 2:
            # Show individual file names
            names = [p.name for p in file_paths]
            return ", ".join(names)
        elif len(file_paths) <= 5:
            # Single directory with multiple files
            if common_prefix and len(common_prefix) > 1:
                common_dir = Path(common_prefix).name or Path(common_prefix).parent.name
                return f"[bold cyan]{common_dir}/[/]"
            else:
                return f"[bold cyan]{len(file_paths)} files[/]"
        elif len(file_paths) <= 15:
            # Multiple directories - yellow warning
            return f"[bold yellow]{len(file_paths)} files[/]"
        else:
            # Large change set - red warning
            return f"[bold red]⚡[/] {len(file_paths)} files"

    @staticmethod
    def get_files_summary(file_paths: list[Path]) -> str:
        """Get a summary of multiple file paths."""
        if not file_paths:
            return "No files"

        if len(file_paths) == 1:
            return str(file_paths[0].name)

        # Try to find common directory
        str_paths = [str(p) for p in file_paths]

        # Find common prefix
        if len(str_paths) > 1:
            common_prefix = ""
            min_path = min(str_paths)
            max_path = max(str_paths)

            for i, char in enumerate(min_path):
                if i < len(max_path) and char == max_path[i]:
                    common_prefix += char
                else:
                    break

            # Clean up to end at directory boundary
            if "/" in common_prefix:
                common_prefix = common_prefix.rsplit("/", 1)[0] + "/"

        # Create summary
        if len(file_paths) <= 3:
            # Show individual file names
            names = [p.name for p in file_paths]
            return ", ".join(names)
        # Show count and common prefix or directory
        elif common_prefix and len(common_prefix) > 1:
            common_dir = Path(common_prefix).name or Path(common_prefix).parent.name
            return f"{len(file_paths)} files in {common_dir}/"
        else:
            return f"{len(file_paths)} files"

    @staticmethod
    def format_event_details_legacy(event, file_paths: list[Path], event_count: int) -> tuple[str, str]:
        """Format event count and file details (legacy method).

        Returns:
            Tuple of (count_str, files_str)
        """
        count_str = str(event_count)

        if len(file_paths) == 0:
            files_str = "No files"
        elif len(file_paths) == 1:
            files_str = str(file_paths[0].name)
        else:
            # Find common prefix for multiple files
            files_str = FilePathFormatter.get_files_summary(file_paths)

        return count_str, files_str


# 🔼⚙️🔚
